# JSON YAML Converter

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![DevOps Friendly](https://img.shields.io/badge/devops-friendly-blue.svg)]()

Convert between JSON and YAML formats from the command line. Used by DevOps engineers, backend developers, and configuration managers worldwide.

## 🌟 Features

- 🔄 **JSON → YAML** - Convert JSON files to YAML format
- 🔄 **YAML → JSON** - Convert YAML files to JSON format
- ✅ **Validation** - Validate if a file is valid JSON or YAML
- 🚀 **Fast** - Quick conversion for configuration files
- 🐍 **Python API** - Use as a library in your code

## 📦 Installation

```bash
git clone https://github.com/Master-626/json-yaml-converter.git
cd json-yaml-converter
pip install .
```

## 🚀 Usage

### Convert JSON to YAML
```bash
json-yaml json-to-yaml -i config.json -o config.yaml
```

### Convert YAML to JSON
```bash
json-yaml yaml-to-json -i config.yaml -o config.json
```

### Validate File
```bash
# Auto-detect if it's JSON or YAML
json-yaml validate -f config.json
json-yaml validate -f config.yaml
```

## 🐍 Python API

```python
from json_yaml_converter import json_to_yaml, yaml_to_json, validate_file

# Convert JSON to YAML
json_to_yaml("input.json", "output.yaml")

# Convert YAML to JSON
yaml_to_json("input.yaml", "output.json")

# Validate file
result = validate_file("config.yaml")
print(f"Valid: {result['is_valid']}, Format: {result['format_detected']}")
```

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT License
