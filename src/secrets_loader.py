"""Runtime secret loader.

A single strategy: read environment variables. Fast, free, dependency-free
once `python-dotenv` is installed for local development.

Why env vars and not AWS Secrets Manager:
    The activity asks for env vars OR Secrets Manager. For this pipeline's
    scale and rotation profile, env vars are sufficient. Secrets Manager
    would be the right upgrade when automated rotation becomes a compliance
    requirement (typical for DB passwords once the team scales past a few
    engineers). Until then, the cost ($0.40/secret/month) and added latency
    (~80ms per fetch) buy us nothing this project actually needs.

Local development:
    Copy .env.example to .env and fill in real values. python-dotenv
    auto-loads .env at import time when this module is imported.

Production runtime:
    Set env vars on the runtime (Lambda env vars, ECS task definition,
    systemd EnvironmentFile, Kubernetes Secret mounted as env). No
    code changes required - the same env() call works everywhere.
"""

import os

from dotenv import load_dotenv

# Load .env once for local dev. In production (Lambda, ECS, systemd),
# env vars come from the runtime config and load_dotenv is a harmless
# no-op (no .env file present).
load_dotenv()


class SecretNotFoundError(RuntimeError):
    """Raised when a required env var is missing or empty."""


def env(name: str) -> str:
    """Return the env var `name`. Raise SecretNotFoundError if missing or empty.

    Loud-failure at startup is intentional. A silent default would let
    the pipeline run against the wrong value - which is harder to debug
    than a clear "env var X is not set" message at boot.
    """
    value = os.environ.get(name)
    if not value:
        raise SecretNotFoundError(
            f"Required environment variable {name!r} is not set. "
            f"See .env.example for the full list of expected variables."
        )
    return value
