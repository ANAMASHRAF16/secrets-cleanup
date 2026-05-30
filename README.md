# Secrets Cleanup (Activity 9)

A small weather-data ingester. The baseline (`main` branch) demonstrates the
anti-pattern Activity 9 fixes: API keys, AWS credentials, and a database
password are all hardcoded directly in source. Anyone with read access to
the repo — including search-index crawlers if it's ever made public — has
production credentials.

The fix branch replaces every hardcoded secret with the right tool for
its lifecycle:

- **AWS credentials** — removed entirely. `boto3` uses its default credential
  chain (`~/.aws/credentials`, env vars, or IAM role on EC2/Lambda).
- **External API key** — read from `WEATHER_API_KEY` environment variable.
- **Database password** — fetched at runtime from **AWS Secrets Manager**,
  enabling automatic rotation without code changes.

The fix branch also adds:

- `SECURITY.md` — secure-development guidelines for contributors
- `.env.example` — documents required env var names (never values)
- `tests/test_no_hardcoded_secrets.py` — regex scanner that fails CI if a
  hardcoded secret pattern reappears
- `.github/workflows/ci.yml` — runs tests + secret scan on every push and PR

## Run locally

```bash
pip install -r requirements.txt
python -m src.ingest London
```

(On `main` this runs against hardcoded credentials. On the fix branch it
requires `.env` + `aws configure` + a Secrets Manager entry.)

See `SECURITY.md` for full setup after the fix is merged.
