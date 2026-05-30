"""Tests for src/secrets_loader - the env-var and Secrets Manager helpers."""

import pytest

from src.secrets_loader import SecretNotFoundError, env, secret


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


def test_secret_fetches_via_boto3(mocker):
    """secret() should call boto3 secretsmanager and return SecretString."""
    secret.cache_clear()  # don't share state across tests
    fake_client = mocker.Mock()
    fake_client.get_secret_value.return_value = {"SecretString": "rotated-password-42"}
    mocker.patch("boto3.client", return_value=fake_client)

    result = secret("some-secret")

    assert result == "rotated-password-42"
    fake_client.get_secret_value.assert_called_once_with(SecretId="some-secret")


def test_secret_is_cached_per_process(mocker):
    """Second call with same name must not hit boto3 again."""
    secret.cache_clear()
    fake_client = mocker.Mock()
    fake_client.get_secret_value.return_value = {"SecretString": "value"}
    mocker.patch("boto3.client", return_value=fake_client)

    secret("cached-secret")
    secret("cached-secret")

    assert fake_client.get_secret_value.call_count == 1


def test_secret_raises_on_client_error(mocker):
    """A Secrets Manager AccessDenied / NotFound must surface as SecretNotFoundError."""
    from botocore.exceptions import ClientError
    secret.cache_clear()
    fake_client = mocker.Mock()
    fake_client.get_secret_value.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
        "GetSecretValue",
    )
    mocker.patch("boto3.client", return_value=fake_client)

    with pytest.raises(SecretNotFoundError, match="ResourceNotFoundException"):
        secret("nonexistent-secret")


def test_secret_raises_on_binary_only_secret(mocker):
    """SecretBinary-only secrets should fail loudly until binary support is added."""
    secret.cache_clear()
    fake_client = mocker.Mock()
    fake_client.get_secret_value.return_value = {"SecretBinary": b"\x00\x01"}
    mocker.patch("boto3.client", return_value=fake_client)

    with pytest.raises(SecretNotFoundError, match="binary"):
        secret("binary-secret")
