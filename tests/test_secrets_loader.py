"""Tests for src/secrets_loader - the env-var loader."""

import pytest

from src.secrets_loader import SecretNotFoundError, env


def test_env_returns_set_variable(monkeypatch):
    monkeypatch.setenv("TEST_VAR", "hello")
    assert env("TEST_VAR") == "hello"


def test_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(SecretNotFoundError, match="MISSING_VAR"):
        env("MISSING_VAR")


def test_env_raises_when_empty(monkeypatch):
    """An env var set to empty string must be treated the same as missing.

    Loud-failure beats accepting a blank value the caller didn't intend.
    """
    monkeypatch.setenv("EMPTY_VAR", "")
    with pytest.raises(SecretNotFoundError):
        env("EMPTY_VAR")


def test_env_returns_value_with_special_chars(monkeypatch):
    """Passwords often contain special characters - make sure env() preserves them."""
    monkeypatch.setenv("SPECIAL", "p@ssw0rd!#$%")
    assert env("SPECIAL") == "p@ssw0rd!#$%"


def test_error_message_mentions_variable_name(monkeypatch):
    """The error message should name the missing variable for fast debugging."""
    monkeypatch.delenv("SOME_SPECIFIC_NAME", raising=False)
    with pytest.raises(SecretNotFoundError) as exc_info:
        env("SOME_SPECIFIC_NAME")
    assert "SOME_SPECIFIC_NAME" in str(exc_info.value)
    assert ".env.example" in str(exc_info.value)
