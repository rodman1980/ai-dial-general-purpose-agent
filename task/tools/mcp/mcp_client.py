"""MCP Client: manages connection to MCP servers via streamable HTTP protocol."""
from typing import Optional, Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent, ReadResourceResult, TextResourceContents, BlobResourceContents
from pydantic import AnyUrl

from task.tools.mcp.mcp_tool_model import MCPToolModel


class MCPClient:
    """
    Handles MCP server connection and tool execution.
    
    Pattern: Async context manager with nested lifecycle
    - Outer: streamablehttp_client (HTTP streaming)
    - Inner: ClientSession (MCP protocol)
    
    Usage:
    ```python
    async with MCPClient.create("http://localhost:8051") as client:
        tools = await client.get_tools()
        result = await client.call_tool("search", {"query": "weather"})
    ```
    
    Lifecycle:
    1. create() → __aenter__() → connect() → initialize session
    2. get_tools() / call_tool() operations
    3. __aexit__() → close() → cleanup contexts
    """

    def __init__(self, mcp_server_url: str) -> None:
        """Initialize with MCP server URL (don't connect yet)."""
        self.server_url = mcp_server_url
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None

    @classmethod
    async def create(cls, mcp_server_url: str) -> 'MCPClient':
        """
        Async factory method to create and connect MCPClient.
        
        Flow:
        1. Create MCPClient instance
        2. Call connect() to establish MCP session
        3. Return connected client
        
        Args:
            mcp_server_url: HTTP URL of MCP server (e.g., http://localhost:8051)
        
        Returns:
            Connected MCPClient ready for tool operations
        
        Usage:
            async with MCPClient.create(url) as client:
                # Use client for tool calls
        """
        client = cls(mcp_server_url)
        await client.connect()
        return client

    async def connect(self):
        """
        Connect to MCP server via streamable HTTP.
        
        Nested context managers:
        1. streamablehttp_client: HTTP streaming layer
        2. ClientSession: MCP protocol layer
        
        Flow:
        1. Check if already connected (idempotent)
        2. Create HTTP streaming context with streamablehttp_client
        3. Extract read/write streams (ignore session param)
        4. Create ClientSession with streams
        5. Enter session context
        6. Initialize session (handshake)
        7. Print initialization result for debugging
        
        External I/O:
            - HTTP connection to MCP server
            - MCP protocol handshake
        """
        # Idempotent: skip if already connected
        if self.session:
            return
        
        # Create HTTP streaming context
        self._streams_context = streamablehttp_client(self.server_url)
        
        # Enter streaming context, get read/write streams
        # Note: streamablehttp_client returns (read_stream, write_stream, session)
        # We ignore session (third param) as we manage ClientSession separately
        read_stream, write_stream, _ = await self._streams_context.__aenter__()
        
        # Create MCP ClientSession with streams
        self._session_context = ClientSession(read_stream, write_stream)
        
        # Enter session context
        self.session = await self._session_context.__aenter__()
        
        # Initialize session (MCP handshake)
        init_result = await self.session.initialize()
        print(f"MCP Client connected to {self.server_url}: {init_result}")

    async def get_tools(self) -> list[MCPToolModel]:
        """
        Get available tools from MCP server.
        
        Flow:
        1. Call session.list_tools() (MCP protocol)
        2. Convert each tool to MCPToolModel
        3. Return list of tool models
        
        Returns:
            List of MCPToolModel with name, description, parameters (JSON Schema)
        
        External I/O:
            - MCP list_tools RPC call
        """
        if not self.session:
            raise RuntimeError("MCPClient not connected. Call connect() first.")
        
        # List tools from MCP server
        tools_result = await self.session.list_tools()
        
        # Convert to MCPToolModel
        return [
            MCPToolModel(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.inputSchema if hasattr(tool, 'inputSchema') else {}
            )
            for tool in tools_result.tools
        ]

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """
        Call a tool on the MCP server.
        
        Flow:
        1. Call session.call_tool() with name and arguments
        2. Extract content array from CallToolResult
        3. Concatenate all TextContent parts
        4. Return combined text
        
        Args:
            tool_name: Name of tool to call
            tool_args: Arguments dict matching tool's inputSchema
        
        Returns:
            Concatenated text content from tool execution
        
        MCP Content Types:
            - TextContent: Regular text result
            - ImageContent: Image data (not currently handled)
            - BlobContent: Binary data (not currently handled)
        
        External I/O:
            - MCP call_tool RPC with streaming result
        """
        if not self.session:
            raise RuntimeError("MCPClient not connected. Call connect() first.")
        
        # Call tool via MCP protocol
        result = await self.session.call_tool(tool_name, tool_args)
        
        # Extract content from result (CallToolResult contains array of content)
        content_parts = []
        for content_item in result.content:
            # Handle TextContent (most common)
            if isinstance(content_item, TextContent):
                content_parts.append(content_item.text)
            # Future: handle ImageContent, BlobContent if needed
        
        # Return concatenated content
        return "\n".join(content_parts)

    async def get_resource(self, uri: AnyUrl) -> str | bytes:
        """
        Get resource from MCP server.
        
        Flow:
        1. Call session.read_resource() with URI
        2. Extract contents array from ReadResourceResult
        3. Return first content (TextResourceContents as str, BlobResourceContents as bytes)
        
        Args:
            uri: URI of resource to fetch
        
        Returns:
            Text content (str) or binary content (bytes)
        
        External I/O:
            - MCP read_resource RPC call
        """
        if not self.session:
            raise RuntimeError("MCPClient not connected. Call connect() first.")
        
        # Read resource via MCP protocol
        result = await self.session.read_resource(uri)
        
        # Extract contents (ReadResourceResult contains array)
        if result.contents:
            content = result.contents[0]
            
            # Handle text resources
            if isinstance(content, TextResourceContents):
                return content.text
            
            # Handle binary resources
            elif isinstance(content, BlobResourceContents):
                return content.blob
        
        return ""

    async def close(self):
        """
        Close connection to MCP server.
        
        Flow:
        1. Exit ClientSession context (MCP protocol cleanup)
        2. Exit streamablehttp_client context (HTTP streaming cleanup)
        3. Clear all references
        
        Cleanup order:
            Inner → Outer (session → streams)
        """
        # Exit session context (MCP protocol)
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        
        # Exit streams context (HTTP streaming)
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)
        
        # Clear all references
        self.session = None
        self._session_context = None
        self._streams_context = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup on context exit."""
        await self.close()
        return False

