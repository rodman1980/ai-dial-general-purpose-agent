"""Python Code Interpreter: executes Python code via MCP server with file handling."""
import base64
import json
from typing import Any, Optional

from aidial_client import Dial
from aidial_sdk.chat_completion import Message, Attachment
from pydantic import StrictStr, AnyUrl

from task.tools.base import BaseTool
from task.tools.py_interpreter._response import _ExecutionResult
from task.tools.mcp.mcp_client import MCPClient
from task.tools.mcp.mcp_tool_model import MCPToolModel
from task.tools.models import ToolCallParams


class PythonCodeInterpreterTool(BaseTool):
    """
    Python code execution via MCP server with file handling.
    
    Wraps: https://github.com/khshanovskyi/mcp-python-code-interpreter
    
    Features:
    - Execute Python code in isolated sessions
    - Generate and download files (plots, CSV, etc.)
    - Upload generated files to DIAL storage
    - Return results with attachments
    
    Pattern:
    - Uses MCPClient to call 'execute_code' tool
    - Downloads generated files via MCP resources
    - Uploads files to DIAL bucket
    - Returns execution result + attachments
    
    ⚠️ This tool wraps all interaction with PyInterpreter MCP Server.
    """

    def __init__(
            self,
            mcp_client: MCPClient,
            mcp_tool_models: list[MCPToolModel],
            tool_name: str,
            dial_endpoint: str,
    ):
        """
        Initialize Python interpreter tool.
        
        Args:
            mcp_client: Connected MCPClient to Python interpreter server
            mcp_tool_models: List of available MCP tools
            tool_name: Name of code execution tool ('execute_code')
            dial_endpoint: DIAL Core endpoint for file uploads
        
        Raises:
            RuntimeError: If execute_code tool not found in MCP tools
        
        Reference:
            https://github.com/khshanovskyi/mcp-python-code-interpreter/blob/main/interpreter/server.py#L303
        """
        self.dial_endpoint = dial_endpoint
        self.mcp_client = mcp_client
        
        # Find execute_code tool in MCP tools
        self._code_execute_tool: Optional[MCPToolModel] = None
        for tool_model in mcp_tool_models:
            if tool_model.name == tool_name:
                self._code_execute_tool = tool_model
                break
        
        # Validate tool found
        if self._code_execute_tool is None:
            raise RuntimeError(
                f"Cannot set up PythonCodeInterpreterTool: '{tool_name}' tool not found in MCP server. "
                f"Available tools: {[t.name for t in mcp_tool_models]}"
            )

    @classmethod
    async def create(
            cls,
            mcp_url: str,
            tool_name: str,
            dial_endpoint: str,
    ) -> 'PythonCodeInterpreterTool':
        """
        Async factory method to create PythonCodeInterpreterTool.
        
        Flow:
        1. Create and connect MCPClient
        2. Get available tools from MCP server
        3. Create PythonCodeInterpreterTool with tools
        
        Args:
            mcp_url: URL of Python interpreter MCP server
            tool_name: Name of code execution tool ('execute_code')
            dial_endpoint: DIAL Core endpoint
        
        Returns:
            Initialized PythonCodeInterpreterTool
        """
        # Create MCP client and connect
        mcp_client = await MCPClient.create(mcp_url)
        
        # Get available tools
        mcp_tool_models = await mcp_client.get_tools()
        
        # Create and return tool instance
        return cls(mcp_client, mcp_tool_models, tool_name, dial_endpoint)

    @property
    def show_in_stage(self) -> bool:
        """
        """
        Execute Python code via MCP server.
        
        Flow:
        1. Parse arguments (code, optional session_id)
        2. Display code in stage
        3. Call execute_code via MCP client
        4. Parse execution result
        5. If files generated: download from MCP, upload to DIAL, attach to message
        6. Truncate output (limit context size)
        7. Return execution result + attachments
        
        Args:
            tool_call_params: Contains stage, api_key, tool_call args
        
        Returns:
            Execution result as JSON string (with attachments if files generated)
        
        External I/O:
            - MCP call_tool (execute Python code)
            - MCP get_resource (download generated files)
            - DIAL upload_file (upload files to bucket)
        """
        # 1. Parse arguments
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        code = arguments.get("code", "")
        session_id = arguments.get("session_id")  # Optional
        
        # 4. Get stage
        stage = tool_call_params.stage
        
        # 5. Display request arguments
        stage.append_content("## Request arguments:\n")
        
        # 6. Display code in Python markdown
        stage.append_content(f"```python\n{code}\n```\n")
        
        # 7. Display session info
        if session_id and session_id != 0:
            stage.append_content(f"**session_id**: {session_id}\n")
        else:
            stage.append_content("New session will be created\n")
        
        # 8. Execute code via MCP client
        response = await self.mcp_client.call_tool(self._code_execute_tool.name, arguments)
        
        # 9. Parse response as JSON
        response_data = json.loads(response)
        
        # 10. Validate with _ExecutionResult
        execution_result = _ExecutionResult(**response_data)
        
        # 11. Handle generated files
        attachments = []
        if execution_result.files:
            # Create DIAL client for file uploads
            dial_client = Dial(
                base_url=self.dial_endpoint,
                api_key=tool_call_params.api_key,
                api_version="2025-01-01-preview"
            )
            
            # Get files home directory
            files_home = dial_client.my_appdata_home()
            
            # Process each generated file
            for file_ref in execution_result.files:
                file_name = file_ref.name
                mime_type = file_ref.mime_type
                
                # Download file from MCP server via resource URI
                # Reference: https://github.com/khshanovskyi/mcp-python-code-interpreter/blob/main/interpreter/server.py#L429
                resource_content = await self.mcp_client.get_resource(AnyUrl(file_ref.uri))
                
                # Decode content based on mime type
                # MCP binary resources are base64 encoded: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#binary-content
                if mime_type.startswith("text/") or mime_type in ["application/json", "application/xml"]:
                    # Text files: encode string to bytes
                    file_bytes = resource_content.encode("utf-8") if isinstance(resource_content, str) else resource_content
                else:
                    # Binary files: decode base64
                    file_bytes = base64.b64decode(resource_content) if isinstance(resource_content, str) else resource_content
                
                # Prepare upload URL
                upload_url = f"files/{(files_home / file_name).as_posix()}"
                
                # Upload file to DIAL bucket
                dial_client.upload_file(upload_url, file_bytes, mime_type)
                
                # Create attachment
                attachment = Attachment(
                    url=StrictStr(upload_url),
                    type=StrictStr(mime_type),
                    title=StrictStr(file_name)
                )
                attachments.append(attachment)
                
                # Display attachment in stage AND add to choice
                stage.append_content(f"\n**Generated file**: [{file_name}]({upload_url})\n")
        
        # 12. Truncate output to avoid context overflow
        if execution_result.output:
            execution_result.output = [
                out[:1000] if len(out) > 1000 else out
                for out in execution_result.output
            ]
        
        # 13. Display execution result in stage
        stage.append_content(f"\n## Execution result:\n```json\n{execution_result.model_dump_json(indent=2)}\n```\n")
        
        # 14. Return result (with attachments if any)
        return execution_result.model_dump_jsonnse as json (️⚠️ here can be potential issues if you didn't properly implemented
        #    MCPClient tool call, it must return string)
        # 10. Validate result with _ExecutionResult (it is full copy of https://github.com/khshanovskyi/mcp-python-code-interpreter/blob/main/interpreter/models.py)
        # 11. If execution_result contains files we need to pool files from PyInterpreter and upload them to DIAL bucked:
        #       - Create Dial client
        #       - Get with client `my_appdata_home` path as `files_home`
        #       - Iterated through files and:
        #           - get file name and mime_type and assign to appropriate variables
        #           - get resource with mcp client by URL from file (https://github.com/khshanovskyi/mcp-python-code-interpreter/blob/main/interpreter/server.py#L429)
        #           - according to MCP binary resources must be encoded with base64 https://modelcontextprotocol.io/specification/2025-06-18/server/resources#binary-content
        #             Check if mime_type starts with `text/` or some of 'application/json', 'application/xml', is yes
        #             then encode resource with 'utf-8' format (text will be present as bytes to upload to DIAL bucket).
        #             Otherwise (binary file) decode it with `b64decode`
        #           - Prepare URL to upload downloaded file: f"files/{(files_home / file_name).as_posix()}"
        #           - Upload file with DIAL client
        #           - Prepare Attachment with url, type (mime_type), and title (file_name)
        #           - Add attachment to stage and also add this attachment to choice (it will be chown in both stage and choice)
        #       - Add to execution_result json addition
        # 12. Check if execution_result output present and if yes iterate through all output results and cut it length
        #     to 1000 chars, it is needed to avoid high costs and context window overload
        # 13. Append to stage response f"```json\n\r{execution_result.model_dump_json(indent=2)}\n\r```\n\r"
        # 14. Return execution result as string (model_dump_json method)
        raise NotImplementedError()
