"""
CLI interface for json-yaml-converter.
"""

import click
from rich.console import Console

from .converter import json_to_yaml, yaml_to_json, validate_file

console = Console()


@click.group()
@click.version_option()
def main():
    """JSON YAML Converter - Convert between JSON and YAML formats."""
    pass


@main.command("json-to-yaml")
@click.option("-i", "--input", required=True, help="Input JSON file")
@click.option("-o", "--output", required=True, help="Output YAML file")
def json_to_yaml_cmd(input, output):
    """Convert JSON file to YAML."""
    json_to_yaml(input, output)
    console.print(f"✅ Converted: {input} -> {output}")


@main.command("yaml-to-json")
@click.option("-i", "--input", required=True, help="Input YAML file")
@click.option("-o", "--output", required=True, help="Output JSON file")
def yaml_to_json_cmd(input, output):
    """Convert YAML file to JSON."""
    yaml_to_json(input, output)
    console.print(f"✅ Converted: {input} -> {output}")


@main.command()
@click.option("-f", "--file", required=True, help="File to validate")
def validate(file):
    """Validate if file is valid JSON or YAML."""
    result = validate_file(file)

    if result["is_valid"]:
        console.print(f"✅ Valid {result['format_detected'].upper()} file")
    else:
        console.print(f"❌ Invalid: {result['error_message']}")


if __name__ == "__main__":
    main()
