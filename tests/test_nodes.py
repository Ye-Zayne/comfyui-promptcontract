import json
from pathlib import Path

import pytest


def test_nodes_are_registered_and_defaults_render(package):
    mappings = package.NODE_CLASS_MAPPINGS
    assert set(mappings) == {"PromptContractInspect", "PromptContractRender"}
    render = mappings["PromptContractRender"]()
    inputs = render.INPUT_TYPES()["required"]
    kwargs = {name: specification[1]["default"] for name, specification in inputs.items()}
    assert all(specification[1]["dynamicPrompts"] is False for specification in inputs.values())
    prompt, report = render.render(**kwargs)
    assert prompt == "A 纸鹤 in ink style, 0 objects."
    assert json.loads(report)["valid"] is True


def test_inspect_invalid_returns_report_while_render_fails(package):
    kwargs = {"template": "{{subject}}", "values_json": "{}", "contract_json": '{"subject":{"type":"string"}}'}
    inspect = package.NODE_CLASS_MAPPINGS["PromptContractInspect"]()
    assert inspect.OUTPUT_NODE is True
    output = inspect.inspect(**kwargs)
    assert output["result"][0:2] == (False, "invalid")
    assert json.loads(output["result"][2])["errors"][0]["code"] == "missing_required"
    with pytest.raises(ValueError, match="Missing required slot"):
        package.NODE_CLASS_MAPPINGS["PromptContractRender"]().render(**kwargs)


def test_standalone_api_example_uses_real_output_node(package):
    path = Path(__file__).resolve().parents[1] / "examples" / "inspect_api.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    node = payload["prompt"]["1"]
    instance = package.NODE_CLASS_MAPPINGS[node["class_type"]]()
    assert instance.OUTPUT_NODE is True
    assert instance.inspect(**node["inputs"])["result"][0] is True


def test_render_api_graph_connects_prompt_and_report_to_native_preview(package):
    path = Path(__file__).resolve().parents[1] / "examples" / "render_api.json"
    graph = json.loads(path.read_text(encoding="utf-8"))["prompt"]
    prompt, report = package.NODE_CLASS_MAPPINGS[graph["1"]["class_type"]]().render(**graph["1"]["inputs"])
    assert prompt == "A 纸鹤 in ink style, 0 objects."
    assert json.loads(report)["valid"] is True
    assert graph["2"] == {"class_type": "PreviewAny", "inputs": {"source": ["1", 0]}}
    assert graph["3"] == {"class_type": "PreviewAny", "inputs": {"source": ["1", 1]}}
