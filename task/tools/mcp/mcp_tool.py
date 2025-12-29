"""MCP Tool: wraps MCP server tools as BaseTool for agent orchestration."""
import json
from typing import Any

from aidial_sdk.chat_completion import Message

from task.tools.base import BaseTool
from task.tools.mcp.mcp_client import MCPClient
from task.tools.mcp.mcp_tool_model import MCPToolModel
from task.tools.models import ToolCallParams


class MCPTool(BaseTool):
    """
    Wraps MCP server tool as BaseTool for DIAL agent integration.
    
    Pattern: Adapter
    - MCP tools (DuckDuckGo search, Python interpreter, etc.) exposed via MCP protocol
    - MCPTool adapts them to BaseTool interface for agent orchestration
    - Delegates execution to MCPClient
    
    Usage:
    ```python
    async with MCPClient.create(url) as client:
        tools_models = await client.get_tools()
        tools = [MCPTool(client, model) for model in tools_models]
        # Now tools can be used by agent
    ```
    
    Lifecycle:
    - MCPClient manages connection (created once, reused for all tools)
    - MCPTool is stateless wrapper (one instance per MCP tool)
    """

    def __init__(self, client: MCPClient, mcp_tool_model: MCPToolModel):
        """
        Initialize with MCP client and tool model.
        
        Args:
            client: Connected MCPClient (shared across all MCP tools)
            mcp_tool_model: Tool metadata (name, description, parameters schema)
        """
        self.client = client
        self.mcp_tool_model = mcp_tool_model

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        """
        Execute MCP tool via client.
        
        Flow:
        1. Parse arguments from tool call
        2. Call MCP tool via client.call_tool()
        3. Append result content to stage (for UI visibility)
        4. Return content as string
        
        Args:
            tool_call_params: Contains stage, api_key, tool_call args
        
        Returns:
            Tool result as string (text content from MCP server)
        
        External I/O:
            - MCP call_tool RPC via client
        """
        # Parse arguments from tool call
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        
        # Call MCP tool via client
        content = await self.client.call_tool(self.mcp_tool_model.name, arguments)
        
        # Append content to stage for visibility
        tool_call_params.stage.append_content(f"\n{content}\n")
        
        # Return content
        return content

    @property
    def name(self) -> str:
        """Tool name from MCP tool model."""
        return self.mcp_tool_model.name

    @property
    def description(self) -> str:
        """Tool description from MCP tool model."""
        return self.mcp_tool_model.description

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters JSON Schema from MCP tool model."""
        return self.mcp_tool_model.parameters
