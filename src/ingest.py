"""Weather data ingester.

Fetches the current weather for a city, stores the raw JSON in S3, posts
a CloudWatch metric for the ingest count, and writes a summary row into
a Postgres analytics database.

Secrets handling:
- AWS credentials: boto3 default chain (~/.aws/credentials, env, IAM role)
- All other secrets (API key, DB password): environment variables loaded
  via python-dotenv. See .env.example for the full list and SECURITY.md
  for guidance on when to upgrade specific secrets to AWS Secrets Manager.

Run:
    python -m src.ingest London
"""

import json
import sys
from datetime import datetime, timezone

import boto3
import requests

from src.secrets_loader import env


# ---------------------------------------------------------------------------
# Configuration  (all non-secret - safe to read from env directly)
# ---------------------------------------------------------------------------

AWS_REGION = env("AWS_REGION")
S3_BUCKET = env("S3_BUCKET")
CW_NAMESPACE = env("CW_NAMESPACE")
DB_HOST = env("DB_HOST")
DB_USER = env("DB_USER")
DB_NAME = env("DB_NAME")

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def fetch_weather(city: str) -> dict:
    """Call the weather API and return parsed JSON."""
    # API key is loaded lazily so an unset env var fails at the first call,
    # not at module import time - keeps unit tests of pure functions runnable
    # without a real key.
    api_key = env("WEATHER_API_KEY")
    resp = requests.get(
        WEATHER_URL,
        params={"q": city, "appid": api_key, "units": "metric"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def store_raw(payload: dict, city: str) -> str:
    """Upload the raw weather payload to S3. Returns the S3 key.

    No credentials passed to boto3 - it picks them up from the default
    credential chain. Production: IAM role on the Lambda/ECS task.
    Local: ~/.aws/credentials from `aws configure`.
    """
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = f"raw/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{city}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(payload).encode())
    return key


def publish_metric(city: str) -> None:
    """Post a CloudWatch metric to track ingest volume."""
    cw = boto3.client("cloudwatch", region_name=AWS_REGION)
    cw.put_metric_data(
        Namespace=CW_NAMESPACE,
        MetricData=[{
            "MetricName": "Ingested",
            "Value": 1,
            "Unit": "Count",
            "Dimensions": [{"Name": "City", "Value": city}],
        }],
    )


def write_summary_to_db(city: str, temp_c: float) -> None:
    """Write a one-row summary to the analytics Postgres database."""
    # DB password comes from the DB_PASSWORD env var. Loaded lazily here
    # (not at module import) so unit tests of pure functions can run
    # without a real password being set in the test environment.
    db_password = env("DB_PASSWORD")
    dsn = f"postgres://{DB_USER}:{db_password}@{DB_HOST}/{DB_NAME}"
    # The actual psycopg2 / SQLAlchemy call is intentionally stubbed -
    # the focus here is that DB_PASSWORD never appears in source.
    print(f"  [would connect to DB using DSN: {dsn[:40]}...]")
    print(f"  [would INSERT INTO weather_summary (city, temp_c) VALUES ('{city}', {temp_c})]")


def main(city: str) -> dict:
    print(f"Ingesting weather for: {city}")
    payload = fetch_weather(city)
    s3_key = store_raw(payload, city)
    publish_metric(city)
    write_summary_to_db(city, payload["main"]["temp"])
    print(f"Done. Stored at s3://{S3_BUCKET}/{s3_key}")
    return {"city": city, "s3_key": s3_key, "temp_c": payload["main"]["temp"]}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.ingest <city>")
        sys.exit(1)
    main(sys.argv[1])
