"""Strict JSON/YAML conversion with non-destructive output publication."""

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Dict

import yaml

# A fully expanded document larger than this is rejected. The cap stops alias
# bombs in linear time; ordinary files count one node per value and key.
_MAX_EXPANDED_NODES = 1_000_000

# YAML 1.2 Core schema (https://yaml.org/spec/1.2.2/#1032-core-schema).
# Order matters at resolve time: integers are tested before floats because the
# float expression also matches digit-only scalars such as "0" and "10".
_YAML12_BOOL = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_YAML12_NULL = re.compile(r"^(?:~|null|Null|NULL|)$")
_YAML12_INT = re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")
_YAML12_FLOAT = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)"
    r"|\.(?:nan|NaN|NAN))$"
)


def _too_large():
    return f"Document expands to more than {_MAX_EXPANDED_NODES} values"


def _normalize_surrogates(value):
    """Decode well-formed UTF-16 surrogate pairs and reject leftover surrogates."""
    if not any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        return value
    try:
        # A successful UTF-16 decode has already replaced pairs with real characters.
        return value.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeDecodeError:
        raise ValueError("Unpaired Unicode surrogates are not supported") from None


def _read_text(path):
    """Read input as UTF-8, ignoring one leading BOM (common in Windows editors)."""
    return path.read_text(encoding="utf-8-sig")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate mapping key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite number is not supported: {value}")


class _StrictLoader(yaml.SafeLoader):
    """Check keys before Python can collapse distinct YAML keys.

    Documents without a version directive, and ``%YAML 1.1``, use PyYAML's
    YAML 1.1 resolvers (via SafeLoader). ``%YAML 1.2`` uses ``_Strict12Loader``.
    """

    def construct_object(self, node, deep=False):
        if node.tag in ("tag:yaml.org,2002:omap", "tag:yaml.org,2002:pairs"):
            raise ValueError("YAML ordered-map and pairs tags are not supported")
        return super().construct_object(node, deep=deep)

    def construct_yaml_str(self, node):
        # PyYAML leaves "\\uD800\\uDC00" as two surrogates. JSON combines them.
        return _normalize_surrogates(self.construct_scalar(node))

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("Expected a YAML mapping")
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise ValueError("YAML merge keys are not supported; expand the mapping first")
            if key_node.tag != "tag:yaml.org,2002:str":
                raise ValueError("YAML mapping keys must be strings; quote scalar keys")
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError("YAML mapping keys must be strings; quote scalar keys")
            if key in result:
                raise ValueError(f"Duplicate mapping key: {key!r}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


_StrictLoader.add_constructor("tag:yaml.org,2002:str", _StrictLoader.construct_yaml_str)


class _Strict12Loader(_StrictLoader):
    """YAML 1.2 Core schema. PyYAML would otherwise keep applying 1.1 types."""

    def resolve(self, kind, value, implicit):
        if kind is yaml.ScalarNode:
            if implicit[0]:
                if _YAML12_BOOL.match(value):
                    return "tag:yaml.org,2002:bool"
                if _YAML12_NULL.match(value):
                    return "tag:yaml.org,2002:null"
                if _YAML12_INT.match(value):
                    return "tag:yaml.org,2002:int"
                if _YAML12_FLOAT.match(value):
                    return "tag:yaml.org,2002:float"
            return "tag:yaml.org,2002:str"
        if kind is yaml.SequenceNode:
            return "tag:yaml.org,2002:seq"
        if kind is yaml.MappingNode:
            return "tag:yaml.org,2002:map"
        return super().resolve(kind, value, implicit)

    def construct_yaml_int(self, node):
        # PyYAML treats every leading zero as octal, so "012" would become 10.
        # In YAML 1.2 that scalar is decimal 12; only the 0o/0x spellings change base.
        raw = self.construct_scalar(node)
        if re.fullmatch(r"[-+]?[0-9]+", raw):
            return int(raw, 10)
        if re.fullmatch(r"0o[0-7]+", raw):
            return int(raw[2:], 8)
        if re.fullmatch(r"0x[0-9a-fA-F]+", raw):
            return int(raw[2:], 16)
        raise ValueError(f"Invalid YAML 1.2 integer: {raw!r}")


_Strict12Loader.add_constructor("tag:yaml.org,2002:int", _Strict12Loader.construct_yaml_int)


def _check_value(value, active=None, sizes=None):
    """Reject values that JSON cannot represent without changing their type.

    Returns how many nodes the value contributes after alias expansion. A shared
    object is measured once and then reused, so an alias bomb fails immediately
    instead of walking an exponential tree.
    """
    if isinstance(value, str):
        _normalize_surrogates(value)
        return 1
    if value is None or isinstance(value, (bool, int)):
        return 1
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not supported")
        return 1
    if not isinstance(value, (list, dict)):
        raise ValueError(f"Value type is not JSON-compatible: {type(value).__name__}")
    if active is None:
        active = set()
        sizes = {}
    identity = id(value)
    if identity in active:
        raise ValueError("Recursive YAML aliases are not supported")
    cached = sizes.get(identity)
    if cached is not None:
        return cached
    active.add(identity)
    count = 1
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                count += _check_value(key, active, sizes)
                if count > _MAX_EXPANDED_NODES:
                    raise ValueError(_too_large())
                count += _check_value(item, active, sizes)
                if count > _MAX_EXPANDED_NODES:
                    raise ValueError(_too_large())
        else:
            for item in value:
                count += _check_value(item, active, sizes)
                if count > _MAX_EXPANDED_NODES:
                    raise ValueError(_too_large())
    finally:
        active.remove(identity)
    sizes[identity] = count
    return count


def _load_json(content):
    data = json.loads(content, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    _check_value(data)
    return data


def _select_yaml_loader(content):
    """Pick a loader from the %YAML directive without scanning the whole body."""
    version = None
    try:
        for token in yaml.scan(content, Loader=yaml.SafeLoader):
            if isinstance(token, yaml.StreamStartToken):
                continue
            if isinstance(token, yaml.DirectiveToken):
                if token.name == "YAML":
                    if version is not None:
                        raise ValueError("A YAML stream may contain only one %YAML directive")
                    version = token.value
                continue
            break
    except yaml.YAMLError:
        return _StrictLoader
    if version is None or version == (1, 1):
        return _StrictLoader
    if version == (1, 2):
        return _Strict12Loader
    major, minor = version
    raise ValueError(f"Unsupported YAML version: {major}.{minor}")


def _load_yaml(content):
    try:
        data = yaml.load(content, Loader=_select_yaml_loader(content))
    except (IndexError, KeyError, AttributeError, TypeError, OverflowError) as error:
        # SafeLoader can raise these for malformed, explicitly tagged scalars.
        raise ValueError(f"Invalid YAML value: {error}") from error
    _check_value(data)
    return data


def _check_output(input_path, output_path):
    """Give a useful early error; publication also checks the destination atomically."""
    try:
        output_path.lstat()
    except FileNotFoundError:
        return
    try:
        if os.path.samefile(input_path, output_path):
            raise ValueError("Input and output must be different files")
    except FileNotFoundError:
        pass
    raise FileExistsError(f"Output already exists; choose a new path: {output_path}")


def _write_new(output_path, content):
    # Serialize/encode before opening any output. A hard link publishes the complete
    # file atomically and cannot replace a file created after the initial check.
    encoded = content.encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".json-yaml-", dir=output_path.parent)
    published = False
    try:
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output_path)
            published = True
        except FileExistsError:
            raise FileExistsError(
                f"Output already exists; choose a new path: {output_path}"
            ) from None
    finally:
        try:
            os.unlink(temporary)
        except OSError as error:
            if published:
                raise OSError(
                    f"Output was created at {output_path}, but temporary file "
                    f"cleanup failed: {temporary} ({error})"
                ) from error
            raise


def json_to_yaml(input_path: str, output_path: str) -> str:
    """Convert strict JSON to YAML, refusing to replace any existing output."""
    source, target = Path(input_path), Path(output_path)
    _check_output(source, target)
    data = _load_json(_read_text(source))
    result = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    _write_new(target, result)
    return result


def yaml_to_json(input_path: str, output_path: str, indent: int = 2) -> str:
    """Convert JSON-compatible YAML to JSON without replacing existing output."""
    source, target = Path(input_path), Path(output_path)
    _check_output(source, target)
    data = _load_yaml(_read_text(source))
    result = json.dumps(data, indent=indent, ensure_ascii=False, allow_nan=False)
    _write_new(target, result)
    return result


def validate_file(file_path: str) -> Dict:
    """Check the same strict data model used by conversion, without writing files."""
    path = Path(file_path)
    try:
        content = _read_text(path)
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            _load_yaml(content)
            detected = "yaml"
        elif suffix == ".json":
            _load_json(content)
            detected = "json"
        else:
            try:
                _load_json(content)
                detected = "json"
            except json.JSONDecodeError:
                _load_yaml(content)
                detected = "yaml"
        return {"is_valid": True, "format_detected": detected, "error_message": None}
    except (OSError, ValueError, RecursionError, yaml.YAMLError) as error:
        return {
            "is_valid": False,
            "format_detected": None,
            "error_message": str(error),
        }
