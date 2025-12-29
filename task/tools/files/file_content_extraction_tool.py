"""
File content extraction tool with pagination support (10K chars/page).
Extracts text from PDF, TXT, CSV (as markdown), HTML files.
"""
import json
from typing import Any

from aidial_sdk.chat_completion import Message

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams
from task.utils.dial_file_conent_extractor import DialFileContentExtractor


class FileContentExtractionTool(BaseTool):
    """
    Extracts text content from files with automatic pagination for large documents.
    
    Supported formats:
    - PDF (text only, no OCR)
    - TXT (plain text)
    - CSV (converted to markdown table)
    - HTML/HTM (text extraction, strips scripts/styles)
    
    Pagination:
    - Files >10,000 chars automatically paginated
    - Response includes: "**Page #X. Total pages: Y**" footer
    - LLM can request specific page with page parameter
    
    Usage pattern:
    - User attaches file → agent calls with page=1
    - If paginated footer present → agent can request additional pages if needed
    - Prefer RAG search for large documents when looking for specific info
    """

    def __init__(self, endpoint: str):
        """
        Initialize with DIAL endpoint for file downloads.
        
        Args:
            endpoint: DIAL Core endpoint (e.g., http://localhost:8080)
        """
        self.endpoint = endpoint

    @property
    def show_in_stage(self) -> bool:
        """
        Custom stage management: tool manually appends to stage.
        
        Returns False to disable automatic stage content display,
        allowing fine-grained control over stage formatting.
        """
        return False

    @property
    def name(self) -> str:
        """Tool name for LLM function calling."""
        return "file_content_extraction_tool"

    @property
    def description(self) -> str:
        """
        Tool description for LLM (guides when to use this tool).
        
        Key info for LLM:
        - Supported formats
        - Pagination behavior
        - When to prefer RAG search instead
        """
        return (
            "Extracts text content from attached files (PDF, TXT, CSV, HTML). "
            "Supports pagination for large files: each page is 10,000 characters. "
            "If response includes 'Page #X. Total pages: Y', you can request additional pages. "
            "For large documents where you need specific information, prefer using the RAG search tool instead "
            "of extracting all pages. CSV files are returned as markdown tables."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """
        Tool parameters JSON Schema (OpenAI function calling format).
        
        Parameters:
        - file_url (required): DIAL file URL
        - page (optional, default 1): Page number for pagination
        """
        return {
            "type": "object",
            "properties": {
                "file_url": {
                    "type": "string",
                    "description": "The URL of the file to extract content from"
                },
                "page": {
                    "type": "integer",
                    "description": "For large documents pagination is enabled. Each page consists of 10000 characters. Default is 1.",
                    "default": 1
                }
            },
            "required": ["file_url"]
        }

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        """
        Extract file content with pagination support.
        
        Flow:
        1. Parse arguments (file_url, page)
        2. Append request info to stage
        3. Extract content via DialFileContentExtractor
        4. If content >10K chars: paginate
           - Calculate total pages
           - Extract page slice
           - Append pagination footer
        5. Append content to stage as markdown text block
        6. Return content (with pagination footer if applicable)
        
        Args:
            tool_call_params: Contains stage, api_key, tool_call args
        
        Returns:
            Extracted text content (possibly paginated with footer)
        
        Pagination footer format:
            "**Page #2. Total pages: 5**"
        
        Error handling:
        - Invalid page number → returns error message
        - File not found → returns error message
        - Extraction failure → returns empty string (logged in extractor)
        """
        # Parse tool arguments
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        file_url = arguments.get("file_url")
        page = arguments.get("page", 1)  # Default to page 1
        
        # Get stage for UI visualization
        stage = tool_call_params.stage
        
        # Display request arguments in stage
        stage.append_content("## Request arguments:\n")
        stage.append_content(f"**File URL**: {file_url}\n")
        if page > 1:
            stage.append_content(f"**Page**: {page}\n")
        stage.append_content("## Response:\n")
        
        # Extract content from file
        extractor = DialFileContentExtractor(
            endpoint=self.endpoint,
            api_key=tool_call_params.api_key
        )
        content = extractor.extract_text(file_url)
        
        # Handle empty content (extraction failed or file empty)
        if not content:
            content = "Error: File content not found."
        
        # Pagination logic for large documents (>10K chars)
        elif len(content) > 10_000:
            page_size = 10_000
            
            # Calculate total pages (ceiling division)
            total_pages = (len(content) + page_size - 1) // page_size
            
            # Sanitize page number (LLM might hallucinate invalid pages)
            if page < 1:
                page = 1
            elif page > total_pages:
                # Page out of range → return error
                content = f"Error: Page {page} does not exist. Total pages: {total_pages}"
            else:
                # Extract page slice
                start_index = (page - 1) * page_size
                end_index = start_index + page_size
                page_content = content[start_index:end_index]
                
                # Append pagination footer (signals to LLM that more content available)
                content = f"{page_content}\n\n**Page #{page}. Total pages: {total_pages}**"
        
        # Display content in stage as markdown text block
        stage.append_content(f"```text\n{content}\n```\n")
        
        return content
