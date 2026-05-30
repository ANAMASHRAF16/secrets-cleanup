# Security Guidelines

## What counts as a secret

Anything that, if leaked, lets someone act as the application:

- API keys (Weather API, Stripe, Gemini, etc.)
- AWS credentials (access key + secret)
- Database passwords
- OAuth client secrets
- Webhook signing keys
- Private keys (TLS, signing)

Public hostnames, region names, bucket names, and table names are **not** secrets — they don't grant access on their own. They live in `.env.example` and source code without concern.

## Where each kind of secret lives

| Secret type | Storage | Why |
|---|---|---|
| AWS access key + secret | `~/.aws/credentials` (local), IAM role (prod) | Default boto3 chain; no code change between local and prod |
| External API key | Environment variable | Low rotation churn; cheap and fast to load |
| Database password | AWS Secrets Manager | Supports automated rotation; auditable via CloudTrail |
| OAuth client secret | AWS Secrets Manager | Same reasoning as DB passwords |

## How `src/ingest.py` loads secrets

| Line | What it reads | How |
|---|---|---|
| `env("WEATHER_API_KEY")` | env var | python-dotenv loads `.env` at startup; production env vars override |
| `boto3.client("s3", region_name=AWS_REGION)` | AWS creds | Default chain — no key/secret passed in code |
| `secret("analytics-db-password")` | DB password | AWS Secrets Manager `get_secret_value` call, cached per-process |

## Local setup

```bash
# 1. Configure AWS credentials
aws configure                       # paste access key + secret, region eu-north-1

# 2. Create the local .env from the template
cp .env.example .env                # then edit values

# 3. Create the database password secret in AWS
aws secretsmanager create-secret \
  --name analytics-db-password \
  --secret-string "$(openssl rand -base64 32)"

# 4. Verify
python -m src.ingest London
```

## IAM policy for the application principal

The IAM user or role running the application needs these permissions and nothing else:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::weather-ingest-staging/*"
    },
    {
      "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {"cloudwatch:namespace": "WeatherIngest"}
      }
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:*:*:secret:analytics-db-password-*"
    }
  ]
}
```

Least privilege — even if these credentials leak, an attacker can only:
- Write to one specific S3 bucket prefix
- Publish CloudWatch metrics under one namespace
- Read one specific Secrets Manager secret

## If a secret leaks

1. **Rotate first, debug later.** Don't try to figure out the blast radius before deactivating the key.
   - AWS access key: IAM Console → Users → Security credentials → Deactivate immediately, then delete
   - API key: External service's dashboard → revoke + issue new
   - DB password: `aws secretsmanager update-secret --secret-id analytics-db-password --secret-string "$(openssl rand -base64 32)"` then rotate the DB
2. **Check CloudTrail / API access logs** for any usage of the leaked credential outside expected sources
3. **Search git history** for the leaked value: `git log -p -S 'AKIA...' --all` — if it's in any commit, that commit hash is permanent record; you'll need to rewrite history *and* assume the key was scraped (rotation is non-negotiable regardless)

## What CI enforces

`tests/test_no_hardcoded_secrets.py` runs on every push and PR. It scans `src/` for these forbidden patterns:

- AWS access key format (`AKIA[A-Z0-9]{16}`) excluding the documented `AKIAIOSFODNN7EXAMPLE` placeholder
- AWS secret format (40-char base64-like) excluding the `wJalrXUtnFEMI...EXAMPLEKEY` placeholder
- Hardcoded password assignments (`password\s*=\s*["']...`)
- API key assignments with literal strings (heuristic — false positives possible; the test allowlists `.env.example` and tests/)

If any pattern matches, the test fails and the PR cannot merge. This catches regressions; it doesn't catch novel patterns. The team is still the line of defense for things the regex doesn't model.

## What contributors should never do

- Paste real credentials into PR descriptions, GitHub issues, Slack, or chat with AI assistants
- Commit `.env` files (it's in `.gitignore` — keep it there)
- Hardcode credentials "just for testing" — the test branch leaves a forever-record in git history
- Email or DM credentials — use a password manager's secure share if a team member needs one

## When in doubt

If you're not sure whether a value is sensitive, treat it as sensitive. The cost of treating something safe as a secret is one env var setup. The cost of treating something sensitive as safe is a security incident.
