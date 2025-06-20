import base64
import json
import mimetypes
import os
from io import BytesIO
from typing import Optional, Tuple

from PIL import Image

from agentpress.thread_manager import ThreadManager
from agentpress.tool import ToolResult, openapi_schema, xml_schema
from sandbox.tool_base import SandboxToolsBase

# Add common image MIME types if mimetypes module is limited
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/gif", ".gif")

# Maximum file size in bytes (e.g., 10MB for original, 5MB for compressed)
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_COMPRESSED_SIZE = 5 * 1024 * 1024

# Compression settings
DEFAULT_MAX_WIDTH = 1920
DEFAULT_MAX_HEIGHT = 1080
DEFAULT_JPEG_QUALITY = 85
DEFAULT_PNG_COMPRESS_LEVEL = 6


class SandboxVisionTool(SandboxToolsBase):
    """Tool for allowing the agent to 'see' images within the sandbox."""

    def __init__(self, project_id: str, thread_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)
        self.thread_id = thread_id
        # Make thread_manager accessible within the tool instance
        self.thread_manager = thread_manager

    def compress_image(
        self, image_bytes: bytes, mime_type: str, file_path: str
    ) -> Tuple[bytes, str]:
        """Compress an image to reduce its size while maintaining reasonable quality.

        Args:
            image_bytes: Original image bytes
            mime_type: MIME type of the image
            file_path: Path to the image file (for logging)

        Returns:
            Tuple of (compressed_bytes, new_mime_type)
        """
        try:
            # Open image from bytes
            img = Image.open(BytesIO(image_bytes))

            # Convert RGBA to RGB if necessary (for JPEG)
            if img.mode in ("RGBA", "LA", "P"):
                # Create a white background
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(
                    img, mask=img.split()[-1] if img.mode == "RGBA" else None
                )
                img = background

            # Calculate new dimensions while maintaining aspect ratio
            width, height = img.size
            if width > DEFAULT_MAX_WIDTH or height > DEFAULT_MAX_HEIGHT:
                ratio = min(DEFAULT_MAX_WIDTH / width, DEFAULT_MAX_HEIGHT / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(
                    f"[SeeImage] Resized image from {width}x{height} to {new_width}x{new_height}"
                )

            # Save to bytes with compression
            output = BytesIO()

            # Determine output format based on original mime type
            if mime_type == "image/gif":
                # Keep GIFs as GIFs to preserve animation
                img.save(output, format="GIF", optimize=True)
                output_mime = "image/gif"
            elif mime_type == "image/png":
                # Compress PNG
                img.save(
                    output,
                    format="PNG",
                    optimize=True,
                    compress_level=DEFAULT_PNG_COMPRESS_LEVEL,
                )
                output_mime = "image/png"
            else:
                # Convert everything else to JPEG for better compression
                img.save(
                    output, format="JPEG", quality=DEFAULT_JPEG_QUALITY, optimize=True
                )
                output_mime = "image/jpeg"

            compressed_bytes = output.getvalue()

            # Log compression results
            original_size = len(image_bytes)
            compressed_size = len(compressed_bytes)
            compression_ratio = (1 - compressed_size / original_size) * 100
            print(
                f"[SeeImage] Compressed '{file_path}' from {original_size / 1024:.1f}KB to {compressed_size / 1024:.1f}KB ({compression_ratio:.1f}% reduction)"
            )

            return compressed_bytes, output_mime

        except Exception as e:
            print(f"[SeeImage] Failed to compress image: {str(e)}. Using original.")
            return image_bytes, mime_type

    @openapi_schema(
        {
            "type": "function",
            "function": {
                "name": "see_image",
                "description": "Allows the agent to 'see' an image file located in the /workspace directory. Provide the relative path to the image. The image will be compressed before sending to reduce token usage. The image content will be made available in the next turn's context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The relative path to the image file within the /workspace directory (e.g., 'screenshots/image.png'). Supported formats: JPG, PNG, GIF, WEBP. Max size: 10MB.",
                        }
                    },
                    "required": ["file_path"],
                },
            },
        }
    )
    @xml_schema(
        tag_name="see-image",
        mappings=[{"param_name": "file_path", "node_type": "attribute", "path": "."}],
        example="""
        <!-- Example: Request to see an image named 'diagram.png' inside the 'docs' folder -->
        <function_calls>
        <invoke name="see_image">
        <parameter name="file_path">docs/diagram.png</parameter>
        </invoke>
        </function_calls>
        """,
    )
    async def see_image(self, file_path: str) -> ToolResult:
        """Reads an image file, compresses it, converts it to base64, and adds it as a temporary message."""
        try:
            # Ensure sandbox is initialized
            await self._ensure_sandbox()

            # Clean and construct full path
            cleaned_path = self.clean_path(file_path)
            full_path = f"{self.workspace_path}/{cleaned_path}"

            # Check if file exists and get info
            try:
                file_info = self.sandbox.fs.get_file_info(full_path)
                if file_info.is_dir:
                    return self.fail_response(
                        f"Path '{cleaned_path}' is a directory, not an image file."
                    )
            except Exception as e:
                return self.fail_response(
                    f"Image file not found at path: '{cleaned_path}'"
                )

            # Check file size
            if file_info.size > MAX_IMAGE_SIZE:
                return self.fail_response(
                    f"Image file '{cleaned_path}' is too large ({file_info.size / (1024*1024):.2f}MB). Maximum size is {MAX_IMAGE_SIZE / (1024*1024)}MB."
                )

            # Read image file content
            try:
                image_bytes = self.sandbox.fs.download_file(full_path)
            except Exception as e:
                return self.fail_response(f"Could not read image file: {cleaned_path}")

            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(full_path)
            if not mime_type or not mime_type.startswith("image/"):
                # Basic fallback based on extension if mimetypes fails
                ext = os.path.splitext(cleaned_path)[1].lower()
                if ext == ".jpg" or ext == ".jpeg":
                    mime_type = "image/jpeg"
                elif ext == ".png":
                    mime_type = "image/png"
                elif ext == ".gif":
                    mime_type = "image/gif"
                elif ext == ".webp":
                    mime_type = "image/webp"
                else:
                    return self.fail_response(
                        f"Unsupported or unknown image format for file: '{cleaned_path}'. Supported: JPG, PNG, GIF, WEBP."
                    )

            # Compress the image
            compressed_bytes, compressed_mime_type = self.compress_image(
                image_bytes, mime_type, cleaned_path
            )

            # Check if compressed image is still too large
            if len(compressed_bytes) > MAX_COMPRESSED_SIZE:
                return self.fail_response(
                    f"Image file '{cleaned_path}' is still too large after compression ({len(compressed_bytes) / (1024*1024):.2f}MB). Maximum compressed size is {MAX_COMPRESSED_SIZE / (1024*1024)}MB."
                )

            # Convert to base64
            base64_image = base64.b64encode(compressed_bytes).decode("utf-8")

            # Prepare the temporary message content
            image_context_data = {
                "mime_type": compressed_mime_type,
                "base64": base64_image,
                "file_path": cleaned_path,  # Include path for context
                "original_size": file_info.size,
                "compressed_size": len(compressed_bytes),
            }

            # Add the temporary message using the thread_manager callback
            # Use a distinct type like 'image_context'
            await self.thread_manager.add_message(
                thread_id=self.thread_id,
                type="image_context",  # Use a specific type for this
                content=image_context_data,  # Store the dict directly
                is_llm_message=False,  # This is context generated by a tool
            )

            # Inform the agent the image will be available next turn
            return self.success_response(
                f"Successfully loaded and compressed the image '{cleaned_path}' (reduced from {file_info.size / 1024:.1f}KB to {len(compressed_bytes) / 1024:.1f}KB)."
            )

        except Exception as e:
            return self.fail_response(
                f"An unexpected error occurred while trying to see the image: {str(e)}"
            )
