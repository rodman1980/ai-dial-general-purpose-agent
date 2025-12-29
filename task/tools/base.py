"""
Base tool pattern: template method wraps _execute with error handling, returns Message.
All tools inherit from BaseTool and implement _execute().
"""
from abc import ABC, abstractmethod
from typing import Any

from aidial_client.types.chat import ToolParam, FunctionParam
from aidial_sdk.chat_completion import Message, Role
from pydantic import StrictStr

from task.tools.models import ToolCallParams


class BaseTool(ABC):
    """
    Abstract base for all tools: file extraction, RAG, MCP, deployment, etc.
    
    Pattern: Template method
    - execute() (public): wraps _execute() with error handling, returns Message
    - _execute() (abstract): subclass implements tool logic, returns str or Message
    
    Error handling:
    - All exceptions caught and returned as tool message content
    - Ensures agent continues even if tool fails
    """

    async def execute(self, tool_call_params: ToolCallParams) -> Message:
        """
        Execute tool with error handling (template method pattern).
        
        Flow:
        1. Create tool message skeleton (role=TOOL, name, tool_call_id)
        2. Try: call subclass _execute() → handle str vs Message result
        3. Except: catch all errors → return as message content
        
        Args:
            tool_call_params: Contains tool_call, stage, choice, api_key, conversation_id
        
        Returns:
            Message with role=TOOL, content (success/error), tool_call_id, name
        
        Error handling:
            All exceptions caught and formatted as error message (not raised)
        """
        # Create tool message skeleton
        message = Message(
            role=Role.TOOL,
            name=tool_call_params.tool_call.function.name,
            tool_call_id=tool_call_params.tool_call.id
        )
        
        try:
            # Call subclass implementation
            result = await self._execute(tool_call_params)
            
            # Handle different return types
            if isinstance(result, Message):
                # Subclass returned full Message (e.g., with attachments)
                message = result
            else:
                # Subclass returned string content
                message.content = result
        except Exception as e:
            # Catch all errors and return as tool message content
            # Agent will see error and can retry or explain to user
            message.content = f"Error executing tool: {str(e)}"
            print(f"⚠️ Tool execution error ({tool_call_params.tool_call.function.name}): {e}")
        
        return message

    @abstractmethod
    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        pass

    @property
    def show_in_stage(self) -> bool:
        return True

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        pass

    @property
    def schema(self) -> ToolParam:
        """
        Tool schema in DIAL/OpenAI function calling format.
        
        Format:
        {
          "type": "function",
          "function": {
            "name": "tool_name",
            "description": "What the tool does (max 1024 chars)",
            "parameters": {JSON Schema for arguments}
          }
        }
        
        References:
        - DIAL API: https://dialx.ai/dial_api#operation/sendChatCompletionRequest
        - OpenAI: https://platform.openai.com/docs/guides/function-calling#defining-functions
        
        Returns:
            ToolParam with type="function" and FunctionParam details
        """
        return ToolParam(
            type="function",
            function=FunctionParam(
                name=self.name,
                description=self.description,
                parameters=self.parameters
            )
        )
