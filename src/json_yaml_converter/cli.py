"""Command-line interface for json-yaml-converter."""

import click
import yaml

from . import __version__
from .converter import json_to_yaml, validate_file, yaml_to_json


def _convert(converter, input, output):
    try:
        converter(input, output)
    except (OSError, ValueError, TypeError, RecursionError, yaml.YAMLError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Converted: {input} -> {output}")


@click.group()
@click.version_option(version=__version__)
def main():
    """JSON YAML Converter - Convert between JSON and YAML formats."""


@main.command("json-to-yaml")
@click.option("-i", "--input", required=True, help="Input JSON file")
@click.option("-o", "--output", required=True, help="New output YAML file (must not exist)")
def json_to_yaml_cmd(input, output):
    """Convert JSON to YAML without overwriting files."""
    _convert(json_to_yaml, input, output)


@main.command("yaml-to-json")
@click.option("-i", "--input", required=True, help="Input YAML file")
@click.option("-o", "--output", required=True, help="New output JSON file (must not exist)")
def yaml_to_json_cmd(input, output):
    """Convert JSON-compatible YAML to JSON without overwriting files."""
    _convert(yaml_to_json, input, output)


@main.command()
@click.option("-f", "--file", required=True, help="File to validate")
def validate(file):
    """Validate a file against the converter's strict data model."""
    result = validate_file(file)
    if not result["is_valid"]:
        raise click.ClickException(f"Invalid: {result['error_message']}")
    click.echo(f"Valid {result['format_detected'].upper()} file")


if __name__ == "__main__":
    main()
