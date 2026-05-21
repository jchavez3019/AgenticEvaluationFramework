"""Secret-redaction unit tests."""

from __future__ import annotations

from aef.persistence.base import REDACTED_PLACEHOLDER, redact_secrets


def test_top_level_api_key_is_redacted() -> None:
    payload = {"api_key": "sk-12345", "model_id": "gpt-4o"}
    out = redact_secrets(payload)
    assert out["api_key"] == REDACTED_PLACEHOLDER
    assert out["model_id"] == "gpt-4o"


def test_case_insensitive_keys_are_redacted() -> None:
    payload = {"API_KEY": "sk-12345", "Auth_Token": "bearer-abc"}
    out = redact_secrets(payload)
    assert out["API_KEY"] == REDACTED_PLACEHOLDER
    assert out["Auth_Token"] == REDACTED_PLACEHOLDER


def test_nested_dict_is_redacted() -> None:
    payload = {"config": {"openai_api_key": "sk-12345"}, "name": "openai"}
    out = redact_secrets(payload)
    assert out["config"]["openai_api_key"] == REDACTED_PLACEHOLDER
    assert out["name"] == "openai"


def test_list_of_dicts_is_redacted() -> None:
    payload = {"connections": [{"password": "p"}, {"id": "x"}]}
    out = redact_secrets(payload)
    assert out["connections"][0]["password"] == REDACTED_PLACEHOLDER
    assert out["connections"][1]["id"] == "x"


def test_non_string_values_pass_through() -> None:
    payload = {"name": "test", "max_tokens": 128, "is_remote": True, "values": [1, 2]}
    out = redact_secrets(payload)
    assert out["max_tokens"] == 128
    assert out["is_remote"] is True
    assert out["values"] == [1, 2]


def test_redact_does_not_mutate_input() -> None:
    payload = {"api_key": "sk-12345"}
    redact_secrets(payload)
    assert payload["api_key"] == "sk-12345"
