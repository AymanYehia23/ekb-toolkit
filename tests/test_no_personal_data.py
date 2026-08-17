#!/usr/bin/env python3
"""Guard against personal data reaching the public repository.

This toolkit was extracted from a private knowledge base full of real career
data, and every future contributor will be running it against their own. The
most likely way this repository leaks something is a copy-paste during a fix,
not a deliberate commit.

So this test asserts two things across every tracked text file:

  1. No credential-shaped content.
  2. No address, path, or handle that points at a real person or company.

It is deliberately blunt. A false positive costs one allowlist entry; a false
negative publishes someone's phone number.

    python3 tests/test_no_personal_data.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".docx", ".zip", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".pyc",
}

# Domains that cannot resolve to a real person or business, plus the handful of
# public sites the docs legitimately link to. Everything else is suspicious.
#
# `.test`, `.example`, `.invalid`, and `.localhost` are reserved by RFC 2606 and
# RFC 6761 precisely so that documentation and fixtures can use them safely.
RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")
SAFE_HOSTS = (
    "example.com", "example.org", "example.net", "localhost",
    "github.com", "play.google.com", "apps.apple.com", "linkedin.com",
    "keepachangelog.com", "semver.org", "opensource.org", "json-schema.org",
    "local.ekb",  # the resume model schema $id; not a real host
)


def safe_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host.endswith(RESERVED_TLDS):
        return True
    return any(host == safe or host.endswith("." + safe) for safe in SAFE_HOSTS)

PATTERNS = [
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY-----"),
    ),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{12,}"
        ),
    ),
    (
        "credentials embedded in a URL",
        re.compile(r"https?://[^/@\s]+:[^/@\s]+@"),
    ),
    (
        "absolute home directory path",
        re.compile(r"/(?:Users|home)/(?!sam\b)[A-Za-z][A-Za-z0-9_.-]*"),
    ),
    (
        "phone number",
        re.compile(r"(?<![\w.])\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}(?![\w.])"),
    ),
]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL = re.compile(r"https?://([A-Za-z0-9.-]+)")

# Lines that legitimately contain a matching shape. Keep this list short and
# specific: a broad entry here defeats the whole test.
ALLOWED_SUBSTRINGS = (
    "noreply@",
    "you@example.com",
    "name@example.com",
    "/absolute/path/to",
    "/Users/sam/dev/",          # the fictional example workspace
    "+00 000 000 0000",         # the placeholder in templates/profile.yaml
    "tel:+000000000000",         # the same fictional phone in URI form
    "$HOME",
    "${HOME}",
    "~/ekb",
    "/home/runner",             # GitHub Actions
)


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        paths = [p for p in out.splitlines() if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = []
        for base, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "workspace"}]
            for name in names:
                paths.append(os.path.relpath(os.path.join(base, name), ROOT))
    return [p for p in paths if os.path.splitext(p)[1].lower() not in BINARY_SUFFIXES]


def allowed(line: str) -> bool:
    return any(token in line for token in ALLOWED_SUBSTRINGS)


def check_line(path: str, number: int, line: str, findings: list[str]) -> None:
    if allowed(line):
        return
    for label, pattern in PATTERNS:
        if pattern.search(line):
            findings.append(f"{path}:{number}: {label}: {line.strip()[:110]}")
    for address in EMAIL.findall(line):
        if not safe_host(address.rsplit("@", 1)[-1]):
            findings.append(f"{path}:{number}: non-example email address: {address}")
    for host in URL.findall(line):
        if not safe_host(host):
            findings.append(f"{path}:{number}: unrecognized host: {host}")


def main() -> int:
    findings: list[str] = []
    self_path = os.path.relpath(os.path.abspath(__file__), ROOT)

    for path in tracked_files():
        if path == self_path:
            continue  # this file necessarily contains the patterns it looks for
        full = os.path.join(ROOT, path)
        try:
            with open(full, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    check_line(path, number, line, findings)
        except (UnicodeDecodeError, OSError):
            continue

    if findings:
        print(f"{len(findings)} possible personal-data finding(s):\n")
        for finding in findings:
            print("  " + finding)
        print(
            "\nEvery example must be fictional and every address must point at "
            "example.com.\nIf a finding is legitimate, add a specific entry to "
            "ALLOWED_SUBSTRINGS in this file."
        )
        return 1

    print("no personal data found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
