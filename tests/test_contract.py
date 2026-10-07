import json

import pytest


def run(core, template, values, contract):
    return core.evaluate(template, json.dumps(values, ensure_ascii=False), json.dumps(contract, ensure_ascii=False))


def codes(result):
    return {error["code"] for error in result.report["errors"]}


def test_unicode_repeat_preserves_exact_values(core):
    result = run(core, "{{subject}} / {{subject}}", {"subject": "纸鹤 🪽"}, {"subject": {"type": "string", "min_length": 4, "max_length": 4}})
    assert result.valid and result.rendered == "纸鹤 🪽 / 纸鹤 🪽"
    assert result.report["slots"] == [{"name": "subject", "occurrences": 2, "type": "string"}]
    assert result.report["rendered_bytes"] == len(result.rendered.encode("utf-8"))


def test_missing_and_unknown_values_have_specific_errors_without_echo(core):
    result = run(core, "{{subject}}", {"subjet": "PRIVATE_VALUE"}, {"subject": {"type": "string"}})
    assert not result.valid and result.rendered is None
    assert {"missing_required", "unknown_value", "unused_value"} <= codes(result)
    assert "PRIVATE_VALUE" not in result.report_json()
    with pytest.raises(core.ContractError, match="Missing required slot 'subject'") as caught:
        core.render_strict("{{subject}}", '{"subjet":"PRIVATE_VALUE"}', '{"subject":{"type":"string"}}')
    assert "PRIVATE_VALUE" not in str(caught.value)


def test_unused_declared_value_is_rejected(core):
    result = run(core, "{{subject}}", {"subject": "bird", "style": "ink"}, {"subject": {"type": "string"}, "style": {"type": "string"}})
    assert {"unused_contract_slot", "unused_value"} <= codes(result)


def test_undeclared_placeholder_is_rejected(core):
    result = run(core, "{{subject}}", {}, {})
    assert "undeclared_slot" in codes(result)
    assert not result.valid


@pytest.mark.parametrize("value", ["", " ", "\t\n", "\u00a0\u3000"])
def test_empty_slots_fail_even_without_length_rule(core, value):
    assert "empty_slot" in codes(run(core, "{{s}}", {"s": value}, {"s": {"type": "string"}}))


@pytest.mark.parametrize("value,rule,rendered", [
    (0, {"type": "integer", "minimum": 0, "maximum": 0, "choices": [0]}, "0"),
    (0.0, {"type": "number", "minimum": 0, "maximum": 0, "choices": [0.0]}, "0.0"),
    (False, {"type": "boolean", "choices": [False]}, "false"),
    (True, {"type": "boolean"}, "true"),
])
def test_zero_and_false_are_present_valid_values(core, value, rule, rendered):
    result = run(core, "{{s}}", {"s": value}, {"s": rule})
    assert result.valid and result.rendered == rendered


@pytest.mark.parametrize("value,value_type", [(False, "integer"), (True, "number"), (0, "boolean"), (1.0, "integer"), (None, "string"), ({}, "string"), ([], "number"), ("1", "integer")])
def test_types_never_coerce_bool_number_or_null(core, value, value_type):
    assert "type_mismatch" in codes(run(core, "{{s}}", {"s": value}, {"s": {"type": value_type}}))


def test_choice_and_bounds_errors_are_independent(core):
    result = run(core, "{{style}} {{count}}", {"style": "longwrong", "count": 3}, {
        "style": {"type": "string", "choices": ["ink"], "max_length": 3},
        "count": {"type": "integer", "minimum": 0, "maximum": 2},
    })
    assert {"choice_mismatch", "length_out_of_range", "number_out_of_range"} <= codes(result)


def test_values_are_not_rendered_recursively_or_expanded(core, monkeypatch):
    monkeypatch.setenv("PROMPTCONTRACT_TEST", "SHOULD_NOT_APPEAR")
    value = "{{other}} $PROMPTCONTRACT_TEST ${PROMPTCONTRACT_TEST} __wildcard__"
    result = run(core, "Value: {{subject}}", {"subject": value}, {"subject": {"type": "string"}})
    assert result.valid and result.rendered == "Value: " + value
    assert "SHOULD_NOT_APPEAR" not in result.rendered


@pytest.mark.parametrize("template,expected", [
    ("{{{{subject}}}}", "{{subject}}"),
    ("{ordinary braces}", "{ordinary braces}"),
    ("{{{{", "{{"),
    ("}}}}", "}}"),
    ("{{{{{{subject}}}}}}", "{{bird}}"),
])
def test_literal_brace_policy_is_unambiguous(core, template, expected):
    used = "{{{{{{" in template
    result = run(core, template, {"subject": "bird"} if used else {}, {"subject": {"type": "string"}} if used else {})
    assert result.valid and result.rendered == expected


@pytest.mark.parametrize("template,code", [
    ("{{subject", "unclosed_slot"), ("subject}}", "unexpected_close"),
    ("{{}}", "invalid_placeholder"), ("{{ subject }}", "invalid_placeholder"),
    ("{{x.y}}", "invalid_placeholder"), ("{{x[0]}}", "invalid_placeholder"),
    ("{{__import__('os')}}", "invalid_placeholder"), ("{{x|default}}", "invalid_placeholder"),
    ("{{日本}}", "invalid_placeholder"), ("{{{x}}}", "invalid_placeholder"),
])
def test_unresolved_and_expression_syntax_rejected(core, template, code):
    result = core.evaluate(template, "{}", "{}")
    assert not result.valid and code in codes(result)


@pytest.mark.parametrize("text,code", [
    ('{"s":"one","s":"two"}', "duplicate_json_key"),
    ('{"s":NaN}', "non_finite_number"), ('{"s":Infinity}', "non_finite_number"),
    ('{"s":1e999}', "non_finite_number"),
    ('[]', "invalid_json_root"), ('{"s":}', "invalid_json"),
    ('{"s":' + "1" * 129 + '}', "number_too_long"),
    ('{"日本":"bird"}', "invalid_slot_name"),
])
def test_adversarial_json_fails_cleanly(core, text, code):
    result = core.evaluate("{{s}}", text, '{"s":{"type":"string"}}')
    assert code in codes(result)
    assert isinstance(json.loads(result.report_json()), dict)


@pytest.mark.parametrize("rule,code", [
    ({"type": "array"}, "invalid_rule_type"),
    ({"type": "string", "required": False}, "invalid_rule"),
    ({"type": "string", "min_length": True}, "invalid_length_rule"),
    ({"type": "string", "min_length": 4, "max_length": 1}, "invalid_length_range"),
    ({"type": "integer", "min_length": 1}, "invalid_length_rule"),
    ({"type": "number", "minimum": False}, "invalid_number_rule"),
    ({"type": "number", "minimum": 2, "maximum": 1}, "invalid_number_range"),
    ({"type": "boolean", "choices": [0]}, "invalid_choices"),
    ({"type": "string", "choices": []}, "invalid_choices"),
])
def test_narrow_contract_rejects_invalid_or_unsupported_rules(core, rule, code):
    assert code in codes(run(core, "{{s}}", {"s": "bird"}, {"s": rule}))


def test_duplicate_contract_rules_fail(core):
    result = core.evaluate("{{s}}", '{"s":"bird"}', '{"s":{"type":"string","type":"integer"}}')
    assert "duplicate_json_key" in codes(result)


def test_unicode_surrogates_are_rejected_with_serializable_report(core):
    result = core.evaluate("{{s}}", '{"s":"\\ud800"}', '{"s":{"type":"string"}}')
    assert "invalid_unicode" in codes(result)
    result.report_json().encode("utf-8")
    assert "invalid_unicode" in codes(core.evaluate("\ud800", "{}", "{}"))


def test_utf8_byte_limit_counts_multibyte_characters(core):
    assert "input_too_large" in codes(core.evaluate("汉" * 21846, "{}", "{}"))
    assert core.evaluate("x" * 65536, "{}", "{}").valid
    assert "input_too_large" in codes(core.evaluate("x" * 65537, "{}", "{}"))
    assert "input_too_large" in codes(core.evaluate("literal", " " * 65537, "{}"))


def test_repetition_cannot_bypass_output_budget(core):
    result = run(core, "{{s}}" * 3, {"s": "x" * 50000}, {"s": {"type": "string"}})
    assert "rendered_too_large" in codes(result) and result.rendered is None


def test_placeholder_and_key_counts_are_bounded(core):
    result = run(core, "{{s}}" * 1025, {"s": "x"}, {"s": {"type": "string"}})
    assert "too_many_placeholders" in codes(result)
    result = core.evaluate("literal", json.dumps({f"s{n}": "x" for n in range(65)}), "{}")
    assert "too_many_slots" in codes(result)


def test_deep_json_does_not_escape_inspection(core):
    text = '{"s":' + "[" * 1200 + "0" + "]" * 1200 + "}"
    result = core.evaluate("{{s}}", text, '{"s":{"type":"string"}}')
    # Python builds differ in JSON parser depth. Both supported outcomes must
    # remain inside Inspect and reject this unsupported nested-array value.
    assert codes(result) & {"invalid_json", "type_mismatch"}
    assert not result.valid
    assert json.loads(result.report_json())["valid"] is False


def test_empty_prompt_fails_but_literal_prompt_needs_no_slots(core):
    assert "empty_prompt" in codes(core.evaluate(" \n", "{}", "{}"))
    assert core.render_strict("A quiet landscape", "{}", "{}").rendered == "A quiet landscape"


def test_report_and_strict_errors_are_bounded(core):
    names = [f"s{n}" for n in range(64)]
    result = run(core, "literal", {f"x{n}": "hidden" for n in range(64)}, {name: {"type": "string"} for name in names})
    assert len(result.report["errors"]) == core.MAX_ERRORS
    assert result.report["errors_omitted"] > 0
    with pytest.raises(core.ContractError) as caught:
        core.render_strict("literal", json.dumps({f"x{n}": "hidden" for n in range(64)}), json.dumps({name: {"type": "string"} for name in names}))
    assert len(str(caught.value)) < 500 and "run Inspect" in str(caught.value)
