"""Runtime secret loaders.

Two strategies in this module:

1. `env(name)` - read an environment variable. Fast, free, and the right
   choice for low-sensitivity values that don't need rotation (API keys
   for internal tools, feature flags, region names).

2. `secret(name)` - read from AWS Secrets Manager. Slower (~80ms cold) and
   costs $0.40 per secret per month, but supports automated rotation
   without code changes - the right choice for database passwords and
   anything that has compliance-driven rotation requirements.

Both return strings. Both raise loudly on missing values so the failure
shows up at startup, not at first use.

Local development:
    Copy .env.example to .env and fill in real values. python-dotenv
    auto-loads .env at import time when this module is imported by the
    main entry point.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

# Load .env once for local dev. In production (Lambda, ECS), env vars come
# from the runtime config and load_dotenv is a no-op (no .env file present).
load_dotenv()


class SecretNotFoundError(RuntimeError):
    """Raised when a required secret can't be loaded."""


def env(name: str) -> str:
    """Return the env var `name`. Raise SecretNotFoundError if missing.

    Loud-failure at startup is intentional. A silent default would let
    the pipeline run with the wrong value - which is harder to debug
    than a clear "env var X is not set" message.
    """
    value = os.environ.get(name)
    if not value:
        raise SecretNotFoundError(
            f"Required environment variable {name!r} is not set. "
            f"See .env.example for the full list of expected variables."
        )
    return value


@lru_cache(maxsize=16)
def secret(name: str, region: str | None = None) -> str:
    """Fetch a secret value from AWS Secrets Manager.

    Cached per-process so we don't pay the ~80ms network round-trip on
    every call. Cache size is bounded so a misconfigured caller can't
    grow it unboundedly.

    The IAM principal running this code needs:
        secretsmanager:GetSecretValue on arn:aws:secretsmanager:*:*:secret:<name>-*
    """
    # Imported here so unit tests can run without boto3 installed if they
    # only exercise the env() path. Keeps module import cheap.
    import boto3
    from botocore.exceptions import ClientError

    region = region or os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)

    try:
        resp = client.get_secret_value(SecretId=name)
    except ClientError as e:
        raise SecretNotFoundError(
            f"Secrets Manager lookup for {name!r} failed: {e.response['Error']['Code']}. "
            f"Verify the secret exists in region {region} and the IAM principal has "
            f"secretsmanager:GetSecretValue."
        ) from e

    # Secrets Manager returns the value as either SecretString or SecretBinary.
    # We only support strings here; binary would need a separate API.
    if "SecretString" not in resp:
        raise SecretNotFoundError(
            f"Secret {name!r} has no SecretString (binary secrets aren't supported)."
        )
    return resp["SecretString"]
