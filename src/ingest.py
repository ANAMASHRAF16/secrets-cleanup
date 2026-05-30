"""Weather data ingester.

Fetches the current weather for a city, stores the raw JSON in S3, posts
a CloudWatch metric for the ingest count, and writes a summary row into
a Postgres analytics database.

WARNING: This file currently hardcodes API keys, AWS credentials, and
the database password directly in source. That's the anti-pattern
Activity 9 fixes. See the fix branch for the env-vars + Secrets Manager
replacement.

Run:
    python -m src.ingest London
"""

import json
import sys
from datetime import datetime, timezone

import boto3
import requests


# ---------------------------------------------------------------------------
# Secrets (HARD-CODED - this is the bug Activity 9 removes)
# ---------------------------------------------------------------------------

WEATHER_API_KEY = "owm_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"           # OpenWeather-style fake key
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"                          # AWS docs example value
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # AWS docs example value
DB_PASSWORD = "supers3cret123"                                      # Postgres analytics-db password

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_BUCKET = "weather-ingest-staging"
CW_NAMESPACE = "WeatherIngest"
DB_HOST = "analytics-db.internal"
DB_USER = "weather_writer"
DB_NAME = "analytics"
AWS_REGION = "us-east-1"

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def fetch_weather(city: str) -> dict:
    """Call the weather API and return parsed JSON."""
    resp = requests.get(
        WEATHER_URL,
        params={"q": city, "appid": WEATHER_API_KEY, "units": "metric"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def store_raw(payload: dict, city: str) -> str:
    """Upload the raw weather payload to S3. Returns the S3 key."""
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    key = f"raw/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{city}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(payload).encode())
    return key


def publish_metric(city: str) -> None:
    """Post a CloudWatch metric to track ingest volume."""
    cw = boto3.client(
        "cloudwatch",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
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
    # The actual psycopg2 / SQLAlchemy call is omitted - the point of this
    # file is to demonstrate that DB_PASSWORD is hardcoded above.
    dsn = f"postgres://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
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
