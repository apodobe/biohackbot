#!/usr/bin/env python3
"""Block git push / CI when secrets or patient corpus would be published."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DENY_CONTENT = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xai-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"TELEGRAM_BOT_TOKEN\s*=\s*[0-9]+:[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"y0_[A-Za-z0-9._-]{20,}"),
    re.compile(r"72\.56\.79\.23"),
    re.compile(r"7752900844000725"),
    re.compile(r"Алексей\s+Юрьевич"),
    re.compile(r"20\.03\.1985"),
    re.compile(r"\b775\d{13}\b"),
]

PUBLIC_BLOCKED_PATHS = re.compile(
    r"^(?:structured_database/(?!README\.md$).+|sources/|incoming/|bot_config\.json|(?:.+/)?\.env$|.*\.pdf$)"
)

ALLOWED_ENV_EXAMPLE = re.compile(r"\.env\.example$")

# Files that embed deny-pattern literals for documentation/guards.
SCAN_SKIP_FILES = re.compile(
    r"^(?:scripts/check_safe_to_push\.py|\.github/workflows/secret-scan\.yml)$"
)

_ZERO_SHA = "0" * 40


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
        errors="replace",
    )


def _staged_files() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _staged_diff() -> str:
    return _git("diff", "--cached", "-U0")


def _tracked_files() -> list[str]:
    out = _git("ls-files")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _files_in_range(commit_range: str) -> list[str]:
    out = _git(
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        commit_range,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _diff_in_range(commit_range: str) -> str:
    return _git("diff", "-U0", commit_range)


def _read_paths(paths: list[str]) -> str:
    chunks: list[str] = []
    for rel in paths:
        if SCAN_SKIP_FILES.match(rel):
            continue
        path = ROOT / rel
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _path_errors(path: str, *, public: bool) -> list[str]:
    errors: list[str] = []
    if public and PUBLIC_BLOCKED_PATHS.match(path):
        errors.append(f"blocked path (public repo): {path}")
    if path.endswith(".env") and not ALLOWED_ENV_EXAMPLE.search(path):
        errors.append(f"blocked env file: {path}")
    return errors


def _added_diff_text(diff_text: str) -> str:
    current_skip = False
    lines_out: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++"):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current_skip = bool(SCAN_SKIP_FILES.match(path))
            continue
        if line.startswith("+") and not line.startswith("+++") and not current_skip:
            lines_out.append(line[1:])
    return "\n".join(lines_out)


def _content_errors(text: str, *, label: str) -> list[str]:
    errors: list[str] = []
    for pat in DENY_CONTENT:
        if pat.search(text):
            errors.append(f"blocked pattern in {label}: {pat.pattern}")
    return errors


def check(
    *,
    public: bool,
    paths: list[str] | None = None,
    diff_text: str | None = None,
    include_file_bodies: bool = False,
) -> list[str]:
    errors: list[str] = []
    file_list = paths or []
    if not file_list and diff_text is None:
        return errors

    for path in file_list:
        errors.extend(_path_errors(path, public=public))

    texts: list[str] = []
    if diff_text is not None:
        texts.append(_added_diff_text(diff_text))
    if include_file_bodies and file_list:
        texts.append(_read_paths(file_list))

    for text in texts:
        errors.extend(_content_errors(text, label="content"))
    return errors


def check_push_range(commit_range: str, *, public: bool) -> list[str]:
    files = _files_in_range(commit_range)
    if not files:
        return []
    return check(
        public=public,
        paths=files,
        diff_text=_diff_in_range(commit_range),
        include_file_bodies=False,
    )


def check_tracked_tree(*, public: bool) -> list[str]:
    files = _tracked_files()
    return check(
        public=public,
        paths=files,
        diff_text=_read_paths(files),
        include_file_bodies=False,
    )


def _push_ranges_from_stdin() -> list[str]:
    ranges: list[str] = []
    for line in sys.stdin:
        parts = line.strip().split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if local_sha == _ZERO_SHA:
            continue
        if remote_sha == _ZERO_SHA:
            ranges.append(local_sha)
        else:
            ranges.append(f"{remote_sha}..{local_sha}")
    return ranges


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public",
        action="store_true",
        help="Strict mode for apodobe/biohackbot (no corpus, no secrets)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Scan all git-tracked files (CI)",
    )
    parser.add_argument(
        "--range",
        metavar="REV_RANGE",
        help="Scan files/diff in a git revision range (pre-push)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Read pre-push stdin and scan each outgoing commit range",
    )
    args = parser.parse_args()

    errors: list[str] = []
    if args.push:
        ranges = _push_ranges_from_stdin()
        if not ranges:
            errors.append("pre-push: no commit ranges on stdin")
        for commit_range in ranges:
            errors.extend(check_push_range(commit_range, public=args.public))
    elif args.scan_all:
        errors.extend(check_tracked_tree(public=args.public))
    elif args.range:
        errors.extend(check_push_range(args.range, public=args.public))
    else:
        files = _staged_files()
        errors.extend(
            check(
                public=args.public,
                paths=files,
                diff_text=_staged_diff() if files else None,
                include_file_bodies=False,
            )
        )

    if errors:
        print("Push blocked — remove sensitive content before pushing:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
