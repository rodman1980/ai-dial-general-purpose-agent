"""
Application entry point: lazy-initializes tools, creates agent, handles chat completion.
Runs on port 5030, exposes /openai/deployments/general-purpose-agent/chat/completions.
"""
import os

import uvicorn
from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response

from task.agent import GeneralPurposeAgent
from task.prompts import SYSTEM_PROMPT
from task.tools.base import BaseTool
from task.tools.deployment.image_generation_tool import ImageGenerationTool
from task.tools.files.file_content_extraction_tool import FileContentExtractionTool
from task.tools.py_interpreter.python_code_interpreter_tool import PythonCodeInterpreterTool
from task.tools.mcp.mcp_client import MCPClient
from task.tools.mcp.mcp_tool import MCPTool
from task.tools.rag.document_cache import DocumentCache
from task.tools.rag.rag_tool import RagTool

# Configuration from environment (defaults for local dev)
DIAL_ENDPOINT = os.getenv('DIAL_ENDPOINT', "http://localhost:8080")
DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'gpt-4o')  # Orchestrator LLM
# DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'claude-sonnet-3-7')  # Alternative orchestrator


class GeneralPurposeAgentApplication(ChatCompletion):
    """
    DIAL ChatCompletion handler for General Purpose Agent.
    
    Pattern: Lazy tool initialization
    - Tools created on first request (async MCP discovery)
    - Cached for subsequent requests
    
    Tools provided:
    - FileContentExtractionTool: PDF/TXT/CSV/HTML extraction with pagination
    - RagTool: Semantic search with FAISS + SentenceTransformer
    - ImageGenerationTool: DALL-E-3 via DIAL deployment
    - PythonCodeInterpreterTool: Stateful Jupyter kernel via MCP
    - MCP Tools: DuckDuckGo search (dynamically discovered)
    """

    def __init__(self):
        """Initialize with empty tool list (lazy initialization on first request)."""
        self.tools: list[BaseTool] = []

    async def _get_mcp_tools(self, url: str) -> list[BaseTool]:
        """
        Discover MCP tools from server and wrap as BaseTool instances.
        
        Flow:
        1. Create MCPClient for given URL
        2. Get tools from MCP server (list of MCPToolModel)
        3. Wrap each as MCPTool (BaseTool subclass)
        
        Args:
            url: MCP server URL (e.g., http://localhost:8051/mcp for DuckDuckGo)
        
        Returns:
            List of MCPTool instances (each wraps one MCP server tool)
        
        External I/O:
            - HTTP connection to MCP server
            - Async tool discovery via MCP protocol
        """
        tools: list[BaseTool] = []
        
        # Create MCP client (async connection to external server)
        client = await MCPClient.create(url)
        
        # Discover available tools from MCP server
        mcp_tool_models = await client.get_tools()
        
        # Wrap each MCP tool as BaseTool for uniform interface
        for mcp_tool_model in mcp_tool_models:
            tools.append(MCPTool(client=client, mcp_tool_model=mcp_tool_model))
        
        return tools

    async def _create_tools(self) -> list[BaseTool]:
        """
        Assemble all tools: deployment, file, RAG, Python interpreter, MCP (web search).
        
        Tool assembly order:
        1. Deployment tools: ImageGenerationTool (DALL-E-3)
        2. File tools: FileContentExtractionTool (PDF/TXT/CSV/HTML)
        3. RAG: RagTool (FAISS + SentenceTransformer for semantic search)
        4. Python interpreter: PythonCodeInterpreterTool (Jupyter kernel via MCP)
        5. MCP tools: Dynamically discovered from DuckDuckGo MCP server
        
        Returns:
            List of all available tools for agent
        
        External I/O:
        - MCP server connections (Python interpreter, DuckDuckGo search)
        - Async tool discovery
        """
        tools: list[BaseTool] = []
        
        # Deployment tool: DALL-E-3 image generation via DIAL
        tools.append(ImageGenerationTool(endpoint=DIAL_ENDPOINT))
        
        # File extraction: PDF, TXT, CSV, HTML with pagination (10K chars/page)
        tools.append(FileContentExtractionTool(endpoint=DIAL_ENDPOINT))
        
        # RAG: Semantic search over documents with FAISS + embeddings
        # DocumentCache: 24h TTL, conversation-scoped indexed documents
        tools.append(RagTool(
            endpoint=DIAL_ENDPOINT,
            deployment_name=DEPLOYMENT_NAME,
            document_cache=DocumentCache.create()
        ))
        
        # Python interpreter: Stateful Jupyter kernel via MCP
        # See: https://github.com/khshanovskyi/mcp-python-code-interpreter
        tools.append(await PythonCodeInterpreterTool.create(
            dial_endpoint=DIAL_ENDPOINT,
            mcp_url="http://localhost:8050/mcp",
            tool_name="execute_code"
        ))
        
        # MCP tools: DuckDuckGo web search (dynamically discovered)
        mcp_tools = await self._get_mcp_tools("http://localhost:8051/mcp")
        tools.extend(mcp_tools)
        
        return tools

    async def chat_completion(self, request: Request, response: Response) -> None:
        """
        Handle chat completion request: lazy-init tools → create agent → orchestrate.
        
        Flow:
        1. Lazy initialize tools on first request (cached for subsequent requests)
        2. Create single choice for response streaming
        3. Create GeneralPurposeAgent with tools
        4. Delegate to agent.handle_request() for orchestration
        
        Args:
            request: Incoming DIAL chat request (messages, headers with API key)
            response: DIAL response object for streaming
        
        Side effects:
            - Lazy tool initialization (cached in self.tools)
            - Streams response to client via choice
        """
        # Lazy tool initialization: create once, reuse for all requests
        if not self.tools:
            self.tools = await self._create_tools()
        
        # Create single choice for streaming response
        with response.create_single_choice() as choice:
            # Create agent with tools and system prompt
            agent = GeneralPurposeAgent(
                endpoint=DIAL_ENDPOINT,
                system_prompt=SYSTEM_PROMPT,
                tools=self.tools
            )
            
            # Delegate to agent for recursive LLM + tool orchestration
            await agent.handle_request(
                choice=choice,
                deployment_name=DEPLOYMENT_NAME,
                request=request,
                response=response
            )


# Module-level: create DIAL app and run with uvicorn
if __name__ == "__main__":
    # Create DIAL application
    app = DIALApp()
    
    # Create agent application instance
    agent_app = GeneralPurposeAgentApplication()
    
    # Register chat completion handler
    # Exposed at: /openai/deployments/general-purpose-agent/chat/completions
    app.add_chat_completion(
        deployment_name="general-purpose-agent",
        impl=agent_app
    )
    
    # Run server on port 5030 (accessible to DIAL Core at host.docker.internal:5030)
    print("🚀 Starting General Purpose Agent on http://0.0.0.0:5030")
    uvicorn.run(app, port=5030, host="0.0.0.0")
