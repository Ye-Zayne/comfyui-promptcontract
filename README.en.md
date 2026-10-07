# PromptContract

[中文](README.md) · **0.1.0** · Python **3.10+** · ComfyUI V1 · MIT

Validate a prompt's inputs before a batch reaches generation. Missing subjects, misspelled keys, stale extra fields, wrong types and out-of-range values fail in Strict Render. Valid inputs produce a `STRING` that connects to `CLIPTextEncode.text`.

The runtime uses only the Python standard library. It loads no model, estimates no tokenizer tokens, reads no files or environment variables, performs no network calls, evaluates no Python expressions and persists no output. Author: **A ad钙**. Publisher: **ye-zayne**.

## Install and connect

Place this repository in `ComfyUI/custom_nodes/comfyui-promptcontract`, then restart ComfyUI. There are no extra pip dependencies.

1. Add **Strict Render** from the `PromptContract` category.
2. Fill `template`, `values_json` and `contract_json`.
3. Connect output `prompt` to `CLIPTextEncode.text`, then route its conditioning to the sampler.
4. Use **Inspect** for diagnostics, or connect `report_json` to native **Preview as Text / PreviewAny**.

Strict Render must be in the sampler's data dependency chain. Inspect alone reports errors and **does not gate another sampling branch**. Model loading or other dependencies may execute first, and this pack does not intercept independent queued work. Use two Strict Render instances for positive and negative prompts, each with only the slots that prompt uses.

## Nodes

| Node / class type | Inputs | Outputs | Invalid input |
| --- | --- | --- | --- |
| Inspect / `PromptContractInspect` | STRING `template`, `values_json`, `contract_json` | BOOLEAN `valid`, STRING `verdict`, STRING `report_json` | Returns `false`, `invalid` and specific errors |
| Strict Render / `PromptContractRender` | Same | STRING `prompt`, STRING `report_json` | Raises a concise error and produces no prompt |

Inspect is an output node and can be queued by itself; its report is also available through API history. Reports include schema/package versions, slot names and occurrence counts, input bytes, rendered bytes and errors. Reports and exceptions do not echo values or the full template.

## Example

Template:

```text
A {{subject}} in {{style}} style, {{count}} objects; enabled={{enabled}}.
```

`values_json`:

```json
{"subject":"纸鹤", "style":"ink", "count":0, "enabled":false}
```

`contract_json`:

```json
{
  "subject": {"type":"string", "min_length":1, "max_length":120},
  "style": {"type":"string", "choices":["ink","photo"]},
  "count": {"type":"integer", "minimum":0, "maximum":10},
  "enabled": {"type":"boolean"}
}
```

Result: `A 纸鹤 in ink style, 0 objects; enabled=false.` Zero and false are supplied values, and neither can impersonate the other's type. Strings preserve their original leading/trailing whitespace; empty strings and strings containing only Unicode whitespace are rejected.

## Exact grammar and escaping

| Template text | Meaning / result |
| --- | --- |
| `{{subject}}` | Substitute slot `subject` |
| `{{subject}} / {{subject}}` | Repeated slots are valid and reuse the same value |
| `{{{{` | Literal `{{` |
| `}}}}` | Literal `}}` |
| `{{{{subject}}}}` | Literal `{{subject}}`, without looking up a slot |
| `{ordinary braces}` | Single braces are ordinary text |

The parser scans left to right, giving four-brace escapes priority. Slot names match `[A-Za-z_][A-Za-z0-9_]{0,63}`. Spaces inside placeholders, attribute/index access, filters, defaults and expressions are invalid. An unclosed `{{`, unescaped standalone `}}` or empty `{{}}` fails. Quotes and backslashes have no special template escape meaning; JSON strings still use normal JSON escaping.

**Only the template is processed, once.** Values containing `{{other}}`, `$HOME` or wildcard text are copied literally. Intentional literals can therefore leave double braces in a valid result. All three local text widgets disable ComfyUI dynamic prompts; this pack cannot undo transformations another upstream node already performed.

## Small contract

This is not general JSON Schema. The contract is an object mapping slot names to rules. Every declared slot is required and must appear in the template. Value keys must match the contract. Unknown values, unused values, unused contract slots and undeclared placeholders fail. There are no optional fields, defaults, coercion or recursive objects.

| Rule | Support |
| --- | --- |
| `type` | Required: `string`, `integer`, `number`, `boolean` |
| `choices` | Optional list of 1–64 values matching the declared type; case sensitive |
| `min_length` / `max_length` | Strings only; nonnegative integers counting Unicode code points, not graphemes or tokenizer tokens |
| `minimum` / `maximum` | Numeric types only; inclusive bounds, minimum cannot exceed maximum |

`integer` rejects `1.0` and booleans. `number` accepts JSON integers and finite floats; fractional numbers use Python floating-point parsing. Booleans render as lowercase `true` / `false`; numbers render as JSON numeric text. Null, arrays and objects cannot be slot values. Unknown rules, including `required`, `enum` and `pattern`, are rejected. Duplicate JSON keys, NaN, Infinity, nonfinite exponent values and invalid Unicode surrogates fail. A literal-only template can use `{}` for both JSON inputs, but its final prompt must be nonblank.

## Limits

- Template: **65,536 UTF-8 bytes**. Each JSON input: **65,536 bytes**.
- At most **64** distinct slots and **1,024** placeholder occurrences. A JSON number may contain at most **128** characters.
- Rendered prompt: **131,072 UTF-8 bytes**. Reports list at most **128** errors and count omitted errors.
- String length rules have an upper bound of 131,072 code points; input/output byte limits also apply.
- These checks establish input/template consistency. They do not judge prompt semantics, image quality or actual CLIP truncation.

## API examples

`examples/inspect_api.json` is a complete model-free Inspect request. `examples/render_api.json` is a complete Strict Render → native `PreviewAny` request; it requires a ComfyUI version with Preview as Text. Separate Preview nodes display the rendered prompt and report.

From the repository directory:

```bash
curl -H 'Content-Type: application/json' --data-binary @examples/render_api.json http://127.0.0.1:8188/prompt
```

Use the returned `prompt_id` with `/history/{prompt_id}`. Removing `subject` from `values_json` makes Strict Render fail execution and prevents both previews from receiving output.

`examples/clip_wiring_fragment.json` is **only a graph fragment**: node `11` output `0` connects to `CLIPTextEncode` node `12`'s `text`. Its `clip` refers to output `1` of an existing node `1`, such as CheckpointLoaderSimple. Merge it into a complete model/sampler/output graph before submitting it.

## Existing nodes and scope

Prompt templates already exist. [ComfyUI-TemplateVars](https://github.com/boobkake22/ComfyUI-TemplateVars) supports missing-variable errors and brace checks in its CLIP template node. [StringConstructor](https://github.com/Lex-DRL/ComfyUI-StringConstructor) documents recursive formatting. PromptContract concentrates on small typed contracts, unknown/unused fields, strict JSON, resource bounds and one-pass substitution. It checks workflow **inputs**; WorkflowCanary checks outputs against a baseline.

## Development

```bash
python -m pip install pytest ruff
python -m pytest tests --rootdir=tests --confcutdir=tests -q
python -m ruff check . --select S102,S307,E702,F
```

Tests cover Unicode, escaping, repeated slots, nonrecursive values, duplicate keys, missing/extra fields, types, choices, length/numeric bounds, zero/false and resource limits. CI runs Python 3.10 and 3.12. V1 registration and API examples have local tests.
