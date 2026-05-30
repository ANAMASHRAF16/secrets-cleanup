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

## Where each kind of secret lives in this project

| Secret type | Storage | Why |
|---|---|---|
| AWS access key + secret | `~/.aws/credentials` (local), IAM role (prod) | Default boto3 chain — no key/secret ever crosses the application boundary in code |
| Weather API key | `WEATHER_API_KEY` env var via `python-dotenv` | Low rotation churn; cheap and fast to load |
| Database password | `DB_PASSWORD` env var | Sufficient for this scale; see "When to upgrade to Secrets Manager" below |

## How `src/ingest.py` loads secrets

| Call | Reads from | How |
|---|---|---|
| `env("WEATHER_API_KEY")` | env var | python-dotenv loads `.env` at startup; production env vars override |
| `env("DB_PASSWORD")` | env var | same loader; loud-failure if unset |
| `boto3.client("s3", region_name=...)` | AWS creds | Default chain — no key/secret passed in code |

The codebase has **zero hardcoded secrets**. The CI test `tests/test_no_hardcoded_secrets.py` fails any future PR that reintroduces one.

## Local setup

```bash
# 1. Configure AWS credentials (used by boto3 default chain)
aws configure                       # paste access key + secret, region eu-north-1

# 2. Create the local .env from the template
cp .env.example .env                # then edit values

# 3. Verify
python -m src.ingest London
```

If any required env var is missing, the pipeline fails immediately at startup with a clear `Required environment variable 'X' is not set` message — never silently with the wrong value.

## When to upgrade DB_PASSWORD to AWS Secrets Manager

For this project, an env var on the Lambda / ECS task definition is sufficient because:

- Rotation is manual and infrequent
- One application reads it
- We can re-deploy quickly to pick up a rotated value

Upgrade to AWS Secrets Manager when **any** of these is true:

- Compliance requires automated rotation (PCI, HIPAA, SOC2)
- Multiple services read the same password (rotation has to be coordinated)
- The team scales past a few engineers (manual rotation becomes a coordination problem)
- Audit logging on every secret read is required (CloudTrail logs `GetSecretValue` calls)

The upgrade path is small: replace `env("DB_PASSWORD")` with a `secret("analytics-db-password")` call backed by `boto3.client("secretsmanager").get_secret_value(...)`. The rest of the pipeline stays the same.

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
    }
  ]
}
```

Least privilege — even if these credentials leak, an attacker can only:

- Write to one specific S3 bucket prefix
- Publish CloudWatch metrics under one namespace

## If a secret leaks

1. **Rotate first, debug later.** Don't try to figure out the blast radius before deactivating the key.
   - AWS access key: IAM Console → Users → Security credentials → Deactivate immediately, then delete
   - API key: External service's dashboard → revoke + issue new
   - DB password: change the password in the database, update `DB_PASSWORD` in every environment that reads it
2. **Check CloudTrail / API access logs** for any usage of the leaked credential outside expected sources
3. **Search git history** for the leaked value: `git log -p -S 'AKIA...' --all` — if it's in any commit, that commit hash is permanent record; you'll need to rewrite history *and* assume the key was scraped (rotation is non-negotiable regardless)

## What CI enforces

`tests/test_no_hardcoded_secrets.py` runs on every push and PR. It scans `src/` for these forbidden patterns:

- AWS access key format (`AKIA[A-Z0-9]{16}`) excluding the documented `AKIAIOSFODNN7EXAMPLE` placeholder
- AWS secret format (40-char base64-like) excluding the `wJalrXUtnFEMI...EXAMPLEKEY` placeholder
- Hardcoded password assignments (`password\s*=\s*["']...`) excluding calls to `env(...)` etc.
- API key assignments with literal strings — heuristic, allowlists `.env.example` and test files

If any pattern matches, the test fails and the PR cannot merge. This catches the specific anti-patterns we already removed; the team is still the line of defense for novel patterns the regex doesn't model.

## GitHub Secrets vs runtime secrets — they solve different problems

This often confuses people:

| Layer | Where secrets live | Read by |
|---|---|---|
| CI/CD workflows (GitHub Actions) | **GitHub Secrets** | The workflow YAML, injected as env vars to workflow steps |
| Application runtime (Lambda, ECS, your laptop) | **env vars** or **AWS Secrets Manager** | Your Python code at request time |

GitHub Secrets are **only** readable from within GitHub Actions workflow runs. A Lambda processing a real customer request cannot reach into GitHub Secrets — they don't exist outside `.github/workflows/*.yml`.

So for this project:

- If we add an integration test in CI that hits real AWS, the workflow reads `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from GitHub Secrets and exports them as env vars to the test step
- If the Lambda is deployed to AWS and runs in production, it gets credentials from its IAM role and other secrets from its Lambda env vars — never from GitHub Secrets

The two layers are complementary, not interchangeable.

## What contributors should never do

- Paste real credentials into PR descriptions, GitHub issues, Slack, or chat with AI assistants
- Commit `.env` files (it's in `.gitignore` — keep it there)
- Hardcode credentials "just for testing" — the test branch leaves a forever-record in git history
- Email or DM credentials — use a password manager's secure share if a team member needs one

## When in doubt

If you're not sure whether a value is sensitive, treat it as sensitive. The cost of treating something safe as a secret is one env var setup. The cost of treating something sensitive as safe is a security incident.
