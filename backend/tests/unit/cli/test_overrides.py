"""Unit tests for the CLI override / loader helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from aef.cli.entrypoint import apply_overrides, coerce_value, load_config


def test_coerce_int_float_bool_null() -> None:
    assert coerce_value("42") == 42
    assert coerce_value("4.5") == 4.5
    assert coerce_value("true") is True
    assert coerce_value("false") is False
    assert coerce_value("null") is None
    assert coerce_value("hello") == "hello"


def test_apply_override_sets_nested_path() -> None:
    cells = apply_overrides({"sampling": {}}, ["sampling.temperature=0.7"])
    assert cells == [{"sampling": {"temperature": 0.7}}]


def test_apply_override_creates_missing_intermediate_dicts() -> None:
    cells = apply_overrides({}, ["model.config.foo=bar"])
    assert cells == [{"model": {"config": {"foo": "bar"}}}]


def test_apply_override_multirun_expands_combinations() -> None:
    cells = apply_overrides({"seed": 0}, ["seed=1,2"])
    assert {c["seed"] for c in cells} == {1, 2}


def test_apply_override_rejects_missing_equals() -> None:
    with pytest.raises(ValueError, match="missing"):
        apply_overrides({}, ["bad-override"])


def testload_config_yaml(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("foo: 1\nbar: hello\n")
    assert load_config(p) == {"foo": 1, "bar": "hello"}


def testload_config_default() -> None:
    cfg = load_config(None)
    assert cfg["model"] == {"name": "mock-chat", "model_id": "mock-chat"}


def testload_config_rejects_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text("[1, 2, 3]")
    with pytest.raises(ValueError, match="mapping"):
        load_config(p)
