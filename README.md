# JSON YAML Converter

## 简体中文

在命令行或 Python 中把 JSON 与 YAML 互相转换。两者共用一套严格数据模型：只保留 JSON 能表示的值，拒绝重复键、非字符串键、非有限数字和不安全标签，并且不会覆盖已有输出文件。

```bash
pip install .
json-yaml json-to-yaml -i config.json -o config.yaml
json-yaml yaml-to-json -i config.yaml -o config.json
pytest
```

未声明版本的 YAML 按 YAML 1.1 解析；`%YAML 1.2` 按 1.2 Core schema 解析。选项、边界情况和开发命令见下文英文说明。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

Convert JSON and JSON-compatible YAML from the command line or Python, with strict
mapping checks and safe creation of new output files.

## Installation

```bash
git clone https://github.com/Master-626/json-yaml-converter.git
cd json-yaml-converter
pip install .
```

## Usage

```bash
json-yaml json-to-yaml -i config.json -o converted.yaml
json-yaml yaml-to-json -i config.yaml -o converted.json
json-yaml yaml-to-json -i config.yaml -o pretty.json --indent 4
json-yaml yaml-to-json -i config.yaml -o compact.json --compact

# Equivalent standalone commands
json2yaml -i config.json -o another.yaml
yaml2json -i config.yaml -o another.json

json-yaml validate -f config.json
json-yaml validate -f config.yaml
json-yaml --version
```

`yaml-to-json` and `yaml2json` accept `--indent N` (default `2`; `0` inserts newlines only)
and `--compact` (one line, same as `indent=None` in Python). Do not pass both.
`json-to-yaml` keeps mapping order and does not sort keys.

Conversion and validation failures exit with a nonzero status and an error message.
A success message is printed only after the output is published and staging cleanup
completes. All input and output text uses UTF-8.

## Output safety in 0.2.0

**The destination must not exist.** This is an intentional compatibility change from
0.1.0, which silently overwrote output files. There is no overwrite flag: choose a
new destination, review it, and manage any replacement yourself.

- Existing files, directories and symlinks (including dangling links) are refused.
- The same input/output path and symlink or hard-link aliases are refused.
- Parsing, validation and serialization finish before a temporary output is written.
- A complete, flushed temporary file in the output directory is published with an
  atomic, no-replace hard link. A destination created concurrently is preserved.
- The output directory must already exist. If hard links are unsupported or denied,
  conversion fails safely instead of falling back to a destructive write.
- New files have private permissions from the temporary-file mechanism (typically
  `0600` on POSIX); existing file permissions are not changed.

Ordinary failures before publication leave no destination and clean up the temporary
file. If cleanup itself fails **after** publication, the error explicitly says the
output was created; the complete output and a `.json-yaml-*` temporary link may remain.
Inspect those files rather than assuming nothing was written. An abrupt process or
machine termination may also leave a temporary file. Directory entries are not
fsynced, so survival across power loss is not guaranteed. Parent directories are
assumed to be trusted; this is not a sandbox against hostile directory replacement.

## Supported data and validation

The shared data model is null, booleans, finite numbers, Unicode strings, lists, and
objects with **string keys**. JSON and YAML duplicate keys are rejected at every
nesting level, including equivalent escaped keys. Non-string YAML keys are rejected
before Python can collapse `true` with `1`, or JSON can turn `1` and `"1"` into the
same object key. Quote intended string keys, such as `"true"`, `"1"` and `"null"`.

The converter rejects non-finite numbers (`NaN`, infinities and floating-point
overflow), unpaired Unicode surrogates, recursive aliases, YAML merge keys (`<<`),
custom or unsafe tags, and values without a JSON representation (such as timestamps,
binary values, sets, ordered-map and pairs tags). Expand merged mappings explicitly and
quote dates when a string is intended. Nonrecursive YAML aliases are supported, up to
1,000,000 values after expansion; a larger expansion is rejected instead of hanging.
Empty YAML represents null. Multiple YAML documents are not supported. A leading
UTF-8 BOM is ignored. Well-formed `\u` surrogate pairs (in JSON or double-quoted
YAML) become the corresponding Unicode character.

PyYAML's safe scalar rules apply, including YAML 1.1 boolean spellings such as
`yes` and `on`. Quote these when you need strings. Integers use Python integers;
decimal numbers use Python binary floating point and may round or underflow. This
is not an exact-decimal, comment-preserving, or formatting-preserving converter.

`%YAML 1.1`, and documents with no version directive, use those YAML 1.1 rules.
`%YAML 1.2` uses the YAML 1.2 Core schema instead: `yes` / `no` / `on` / `off` stay
strings, `012` is decimal 12, `0o12` is octal, `0x3A` is hex, scientific notation
such as `1e2` is a float, and sexagesimal, timestamps, `0b` binary, and underscores
in numbers stay strings. `<<` is an ordinary string key. Any other `%YAML` version
is rejected, because PyYAML would otherwise apply 1.1 types and silently change
values such as `yes` or `012`.

`validate` checks this same conversion-safe data model, not all possible YAML:
`.json` files must be JSON; `.yaml`/`.yml` files are checked as YAML. Other extensions
try JSON first, then YAML only on a JSON syntax error. A duplicate key or unsupported
JSON value cannot bypass validation through format fallback.

## Python API

```python
from json_yaml_converter import json_to_yaml, yaml_to_json, validate_file

# Accept strings or pathlib.Path objects. Return the exact text written.
yaml_text = json_to_yaml("input.json", "new-output.yaml")
json_text = yaml_to_json("input.yaml", "new-output.json", indent=2)
compact = yaml_to_json("input.yaml", "compact.json", indent=None)
result = validate_file("config.yaml")
print(result["is_valid"], result["format_detected"], result["error_message"])
```

Conversion raises `FileExistsError` for existing output, `ValueError` for aliases or
unsupported data, parser errors for invalid syntax, and `OSError` for file-system
failures. `validate_file` returns a result dictionary for invalid or unreadable files.

## Development

```bash
pip install -e ".[dev]"
python -m pytest --cov=json_yaml_converter --cov-branch --cov-report=term-missing
ruff check src tests
ruff format --check src tests
python -m build
```

Tests cover round trips, strict mapping validation, CLI failures, same-file aliases,
concurrent writers and injected publication failures. CI runs Linux Python 3.8–3.14,
plus Python 3.13 on macOS and Windows. Symlink tests skip only when the platform does
not permit creating symlinks; this is reported by pytest.

## License

MIT License
