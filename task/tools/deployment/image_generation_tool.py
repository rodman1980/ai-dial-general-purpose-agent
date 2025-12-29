"""
Image generation tool: uses DALL-E-3 via DIAL deployment to generate images.
Returns images as attachments that are propagated to assistant message.
"""
from typing import Any

from aidial_sdk.chat_completion import Message
from pydantic import StrictStr

from task.tools.deployment.base import DeploymentTool
from task.tools.models import ToolCallParams


class ImageGenerationTool(DeploymentTool):
    """
    Generate images using DALL-E-3 deployment.
    
    Process:
    1. User request contains prompt + optional parameters (size, quality, style)
    2. Call DALL-E-3 deployment via parent DeploymentTool._execute
    3. Collect generated images from attachments
    4. Propagate images to choice as markdown (visible in assistant message)
    
    Example user request: "Generate a picture of a smiling cat"
    Example tool call: {"prompt": "a smiling cat", "size": "1024x1024", "quality": "standard"}
    """

    async def _execute(self, tool_call_params: ToolCallParams) -> str | Message:
        """
        Generate image and propagate to choice.
        
        Flow:
        1. Call parent DeploymentTool._execute (calls DALL-E-3, collects content + images)
        2. Extract image attachments (filter by image/* mime types)
        3. Append images to choice as markdown: ![image](url)
        4. Add success instruction if no text content from DALL-E-3
        
        Args:
            tool_call_params: Contains stage, api_key, tool_call args
        
        Returns:
            Message with content (success message + image markdown), attachments, tool_call_id
        
        Propagation:
            Images returned in custom_content.attachments AND as markdown in content
            This ensures images are visible in assistant message (choice)
        """
        # Call parent to generate image via DALL-E-3
        result = await super()._execute(tool_call_params)
        
        # Handle both str and Message returns (though parent always returns Message)
        if isinstance(result, str):
            return result
        
        # Extract image attachments (filter by image mime types)
        image_attachments = []
        if result.custom_content and result.custom_content.attachments:
            for attachment in result.custom_content.attachments:
                # DALL-E-3 returns image/png or image/jpeg
                if attachment.type and attachment.type.startswith("image/"):
                    image_attachments.append(attachment)
        
        # Prepare content with image markdown for propagation to choice
        content_parts = []
        
        # Add original content if present (DALL-E-3 may return description)
        if result.content:
            content_parts.append(str(result.content))
        
        # Append images as markdown (propagates to assistant message)
        for attachment in image_attachments:
            # Title fallback: use filename or "Generated Image"
            title = attachment.title or "Generated Image"
            content_parts.append(f"\n\r![{title}]({attachment.url})\n\r")
        
        # Add success instruction if no original content
        if not result.content and image_attachments:
            content_parts.insert(
                0,
                "The image has been successfully generated according to request and shown to user!"
            )
        
        # Update message content (keep attachments in custom_content)
        result.content = "\n".join(content_parts) if content_parts else None
        
        return result

    @property
    def deployment_name(self) -> str:
        """DALL-E-3 deployment name (configured in core/config.json)."""
        return "dall-e-3"

    @property
    def name(self) -> str:
        """Tool name for LLM function calling."""
        return "image_generation"

    @property
    def description(self) -> str:
        """Tool description for LLM to understand when to use."""
        return (
            "Generate images using DALL-E-3. "
            "Provide a detailed text prompt describing the image to generate. "
            "Optional parameters: size (1024x1024, 1792x1024, 1024x1792), "
            "quality (standard, hd), style (vivid, natural). "
            "Use this tool when user explicitly requests image creation or picture generation."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """
        JSON Schema for tool parameters.
        
        Standard pattern: 'prompt' parameter + deployment-specific params.
        Extra params (size, quality, style) are passed to DALL-E-3 via custom_fields.
        """
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Extensive description of the image that should be generated. "
                        "Be specific about subject, style, composition, colors, lighting, etc."
                    )
                },
                "size": {
                    "type": "string",
                    "description": "Image dimensions (1024x1024 square, 1792x1024 wide, or 1024x1792 tall)",
                    "enum": ["1024x1024", "1792x1024", "1024x1792"]
                },
                "quality": {
                    "type": "string",
                    "description": "Image quality: 'standard' for normal, 'hd' for finer details and consistency",
                    "enum": ["standard", "hd"]
                },
                "style": {
                    "type": "string",
                    "description": "Image style: 'vivid' for hyper-realistic/dramatic, 'natural' for more realistic/subtle",
                    "enum": ["vivid", "natural"]
                }
            },
            "required": ["prompt"]
        }

