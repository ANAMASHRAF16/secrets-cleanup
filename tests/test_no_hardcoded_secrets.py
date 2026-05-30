"""Regression test that scans the source tree for hardcoded secrets.

Runs on every push and PR via .github/workflows/ci.yml. If a future
commit reintroduces a hardcoded secret, this test fails and blocks
the merge.

The patterns here are deliberately conservative - they match the
specific anti-patterns the baseline had, plus a few well-known ones.
Novel secret shapes (custom API key formats) won't be caught by regex
alone; the team is the line of defence for those.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCANNED_DIRS = [ROOT / "src"]

# Files that legitimately contain secret-looking values (docs, examples).
# These are checked into git deliberately because they explain the contract.
ALLOWLIST = {
    ".env.example",
    "test_no_hardcoded_secrets.py",  # this very file mentions the patterns
}

# (label, pattern, allowed substrings that mark it as a documented placeholder)
FORBIDDEN_PATTERNS = [
    (
        "AWS access key id",
        re.compile(r"AKIA[A-Z0-9]{16}"),
        ["EXAMPLE"],
    ),
    (
        "AWS secret access key",
        re.compile(r'["\']wJalrXUtnFEMI[A-Za-z0-9+/=]{20,}["\']'),
        ["EXAMPLEKEY"],
    ),
    (
        "hardcoded password assignment",
        re.compile(r'(?i)password\s*=\s*["\'][^"\']{6,}["\']'),
        ["os.environ", "secret(", "env(", "getenv"],
    ),
    (
        "hardcoded API key assignment",
        re.compile(r'(?i)(api_key|apikey)\s*=\s*["\'][A-Za-z0-9_]{16,}["\']'),
        ["os.environ", "secret(", "env(", "getenv"],
    ),
]


def _files_to_scan():
    for d in SCANNED_DIRS:
        for path in d.rglob("*.py"):
            if path.name in ALLOWLIST:
                continue
            yield path


@pytest.mark.parametrize(
    "label,pattern,placeholders",
    FORBIDDEN_PATTERNS,
    ids=[label for label, _, _ in FORBIDDEN_PATTERNS],
)
def test_no_hardcoded_pattern_in_source(label, pattern, placeholders):
    """Source under src/ must not contain hardcoded secret patterns."""
    offences = []
    for path in _files_to_scan():
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            # Allow documented placeholders (AWS docs example keys, etc.).
            if any(p in match.group(0) for p in placeholders):
                continue
            line_no = text[: match.start()].count("\n") + 1
            offences.append(f"{path.relative_to(ROOT)}:{line_no}  {match.group(0)[:40]}...")

    assert not offences, (
        f"\nForbidden {label!r} pattern found in source:\n  "
        + "\n  ".join(offences)
        + f"\n\nMove these values to env vars or AWS Secrets Manager - see SECURITY.md."
    )


def test_no_dotenv_committed():
    """A real .env file must never be committed."""
    dotenv = ROOT / ".env"
    if dotenv.exists():
        # It's allowed to exist locally - the test only fails if it would
        # be tracked by git. We can't easily check git status from a unit
        # test, but presence + .gitignore enforcement is the contract.
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore.split("\n"), (
            "A local .env file exists and .gitignore does not list .env. "
            "Add `.env` to .gitignore to prevent accidental commits."
        )
