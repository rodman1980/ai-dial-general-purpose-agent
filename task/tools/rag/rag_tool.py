"""
RAG tool: semantic search over documents using FAISS + SentenceTransformer embeddings.
Indexes documents (cached per conversation), retrieves relevant chunks, generates answers.
"""
import json
from typing import Any

import faiss
import numpy as np
from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Role
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams
from task.tools.rag.document_cache import DocumentCache
from task.utils.dial_file_conent_extractor import DialFileContentExtractor

# System prompt for generation step: emphasize using context and avoiding hallucination
_SYSTEM_PROMPT = """
You are a helpful assistant that answers questions based on provided document context.

CRITICAL RULES:
1. Base your answer ONLY on the provided context from the document
2. If the context doesn't contain enough information to answer, say so clearly
3. Do NOT make up information or use knowledge outside the provided context
4. Quote relevant parts of the context when appropriate
5. Be concise but complete in your answers

The context will be provided in the user's message.
"""


class RagTool(BaseTool):
    """
    Semantic search tool using FAISS + SentenceTransformer for document Q&A.
    
    Flow:
    1. Index document (or retrieve from cache): extract → split → embed → FAISS index
    2. Encode query → search top-3 chunks
    3. Augment prompt with retrieved context
    4. Generate answer via LLM (streams to stage)
    
    Performance:
    - Embedding model: all-MiniLM-L6-v2 (384 dims, lightweight, CPU-friendly)
    - Chunking: 500 chars with 50 char overlap (maintains context)
    - Cache: Conversation-scoped (key: {conversation_id}_{file_url})
    - Top-k: 3 chunks retrieved per query
    
    Advantages over full extraction:
    - Much faster for large documents
    - Only retrieves relevant sections
    - No pagination needed
    """

    def __init__(self, endpoint: str, deployment_name: str, document_cache: DocumentCache):
        """
        Initialize RAG tool with embedding model and text splitter.
        
        Args:
            endpoint: DIAL Core endpoint
            deployment_name: LLM model for generation step (gpt-4o, claude, etc.)
            document_cache: Thread-safe cache for indexed documents (24h TTL)
        
        Side effects:
            - Loads SentenceTransformer model (all-MiniLM-L6-v2) into memory
            - Creates RecursiveCharacterTextSplitter with 500 char chunks
        """
        self.endpoint = endpoint
        self.deployment_name = deployment_name
        self.document_cache = document_cache
        
        # Load embedding model (lightweight, 384-dim, CPU-friendly)
        # See: https://medium.com/@rahultiwari065/unlocking-the-power-of-sentence-embeddings-with-all-minilm-l6-v2-7d6589a5f0aa
        self.model = SentenceTransformer(
            'all-MiniLM-L6-v2',
            device='cpu'  # Force CPU (works without GPU, avoids CUDA setup)
        )
        
        # Text splitter: 500 chars with 50 overlap (preserves context at boundaries)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]  # Priority order for splits
        )

    @property
    def show_in_stage(self) -> bool:
        """Custom stage management: manually control display."""
        return False

    @property
    def name(self) -> str:
        """Tool name for LLM function calling."""
        return "rag_search_tool"

    @property
    def description(self) -> str:
        """
        Tool description for LLM (guides when to prefer RAG over full extraction).
        
        Key decision factors:
        - Large documents + specific question → use RAG
        - Need full content or structure → use file extraction
        """
        return (
            "Performs semantic search on document content to find and answer specific questions. "
            "More efficient than full file extraction for large documents when you need specific information. "
            "Searches through the document, retrieves relevant sections, and generates an answer based on context. "
            "Supports PDF, TXT, CSV, HTML. Use this instead of paginating through large documents "
            "when looking for specific information."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """
        Tool parameters JSON Schema.
        
        Parameters:
        - request: Search query/question (required)
        - file_url: DIAL file URL (required)
        """
        return {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The search query or question to search for in the document"
                },
                "file_url": {
                    "type": "string",
                    "description": "The URL of the file to search in"
                }
            },
            "required": ["request", "file_url"]
        }

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        """
        Execute RAG search: index (or retrieve cache) → search → augment → generate.
        
        Flow:
        1. Parse arguments (request, file_url)
        2. Build cache key: {conversation_id}_{file_url}
        3. Check document cache:
           - Hit: reuse existing FAISS index + chunks
           - Miss: extract → split → embed → index → cache
        4. Encode query → search top-3 chunks
        5. Augment prompt with retrieved context
        6. Generate answer via LLM (stream to stage + collect content)
        7. Return generated answer
        
        Args:
            tool_call_params: Contains stage, api_key, conversation_id, tool_call args
        
        Returns:
            Generated answer based on retrieved document context
        
        Performance notes:
        - Document indexing: ~1-2s for 50-page PDF (one-time per conversation)
        - Query search: <100ms (FAISS is very fast)
        - Generation: depends on LLM speed (streamed to user in real-time)
        
        Error handling:
        - File extraction failure → return error message
        - Empty document → return error message
        - Generation failure → caught by BaseTool.execute()
        """
        # Parse arguments
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        request = arguments.get("request")
        file_url = arguments.get("file_url")
        
        # Get stage for UI visualization
        stage = tool_call_params.stage
        
        # Display request arguments in stage
        stage.append_content("## Request arguments:\n")
        stage.append_content(f"**Request**: {request}\n")
        stage.append_content(f"**File URL**: {file_url}\n")
        
        # Build cache key: conversation-scoped to isolate user sessions
        cache_document_key = f"{tool_call_params.conversation_id}_{file_url}"
        
        # Check document cache (thread-safe, 24h TTL)
        cached_data = self.document_cache.get(cache_document_key)
        
        if cached_data:
            # Cache hit: reuse existing index and chunks
            index, chunks = cached_data
        else:
            # Cache miss: index document (extract → split → embed → FAISS)
            
            # Extract text content from file
            extractor = DialFileContentExtractor(
                endpoint=self.endpoint,
                api_key=tool_call_params.api_key
            )
            text_content = extractor.extract_text(file_url)
            
            # Handle extraction failure
            if not text_content:
                error_msg = "Error: File content not found or could not be extracted."
                stage.append_content(f"**Error**: {error_msg}\n")
                return error_msg
            
            # Split text into chunks (500 chars, 50 overlap)
            chunks = self.text_splitter.split_text(text_content)
            
            # Generate embeddings for all chunks (384-dim vectors)
            embeddings = self.model.encode(chunks, convert_to_numpy=True)
            
            # Create FAISS index (IndexFlatL2: exact L2 distance search)
            # 384 dimensions = all-MiniLM-L6-v2 embedding size
            # See: https://shayan-fazeli.medium.com/faiss-a-quick-tutorial-to-efficient-similarity-search-595850e08473
            index = faiss.IndexFlatL2(384)
            
            # Add embeddings to index (must be float32)
            index.add(np.array(embeddings, dtype='float32'))
            
            # Cache index + chunks for this conversation
            self.document_cache.set(cache_document_key, (index, chunks))
        
        # Encode query (same 384-dim space as document chunks)
        query_embedding = self.model.encode([request], convert_to_numpy=True).astype('float32')
        
        # Search top-3 most relevant chunks (k=3)
        # Returns: distances (L2 distance, lower=more similar), indices (chunk positions)
        distances, indices = index.search(query_embedding, k=3)
        
        # Retrieve top-3 chunks by index
        retrieved_chunks = [chunks[idx] for idx in indices[0]]
        
        # Augment prompt: combine retrieved context + user query
        augmented_prompt = self.__augmentation(request, retrieved_chunks)
        
        # Display RAG request in stage
        stage.append_content("## RAG Request:\n")
        stage.append_content(f"```text\n{augmented_prompt}\n```\n")
        stage.append_content("## Response:\n")
        
        # Generation step: call LLM with augmented prompt
        async with AsyncDial(
            base_url=self.endpoint,
            api_key=tool_call_params.api_key,
            api_version="2025-01-01-preview"
        ) as client:
            # Stream LLM response
            chunks_stream = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": augmented_prompt}
                ],
                deployment_name=self.deployment_name,
                stream=True
            )
            
            # Collect content while streaming to stage (real-time user feedback)
            content = ""
            async for chunk in chunks_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta_content = chunk.choices[0].delta.content
                    stage.append_content(delta_content)  # Stream to UI
                    content += delta_content  # Collect for return
        
        return content

    def __augmentation(self, request: str, chunks: list[str]) -> str:
        """
        Augment user query with retrieved document context.
        
        Format:
        ---
        Context from document:
        [Chunk 1]
        ---
        [Chunk 2]
        ---
        [Chunk 3]
        ---
        
        Question: [User's question]
        
        Args:
            request: User's search query/question
            chunks: Top-3 retrieved document chunks
        
        Returns:
            Augmented prompt with context + question
        """
        # Format context sections
        context_sections = "\n---\n".join(chunks)
        
        # Build augmented prompt
        augmented_prompt = f"""Context from document:
---
{context_sections}
---

Question: {request}"""
        
        return augmented_prompt
