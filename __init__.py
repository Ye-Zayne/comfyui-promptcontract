"""PromptContract: validate inputs before rendering a conditioning prompt."""

from .nodes import PromptContractInspect, PromptContractRender

NODE_CLASS_MAPPINGS = {
    "PromptContractInspect": PromptContractInspect,
    "PromptContractRender": PromptContractRender,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptContractInspect": "PromptContract · Inspect",
    "PromptContractRender": "PromptContract · Strict Render",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
