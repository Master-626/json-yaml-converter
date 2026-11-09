"""Strict JSON/YAML conversion with non-destructive output publication."""

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Dict

import yaml


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
    """Check keys before Python can collapse distinct YAML keys."""

    def construct_object(self, node, deep=False):
        if node.tag in ("tag:yaml.org,2002:omap", "tag:yaml.org,2002:pairs"):
            raise ValueError("YAML ordered-map and pairs tags are not supported")
        return super().construct_object(node, deep=deep)

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
            if key in result:
                raise ValueError(f"Duplicate mapping key: {key!r}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _check_value(value, active=None):
    """Reject values that JSON cannot represent without changing their type."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Unpaired Unicode surrogates are not supported") from None
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not supported")
        return
    if not isinstance(value, (list, dict)):
        raise ValueError(f"Value type is not JSON-compatible: {type(value).__name__}")
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        raise ValueError("Recursive YAML aliases are not supported")
    active.add(identity)
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                _check_value(key, active)
                _check_value(item, active)
        else:
            for item in value:
                _check_value(item, active)
    finally:
        active.remove(identity)


def _load_json(content):
    data = json.loads(content, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    _check_value(data)
    return data


def _load_yaml(content):
    try:
        data = yaml.load(content, Loader=_StrictLoader)
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
    data = _load_json(source.read_text(encoding="utf-8"))
    result = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    _write_new(target, result)
    return result


def yaml_to_json(input_path: str, output_path: str, indent: int = 2) -> str:
    """Convert JSON-compatible YAML to JSON without replacing existing output."""
    source, target = Path(input_path), Path(output_path)
    _check_output(source, target)
    data = _load_yaml(source.read_text(encoding="utf-8"))
    result = json.dumps(data, indent=indent, ensure_ascii=False, allow_nan=False)
    _write_new(target, result)
    return result


def validate_file(file_path: str) -> Dict:
    """Check the same strict data model used by conversion, without writing files."""
    path = Path(file_path)
    try:
        content = path.read_text(encoding="utf-8")
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
