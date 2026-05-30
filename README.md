# Secrets Cleanup (Activity 9)

[![CI](https://github.com/ANAMASHRAF16/secrets-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/ANAMASHRAF16/secrets-cleanup/actions/workflows/ci.yml)

A small weather-data ingester. The baseline (`main`) demonstrates the anti-pattern this PR fixes: API keys, AWS credentials, and a database password are all hardcoded directly in source. Anyone with read access to the repo — including automated GitHub scanners and search engines if it's ever public — has production credentials.

The fix branch replaces every hardcoded secret with the right tool for its lifecycle:

- **AWS credentials** — removed entirely. `boto3` uses its default credential chain (`~/.aws/credentials`, env vars, or IAM role on EC2/Lambda).
- **External API key** — loaded from the `WEATHER_API_KEY` environment variable via `python-dotenv`.
- **Database password** — fetched at runtime from **AWS Secrets Manager**, enabling automatic rotation without code changes.

The fix also adds:

- `SECURITY.md` — secure-development guidelines for contributors
- `.env.example` — documents every required env var (never values)
- `tests/test_no_hardcoded_secrets.py` — regex scanner that fails CI if a hardcoded secret pattern reappears
- `tests/test_secrets_loader.py` — covers both env-var and Secrets Manager code paths with mocked AWS
- `.github/workflows/ci.yml` — runs tests + an extra grep-based AKIA scan on every push and PR

## Run locally

```bash
pip install -r requirements.txt

# Baseline (main) - uses hardcoded values, works out of the box for demo
git checkout main
python -m src.ingest London

# Fix branch - requires env + Secrets Manager setup, see SECURITY.md
git checkout fix/env-vars-and-secrets-manager
aws configure                                                # AWS creds for boto3 default chain
cp .env.example .env && $EDITOR .env                         # fill in env vars
aws secretsmanager create-secret \
  --name analytics-db-password \
  --secret-string "$(openssl rand -base64 32)"               # one-time secret setup
python -m src.ingest London
```

See `SECURITY.md` for the full secure-development guide including IAM least-privilege policy and the leak-response runbook.

## Where each secret lives after the fix

| Secret | Storage | Rotated by |
|---|---|---|
| AWS access key + secret | `~/.aws/credentials` (local) or IAM role (prod) | IAM (manual or automated key rotation policy) |
| Weather API key | `WEATHER_API_KEY` env var | External service dashboard |
| DB password | AWS Secrets Manager `analytics-db-password` | Secrets Manager auto-rotation (Lambda) |

## Trade-offs documented

- **Env vars for the API key, Secrets Manager for the DB password.** Both are valid storage; the choice is driven by rotation needs. API keys rotate quarterly at most; DB passwords need quarterly rotation as compliance baseline and may rotate weekly under stricter regimes. Secrets Manager's rotation-as-a-service pays for itself on the DB side and would be over-engineered for the API key.
- **`@lru_cache(maxsize=16)` on `secret()`.** Avoids paying ~80ms per call after the first hit. The trade-off is that a rotated password isn't picked up until the process restarts — fine for Lambda (every cold start fetches afresh), worth re-evaluating for long-lived workers.
- **Regex-based CI scanner over commercial secret scanners.** A simple regex test catches the specific anti-patterns the baseline had and runs in 0.5 seconds. Commercial tools (truffleHog, GitGuardian) catch more shapes but add dependency weight and slower CI. For a small project the regex is the right starting point; a larger team would add truffleHog on top.
