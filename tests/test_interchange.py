"""Edge cases where the strict model used to misread or hang on real input."""

import json
import math
import time

import pytest
import yaml

from json_yaml_converter import converter


def _convert(tmp_path, content, name="input.yaml"):
    source, target = tmp_path / name, tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    return converter.yaml_to_json(source, target)


def test_yaml11_scalars_stay_on_pyyaml_rules():
    assert converter._load_yaml("yes\n") is True
    assert converter._load_yaml("%YAML 1.1\n---\nyes\n") is True
    assert converter._load_yaml("012\n") == 10
    assert converter._load_yaml("0o12\n") == "0o12"
    assert converter._load_yaml("0b101\n") == 5
    assert converter._load_yaml("1_000\n") == 1000
    assert converter._load_yaml("1:2:3\n") == 3723
    assert converter._load_yaml("n: 1e2\n") == {"n": "1e2"}
    with pytest.raises(ValueError, match="date"):
        converter._load_yaml("2026-01-01\n")
    with pytest.raises(ValueError, match="merge keys"):
        converter._load_yaml("<<: {a: 1}\n")
    with pytest.raises(ValueError, match="must be strings"):
        converter._load_yaml("yes: 1\n")


@pytest.mark.parametrize(
    "content,expected",
    [
        ("yes\n", "yes"),
        ("no\n", "no"),
        ("on\n", "on"),
        ("off\n", "off"),
        ("true\n", True),
        ("TRUE\n", True),
        ("false\n", False),
        ("null\n", None),
        ("~\n", None),
        ("\n", None),
        ("''\n", ""),
        ("012\n", 12),
        ("-012\n", -12),
        ("0o12\n", 10),
        ("0x3A\n", 58),
        ("0b101\n", "0b101"),
        ("1_000\n", "1_000"),
        ("1:2:3\n", "1:2:3"),
        ("2026-01-01\n", "2026-01-01"),
        ("0.\n", 0.0),
        (".5\n", 0.5),
        ("+12e03\n", 12000.0),
        ("-2E+05\n", -200000.0),
    ],
)
def test_yaml12_core_schema(content, expected):
    loaded = converter._load_yaml("%YAML 1.2\n---\n" + content)
    assert loaded == expected
    if isinstance(expected, float):
        assert isinstance(loaded, float)


def test_yaml12_distinguishes_bool_int_and_string_keys(tmp_path):
    text = _convert(
        tmp_path,
        "%YAML 1.2\n---\n"
        "yes: 1\n"
        "numbers:\n"
        "  plain: 012\n"
        "  scientific: 1e2\n"
        "  negative_zero: -0.0\n"
        "merge:\n"
        "  <<: {a: 1}\n"
        "  b: 2\n",
    )
    loaded = json.loads(text)
    assert loaded["yes"] == 1
    assert loaded["numbers"]["plain"] == 12
    assert loaded["numbers"]["scientific"] == 100.0
    assert loaded["numbers"]["negative_zero"] == 0.0
    assert math.copysign(1.0, loaded["numbers"]["negative_zero"]) == -1.0
    assert loaded["merge"] == {"<<": {"a": 1}, "b": 2}


def test_yaml12_nonfinite_and_unknown_versions_write_nothing(tmp_path):
    source, target = tmp_path / "input.yaml", tmp_path / "output"
    source.write_text("%YAML 1.2\n---\n1e309\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Non-finite"):
        converter.yaml_to_json(source, target)
    source.write_text("%YAML 1.3\n---\na: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported YAML version: 1.3"):
        converter.yaml_to_json(source, target)
    source.write_text("%YAML 1.2\n%YAML 1.1\n---\na: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only one %YAML"):
        converter.yaml_to_json(source, target)
    assert not target.exists()
    assert not converter.validate_file(source)["is_valid"]


def test_yaml12_sequences_and_explicit_integers():
    assert converter._load_yaml("%YAML 1.2\n---\n[yes, 012, '012']\n") == ["yes", 12, "012"]
    assert converter._load_yaml('%YAML 1.2\n---\n!!int "012"\n') == 12
    with pytest.raises(ValueError, match="Invalid YAML 1.2 integer"):
        converter._load_yaml('%YAML 1.2\n---\n!!int "0b101"\n')


def test_non_yaml_directive_and_scanner_errors_stay_clean():
    assert converter._load_yaml("%TAG ! tag:example.com,2000:app/\n---\na: 1\n") == {"a": 1}
    with pytest.raises(yaml.YAMLError):
        converter._load_yaml("%\n")


def test_yaml12_directive_after_comment_and_blank_line():
    loaded = converter._load_yaml("# generated\n\n%YAML 1.2\n---\nn: 012\n")
    assert loaded == {"n": 12}


def test_loader_registration_does_not_change_pyyaml():
    assert yaml.safe_load("yes") is True
    assert yaml.safe_load("012") == 10
    assert yaml.safe_load('"\\uD800\\uDC00"') == "\ud800\udc00"


def test_utf8_bom_is_ignored(tmp_path):
    json_source = tmp_path / "bom.json"
    yaml_source = tmp_path / "bom.yaml"
    json_out, yaml_out = tmp_path / "from-json.yaml", tmp_path / "from-yaml.json"
    json_source.write_bytes(b'\xef\xbb\xbf{"name": "\xe6\xba\x90"}\n')
    yaml_source.write_bytes(b"\xef\xbb\xbf%YAML 1.2\n---\nyes: '\xe6\xba\x90'\n")
    assert converter.validate_file(json_source)["is_valid"]
    assert converter.validate_file(yaml_source)["format_detected"] == "yaml"
    dumped = converter.json_to_yaml(json_source, json_out)
    assert converter._load_yaml(dumped) == {"name": "源"}
    assert json.loads(converter.yaml_to_json(yaml_source, yaml_out)) == {"yes": "源"}
    only_bom = tmp_path / "empty.yaml"
    only_bom.write_bytes(b"\xef\xbb\xbf")
    assert converter.validate_file(only_bom) == {
        "is_valid": True,
        "format_detected": "yaml",
        "error_message": None,
    }
    bare_bom_json = tmp_path / "empty.json"
    bare_bom_json.write_bytes(b"\xef\xbb\xbf")
    assert not converter.validate_file(bare_bom_json)["is_valid"]


def test_surrogate_pairs_round_trip_and_unpaired_still_fail(tmp_path):
    character = "\U00010000"
    source, target = tmp_path / "input.yaml", tmp_path / "output"
    source.write_text('"\\uD800\\uDC00"\n', encoding="utf-8")
    assert json.loads(converter.yaml_to_json(source, target)) == character
    key_file, key_out = tmp_path / "key.yaml", tmp_path / "key.json"
    key_file.write_text('"\\uD800\\uDC00": "\\uD83D\\uDE00"\n', encoding="utf-8")
    assert json.loads(converter.yaml_to_json(key_file, key_out)) == {character: "😀"}
    duplicate = tmp_path / "dup.yaml"
    duplicate.write_text(f'"\\uD800\\uDC00": 1\n"{character}": 2\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate mapping key"):
        converter.yaml_to_json(duplicate, tmp_path / "dup.json")
    json_source = tmp_path / "pair.json"
    json_source.write_text('"\\uD800\\uDC00"', encoding="utf-8")
    yaml_text = converter.json_to_yaml(json_source, tmp_path / "pair.yaml")
    assert converter._load_yaml(yaml_text) == character
    for content in ('"\\ud800"', '{"x": "\\udfff"}', '"\\uD800\\uDC00\\uD800"'):
        bad = tmp_path / "bad.yaml"
        bad.write_text(content + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="surrogates"):
            converter.yaml_to_json(bad, tmp_path / "bad-out")


def test_alias_expansion_limit_counts_each_use(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "_MAX_EXPANDED_NODES", 8)
    small, small_out = tmp_path / "small.yaml", tmp_path / "small.json"
    small.write_text("a: &a [1]\nb: *a\n", encoding="utf-8")
    assert json.loads(converter.yaml_to_json(small, small_out)) == {
        "a": [1],
        "b": [1],
    }
    boundary = tmp_path / "boundary.yaml"
    boundary.write_text("a: [1]\nb: 1\n", encoding="utf-8")
    monkeypatch.setattr(converter, "_MAX_EXPANDED_NODES", 4)
    with pytest.raises(ValueError, match="expands to more than 4"):
        converter.yaml_to_json(boundary, tmp_path / "boundary.json")
    monkeypatch.setattr(converter, "_MAX_EXPANDED_NODES", 8)
    large = tmp_path / "large.yaml"
    large.write_text("a: &a [1, 2]\nb: *a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expands to more than 8"):
        converter.yaml_to_json(large, tmp_path / "large.json")
    assert not (tmp_path / "large.json").exists()


def test_alias_bomb_is_rejected_quickly(tmp_path):
    lines = ["a0: &a0 [1]"]
    for level in range(1, 12):
        refs = ", ".join([f"*a{level - 1}"] * 10)
        lines.append(f"a{level}: &a{level} [{refs}]")
    lines.append("top: *a11")
    source, target = tmp_path / "bomb.yaml", tmp_path / "bomb.json"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    started = time.perf_counter()
    with pytest.raises(ValueError, match="expands to more than 1000000"):
        converter.yaml_to_json(source, target)
    assert time.perf_counter() - started < 1
    assert not target.exists()
    assert not converter.validate_file(source)["is_valid"]
