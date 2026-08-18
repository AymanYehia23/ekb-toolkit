"""Shared, stack-agnostic quality checks for public engineering bullets.

The prompt still makes the important judgement: whether a record communicates
an outcome, impact, meaningful scope, or merely activity.  This module enforces
the objective boundaries around that judgement so a generated bank and a final
resume cannot silently drift apart.
"""

from __future__ import annotations

import re
from typing import Any


TOP_LEVEL_BULLET = re.compile(r"^-\s+(.+?)\s*$")
SOURCE_COMMENT = re.compile(r"<!--\s*src:\s*([a-z0-9_-]+-\d{3})\s*-->", re.I)
VARIANT_COMMENT = re.compile(r"<!--\s*variant[^:]*:\s*(.+?)-->", re.I | re.S)
NOT_SELECTED = re.compile(r"^#{2,6}\s+.*not\s+selected", re.I | re.M)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def word_count(text: str) -> int:
    """Count visible whitespace-delimited words, matching the editorial gate."""
    return len(text.split())


def bullet_text_findings(text: str, policy: dict[str, Any]) -> list[str]:
    """Return objective wording-policy violations for one public bullet."""
    quality = policy.get("bullet_quality") or {}
    style = policy.get("writing_style") or {}
    findings: list[str] = []
    stripped = " ".join(text.split())

    maximum_words = int(quality.get("maximum_words", 36))
    if maximum_words < 1:
        findings.append("policy bullet_quality.maximum_words must be positive")
    elif word_count(stripped) > maximum_words:
        findings.append(
            f"contains {word_count(stripped)} words; maximum is {maximum_words}"
        )

    maximum_sentences = int(quality.get("maximum_sentences", 1))
    if maximum_sentences < 1:
        findings.append("policy bullet_quality.maximum_sentences must be positive")
    else:
        sentence_count = len(re.findall(r"[.!?]+(?=\s|$)", stripped))
        if sentence_count > maximum_sentences:
            findings.append(
                f"contains {sentence_count} sentences; maximum is {maximum_sentences}"
            )

    if quality.get("require_terminal_punctuation", True) and not stripped.endswith(
        (".", "!", "?")
    ):
        findings.append("must end with terminal punctuation")

    openings = quality.get("forbidden_openings") or []
    if not isinstance(openings, list) or not all(
        isinstance(item, str) and item.strip() for item in openings
    ):
        findings.append(
            "policy bullet_quality.forbidden_openings must contain non-empty strings"
        )
    else:
        for opening in openings:
            if re.match(rf"^{re.escape(opening)}\b", stripped, flags=re.I):
                findings.append(
                    f"starts with vague duty wording {opening!r}; name the contribution"
                )
                break

    symbols = style.get("forbidden_symbols") or {}
    if isinstance(symbols, dict):
        for symbol, label in symbols.items():
            if symbol in stripped:
                findings.append(f"contains forbidden {label} symbol {symbol!r}")

    terms = [*(style.get("forbidden_terms") or []), *(style.get("forbidden_phrases") or [])]
    for phrase in terms:
        if isinstance(phrase, str) and phrase and re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)", stripped, flags=re.I
        ):
            findings.append(f"contains forbidden generic wording {phrase!r}")

    return findings


def parse_bullet_bank(text: str) -> list[dict[str, Any]]:
    """Extract publishable top-level bullets and their source comments.

    Content below ``Not selected`` is an audit, not public prose.  Source
    comments may be inline or on following lines so older valid banks remain
    readable while new banks keep comments immediately after the bullet.
    """
    cutoff = NOT_SELECTED.search(text)
    publishable = text[: cutoff.start()] if cutoff else text
    lines = publishable.splitlines()
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        block = "\n".join(current.pop("block"))
        current["sources"] = SOURCE_COMMENT.findall(block)
        current["variants"] = [" ".join(value.split()) for value in VARIANT_COMMENT.findall(block)]
        body = COMMENT.sub(" ", block)
        body = re.sub(r"^-\s+", "", body, count=1)
        current["text"] = " ".join(body.split())
        entries.append(current)
        current = None

    for line_number, line in enumerate(lines, start=1):
        if TOP_LEVEL_BULLET.match(line):
            finish()
            current = {"line": line_number, "block": [line]}
        elif current is not None:
            if re.match(r"^(?:#{1,6}\s+|---+\s*$)", line):
                finish()
            else:
                current["block"].append(line)
    finish()
    return entries
