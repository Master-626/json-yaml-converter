import json

import pytest
from click.testing import CliRunner

from json_yaml_converter import __version__
from json_yaml_converter.cli import json_to_yaml_cmd, main, yaml_to_json_cmd


@pytest.mark.parametrize("command", ["json-to-yaml", "yaml-to-json"])
def test_cli_conversion_and_no_clobber(tmp_path, command):
    source, target = tmp_path / "input", tmp_path / "output"
    source.write_text('{"x": 1}', encoding="utf-8")
    runner = CliRunner()
    args = [command, "-i", str(source), "-o", str(target)]
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    assert "Converted:" in result.output
    original = target.read_bytes()
    result = runner.invoke(main, args)
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert "Converted:" not in result.output
    assert "Traceback" not in result.output
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "command,content",
    [
        ("json-to-yaml", "{"),
        ("json-to-yaml", '{"x":1,"x":2}'),
        ("yaml-to-json", "x: ["),
        ("yaml-to-json", "true: a\n1: b"),
        ("yaml-to-json", "x: .nan"),
    ],
)
def test_cli_bad_data_exits_nonzero_without_output(tmp_path, command, content):
    source, target = tmp_path / "input", tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(main, [command, "-i", str(source), "-o", str(target)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output
    assert not target.exists()


def test_cli_input_output_same_file(tmp_path):
    source = tmp_path / "input"
    source.write_text('{"x":1}', encoding="utf-8")
    result = CliRunner().invoke(main, ["json-to-yaml", "-i", str(source), "-o", str(source)])
    assert result.exit_code == 1
    assert "different files" in result.output
    assert source.read_text(encoding="utf-8") == '{"x":1}'


@pytest.mark.parametrize("content,code", [('{"x":1}', 0), ('{"x":1,"x":2}', 1), ("x: 1", 1)])
def test_cli_validate_exit_status(tmp_path, content, code):
    source = tmp_path / "input.json"
    source.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(main, ["validate", "-f", str(source)])
    assert result.exit_code == code
    assert ("Valid JSON" if code == 0 else "Invalid:") in result.output


def test_cli_missing_input(tmp_path):
    result = CliRunner().invoke(
        main, ["json-to-yaml", "-i", str(tmp_path / "missing"), "-o", str(tmp_path / "out")]
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output


def test_cli_json_indent_and_compact(tmp_path):
    source = tmp_path / "input.yaml"
    source.write_text("a: 1\n", encoding="utf-8")
    runner = CliRunner()
    default, pretty, compact, newlines = (
        tmp_path / "default.json",
        tmp_path / "pretty.json",
        tmp_path / "compact.json",
        tmp_path / "newlines.json",
    )
    assert (
        runner.invoke(main, ["yaml-to-json", "-i", str(source), "-o", str(default)]).exit_code == 0
    )
    assert default.read_text(encoding="utf-8") == '{\n  "a": 1\n}'
    args = ["yaml-to-json", "-i", str(source), "-o", str(pretty), "--indent", "4"]
    assert runner.invoke(main, args).exit_code == 0
    assert pretty.read_text(encoding="utf-8") == '{\n    "a": 1\n}'
    assert (
        runner.invoke(
            yaml_to_json_cmd, ["-i", str(source), "-o", str(compact), "--compact"]
        ).exit_code
        == 0
    )
    assert compact.read_text(encoding="utf-8") == '{"a": 1}'
    zero = runner.invoke(
        yaml_to_json_cmd, ["-i", str(source), "-o", str(newlines), "--indent", "0"]
    )
    assert zero.exit_code == 0
    assert newlines.read_text(encoding="utf-8") == '{\n"a": 1\n}'
    conflict = runner.invoke(
        main,
        [
            "yaml-to-json",
            "-i",
            str(source),
            "-o",
            str(tmp_path / "nope"),
            "--compact",
            "--indent",
            "4",
        ],
    )
    assert conflict.exit_code == 2
    assert "not both" in conflict.output
    assert not (tmp_path / "nope").exists()
    negative = runner.invoke(
        main, ["yaml-to-json", "-i", str(source), "-o", str(tmp_path / "neg"), "--indent", "-1"]
    )
    assert negative.exit_code != 0
    assert not (tmp_path / "neg").exists()


def test_version_and_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    result = runner.invoke(main, ["json-to-yaml", "--help"])
    assert result.exit_code == 0
    assert "must not exist" in result.output


def test_standalone_commands(tmp_path):
    source, intermediate, target = [tmp_path / s for s in ("input", "yaml", "json")]
    source.write_text('{"x":1}', encoding="utf-8")
    runner = CliRunner()
    assert (
        runner.invoke(json_to_yaml_cmd, ["-i", str(source), "-o", str(intermediate)]).exit_code == 0
    )
    assert (
        runner.invoke(yaml_to_json_cmd, ["-i", str(intermediate), "-o", str(target)]).exit_code == 0
    )
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}


@pytest.mark.parametrize(
    "content", ["!!int ''", "!!float ''", "!!bool nonsense", "!!timestamp nonsense", '"\\ud800"']
)
def test_cli_bad_explicit_yaml_scalar_has_clean_error(tmp_path, content):
    source, target = tmp_path / "input.yaml", tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    for args in [
        ["yaml-to-json", "-i", str(source), "-o", str(target)],
        ["validate", "-f", str(source)],
    ]:
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Traceback" not in result.output
    assert not target.exists()


def test_module_entrypoint(monkeypatch, capsys):
    import runpy
    import sys

    monkeypatch.delitem(sys.modules, "json_yaml_converter.cli")
    monkeypatch.setattr(sys, "argv", ["json-yaml", "--version"])
    with pytest.raises(SystemExit) as error:
        runpy.run_module("json_yaml_converter.cli", run_name="__main__")
    assert error.value.code == 0
    assert __version__ in capsys.readouterr().out
