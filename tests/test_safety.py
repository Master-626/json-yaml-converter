"""Regressions for output publication and lossy mapping construction."""

import errno
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from json_yaml_converter import converter


def _symlink(link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except (NotImplementedError, OSError) as error:
        if isinstance(error, NotImplementedError) or getattr(error, "winerror", None) == 1314:
            pytest.skip(f"Platform does not permit symlinks: {error}")
        raise


@pytest.fixture(params=[converter.json_to_yaml, converter.yaml_to_json])
def conversion(request, tmp_path):
    source = tmp_path / "source"
    content = '{"name": "源数据", "n": 7}'
    source.write_text(content, encoding="utf-8")
    return request.param, source, content


def test_existing_file_is_unchanged(conversion, tmp_path):
    convert, source, original = conversion
    target = tmp_path / "target"
    target.write_bytes(b"KEEP ORIGINAL")
    with pytest.raises(FileExistsError, match="already exists"):
        convert(source, target)
    assert source.read_text(encoding="utf-8") == original
    assert target.read_bytes() == b"KEEP ORIGINAL"
    assert not list(tmp_path.glob(".json-yaml-*"))


@pytest.mark.parametrize("alias", ["same", "relative", "hardlink", "symlink", "parent_symlink"])
def test_input_alias_is_unchanged(conversion, tmp_path, alias, monkeypatch):
    convert, source, original = conversion
    target = tmp_path / "target"
    if alias == "same":
        target = source
    elif alias == "relative":
        monkeypatch.chdir(tmp_path)
        target = "source"
    elif alias == "hardlink":
        os.link(source, target)
    elif alias == "symlink":
        _symlink(target, source)
    else:
        parent = tmp_path / "parent"
        _symlink(parent, tmp_path, target_is_directory=True)
        target = parent / "source"
    with pytest.raises(ValueError, match="different files"):
        convert(source, target)
    assert source.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("kind", ["dangling_symlink", "unrelated_symlink", "directory"])
def test_other_existing_destinations_are_untouched(conversion, tmp_path, kind):
    convert, source, _ = conversion
    target = tmp_path / "target"
    other = tmp_path / "other"
    if kind == "directory":
        target.mkdir()
    else:
        if kind == "unrelated_symlink":
            other.write_text("KEEP", encoding="utf-8")
        _symlink(target, other)
    with pytest.raises(FileExistsError):
        convert(source, target)
    if kind == "directory":
        assert target.is_dir()
    else:
        assert target.is_symlink()
        if kind == "unrelated_symlink":
            assert other.read_text(encoding="utf-8") == "KEEP"
        else:
            assert not other.exists()


@pytest.mark.parametrize("kind", ["file", "hardlink", "symlink", "dangling_symlink"])
def test_destination_created_during_conversion_is_preserved(
    conversion, tmp_path, monkeypatch, kind
):
    convert, source, original = conversion
    target = tmp_path / "target"
    real_link = os.link

    def raced_link(staged, destination):
        assert not target.exists()
        if kind == "file":
            target.write_text("RACE WINNER", encoding="utf-8")
        elif kind == "hardlink":
            real_link(source, target)
        elif kind == "symlink":
            _symlink(target, source)
        else:
            _symlink(target, tmp_path / "missing")
        return real_link(staged, destination)

    monkeypatch.setattr(converter.os, "link", raced_link)
    with pytest.raises(FileExistsError, match="already exists"):
        convert(source, target)
    assert source.read_text(encoding="utf-8") == original
    if kind == "file":
        assert target.read_text(encoding="utf-8") == "RACE WINNER"
    elif kind == "dangling_symlink":
        assert target.is_symlink() and not target.exists()
    else:
        assert target.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".json-yaml-*"))


@pytest.mark.parametrize("phase", ["stage", "write", "flush", "sync", "link"])
def test_output_failures_leave_no_partial_target(conversion, tmp_path, monkeypatch, phase):
    convert, source, original = conversion
    target = tmp_path / "target"

    def fail(*args, **kwargs):
        raise OSError(errno.EIO, "injected failure")

    if phase == "stage":
        monkeypatch.setattr(converter.tempfile, "mkstemp", fail)
    elif phase == "sync":
        monkeypatch.setattr(converter.os, "fsync", fail)
    elif phase == "link":
        monkeypatch.setattr(converter.os, "link", fail)
    else:
        real_fdopen = os.fdopen

        class FailingStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def write(self, data):
                self.stream.write(data[:3])
                if phase == "write":
                    fail()

            def flush(self):
                fail()

        monkeypatch.setattr(converter.os, "fdopen", lambda *a: FailingStream(real_fdopen(*a)))
    with pytest.raises(OSError, match="injected failure"):
        convert(source, target)
    assert not target.exists()
    assert source.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(".json-yaml-*"))


def test_missing_output_parent_is_not_created(conversion, tmp_path):
    convert, source, _ = conversion
    target = tmp_path / "missing" / "target"
    with pytest.raises(FileNotFoundError):
        convert(source, target)
    assert not target.parent.exists()


def test_keyboard_interrupt_cleans_stage(conversion, tmp_path, monkeypatch):
    convert, source, _ = conversion
    target = tmp_path / "target"

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(converter.os, "fsync", interrupt)
    with pytest.raises(KeyboardInterrupt):
        convert(source, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".json-yaml-*"))


def test_concurrent_writers_publish_one_complete_file(tmp_path, monkeypatch):
    target = tmp_path / "target"
    sources = []
    for i in range(4):
        source = tmp_path / str(i)
        source.write_text(json.dumps({"writer": i, "data": "x" * 10000}), encoding="utf-8")
        sources.append(source)
    barrier = threading.Barrier(len(sources))
    check = converter._check_output

    def synchronized_check(*args):
        check(*args)
        barrier.wait(timeout=10)

    monkeypatch.setattr(converter, "_check_output", synchronized_check)

    def run(source):
        try:
            return converter.json_to_yaml(source, target)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, sources))
    winners = [r for r in results if r is not None]
    assert winners == [target.read_text(encoding="utf-8")]
    assert yaml.safe_load(winners[0])["data"] == "x" * 10000
    assert not list(tmp_path.glob(".json-yaml-*"))


@pytest.mark.parametrize(
    "content",
    [
        '{"x": 1, "x": 2}',
        '{"outer": [{"x": 1, "x": 2}]}',
        '{"a": 1, "\\u0061": 2}',
        '{"n": NaN}',
        '{"n": Infinity}',
        '{"n": -Infinity}',
        '{"n": 1e400}',
        '{"n": -1e400}',
        "{",
    ],
)
def test_reject_lossy_or_invalid_json(tmp_path, content):
    source, target = tmp_path / "source.json", tmp_path / "target"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        converter.json_to_yaml(source, target)
    assert not target.exists()
    assert not converter.validate_file(source)["is_valid"]
    assert source.read_text(encoding="utf-8") == content


@pytest.mark.parametrize(
    "content",
    [
        "x: first\nx: second",
        "outer:\n  - x: first\n    x: second",
        '"a": first\n"\\u0061": second',
        "true: first\n1: second",
        '1: first\n"1": second',
        'null: first\n"null": second',
        ".nan: first",
        "false: first\n0: second",
        "1: first\n1.0: second",
        "? [a, b]\n: value",
        "2026-01-01: value",
        "n: .inf",
        "n: -.inf",
        "n: .nan",
        "n: 1.0e+400",
        "date: 2026-01-01",
        "data: !!binary aGVsbG8=",
        "data: !!set {a: null}",
        "data: !!omap [{a: 1}]",
        "data: !Custom value",
        '!!python/object/apply:os.system ["echo no"]',
        "x: &x {nested: *x}",
        "x: &x [*x]",
        "defaults: &base {x: 1}\nobj: {<<: *base}",
        "x: 1\n---\nx: 2",
        "x: [",
    ],
)
def test_reject_lossy_or_unsupported_yaml(tmp_path, content):
    source, target = tmp_path / "source.yaml", tmp_path / "target"
    source.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, yaml.YAMLError)):
        converter.yaml_to_json(source, target)
    assert not target.exists()
    assert not converter.validate_file(source)["is_valid"]
    assert source.read_text(encoding="utf-8") == content


@pytest.mark.parametrize(
    "data",
    [
        None,
        True,
        False,
        42,
        1.25,
        "你好",
        [],
        {},
        [1, "x"],
        {"false": "no", "1": 1, "null": None, "on": "yes", "<<": "literal", "é": "值"},
        {"a": {"x": 1}, "b": {"x": 2}},
        {"big": 123456789012345678901234567890},
    ],
)
def test_roundtrip_json_compatible_values(tmp_path, data):
    source, intermediate, target = [tmp_path / p for p in ("in.json", "out.yaml", "out.json")]
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    yaml_result = converter.json_to_yaml(source, intermediate)
    json_result = converter.yaml_to_json(intermediate, target, indent=4)
    assert intermediate.read_text(encoding="utf-8") == yaml_result
    assert target.read_text(encoding="utf-8") == json_result
    assert json.loads(json_result) == data
    assert converter.validate_file(source)["is_valid"]
    assert converter.validate_file(intermediate)["is_valid"]
    assert converter.validate_file(target)["is_valid"]


def test_acyclic_aliases_are_supported(tmp_path):
    source, target = tmp_path / "source.yaml", tmp_path / "target"
    source.write_text("a: &a {x: [1, 2]}\nb: *a\nc: *a", encoding="utf-8")
    assert json.loads(converter.yaml_to_json(source, target)) == {
        "a": {"x": [1, 2]},
        "b": {"x": [1, 2]},
        "c": {"x": [1, 2]},
    }


@pytest.mark.parametrize(
    "suffix,content,valid,detected",
    [
        (".JSON", "name: value", False, None),
        (".json", "", False, None),
        (".yaml", "", True, "yaml"),
        (".yml", "null", True, "yaml"),
        (".yaml", '{"x": 1}', True, "yaml"),
        (".txt", '{"x": 1}', True, "json"),
        ("", "x: 1", True, "yaml"),
        (".txt", '{"x": 1, "x": 2}', False, None),
        (".txt", '{"x": NaN}', False, None),
        (".txt", '{"x": 1e400}', False, None),
    ],
)
def test_validation_respects_format_and_cannot_bypass_strict_json(
    tmp_path, suffix, content, valid, detected
):
    source = tmp_path / ("source" + suffix)
    source.write_text(content, encoding="utf-8")
    result = converter.validate_file(source)
    assert result["is_valid"] == valid
    assert result["format_detected"] == detected
    assert bool(result["error_message"]) != valid


@pytest.mark.parametrize("kind", ["directory", "missing", "bad_encoding"])
def test_unreadable_input_is_reported_without_output(tmp_path, kind):
    source, target = tmp_path / "source", tmp_path / "target"
    if kind == "directory":
        source.mkdir()
    elif kind == "bad_encoding":
        source.write_bytes(b"\xff")
    with pytest.raises((OSError, UnicodeError)):
        converter.json_to_yaml(source, target)
    assert not target.exists()
    assert not converter.validate_file(source)["is_valid"]


@pytest.mark.parametrize(
    "content",
    [
        "!!int ''",
        "!!float ''",
        "!!bool nonsense",
        "!!timestamp nonsense",
        "!!int nonsense",
        "!!binary []",
    ],
)
def test_invalid_explicit_yaml_tags_are_clean_errors(tmp_path, content):
    source, target = tmp_path / "input.yaml", tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    assert not converter.validate_file(source)["is_valid"]
    with pytest.raises((ValueError, yaml.YAMLError)):
        converter.yaml_to_json(source, target)
    assert not target.exists()


@pytest.mark.parametrize("content", ['"\\ud800"', '{"x": "\\udfff"}', '{"\\ud800": 1}'])
@pytest.mark.parametrize("format", ["json", "yaml"])
def test_unpaired_surrogates_rejected_consistently(tmp_path, content, format):
    source, target = tmp_path / ("input." + format), tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    assert not converter.validate_file(source)["is_valid"]
    convert = converter.json_to_yaml if format == "json" else converter.yaml_to_json
    with pytest.raises(ValueError, match="surrogates"):
        convert(source, target)
    assert not target.exists()


def test_cleanup_failure_reports_completed_output(conversion, tmp_path, monkeypatch):
    convert, source, original = conversion
    target = tmp_path / "target"

    def fail(*args):
        raise PermissionError("injected cleanup failure")

    with monkeypatch.context() as m:
        m.setattr(converter.os, "unlink", fail)
        with pytest.raises(OSError, match="Output was created.*cleanup failed"):
            convert(source, target)
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == json.loads(original)
    stages = list(tmp_path.glob(".json-yaml-*"))
    assert len(stages) == 1
    assert stages[0].read_bytes() == target.read_bytes()
    stages[0].unlink()


def test_fdopen_failure_closes_descriptor(conversion, tmp_path, monkeypatch):
    convert, source, _ = conversion
    target = tmp_path / "target"
    descriptors = []

    def fail(fd, *args):
        descriptors.append(fd)
        raise OSError("injected fdopen failure")

    monkeypatch.setattr(converter.os, "fdopen", fail)
    with pytest.raises(OSError, match="fdopen failure"):
        convert(source, target)
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert not target.exists()
    assert not list(tmp_path.glob(".json-yaml-*"))


def test_invalid_explicit_mapping_shape_is_rejected(tmp_path):
    source, target = tmp_path / "source.yaml", tmp_path / "target"
    source.write_text("!!map []", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a YAML mapping"):
        converter.yaml_to_json(source, target)
    assert not converter.validate_file(source)["is_valid"]
    assert not target.exists()


def test_cleanup_failure_before_publication_never_creates_target(conversion, tmp_path, monkeypatch):
    convert, source, original = conversion
    target = tmp_path / "target"

    def fail_link(*args):
        raise PermissionError("injected publication failure")

    def fail_unlink(*args):
        raise PermissionError("injected cleanup failure")

    with monkeypatch.context() as m:
        m.setattr(converter.os, "link", fail_link)
        m.setattr(converter.os, "unlink", fail_unlink)
        with pytest.raises(PermissionError, match="cleanup failure"):
            convert(source, target)
    assert not target.exists()
    assert source.read_text(encoding="utf-8") == original
    stages = list(tmp_path.glob(".json-yaml-*"))
    assert len(stages) == 1
    stages[0].unlink()


@pytest.mark.parametrize(
    "content",
    [
        "!!omap []",
        "!!pairs []",
        "outer: !!omap []",
        "outer: !!pairs []",
        "!!pairs [{a: 1}]",
        "outer: !!omap [{a: 1}]",
    ],
)
def test_reject_sequence_tags_even_when_empty(tmp_path, content):
    source, target = tmp_path / "input.yaml", tmp_path / "output"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="ordered-map and pairs tags"):
        converter.yaml_to_json(source, target)
    assert not converter.validate_file(source)["is_valid"]
    assert not target.exists()
