# Secrets Cleanup (Activity 9)

[![CI](https://github.com/ANAMASHRAF16/secrets-cleanup/actions/workflows/ci.yml/badge.svg)](https://github.com/ANAMASHRAF16/secrets-cleanup/actions/workflows/ci.yml)

A small weather-data ingester. The baseline (`main`) demonstrates the anti-pattern this PR fixes: a weather API key, AWS access key, AWS secret, and database password are all hardcoded directly in source. Anyone with read access to the repo — current team, ex-team, automated GitHub scanners, search-engine crawlers if it's ever public — has production credentials.

The fix branch removes all four hardcoded secrets and replaces them with the right loading strategy for each:

- **AWS credentials** — removed entirely. `boto3` uses its default credential chain (`~/.aws/credentials`, env vars, or IAM role on EC2/Lambda). No key/secret ever crosses the application boundary in code.
- **Weather API key and database password** — loaded from environment variables via `python-dotenv`. Single helper (`env()`) raises a loud `SecretNotFoundError` at startup if anything is missing, so misconfiguration shows up immediately instead of silently producing wrong output.

The fix also adds:

- `SECURITY.md` — secure-development guidelines for contributors, including a "when to upgrade DB password to AWS Secrets Manager" trigger list
- `.env.example` — documents every required env var; never holds real values
- `tests/test_no_hardcoded_secrets.py` — regex scanner that fails CI if a hardcoded secret pattern reappears in `src/`
- `tests/test_secrets_loader.py` — 5 unit tests covering missing, empty, special-character, and error-message cases
- `.github/workflows/ci.yml` — runs the tests + a belt-and-braces `grep` for raw AWS key patterns on every push and PR

## Run locally

```bash
pip install -r requirements.txt

# Baseline (main) - uses hardcoded values, runs out of the box for the demo
git checkout main
python -m src.ingest London

# Fix branch - requires .env + AWS credentials configured
git checkout fix/env-vars-and-secrets-manager
aws configure                                                # one-time, used by boto3 default chain
cp .env.example .env && $EDITOR .env                         # fill in real values
python -m src.ingest London
```

See `SECURITY.md` for the full secure-development guide.

## Where each secret lives after the fix

| Secret | Storage | Loaded by |
|---|---|---|
| AWS access key + secret | `~/.aws/credentials` (local) or IAM role (prod) | boto3 default chain — never visible in source |
| Weather API key | `WEATHER_API_KEY` env var | `env("WEATHER_API_KEY")` via python-dotenv |
| DB password | `DB_PASSWORD` env var | `env("DB_PASSWORD")` via python-dotenv |

## Trade-offs documented

- **Env vars chosen over AWS Secrets Manager.** The activity spec asks for env vars *or* Secrets Manager. For this project's scale env vars are sufficient — Secrets Manager costs $0.40/secret/month plus ~80ms per fetch and pays for itself only when automated rotation becomes a compliance requirement. `SECURITY.md` lists the exact triggers that would justify the upgrade.
- **Single loader interface.** All non-AWS-credential secrets go through one `env()` function, which means one place to swap to Secrets Manager later if the trigger conditions are met. The application code (`src/ingest.py`) wouldn't change shape — just the helper.
- **Documented AWS docs placeholder values are allowlisted.** The regex scanner skips `AKIAIOSFODNN7EXAMPLE` and `wJalrXUtnFEMI...EXAMPLEKEY` because those are AWS's official documentation placeholders used in `.env.example` and `SECURITY.md`. Real-looking AKIA values would still trigger the scanner.
- **Regex scanner, not commercial secret scanner.** truffleHog or GitGuardian would catch more shapes but add ~30s of CI time and a 150 MB tool. For preventing the four specific anti-patterns we just removed, a focused regex is fast, cheap, and easy to audit. A larger team would add truffleHog on top.
