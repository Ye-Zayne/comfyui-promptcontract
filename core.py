"""Bounded, one-pass prompt substitution with a deliberately small contract."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
import re

VERSION = "0.1.0"
MAX_TEMPLATE_BYTES = 65536
MAX_JSON_BYTES = 65536
MAX_RENDERED_BYTES = 131072
MAX_SLOTS = 64
MAX_PLACEHOLDERS = 1024
MAX_NUMBER_CHARACTERS = 128
MAX_ERRORS = 128
SLOT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
TYPES = frozenset({"string", "integer", "number", "boolean"})
RULES = frozenset({"type", "choices", "min_length", "max_length", "minimum", "maximum"})


class ContractError(ValueError):
    """A bounded diagnostic; values and full templates are never echoed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Evaluation:
    valid: bool
    rendered: str | None
    report: dict

    @property
    def verdict(self) -> str:
        return "valid" if self.valid else "invalid"

    def report_json(self) -> str:
        return json.dumps(self.report, ensure_ascii=False, allow_nan=False, indent=2)


def _text_bytes(text: str, label: str, maximum: int) -> int:
    if not isinstance(text, str):
        raise ContractError("invalid_input_type", f"{label} must be a string.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ContractError("invalid_unicode", f"{label} contains an invalid Unicode surrogate.") from None
    if size > maximum:
        raise ContractError("input_too_large", f"{label} exceeds {maximum} UTF-8 bytes.")
    return size


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_json_key", "JSON contains a duplicate object key.")
        result[key] = value
    return result


def _integer(text: str) -> int:
    if len(text) > MAX_NUMBER_CHARACTERS:
        raise ContractError("number_too_long", "A JSON number exceeds 128 characters.")
    return int(text)


def _number(text: str) -> float:
    if len(text) > MAX_NUMBER_CHARACTERS:
        raise ContractError("number_too_long", "A JSON number exceeds 128 characters.")
    number = float(text)
    if not math.isfinite(number):
        raise ContractError("non_finite_number", "JSON numbers must be finite.")
    return number


def _constant(_text: str):
    raise ContractError("non_finite_number", "NaN and infinity are not valid contract values.")


def _json_object(text: str, label: str) -> tuple[dict, int]:
    size = _text_bytes(text, label, MAX_JSON_BYTES)
    try:
        parsed = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                            parse_float=_number, parse_constant=_constant)
    except ContractError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ContractError("invalid_json", f"{label} must be valid JSON.") from None
    if not isinstance(parsed, dict):
        raise ContractError("invalid_json_root", f"{label} must be a JSON object.")
    if len(parsed) > MAX_SLOTS:
        raise ContractError("too_many_slots", f"{label} may contain at most {MAX_SLOTS} slot keys.")
    if any(not SLOT_NAME.fullmatch(key) for key in parsed):
        raise ContractError("invalid_slot_name", f"{label} keys must be ASCII identifiers of 1–64 characters.")
    return parsed, size


def _template(text: str) -> tuple[list[tuple[str, str]], Counter, int]:
    size = _text_bytes(text, "template", MAX_TEMPLATE_BYTES)
    pieces, literal = [], []
    counts = Counter()
    position = 0
    occurrences = 0
    while position < len(text):
        if text.startswith("{{{{", position):
            literal.append("{{")
            position += 4
        elif text.startswith("}}}}", position):
            literal.append("}}")
            position += 4
        elif text.startswith("{{", position):
            end = text.find("}}", position + 2)
            if end == -1:
                raise ContractError("unclosed_slot", f"Unclosed template slot at character {position + 1}.")
            name = text[position + 2:end]
            if not SLOT_NAME.fullmatch(name):
                raise ContractError("invalid_placeholder", f"Invalid template slot at character {position + 1}; use {{{{name}}}} with an ASCII identifier.")
            if literal:
                pieces.append(("literal", "".join(literal)))
                literal = []
            pieces.append(("slot", name))
            counts[name] += 1
            occurrences += 1
            if len(counts) > MAX_SLOTS or occurrences > MAX_PLACEHOLDERS:
                raise ContractError("too_many_placeholders", "Template exceeds 64 distinct slots or 1024 placeholder occurrences.")
            position = end + 2
        elif text.startswith("}}", position):
            raise ContractError("unexpected_close", f"Unexpected closing braces at character {position + 1}; escape literal double braces as }}}}}}}}.")
        else:
            literal.append(text[position])
            position += 1
    if literal:
        pieces.append(("literal", "".join(literal)))
    return pieces, counts, size


def _matches(value, value_type: str) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "boolean":
        return type(value) is bool
    if value_type == "integer":
        return type(value) is int
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _contract(text: str) -> tuple[dict, int]:
    contract, size = _json_object(text, "contract_json")
    for name, rule in contract.items():
        if not isinstance(rule, dict) or not set(rule).issubset(RULES):
            raise ContractError("invalid_rule", f"Slot '{name}' must use an object with only supported contract rules.")
        value_type = rule.get("type")
        if not isinstance(value_type, str) or value_type not in TYPES:
            raise ContractError("invalid_rule_type", f"Slot '{name}' needs type string, integer, number, or boolean.")
        for key in ("min_length", "max_length"):
            if key in rule and (value_type != "string" or type(rule[key]) is not int or rule[key] < 0 or rule[key] > MAX_RENDERED_BYTES):
                raise ContractError("invalid_length_rule", f"Slot '{name}' length bounds need nonnegative integers on a string type.")
        if rule.get("min_length", 0) > rule.get("max_length", MAX_RENDERED_BYTES):
            raise ContractError("invalid_length_range", f"Slot '{name}' minimum length exceeds its maximum.")
        for key in ("minimum", "maximum"):
            if key in rule and (value_type not in {"integer", "number"} or not _matches(rule[key], "number")):
                raise ContractError("invalid_number_rule", f"Slot '{name}' numeric bounds need finite numbers on a numeric type.")
        if "minimum" in rule and "maximum" in rule and rule["minimum"] > rule["maximum"]:
            raise ContractError("invalid_number_range", f"Slot '{name}' minimum exceeds its maximum.")
        if "choices" in rule:
            choices = rule["choices"]
            if not isinstance(choices, list) or not 1 <= len(choices) <= MAX_SLOTS or any(not _matches(value, value_type) for value in choices):
                raise ContractError("invalid_choices", f"Slot '{name}' choices must contain 1–64 values of its declared type.")
            for value in choices:
                if isinstance(value, str):
                    _text_bytes(value, f"choices for '{name}'", MAX_JSON_BYTES)
    return contract, size


def _format_value(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def evaluate(template: str, values_json: str, contract_json: str) -> Evaluation:
    """Inspect without raising for user input errors. Never evaluate expressions."""
    errors = []
    omitted = 0
    def issue(code: str, message: str, slot: str | None = None):
        nonlocal omitted
        if len(errors) >= MAX_ERRORS:
            omitted += 1
            return
        record = {"code": code, "message": message}
        if slot is not None:
            record["slot"] = slot
        errors.append(record)

    pieces, counts, template_size = [], Counter(), None
    values, values_size, contract, contract_size = {}, None, {}, None
    parsed = 0
    try:
        pieces, counts, template_size = _template(template)
        parsed += 1
    except ContractError as error:
        issue(error.code, str(error))
    try:
        values, values_size = _json_object(values_json, "values_json")
        parsed += 1
    except ContractError as error:
        issue(error.code, str(error))
    try:
        contract, contract_size = _contract(contract_json)
        parsed += 1
    except ContractError as error:
        issue(error.code, str(error))
    if parsed == 3:
        for name in sorted(set(counts) - set(contract)):
            issue("undeclared_slot", f"Template slot '{name}' is not declared in the contract.", name)
        for name in sorted(set(contract) - set(counts)):
            issue("unused_contract_slot", f"Contract slot '{name}' is not used in the template.", name)
        for name in sorted(set(contract) - set(values)):
            issue("missing_required", f"Missing required slot '{name}'.", name)
        for name in sorted(set(values) - set(contract)):
            issue("unknown_value", f"Value '{name}' is not declared in the contract.", name)
        for name in sorted(set(values) - set(counts)):
            issue("unused_value", f"Value '{name}' is not used in the template.", name)
        for name in sorted(set(contract) & set(values)):
            rule, value = contract[name], values[name]
            value_type = rule["type"]
            if not _matches(value, value_type):
                issue("type_mismatch", f"Slot '{name}' must have JSON type {value_type}.", name)
                continue
            if value_type == "string":
                try:
                    _text_bytes(value, f"value for '{name}'", MAX_JSON_BYTES)
                except ContractError as error:
                    issue(error.code, str(error), name)
                    continue
                if not value.strip():
                    issue("empty_slot", f"Slot '{name}' must not be empty or whitespace only.", name)
                if len(value) < rule.get("min_length", 0) or len(value) > rule.get("max_length", MAX_RENDERED_BYTES):
                    issue("length_out_of_range", f"Slot '{name}' is outside its character length bounds.", name)
            if value_type in {"integer", "number"} and (
                ("minimum" in rule and value < rule["minimum"]) or ("maximum" in rule and value > rule["maximum"])
            ):
                issue("number_out_of_range", f"Slot '{name}' is outside its numeric bounds.", name)
            if "choices" in rule and value not in rule["choices"]:
                issue("choice_mismatch", f"Slot '{name}' is not one of its allowed choices.", name)
    rendered = None
    rendered_size = None
    if not errors and not omitted:
        output, rendered_size = [], 0
        for kind, value in pieces:
            part = value if kind == "literal" else _format_value(values[value])
            rendered_size += len(part.encode("utf-8"))
            if rendered_size > MAX_RENDERED_BYTES:
                issue("rendered_too_large", f"Rendered prompt exceeds {MAX_RENDERED_BYTES} UTF-8 bytes.")
                break
            output.append(part)
        if not errors:
            rendered = "".join(output)
            if not rendered.strip():
                issue("empty_prompt", "Rendered prompt must not be empty or whitespace only.")
                rendered = None
    valid = not errors and not omitted
    report = {
        "schema_version": 1, "package_version": VERSION, "valid": valid,
        "verdict": "valid" if valid else "invalid",
        "slots": [{"name": name, "occurrences": count, "type": contract.get(name, {}).get("type")} for name, count in counts.items()],
        "input_bytes": {"template": template_size, "values_json": values_size, "contract_json": contract_size},
        "rendered_bytes": rendered_size if valid else None,
        "errors": errors, "errors_omitted": omitted,
    }
    return Evaluation(valid, rendered if valid else None, report)


def render_strict(template: str, values_json: str, contract_json: str) -> Evaluation:
    result = evaluate(template, values_json, contract_json)
    if not result.valid:
        messages = [error["message"] for error in result.report["errors"][:3]]
        extra = len(result.report["errors"]) + result.report["errors_omitted"] - len(messages)
        suffix = f" (+{extra} more; run Inspect for the report)" if extra else ""
        raise ContractError("contract_invalid", "PromptContract: " + " ".join(messages) + suffix)
    return result
