"""ComfyUI V1 nodes; render must be in the CLIP/sampler dependency chain."""

from .core import evaluate, render_strict

DEFAULT_TEMPLATE = "A {{subject}} in {{style}} style, {{count}} objects."
DEFAULT_VALUES = '{"subject":"纸鹤", "style":"ink", "count":0}'
DEFAULT_CONTRACT = '{"subject":{"type":"string","max_length":120}, "style":{"type":"string","choices":["ink","photo"]}, "count":{"type":"integer","minimum":0,"maximum":10}}'


def inputs():
    return {"required": {
        "template": ("STRING", {"multiline": True, "dynamicPrompts": False, "default": DEFAULT_TEMPLATE}),
        "values_json": ("STRING", {"multiline": True, "dynamicPrompts": False, "default": DEFAULT_VALUES}),
        "contract_json": ("STRING", {"multiline": True, "dynamicPrompts": False, "default": DEFAULT_CONTRACT}),
    }}


class PromptContractInspect:
    @classmethod
    def INPUT_TYPES(cls):
        return inputs()

    RETURN_TYPES = ("BOOLEAN", "STRING", "STRING")
    RETURN_NAMES = ("valid", "verdict", "report_json")
    FUNCTION = "inspect"
    CATEGORY = "PromptContract"
    OUTPUT_NODE = True
    DESCRIPTION = "Inspect template/JSON/typed slots without rendering an invalid prompt. The report does not gate another sampler branch."

    def inspect(self, template, values_json, contract_json):
        result = evaluate(template, values_json, contract_json)
        report = result.report_json()
        return {"ui": {"text": [result.verdict, report]}, "result": (result.valid, result.verdict, report)}


class PromptContractRender:
    @classmethod
    def INPUT_TYPES(cls):
        return inputs()

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "report_json")
    FUNCTION = "render"
    CATEGORY = "PromptContract"
    DESCRIPTION = "Strict one-pass rendering. Connect prompt to CLIPTextEncode.text; invalid input raises before this dependency can reach the sampler."

    def render(self, template, values_json, contract_json):
        result = render_strict(template, values_json, contract_json)
        return result.rendered, result.report_json()
