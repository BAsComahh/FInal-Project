"""Optional Real-ESRGAN image enhancement for the tray-edge fallback."""

from .upscaler import DEFAULT_RUNTIME, upscale_image

__all__ = ["DEFAULT_RUNTIME", "upscale_image"]
