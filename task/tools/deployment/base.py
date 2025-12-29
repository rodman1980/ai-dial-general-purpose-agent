"""
Base deployment tool: calls DIAL models (deployments) as tools with streaming support.
Subclasses implement specific deployments (image generation, etc.).
"""
import json
from abc import ABC, abstractmethod
from typing import Any

from aidial_client import AsyncDial
from aidial_sdk.chat_completion import Message, Role, CustomContent
from pydantic import StrictStr

from task.tools.base import BaseTool
from task.tools.models import ToolCallParams


class DeploymentTool(BaseTool, ABC):
    """
    Base class for tools that wrap DIAL model deployments (DALL-E-3, etc.).
    
    Pattern: Template method with streaming
    - Subclass provides deployment_name and tool_parameters
    - Base class handles AsyncDial client, streaming, attachment collection
    - Subclass can override _execute for post-processing (e.g., propagate images to choice)
    
    Usage:
    - Image generation: DALL-E-3 deployment
    - Future: Could wrap other deployments (embeddings, etc.)
    """

    def __init__(self, endpoint: str):
        """
        Initialize with DIAL endpoint.
        
        Args:
            endpoint: DIAL Core endpoint (e.g., http://localhost:8080)
        """
        self.endpoint = endpoint

    @property
    @abstractmethod
    def deployment_name(self) -> str:
        """
        Name of DIAL deployment to call (configured in core/config.json).
        
        Examples: 'dall-e-3', 'gpt-4o', 'claude-sonnet-3-7'
        """
        pass

    @property
    def tool_parameters(self) -> dict[str, Any]:
        """
        Additional parameters for LLM call (temperature, top_p, etc.).
        
        Override in subclass if needed. Default: empty dict.
        """
        return {}

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        """
        Execute deployment tool: extract prompt → call DIAL model → collect response + attachments.
        
        Flow:
        1. Parse arguments, extract 'prompt' (standard param for deployment tools)
        2. Remove 'prompt' from args (other params go to custom_fields)
        3. Create AsyncDial client
        4. Call chat.completions.create with streaming
        5. Collect content + attachments while streaming to stage
        6. Return Message with role=TOOL, content, custom_content (attachments)
        
        Args:
            tool_call_params: Contains stage, api_key, tool_call args
        
        Returns:
            Message with tool role, content, attachments (if any), tool_call_id
        
        Custom fields:
            Extra parameters (beyond 'prompt') passed to deployment via extra_body.custom_fields
            Example: DALL-E-3 size, quality, style parameters
        
        External I/O:
            - HTTP streaming call to DIAL deployment (model inference)
        """
        # Parse arguments
        arguments = json.loads(tool_call_params.tool_call.function.arguments)
        
        # Extract prompt (standard param for deployment tools)
        prompt = arguments.get("prompt", "")
        
        # Remove prompt from args (remaining params go to custom_fields)
        arguments.pop("prompt", None)
        
        # Create AsyncDial client for deployment call
        async with AsyncDial(
            base_url=self.endpoint,
            api_key=tool_call_params.api_key,
            api_version="2025-01-01-preview"
        ) as client:
            # Call deployment with streaming
            # System prompt: optional, subclass can add via override
            # User message: prompt
            # Extra body: custom_fields for deployment-specific params (size, quality, etc.)
            chunks = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                deployment_name=self.deployment_name,
                stream=True,
                extra_body={"custom_fields": arguments} if arguments else None,
                **self.tool_parameters  # Additional LLM params (temperature, etc.)
            )
            
            # Collect content and attachments while streaming
            content = ""
            attachments = []
            
            async for chunk in chunks:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    
                    # Collect content
                    if delta.content:
                        content += delta.content
                        tool_call_params.stage.append_content(delta.content)
                    
                    # Collect attachments (e.g., generated images)
                    if delta.custom_content and delta.custom_content.attachments:
                        for attachment in delta.custom_content.attachments:
                            if attachment not in attachments:
                                attachments.append(attachment)
                                # Display attachment in stage (for visibility)
                                tool_call_params.stage.append_content(
                                    f"\n**Attachment**: {attachment.title or attachment.url}\n"
                                )
        
        # Return Message with tool role, content, attachments
        return Message(
            role=Role.TOOL,
            content=StrictStr(content) if content else None,
            custom_content=CustomContent(attachments=attachments) if attachments else None,
            tool_call_id=StrictStr(tool_call_params.tool_call.id),
            name=StrictStr(tool_call_params.tool_call.function.name)
        )
