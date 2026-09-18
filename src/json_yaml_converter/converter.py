"""
Core JSON/YAML conversion logic.
"""

import json
from pathlib import Path
from typing import Dict, Optional

import yaml


def json_to_yaml(input_path: str, output_path: str) -> str:
    """Convert JSON file to YAML."""
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
    Path(output_path).write_text(yaml_str, encoding="utf-8")
    return yaml_str


def yaml_to_json(input_path: str, output_path: str, indent: int = 2) -> str:
    """Convert YAML file to JSON."""
    data = yaml.safe_load(Path(input_path).read_text(encoding="utf-8"))
    json_str = json.dumps(data, indent=indent, ensure_ascii=False)
    Path(output_path).write_text(json_str, encoding="utf-8")
    return json_str


def validate_file(file_path: str) -> Dict:
    """Validate if file is valid JSON or YAML."""
    path = Path(file_path)

    if not path.exists():
        return {
            "is_valid": False,
            "format_detected": None,
            "error_message": "File does not exist",
        }

    content = path.read_text(encoding="utf-8")

    # Try JSON
    try:
        json.loads(content)
        return {
            "is_valid": True,
            "format_detected": "json",
            "error_message": None,
        }
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        yaml.safe_load(content)
        return {
            "is_valid": True,
            "format_detected": "yaml",
            "error_message": None,
        }
    except yaml.YAMLError as e:
        return {
            "is_valid": False,
            "format_detected": None,
            "error_message": str(e),
        }
