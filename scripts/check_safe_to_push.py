#!/usr/bin/env python3
"""Block git push when secrets or patient corpus would be published."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DENY_CONTENT = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"TELEGRAM_[A-Z_]*TOKEN\s*=\s*[^\s#]+", re.IGNORECASE),
    re.compile(r"Подобедов"),
    re.compile(r"72\.56\.79\.23"),
]

PUBLIC_BLOCKED_PATHS = re.compile(
    r"^(?:structured_database/(?!README\.md$).+|sources/|incoming/|bot_config\.json|.*\.env$|.*\.pdf$)"
)

ALLOWED_ENV_EXAMPLE = re.compile(r"\.env\.example$")


def _staged_files() -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _staged_diff() -> str:
    return subprocess.check_output(
        ["git", "diff", "--cached", "-U0"],
        cwd=ROOT,
        text=True,
        errors="replace",
    )


def check(*, public: bool) -> list[str]:
    errors: list[str] = []
    files = _staged_files()
    if not files:
        return errors

    for path in files:
        if public and PUBLIC_BLOCKED_PATHS.match(path):
            errors.append(f"blocked path (public repo): {path}")
        if path.endswith(".env") and not ALLOWED_ENV_EXAMPLE.search(path):
            errors.append(f"blocked env file: {path}")

    diff = _staged_diff()
    for pat in DENY_CONTENT:
        if pat.search(diff):
            errors.append(f"blocked pattern in staged diff: {pat.pattern}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public",
        action="store_true",
        help="Strict mode for apodobe/biohackbot (no corpus, no secrets)",
    )
    args = parser.parse_args()
    errors = check(public=args.public)
    if errors:
        print("Push blocked — remove sensitive content before pushing:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
