"""
Core agent orchestration: streams LLM responses, executes tool calls in parallel, and recursively 
handles multi-turn conversations until task completion.
"""
import asyncio
import json
from typing import Any

from aidial_client import AsyncDial
from aidial_client.types.chat.legacy.chat_completion import CustomContent, ToolCall
from aidial_sdk.chat_completion import Message, Role, Choice, Request, Response

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams
from task.utils.constants import TOOL_CALL_HISTORY_KEY
from task.utils.history import unpack_messages
from task.utils.stage import StageProcessor


class GeneralPurposeAgent:
    """
    Orchestrates LLM + tool execution via recursive streaming pattern.
    
    Flow:
    1. Receives user request → prepares messages (inject system prompt, unpack hidden state)
    2. Streams LLM response → accumulates content + tool_calls by index
    3. If tool_calls present → executes in parallel → appends to state → recurses
    4. If no tool_calls → returns final assistant message
    
    Key patterns:
    - System prompt injected per-request (never visible to user - security)
    - Tool call history hidden in custom_content.state (TOOL_CALL_HISTORY_KEY)
    - Streaming tool calls accumulated by index (OpenAI streaming spec)
    - Parallel tool execution with asyncio.gather()
    """

    def __init__(
            self,
            endpoint: str,
            system_prompt: str,
            tools: list[BaseTool],
    ):
        """
        Initialize agent with DIAL endpoint, system prompt, and available tools.
        
        Args:
            endpoint: DIAL Core API endpoint (e.g., http://localhost:8080)
            system_prompt: Injected per-request for security (hidden from user)
            tools: List of executable tools (file extraction, RAG, MCP, etc.)
        
        Side effects:
            - Creates tool name → tool lookup dict for O(1) access
            - Initializes state dict with empty TOOL_CALL_HISTORY_KEY array
        """
        self.endpoint = endpoint
        self.system_prompt = system_prompt
        self.tools = tools
        
        # Build O(1) lookup for tool execution: tool_name -> BaseTool
        self._tools_dict = {tool.name: tool for tool in tools}
        
        # Initialize hidden state for tool call history (not visible in UI)
        # Preserves full conversation context across recursive calls
        self.state = {TOOL_CALL_HISTORY_KEY: []}

    async def handle_request(self, deployment_name: str, choice: Choice, request: Request, response: Response) -> Message:
        """
        Main orchestration loop: stream LLM → execute tools → recurse until completion.
        
        Flow:
        1. Create AsyncDial client with per-request API key
        2. Stream chat completion with tools enabled
        3. Accumulate streaming tool_calls by index (OpenAI spec)
        4. If tool_calls present:
           - Execute all tools in parallel (asyncio.gather)
           - Append assistant msg + tool results to state
           - Recurse with updated history
        5. If no tool_calls: return final response
        
        Args:
            deployment_name: LLM model to use (gpt-4o, claude-sonnet-3-7, etc.)
            choice: DIAL response choice for streaming content to UI
            request: Incoming chat request with messages + headers
            response: DIAL response object (unused but required by SDK)
        
        Returns:
            Final assistant message with role=ASSISTANT
        
        Error handling:
            - Per-request API key from headers (DIAL forwards upstream keys)
            - Tool execution errors caught in BaseTool.execute()
        """
        # Create DIAL client with per-request API key (security: user's own key, not shared)
        # https://docs.dialx.ai/platform/core/per-request-keys
        async with AsyncDial(
            base_url=self.endpoint,
            api_key=request.headers.get("authorization", ""),
            api_version=request.headers.get("api-version", "")
        ) as client:
            # Stream LLM response with tools enabled
            chunks = client.chat.completions.create(
                messages=self._prepare_messages(request.messages),
                tools=[tool.schema for tool in self.tools],  # Provide tool schemas (OpenAI format)
                deployment_name=deployment_name,
                stream=True
            )
            
            # Accumulate streaming response: content + tool_calls by index
            # Tool calls arrive incrementally: first chunk has 'id', subsequent chunks accumulate arguments
            # See: https://platform.openai.com/docs/guides/function-calling#streaming
            tool_call_index_map: dict[int, Any] = {}  # index -> tool_call_delta
            content = ""
            
            # Process streaming chunks
            async for chunk in chunks:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    
                    if delta:
                        # Stream content to UI in real-time
                        if delta.content:
                            choice.append_content(delta.content)
                            content += delta.content
                        
                        # Accumulate tool calls by index
                        if delta.tool_calls:
                            for tool_call_delta in delta.tool_calls:
                                index = tool_call_delta.index
                                
                                # First chunk of new tool call (has 'id')
                                if tool_call_delta.id:
                                    tool_call_index_map[index] = tool_call_delta
                                else:
                                    # Subsequent chunks: accumulate function arguments
                                    existing_tool_call = tool_call_index_map[index]
                                    if tool_call_delta.function:
                                        # Safely get arguments, default to empty string to avoid None concatenation
                                        argument_chunk = tool_call_delta.function.arguments or ""
                                        existing_tool_call.function.arguments += argument_chunk
            
            # Build assistant message from accumulated data
            # Use ToolCall.validate() for pydantic v1 compatibility (DIAL SDK uses v1)
            assistant_message = Message(
                role=Role.ASSISTANT,
                content=content,
                tool_calls=[ToolCall.validate(tc) for tc in tool_call_index_map.values()] if tool_call_index_map else None
            )
            
            # Decision point: continue with tool execution or return final response?
            if assistant_message.tool_calls:
                # Parallel tool execution phase
                conversation_id = request.headers.get("x-conversation-id", "")
                api_key = request.headers.get("authorization", "")
                
                # Create async tasks for parallel execution (don't await yet)
                tasks = [
                    self._process_tool_call(tool_call, choice, api_key, conversation_id)
                    for tool_call in assistant_message.tool_calls
                ]
                
                # Execute all tools in parallel
                tool_messages = await asyncio.gather(*tasks)
                
                # Update hidden state with assistant message + tool results
                # This preserves full conversation for next recursive call
                self.state[TOOL_CALL_HISTORY_KEY].append(assistant_message.dict(exclude_none=True))
                self.state[TOOL_CALL_HISTORY_KEY].extend(tool_messages)
                
                # Recursive call: LLM sees tool results and continues reasoning
                return await self.handle_request(deployment_name, choice, request, response)
            
            # No tool calls: task complete, return final response
            choice.set_custom_content(CustomContent(state=self.state))
            return assistant_message

    def _prepare_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """
        Prepare messages for LLM: unpack state, inject system prompt, log history.
        
        Flow:
        1. Unpack messages from state (extracts tool call history from custom_content.state)
        2. Inject system prompt at index 0 (security: hidden from user per-request)
        3. Log full history for debugging (includes unpacked tool calls)
        
        Args:
            messages: Incoming DIAL messages (may contain state with hidden tool history)
        
        Returns:
            List of message dicts ready for LLM consumption (includes system prompt + unpacked history)
        
        Security note:
            System prompt injected per-request to prevent user manipulation/extraction.
        """
        # Unpack tool call history from state (hidden in assistant messages)
        unpacked_messages = unpack_messages(messages, self.state[TOOL_CALL_HISTORY_KEY])
        
        # Inject system prompt at position 0 (security: per-request injection)
        # Why not store in history? Prevents prompt extraction attacks
        unpacked_messages.insert(0, {"role": "system", "content": self.system_prompt})
        
        # Debug logging: print full conversation history
        print("\n=== Conversation History ===")
        for msg in unpacked_messages:
            print(json.dumps(msg, indent=2))
        print("=== End History ===\n")
        
        return unpacked_messages

    async def _process_tool_call(self, tool_call: ToolCall, choice: Choice, api_key: str, conversation_id: str) -> dict[str, Any]:
        """
        Execute single tool call: open stage → show args → execute → close stage.
        
        Flow:
        1. Extract tool name from tool_call.function.name
        2. Open Stage (UI visualization in DIAL Chat)
        3. If tool.show_in_stage: display request arguments as JSON
        4. Execute tool with ToolCallParams (includes stage, choice, api_key, conversation_id)
        5. Close stage (gracefully handles errors)
        6. Return tool message as dict
        
        Args:
            tool_call: LLM's tool invocation (id, function.name, function.arguments)
            choice: DIAL choice for streaming UI updates
            api_key: Per-request API key (forwarded to tool if needed)
            conversation_id: For scoping caches (e.g., RAG document cache)
        
        Returns:
            Tool message dict with role=TOOL, content, tool_call_id, name
        
        Error handling:
            - BaseTool.execute() catches exceptions and returns error as content
            - StageProcessor.close_stage_safely() handles orphaned stages
        """
        # Extract tool name for lookup
        tool_name = tool_call.function.name
        
        # Open Stage for UI visualization (shows in DIAL Chat as expandable section)
        stage = StageProcessor.open_stage(choice, tool_name)
        
        # Get tool from lookup dict (O(1) access)
        tool = self._tools_dict[tool_name]
        
        # Conditionally display request arguments (some tools manage stage manually)
        if tool.show_in_stage:
            stage.append_content("## Request arguments:\n")
            # Pretty-print JSON arguments
            stage.append_content(f"```json\n{json.dumps(json.loads(tool_call.function.arguments), indent=2)}\n```\n")
            stage.append_content("## Response:\n")
        
        # Execute tool (async, may involve external I/O: DIAL, MCP servers, embeddings)
        tool_message = await tool.execute(
            ToolCallParams(
                tool_call=tool_call,
                stage=stage,
                choice=choice,
                api_key=api_key,
                conversation_id=conversation_id
            )
        )
        
        # Close stage gracefully (catches errors to prevent orphaned UI elements)
        StageProcessor.close_stage_safely(stage)
        
        # Return as dict for state storage
        return tool_message.dict(exclude_none=True)
