# PromptContract

[English](README.en.md) · **0.1.0** · Python **3.10+** · ComfyUI V1 · MIT

在批量生产前校验提示词输入：漏填主体、字段拼错、多带了旧字段、类型不符或长度超限时，让工作流在严格渲染节点报错。合法输入才输出可连接到 `CLIPTextEncode.text` 的 `STRING`。

运行时只使用 Python 标准库，不加载模型，不计算 tokenizer 的 token 数，不读取文件或环境变量，也不联网、执行 Python 表达式或保存输出。作者 **A ad钙**，发布者 **ye-zayne**。

## 安装和连接

把本仓库放入 `ComfyUI/custom_nodes/comfyui-promptcontract`，重启 ComfyUI。没有额外 pip 依赖。

1. 在 `PromptContract` 分类添加 **Strict Render**。
2. 填写 `template`、`values_json`、`contract_json`。
3. 把输出 `prompt` 接到 `CLIPTextEncode` 的 `text`；把生成的 conditioning 接到采样器。
4. 调试时添加 **Inspect**，或把 `report_json` 接到原生 **Preview as Text / PreviewAny**。

严格渲染必须在采样器的数据依赖链上。独立放置 Inspect 只生成报告，**不能阻止另一条采样分支**。模型加载等其他依赖可能先执行；本包不会拦截队列中独立的任务。正、负提示词可各用一个 Strict Render，分别提供本提示词实际使用的合同和值。

## 节点

| 节点 / class type | 输入 | 输出 | 无效输入 |
| --- | --- | --- | --- |
| Inspect / `PromptContractInspect` | 三个 STRING：`template`、`values_json`、`contract_json` | BOOLEAN `valid`、STRING `verdict`、STRING `report_json` | 返回 `false` / `invalid` 和具体错误列表 |
| Strict Render / `PromptContractRender` | 同上 | STRING `prompt`、STRING `report_json` | 抛出简短错误，不输出提示词 |

Inspect 是输出节点，可独立排队；报告可在 API history 中读取。渲染报告包含格式版本、槽位名和出现次数、输入字节数、输出字节数及错误。报告和异常不重复打印输入值或整段模板。

## 示例

模板：

```text
A {{subject}} in {{style}} style, {{count}} objects; enabled={{enabled}}.
```

`values_json`：

```json
{"subject":"纸鹤", "style":"ink", "count":0, "enabled":false}
```

`contract_json`：

```json
{
  "subject": {"type":"string", "min_length":1, "max_length":120},
  "style": {"type":"string", "choices":["ink","photo"]},
  "count": {"type":"integer", "minimum":0, "maximum":10},
  "enabled": {"type":"boolean"}
}
```

结果：`A 纸鹤 in ink style, 0 objects; enabled=false.`。`0` 和 `false` 是已填写的合法值，不能相互冒充类型。字符串原样插入，不自动去除首尾空白；只拒绝空字符串和全部由 Unicode 空白字符组成的字符串。

## 精确语法和转义

| 模板文字 | 含义 / 结果 |
| --- | --- |
| `{{subject}}` | 引用槽位 `subject` |
| `{{subject}} / {{subject}}` | 重复槽位合法，两处使用同一个值 |
| `{{{{` | 字面量 `{{` |
| `}}}}` | 字面量 `}}` |
| `{{{{subject}}}}` | 字面量 `{{subject}}`，不会查询该槽位 |
| `{ordinary braces}` | 单花括号属于普通文字 |

按从左到右顺序扫描，四个花括号的转义优先于槽位识别。槽位名必须满足 `[A-Za-z_][A-Za-z0-9_]{0,63}`；`{{ subject }}`、属性访问、索引、过滤器、默认值或表达式都无效。未闭合 `{{`、未转义的独立 `}}` 和空槽位 `{{}}` 报错。引号和反斜杠没有模板转义含义；JSON 字符串仍遵守 JSON 自身的转义规则。

**只渲染一遍模板**。如果值本身包含 `{{other}}`、`$HOME` 或通配符文字，这些内容会原样进入结果，不继续展开。因此合法输出可以包含刻意转义或值中自带的双花括号。三个输入的本节点文本控件都关闭了 ComfyUI dynamic prompts；其他上游节点如果已改写文字，本包不能还原。

## 最小合同

合同不是通用 JSON Schema。顶层是“槽位名 → 规则对象”；每个定义的槽位都必填、必须在模板使用，值的键必须与合同一致。未知值、未使用值、未使用合同槽位和未声明的模板槽位均报错。没有可选字段、默认值、类型转换或递归对象。

| 规则 | 支持范围 |
| --- | --- |
| `type` | 必填：`string`、`integer`、`number`、`boolean` |
| `choices` | 可选：1–64 个与声明类型匹配的值，区分大小写 |
| `min_length` / `max_length` | 仅字符串；非负整数，按 Unicode 码点计数，不是可见字符或 token 数 |
| `minimum` / `maximum` | 仅数值；包含边界，最小值不得大于最大值 |

`integer` 不接收 `1.0` 或布尔值；`number` 接收 JSON 整数和有限浮点数，浮点数采用 Python 的浮点解析。布尔值输出小写 `true` / `false`，数值输出 JSON 数值文字。`null`、数组和对象不能当作槽位值。未知规则（包括 `required`、`enum`、`pattern`）报错。重复 JSON 键、NaN、Infinity、非有限的指数值及无效 Unicode surrogate 都被拒绝。纯文字模板可使用两份 `{}`，但最终提示词仍须非空。

## 限制

- 模板最多 **65,536 UTF-8 字节**；每份 JSON 同样最多 **65,536 字节**。
- 最多 **64** 个不同槽位、**1,024** 次占位符引用；一个 JSON 数值文字最多 **128** 个字符。
- 渲染结果最多 **131,072 UTF-8 字节**；报告最多列出 **128** 条错误，并提供省略数量。
- 字符串长度限制上限为 131,072 码点；输入和输出字节限制仍同时生效。
- 这些检查保证输入和模板合同一致，不评价提示词语义、最终画质或实际 CLIP token 截断。

## API 示例

`examples/inspect_api.json` 是不依赖模型的完整 Inspect 请求。`examples/render_api.json` 是 Strict Render → 原生 `PreviewAny` 的完整请求，需安装版本包含原生 Preview as Text；提示词与报告分别在两个 Preview 输出中。

从仓库目录提交示例：

```bash
curl -H 'Content-Type: application/json' --data-binary @examples/render_api.json http://127.0.0.1:8188/prompt
```

使用响应的 `prompt_id` 读取 `/history/{prompt_id}`。把 `values_json` 的 `subject` 删除后，Strict Render 会产生执行错误，两个 Preview 不会收到结果。

`examples/clip_wiring_fragment.json` **只是 API 图片段**：节点 `11` 的输出 `0` 接到 `CLIPTextEncode` 节点 `12` 的 `text`，其 `clip` 指向已有节点 `1` 的输出 `1`（例如 CheckpointLoaderSimple）。必须合入已有加载模型、采样器和输出节点的完整图才能提交。

## 已有节点和本包差异

已有提示词模板节点。[ComfyUI-TemplateVars](https://github.com/boobkake22/ComfyUI-TemplateVars) 已支持缺失变量报错，其 CLIP 模板节点也检查花括号；[StringConstructor](https://github.com/Lex-DRL/ComfyUI-StringConstructor) 明确提供递归格式化。PromptContract 集中提供小型类型合同、未知与未使用字段检查、严格 JSON、资源上限和一次性插值。它检查工作流**输入**；WorkflowCanary 检查输出是否相对基准发生变化，用途不同。

## 开发验证

```bash
python -m pip install pytest ruff
python -m pytest tests --rootdir=tests --confcutdir=tests -q
python -m ruff check . --select S102,S307,E702,F
```

测试覆盖 Unicode、转义、重复槽位、非递归值、重复 JSON 键、缺失与多余字段、类型/choices/长度/数值边界、`0`/`false` 和资源限制。CI 使用 Python 3.10 / 3.12。ComfyUI V1 注册和 API 示例也有本地测试。
