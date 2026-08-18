"""Shared, stack-agnostic quality checks for public engineering bullets.

The prompt still makes the important judgement: whether a record communicates
an outcome, impact, meaningful scope, or merely activity.  This module enforces
the objective boundaries around that judgement so a generated bank and a final
resume cannot silently drift apart.
"""

from __future__ import annotations

import json
import re
from typing import Any


TOP_LEVEL_BULLET = re.compile(r"^-\s+(.+?)\s*$")
SOURCE_COMMENT = re.compile(r"<!--\s*src:\s*([a-z0-9_-]+-\d{3})\s*-->", re.I)
VARIANT_COMMENT = re.compile(r"<!--\s*variant[^:]*:\s*(.+?)-->", re.I | re.S)
QUALITY_COMMENT = re.compile(r"<!--\s*quality:\s*(\{.*?\})\s*-->", re.I | re.S)
NOT_SELECTED = re.compile(r"^#{2,6}\s+.*not\s+selected", re.I | re.M)
COMMENT = re.compile(r"<!--.*?-->", re.S)

QUALITY_CHECKS = {
    "specificity",
    "ownership",
    "result",
    "evidence",
    "metric",
    "relevance",
    "readability",
    "credibility",
}
QUALITY_LEVELS = {"outcome", "impact", "scope"}
RESULT_TYPES = {
    "user",
    "product",
    "business",
    "engineering",
    "delivery",
    "reliability",
    "team",
    "scale",
    "security",
    "other",
}
METRIC_STATUSES = {
    "used",
    "available-not-used",
    "not-applicable",
    "estimated-not-used",
}


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


def semantic_review_findings(
    review: Any,
    expected_sources: list[str] | None = None,
    expected_path: str | None = None,
) -> list[str]:
    """Validate the explicit A-H editorial review for one public bullet.

    This deliberately does not try to infer impact from prose. The generator
    must record its judgement, evidence boundary, and metric decision; the
    validator makes omissions and activity-only selections impossible to hide.
    Source checkers still decide whether the cited records license the claim.
    """
    if not isinstance(review, dict):
        return ["must provide one quality review object"]

    findings: list[str] = []
    required = {"level", "result_type", "change", "metric", "checks"}
    allowed = required | {"path", "evidence_refs", "scope_justification"}
    missing = required - set(review)
    unexpected = set(review) - allowed
    if missing:
        findings.append(f"quality review is missing {', '.join(sorted(missing))}")
    if unexpected:
        findings.append(
            f"quality review has unexpected fields {', '.join(sorted(unexpected))}"
        )

    level = review.get("level")
    if level not in QUALITY_LEVELS:
        findings.append("level must be outcome, impact, or scope; activity is not publishable")
    result_type = review.get("result_type")
    if result_type not in RESULT_TYPES:
        findings.append(
            "result_type must be user, product, business, engineering, delivery, "
            "reliability, team, scale, security, or other"
        )
    change = review.get("change")
    if not isinstance(change, str) or not change.strip():
        findings.append("change must state what became possible or different")
    if level == "scope":
        justification = review.get("scope_justification")
        if not isinstance(justification, str) or not justification.strip():
            findings.append("scope bullets require a non-empty scope_justification")

    if expected_path is not None and review.get("path") != expected_path:
        findings.append(f"path must be {expected_path!r}")
    if expected_sources is not None:
        refs = review.get("evidence_refs")
        if not isinstance(refs, list) or refs != expected_sources:
            findings.append("evidence_refs must exactly match the bullet source references")

    metric = review.get("metric")
    if not isinstance(metric, dict):
        findings.append("metric must record the number decision")
    else:
        metric_allowed = {
            "status",
            "basis",
            "assumptions",
            "calculation",
            "confidence",
            "resume_use",
        }
        if set(metric) - metric_allowed:
            findings.append("metric contains unexpected fields")
        status = metric.get("status")
        if status not in METRIC_STATUSES:
            findings.append(
                "metric.status must be used, available-not-used, not-applicable, "
                "or estimated-not-used"
            )
        if status in {"used", "available-not-used"} and (
            not isinstance(metric.get("basis"), str) or not metric["basis"].strip()
        ):
            findings.append(f"metric status {status!r} requires a non-empty basis")
        if status == "estimated-not-used":
            for key in ("basis", "assumptions", "calculation", "confidence"):
                if not isinstance(metric.get(key), str) or not metric[key].strip():
                    findings.append(f"estimated metrics require a non-empty {key}")
            if metric.get("resume_use") is not False:
                findings.append("an unconfirmed estimate must set resume_use to false")

    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != QUALITY_CHECKS:
        findings.append("checks must contain exactly the A-H quality checks")
    else:
        for name, value in checks.items():
            allowed_values = {"pass", "not-applicable"} if name == "metric" else {"pass"}
            if value not in allowed_values:
                findings.append(f"check {name!r} must be {' or '.join(sorted(allowed_values))}")
        metric_status = metric.get("status") if isinstance(metric, dict) else None
        if (
            metric_status in {"used", "available-not-used", "estimated-not-used"}
            and checks.get("metric") != "pass"
        ):
            findings.append(
                "the metric check must pass when a number is used, omitted deliberately, or estimated"
            )

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
        quality_values = QUALITY_COMMENT.findall(block)
        current["quality_reviews"] = []
        current["quality_errors"] = []
        for value in quality_values:
            try:
                current["quality_reviews"].append(json.loads(value))
            except json.JSONDecodeError as exc:
                current["quality_errors"].append(f"invalid quality JSON: {exc.msg}")
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
