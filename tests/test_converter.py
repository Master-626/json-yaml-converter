import pytest
import json
import yaml
from pathlib import Path
from json_yaml_converter.converter import json_to_yaml, yaml_to_json, validate_file


def test_json_to_yaml(tmp_path):
    """Test JSON to YAML conversion."""
    data = {"name": "test", "version": "1.0", "items": [1, 2, 3]}

    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(data))

    output_file = tmp_path / "output.yaml"
    json_to_yaml(str(input_file), str(output_file))

    assert output_file.exists()
    loaded = yaml.safe_load(output_file.read_text())
    assert loaded == data


def test_yaml_to_json(tmp_path):
    """Test YAML to JSON conversion."""
    data = {"name": "test", "version": "1.0", "items": [1, 2, 3]}

    input_file = tmp_path / "input.yaml"
    input_file.write_text(yaml.dump(data))

    output_file = tmp_path / "output.json"
    yaml_to_json(str(input_file), str(output_file))

    assert output_file.exists()
    loaded = json.loads(output_file.read_text())
    assert loaded == data


def test_validate_json(tmp_path):
    """Test JSON validation."""
    input_file = tmp_path / "test.json"
    input_file.write_text('{"name": "test"}')

    result = validate_file(str(input_file))
    assert result["is_valid"] is True
    assert result["format_detected"] == "json"


def test_validate_yaml(tmp_path):
    """Test YAML validation."""
    input_file = tmp_path / "test.yaml"
    input_file.write_text("name: test\nversion: 1.0")

    result = validate_file(str(input_file))
    assert result["is_valid"] is True
    assert result["format_detected"] == "yaml"


def test_validate_missing_file():
    """Test validation of missing file."""
    result = validate_file("does_not_exist.json")
    assert result["is_valid"] is False
