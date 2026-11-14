#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import unicodedata

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as DOCX_RT
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement
from docx.shared import Inches, Pt, RGBColor
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate

from bullet_quality import bullet_text_findings, semantic_review_findings
from ekb_paths import config_path
from ekb_screening import APPLICATION_ID_PATTERN, ScreeningError, frozen_application, posting_digest, require_screening
from ekb_requirements import alignment_projection, load_decisions
from resume_publish import PublicationError, previous_pdf, publication_lock, publish, require_atomic_update
from uuid import uuid4


class ResumeError(Exception):
    pass


NO_BREAK_SPACE_MARKER = "\ue000"
DELIVERY_STATUS = "private_draft_human_approval_required"
ROLE_PROJECTS_HEADING = "PROJECTS"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResumeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResumeError(f"{path} must contain a JSON object")
    return value


def whole_item_link_allowed(path: str) -> bool:
    """Whether a sourced item's entire visible text may be a hyperlink.

    Whole-item links are reserved for contact/profile values and entity labels.
    Summary text is always plain. Other narrative prose must name the linked
    entity explicitly through ``link_text`` so a project URL cannot turn an
    entire achievement bullet into blue underlined text.
    """
    patterns = (
        r"basics\.(?:contact|links)\[\d+\]",
        r"experience\[\d+\]\.organization",
        r"experience\[\d+\]\.engagements\[\d+\]\.name",
        r"projects\[\d+\]\.primary",
        r"(?:education|certifications|awards|activities)\[\d+\]\.primary",
    )
    return any(re.fullmatch(pattern, path) for pattern in patterns)


def sourced(value: Any, path: str, nullable: bool = False) -> dict[str, str] | None:
    if value is None and nullable:
        return None
    allowed = {"text", "source_ref", "source_refs", "url", "link_text"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ResumeError(
            f"{path} must contain text and source_ref or source_refs, and may contain url and link_text"
        )
    has_one = "source_ref" in value
    has_many = "source_refs" in value
    if has_one == has_many:
        raise ResumeError(f"{path} must use exactly one of source_ref or source_refs")
    if "text" not in value or not isinstance(value["text"], str) or not value["text"].strip():
        raise ResumeError(f"{path}.text must be a non-empty string")
    if has_one:
        if not isinstance(value["source_ref"], str) or not value["source_ref"].strip():
            raise ResumeError(f"{path}.source_ref must be a non-empty string")
    else:
        # Composition, for a claim that is inherently plural. The Ruby source
        # checker enforces the evidence rules; this is the structural gate.
        refs = value["source_refs"]
        if not isinstance(refs, list) or len(refs) < 2:
            raise ResumeError(f"{path}.source_refs must list at least two source IDs")
        if len(refs) > 4:
            raise ResumeError(f"{path}.source_refs composes more than four sources")
        if len(set(refs)) != len(refs):
            raise ResumeError(f"{path}.source_refs repeats a source")
        if not all(isinstance(ref, str) and ref.strip() for ref in refs):
            raise ResumeError(f"{path}.source_refs entries must be non-empty strings")
    if "url" in value:
        url = value["url"]
        if not isinstance(url, str) or not url.strip():
            raise ResumeError(f"{path}.url must be a non-empty string when present")
        if not re.match(r"^(https://|mailto:|tel:)", url.strip()):
            raise ResumeError(f"{path}.url must start with https://, mailto:, or tel:")
        if re.fullmatch(r"summary\[\d+\]", path):
            raise ResumeError(f"{path}.url is not allowed; summary prose must render without hyperlinks")
    if "link_text" in value:
        link_text = value["link_text"]
        if "url" not in value:
            raise ResumeError(f"{path}.link_text requires url")
        if not isinstance(link_text, str) or not link_text.strip():
            raise ResumeError(f"{path}.link_text must be a non-empty string when present")
        if value["text"].count(link_text) != 1:
            raise ResumeError(f"{path}.link_text must occur exactly once in text")
        if link_text == value["text"]:
            raise ResumeError(f"{path}.link_text must identify only part of text")
    elif "url" in value and not whole_item_link_allowed(path):
        raise ResumeError(
            f"{path}.url would hyperlink narrative prose; add link_text for the named entity or remove url"
        )
    return value


def url_of(value: dict[str, str] | None) -> str:
    """Optional hyperlink target for a sourced item; empty when it is plain text."""
    return "" if value is None else str(value.get("url", "")).strip()


def link_text_of(value: dict[str, str] | None) -> str:
    """Optional substring that alone receives the item's hyperlink."""
    return "" if value is None else str(value.get("link_text", ""))


def link_fragments(value: dict[str, str]) -> list[tuple[str, bool]]:
    """Split sourced text into plain and linked fragments."""
    text = text_of(value)
    link_text = link_text_of(value)
    if not link_text:
        return [(text, True)]
    before, after = text.split(link_text, 1)
    return [(before, False), (link_text, True), (after, False)]


def links_enabled(model: dict[str, Any]) -> bool:
    return model["layout"].get("hyperlinks", "auto") != "off"


def supporting_sections(model: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Supporting-section keys and their visible headings."""
    activities_heading = str(model["layout"].get("activities_heading", "Activities")).strip()
    return (
        ("education", "Education"),
        ("certifications", "Certificates"),
        ("awards", "Awards"),
        ("activities", activities_heading),
    )


def link_of(model: dict[str, Any], value: dict[str, str] | None) -> str:
    """Hyperlink target honoring the document-level hyperlink mode."""
    return url_of(value) if links_enabled(model) else ""


def link_appearance(policy: dict[str, Any]) -> tuple[str, bool]:
    """Return the explicit cross-format hyperlink treatment."""
    links = policy.get("links", {})
    color = str(links.get("color_hex", "0563C1")).lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", color):
        raise ResumeError("policy.links.color_hex must contain exactly six hexadecimal digits")
    return color, bool(links.get("underline", True))


def bullet_layout(policy: dict[str, Any]) -> dict[str, float]:
    """Validated cross-format bullet geometry in points."""
    raw = policy.get("bullets", {})
    defaults = {
        "text_indent_pt": 20.0,
        "hanging_pt": 11.0,
        "marker_font_size_pt": 6.0,
        "marker_vertical_offset_pt": -1.5,
        "engagement_title_indent_pt": 32.0,
        "engagement_text_indent_pt": 49.0,
    }
    layout: dict[str, float] = {}
    for key, fallback in defaults.items():
        value = raw.get(key, fallback)
        if not isinstance(value, (int, float)):
            raise ResumeError(f"policy.bullets.{key} must be numeric")
        layout[key] = float(value)
    # Older workspace policies copied the former defaults. Upgrade that
    # geometry while preserving independently configured indentation.
    if (layout["text_indent_pt"], layout["engagement_title_indent_pt"],
            layout["engagement_text_indent_pt"]) == (20.0, 20.0, 40.0):
        for key in ("engagement_title_indent_pt", "engagement_text_indent_pt"):
            layout[key] = defaults[key]
    if layout["text_indent_pt"] <= 0:
        raise ResumeError("policy.bullets.text_indent_pt must be positive")
    if not 0 < layout["hanging_pt"] < layout["text_indent_pt"]:
        raise ResumeError(
            "policy.bullets.hanging_pt must be positive and smaller than text_indent_pt"
        )
    if layout["marker_font_size_pt"] <= 0:
        raise ResumeError("policy.bullets.marker_font_size_pt must be positive")
    if not layout["text_indent_pt"] <= layout["engagement_title_indent_pt"] + layout["hanging_pt"]:
        raise ResumeError(
            "policy.bullets.engagement_title_indent_pt must keep an engagement title "
            "inside the role bullet margin"
        )
    if layout["engagement_text_indent_pt"] <= layout["engagement_title_indent_pt"]:
        raise ResumeError(
            "policy.bullets.engagement_text_indent_pt must be deeper than "
            "engagement_title_indent_pt"
        )
    return layout


def engagements_of(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Named engagements inside a role, or an empty list for a flat role."""
    value = entry.get("engagements")
    return value if isinstance(value, list) else []


def experience_items(model: dict[str, Any]) -> list[dict[str, str]]:
    """Every sourced achievement in Experience, role bullets and engagement
    bullets alike. Emphasis density, bullet-opening variety, and extraction
    order all need the complete list, not just the top level."""
    items: list[dict[str, str]] = []
    for entry in model.get("experience", []):
        engagements = engagements_of(entry)
        if entry.get("bullets_position") == "after_engagements":
            for engagement in engagements:
                items.extend(engagement.get("bullets", []))
            items.extend(entry.get("bullets", []))
        else:
            items.extend(entry.get("bullets", []))
            for engagement in engagements:
                items.extend(engagement.get("bullets", []))
    return items


def emphasis_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w.+#-]){re.escape(term)}(?![\w+#-])", re.IGNORECASE)


def visible_emphasis_fragments(model: dict[str, Any], sections: Iterable[str]) -> list[str]:
    items_by_section = {
        "Summary": model.get("summary", []),
        "Experience": experience_items(model),
        "Freelance Projects": [item for entry in model.get("projects", []) for item in entry["details"]],
        "Skills": [item for group in model.get("skills", []) for item in group["items"]],
    }
    return [
        fragment
        for section in sections
        for item in items_by_section.get(section, [])
        for fragment, _ in link_fragments(item)
        if fragment
    ]


def emphasis_plan(model: dict[str, Any], policy: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Terms to bold, derived from the requirements the resume actually matched.

    Deriving them instead of accepting a hand-written list keeps two promises at
    once: a bolded term is always a term the target asked for, and it always has
    selected evidence behind it — the source checker already refuses a `matched`
    requirement without both.

    Current reviewed applications select one visible phrase per matched
    requirement. Older alignment records retain their per-section alias behavior.
    Returns the selected phrases and the requirements dropped by the cap.
    """
    if model["layout"].get("emphasis", "matched-requirements") == "none":
        return [], []
    candidates = [
        requirement for requirement in model["alignment"]["requirements"]
        if requirement["status"] == "matched" and requirement.get("emphasize", True)
    ]
    # Required-and-critical first, then required, then preferred; stable within
    # each group so the model's own ordering still decides near-equal terms.
    candidates.sort(
        key=lambda requirement: (
            0 if requirement["critical"] and requirement["priority"] == "required"
            else 1 if requirement["priority"] == "required"
            else 2
        )
    )
    emphasis = policy.get("emphasis", {})
    maximum = emphasis.get("max_terms")
    excluded = {
        str(term).strip().casefold()
        for term in emphasis.get("excluded_terms", [])
        if str(term).strip()
    }
    terms: list[str] = []
    seen: set[str] = set()
    dropped: list[str] = []
    if "requirement_map_sha256" in model["alignment"]:
        fragments = visible_emphasis_fragments(model, emphasis.get("sections", []))
        for requirement in candidates:
            for raw in (requirement["term"], *requirement["aliases"]):
                term = raw.strip()
                if not term or term.casefold() in excluded:
                    continue
                pattern = emphasis_pattern(term)
                if not any(pattern.search(fragment) for fragment in fragments):
                    continue
                if term.casefold() not in seen:
                    seen.add(term.casefold())
                    if maximum and len(terms) >= maximum:
                        dropped.append(requirement["term"])
                    else:
                        terms.append(term)
                break
        return sorted(terms, key=len, reverse=True), dropped

    kept = candidates[:maximum] if maximum else candidates
    dropped = [requirement["term"] for requirement in candidates[len(kept):]]
    for requirement in kept:
        for term in [requirement["term"], *requirement["aliases"]]:
            cleaned = term.strip()
            folded = cleaned.casefold()
            if cleaned and folded not in excluded and folded not in seen:
                seen.add(folded)
                terms.append(cleaned)
    # Longest first so "Clean Architecture" wins over a nested "architecture".
    return sorted(terms, key=len, reverse=True), dropped


class Emphasizer:
    """Highlight the first occurrence of each selected phrase in reading order."""

    def __init__(self, model: dict[str, Any], policy: dict[str, Any]) -> None:
        self.terms, self.dropped = emphasis_plan(model, policy)
        self.patterns = [(term, emphasis_pattern(term)) for term in self.terms]
        self.reviewed = "requirement_map_sha256" in model["alignment"]
        self.limit = 1 if self.reviewed else int(policy.get("emphasis", {}).get("occurrences_per_term_per_section", 1))
        self.sections = set(policy.get("emphasis", {}).get("sections", []))
        self.used: dict[tuple[str, str], int] = {}
        self.per_section: dict[str, int] = {}
        self.section = ""
        self.count = 0

    def enter(self, section: str) -> None:
        self.section = section

    def active(self) -> bool:
        return bool(self.terms) and self.section in self.sections

    def split(self, text: str) -> list[tuple[str, bool]]:
        """Split text into (fragment, bold) pairs in reading order."""
        if not self.active() or not text:
            return [(text, False)]
        # Protected phrase spaces use a same-width private marker until the
        # final renderer converts them to non-breaking spaces. Search against
        # ordinary spaces so emphasis spans remain identical and can still be
        # applied inside a protected phrase such as "Clean Architecture".
        search_text = text.replace(NO_BREAK_SPACE_MARKER, " ")
        spans: list[tuple[int, int]] = []
        for term, pattern in self.patterns:
            key = ("" if self.reviewed else self.section, term.casefold())
            remaining = self.limit - self.used.get(key, 0)
            if remaining <= 0:
                continue
            for match in pattern.finditer(search_text):
                if any(match.start() < end and start < match.end() for start, end in spans):
                    continue
                spans.append((match.start(), match.end()))
                self.used[key] = self.used.get(key, 0) + 1
                self.per_section[self.section] = self.per_section.get(self.section, 0) + 1
                self.count += 1
                remaining -= 1
                if remaining <= 0:
                    break
        if not spans:
            return [(text, False)]
        parts: list[tuple[str, bool]] = []
        cursor = 0
        for start, end in sorted(spans):
            if start > cursor:
                parts.append((text[cursor:start], False))
            parts.append((text[start:end], True))
            cursor = end
        if cursor < len(text):
            parts.append((text[cursor:], False))
        return parts

    def markup(self, text: str) -> str:
        """The same split expressed as ReportLab inline markup."""
        return "".join(
            (
                f"<b>{html.escape(fragment).replace(NO_BREAK_SPACE_MARKER, '&nbsp;')}</b>"
                if bold
                else html.escape(fragment).replace(NO_BREAK_SPACE_MARKER, "&nbsp;")
            )
            for fragment, bold in self.split(text)
        )


def protected_line_phrases(model: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Return configured and target-derived phrases that must stay on one line."""
    wrapping = policy.get("line_wrap", {})
    configured = wrapping.get("protected_phrases", [])
    if not isinstance(configured, list) or not all(
        isinstance(item, str) and item.strip() for item in configured
    ):
        raise ResumeError("policy line_wrap.protected_phrases must contain non-empty strings")
    alias_max = int(wrapping.get("alignment_alias_max_words", 4))
    skill_max = int(wrapping.get("skill_item_max_words", 4))
    candidates = list(configured)
    for requirement in model.get("alignment", {}).get("requirements", []):
        candidates.extend([requirement.get("term", ""), *requirement.get("aliases", [])])
    for group in model.get("skills", []):
        candidates.extend(text_of(item) for item in group.get("items", []))

    phrases: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        phrase = re.sub(r"\s+", " ", str(candidate).strip())
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+#/-]*", phrase)
        limit = skill_max if candidate not in configured else max(skill_max, alias_max, 12)
        if not 2 <= len(words) <= limit:
            continue
        if any(mark in phrase for mark in (",", ";", ":", "(", ")")):
            continue
        folded = phrase.casefold()
        if folded not in seen:
            seen.add(folded)
            phrases.append(phrase)
    return sorted(phrases, key=lambda item: (-len(item.split()), -len(item), item.casefold()))


def protect_phrase_spaces(text: str, phrases: Iterable[str]) -> str:
    """Replace spaces inside selected phrases with an intermediate marker."""
    protected = text
    for phrase in phrases:
        escaped = re.escape(phrase).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
        protected = pattern.sub(
            lambda match: re.sub(r"\s+", NO_BREAK_SPACE_MARKER, match.group(0)),
            protected,
        )
    return protected


def sourced_list(value: Any, path: str, minimum: int = 0) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ResumeError(f"{path} must be an array with at least {minimum} item(s)")
    return [sourced(item, f"{path}[{index}]") for index, item in enumerate(value)]  # type: ignore[list-item]


# Default summary length, in words. Four to six sentences need room for the
# supported identity, relevant experience and expertise, career direction, and
# applicable mobility context. The ceiling keeps that overview compact; it is
# not permission to pad beyond the available evidence.
SUMMARY_DEFAULT_WORDS = 90
SUMMARY_MINIMUM_SENTENCES = 4
SUMMARY_MAXIMUM_SENTENCES = 6
SUMMARY_EXPERIENCE_PATTERN = re.compile(
    r"\b(\d+)\+\s+years?\s+of\s+experience\b", flags=re.IGNORECASE
)


def summary_limit(model: dict[str, Any], policy: dict[str, Any] | None = None) -> int:
    """Word limit for the summary: model override, then policy, then default."""
    if "summary_word_limit" in model["layout"]:
        return int(model["layout"]["summary_word_limit"])
    if policy:
        return int(policy.get("summary", {}).get("default_words", SUMMARY_DEFAULT_WORDS))
    return SUMMARY_DEFAULT_WORDS


def summary_sentence_count(text: str) -> int:
    """Count complete prose sentences using terminal punctuation.

    Resume summaries should avoid abbreviations that make sentence boundaries
    ambiguous. Requiring terminal punctuation also catches fragments that would
    otherwise satisfy a raw item count.
    """
    return len(re.findall(r"[.!?]+(?=(?:[\"')\]]*)\s|$)", text.strip()))


def public_resume_text(model: dict[str, Any]) -> list[tuple[str, str]]:
    """Return only text that renders publicly, excluding private targeting data."""
    sections = (
        "basics", "summary", "experience", "projects", "career_breaks", "skills",
        "languages", "education", "certifications", "awards", "activities", "hobbies",
    )
    results: list[tuple[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("text"), str):
                results.append((f"{path}.text", value["text"]))
                return
            for key, child in value.items():
                if path.startswith("skills[") and key == "name" and isinstance(child, str):
                    results.append((f"{path}.name", child))
                elif isinstance(child, (dict, list)):
                    visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    for section in sections:
        if section in model:
            visit(model[section], section)
    return results


def validate_writing_style(model: dict[str, Any], policy: dict[str, Any] | None) -> None:
    if not policy:
        return
    style = policy.get("writing_style", {})
    symbols = style.get("forbidden_symbols", {})
    terms = style.get("forbidden_terms", [])
    phrases = style.get("forbidden_phrases", [])
    typo_fixes = policy.get("proofreading", {}).get("forbidden_typos", {})
    if not isinstance(symbols, dict):
        raise ResumeError("policy writing_style.forbidden_symbols must be an object")
    if not isinstance(terms, list) or not all(isinstance(item, str) and item for item in terms):
        raise ResumeError("policy writing_style.forbidden_terms must contain non-empty strings")
    if not isinstance(phrases, list) or not all(isinstance(item, str) and item for item in phrases):
        raise ResumeError("policy writing_style.forbidden_phrases must contain non-empty strings")
    if not isinstance(typo_fixes, dict) or not all(
        isinstance(typo, str)
        and typo.strip()
        and isinstance(replacement, str)
        and replacement.strip()
        for typo, replacement in typo_fixes.items()
    ):
        raise ResumeError("policy proofreading.forbidden_typos must map typos to replacements")

    for path, text in public_resume_text(model):
        for symbol, label in symbols.items():
            if symbol in text:
                raise ResumeError(f"{path} contains forbidden {label} symbol {symbol!r}")
        for phrase in [*terms, *phrases]:
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.IGNORECASE):
                raise ResumeError(f"{path} contains forbidden AI-style wording {phrase!r}")
        for typo, replacement in typo_fixes.items():
            if re.search(rf"(?<!\w){re.escape(typo)}(?!\w)", text, flags=re.IGNORECASE):
                raise ResumeError(
                    f"{path} contains probable typo {typo!r}; use {replacement!r}"
                )


NUMBER_FORMAT_PATH = re.compile(
    r"^(?:"
    r"summary\[\d+\]|"
    r"experience\[\d+\]\.bullets\[\d+\]|"
    r"experience\[\d+\]\.engagements\[\d+\]\.bullets\[\d+\]|"
    r"projects\[\d+\]\.details\[\d+\]"
    r")\.text$"
)


def validate_number_format(model: dict[str, Any], policy: dict[str, Any] | None) -> None:
    """Keep public quantities scannable without rewriting names or credentials."""
    if not policy:
        return
    number_policy = policy.get("number_format", {})
    if not number_policy.get("digits_default", False):
        return
    spelled = number_policy.get("spelled_numbers", [])
    one_units = number_policy.get("one_count_units", [])
    if not isinstance(spelled, list) or not all(
        isinstance(item, str) and item.strip() for item in spelled
    ):
        raise ResumeError("policy number_format.spelled_numbers must contain non-empty strings")
    if not isinstance(one_units, list) or not all(
        isinstance(item, str) and item.strip() for item in one_units
    ):
        raise ResumeError("policy number_format.one_count_units must contain non-empty strings")

    patterns: list[re.Pattern[str]] = []
    if spelled:
        patterns.append(
            re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(item) for item in spelled) + r")(?!\w)",
                flags=re.IGNORECASE,
            )
        )
    if one_units:
        patterns.append(
            re.compile(
                r"(?<!\w)one\s+(?:" + "|".join(re.escape(item) for item in one_units) + r")(?!\w)",
                flags=re.IGNORECASE,
            )
        )
    for path, text in public_resume_text(model):
        if not NUMBER_FORMAT_PATH.fullmatch(path):
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                raise ResumeError(
                    f"{path} uses spelled-out quantity {match.group(0)!r}; use digits by default"
                )


def validate_quantifier_quality(model: dict[str, Any], policy: dict[str, Any] | None) -> None:
    """Reject test and source-code size metrics that can be inflated mechanically."""
    if not policy:
        return
    quality = policy.get("quantifier_quality", {})
    context_terms = quality.get("test_context_terms", [])
    units = quality.get("forbidden_test_count_units", [])
    if not isinstance(context_terms, list) or not all(
        isinstance(item, str) and item for item in context_terms
    ):
        raise ResumeError("policy quantifier_quality.test_context_terms must contain non-empty strings")
    if not isinstance(units, list) or not all(isinstance(item, str) and item for item in units):
        raise ResumeError(
            "policy quantifier_quality.forbidden_test_count_units must contain non-empty strings"
        )
    if not context_terms or not units:
        test_enabled = False
    else:
        test_enabled = True

    context_pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(item) for item in context_terms) + r")(?!\w)",
        flags=re.IGNORECASE,
    )
    count_pattern = re.compile(
        r"(?<!\w)\d[\d,]*(?:\.\d+)?\s*(?:\+|to|-)?\s*"
        r"(?:" + "|".join(re.escape(item) for item in units) + r")(?!\w)",
        flags=re.IGNORECASE,
    )
    for path, text in public_resume_text(model):
        match = count_pattern.search(text) if test_enabled and context_pattern.search(text) else None
        if match is not None:
            raise ResumeError(
                f"{path} contains a gameable testing-size count {match.group(0)!r}; "
                "describe tested behaviors, boundaries, or failure paths instead"
            )

    code_context_terms = quality.get("code_context_terms", [])
    code_units = quality.get("forbidden_code_count_units", [])
    if not isinstance(code_context_terms, list) or not all(
        isinstance(item, str) and item for item in code_context_terms
    ):
        raise ResumeError("policy quantifier_quality.code_context_terms must contain non-empty strings")
    if not isinstance(code_units, list) or not all(
        isinstance(item, str) and item for item in code_units
    ):
        raise ResumeError(
            "policy quantifier_quality.forbidden_code_count_units must contain non-empty strings"
        )
    if not code_context_terms or not code_units:
        return

    code_context_pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(item) for item in code_context_terms) + r")(?!\w)",
        flags=re.IGNORECASE,
    )
    code_count_pattern = re.compile(
        r"(?<!\w)\d[\d,]*(?:\.\d+)?\s*(?:\+)?"
        r"(?:\s*(?:to|of|-)\s*\d[\d,]*(?:\.\d+)?\s*(?:\+)?)?\s*[- ]?\s*"
        r"(?:" + "|".join(re.escape(item) for item in code_units) + r")(?!\w)",
        flags=re.IGNORECASE,
    )
    for path, text in public_resume_text(model):
        if not code_context_pattern.search(text):
            continue
        match = code_count_pattern.search(text)
        if match:
            raise ResumeError(
                f"{path} contains a gameable code-size count {match.group(0)!r}; "
                "describe the structural change or delivered capability instead"
            )


BULLET_TEXT_PATH = re.compile(
    r"^(?:"
    r"experience\[\d+\]\.bullets\[\d+\]|"
    r"experience\[\d+\]\.engagements\[\d+\]\.bullets\[\d+\]|"
    r"projects\[\d+\]\.details\[\d+\]"
    r")\.text$"
)


def validate_bullet_quality(model: dict[str, Any], policy: dict[str, Any] | None) -> None:
    """Enforce wording plus the explicit evidence-backed A-H quality review."""
    if not policy:
        return
    bullet_policy = {"bullet_quality": policy.get("bullet_quality") or {}}
    bullet_sources: dict[str, list[str]] = {}
    for path, text in public_resume_text(model):
        if not BULLET_TEXT_PATH.fullmatch(path):
            continue
        findings = bullet_text_findings(text, bullet_policy)
        if findings:
            raise ResumeError(f"{path} {findings[0]}")
        item_path = path.removesuffix(".text")
        value: Any = model
        for token in re.findall(r"[^.\[\]]+|\d+", item_path):
            value = value[int(token)] if token.isdigit() else value[token]
        refs = (
            [value["source_ref"]]
            if "source_ref" in value
            else list(value.get("source_refs") or [])
        )
        bullet_sources[item_path] = refs

    if model.get("schema_version") != 2:
        return
    reviews = model.get("bullet_quality_review")
    if not isinstance(reviews, list):
        raise ResumeError("schema_version 2 requires bullet_quality_review")
    review_by_path: dict[str, dict[str, Any]] = {}
    for index, review in enumerate(reviews):
        path = review.get("path") if isinstance(review, dict) else None
        if not isinstance(path, str) or not path:
            raise ResumeError(f"bullet_quality_review[{index}].path must be non-empty")
        if path in review_by_path:
            raise ResumeError(f"bullet_quality_review repeats path {path!r}")
        review_by_path[path] = review
    missing = set(bullet_sources) - set(review_by_path)
    unexpected = set(review_by_path) - set(bullet_sources)
    if missing or unexpected:
        raise ResumeError(
            "bullet_quality_review paths do not match public bullets; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    for path, sources in bullet_sources.items():
        findings = semantic_review_findings(
            review_by_path[path], expected_sources=sources, expected_path=path
        )
        if findings:
            raise ResumeError(f"bullet_quality_review[{path!r}] {findings[0]}")


def validate_model(model: dict[str, Any], policy: dict[str, Any] | None = None) -> None:
    required = {
        "schema_version", "application_id", "target", "layout", "basics", "experience",
        "projects", "skills", "education", "certifications", "alignment", "quantifier_review",
    }
    optional = {
        "summary", "languages", "awards", "activities", "hobbies", "career_breaks",
        "bullet_quality_review", "claim_reviews",
    }
    missing, unexpected = required - set(model), set(model) - required - optional
    if missing or unexpected:
        raise ResumeError(f"resume model keys invalid; missing={sorted(missing)}, unexpected={sorted(unexpected)}")
    if model["schema_version"] not in {1, 2}:
        raise ResumeError("resume model schema_version must be 1 or 2")
    if model["schema_version"] == 2 and "bullet_quality_review" not in model:
        raise ResumeError("resume model schema_version 2 requires bullet_quality_review")
    app_id = model["application_id"]
    if not isinstance(app_id, str) or not re.fullmatch(APPLICATION_ID_PATTERN, app_id):
        raise ResumeError("application_id is not safe or date-prefixed")
    target = model["target"]
    target_required = {
        "mode", "company", "role", "market", "market_basis", "job_country", "job_country_code",
        "location_scope", "location_basis",
    }
    target_optional = {"summary_lead"}
    if (
        not isinstance(target, dict)
        or not target_required.issubset(target)
        or set(target) - target_required - target_optional
    ):
        raise ResumeError(
            "target must contain mode, company, role, market, market_basis, job_country, job_country_code, "
            "location_scope, and location_basis, "
            "and may contain summary_lead"
        )
    for key in target_required - {"job_country", "job_country_code"}:
        if not isinstance(target[key], str) or not target[key].strip():
            raise ResumeError(f"target.{key} must be a non-empty string")
    if target["job_country"] is not None and (
        not isinstance(target["job_country"], str) or not target["job_country"].strip()
    ):
        raise ResumeError("target.job_country must be null or a non-empty string")
    if target["job_country_code"] is not None and (
        not isinstance(target["job_country_code"], str)
        or not re.fullmatch(r"[A-Z]{2}", target["job_country_code"])
    ):
        raise ResumeError("target.job_country_code must be null or an ISO 3166-1 alpha-2 code")
    if (target["job_country"] is None) != (target["job_country_code"] is None):
        raise ResumeError("target.job_country and target.job_country_code must both be set or both be null")
    if target["mode"] not in {"master", "job-targeted"}:
        raise ResumeError("target.mode must be master or job-targeted")
    if target["market"] not in {"europe", "north-america"}:
        raise ResumeError("target.market must be europe or north-america")
    if target["market_basis"] not in {"job-location", "profile-default", "user-override"}:
        raise ResumeError("target.market_basis is invalid")
    if target["location_scope"] not in {
        "same-country", "outside-country", "location-independent", "unspecified"
    }:
        raise ResumeError("target.location_scope is invalid")
    if target["location_basis"] not in {
        "job-description", "job-url", "user-request", "unresolved"
    }:
        raise ResumeError("target.location_basis is invalid")
    layout = model["layout"]
    layout_keys = {
        "page_target",
        "summary_word_limit",
        "page_break_before",
        "hyperlinks",
        "emphasis",
        "activities_heading",
    }
    if (
        not isinstance(layout, dict)
        or "page_target" not in layout
        or set(layout) - layout_keys
        or layout["page_target"] not in {1, 2}
    ):
        raise ResumeError("layout must contain page_target of 1 or 2 and may contain summary_word_limit")
    if layout.get("hyperlinks", "auto") not in {"auto", "off"}:
        raise ResumeError("layout.hyperlinks must be auto or off")
    if layout.get("emphasis", "matched-requirements") not in {"matched-requirements", "none"}:
        raise ResumeError("layout.emphasis must be matched-requirements or none")
    if "activities_heading" in layout and (
        not isinstance(layout["activities_heading"], str)
        or not layout["activities_heading"].strip()
        or len(layout["activities_heading"].strip()) > 40
    ):
        raise ResumeError("layout.activities_heading must be a non-empty string of at most 40 characters")
    summary_policy = (policy or {}).get("summary", {})
    minimum_override = int(summary_policy.get("minimum_override", 40))
    maximum_override = int(summary_policy.get("maximum_override", 120))
    if "summary_word_limit" in layout and (
        not isinstance(layout["summary_word_limit"], int)
        or not minimum_override <= layout["summary_word_limit"] <= maximum_override
    ):
        raise ResumeError(
            "layout.summary_word_limit must be an integer from "
            f"{minimum_override} to {maximum_override}"
        )
    if "page_break_before" in layout and layout["page_break_before"] not in {"selected-projects"}:
        raise ResumeError("layout.page_break_before must be selected-projects when present")
    if "page_break_before" in layout and layout["page_target"] != 2:
        raise ResumeError("layout.page_break_before is only valid when page_target is 2")

    basics = model["basics"]
    if not isinstance(basics, dict) or set(basics) != {"name", "title", "contact", "links", "mobility"}:
        raise ResumeError("basics must contain exactly name, title, contact, links, and mobility")
    sourced(basics["name"], "basics.name")
    sourced(basics["title"], "basics.title")
    sourced_list(basics["contact"], "basics.contact", 1)
    sourced_list(basics["links"], "basics.links")
    sourced(basics["mobility"], "basics.mobility", nullable=True)
    mobility_required = (
        target["mode"] == "master" or target["location_scope"] == "outside-country"
    )
    if mobility_required and basics["mobility"] is None:
        raise ResumeError(
            "basics.mobility is required for master resumes and outside-country jobs"
        )
    if basics["mobility"] is not None:
        mobility_refs = (
            [basics["mobility"].get("source_ref")]
            if basics["mobility"].get("source_ref")
            else list(basics["mobility"].get("source_refs") or [])
        )
        if not any(str(ref).startswith("profile-eligibility-") for ref in mobility_refs):
            raise ResumeError(
                "basics.mobility must cite a profile-eligibility relocation source"
            )
    summary = sourced_list(model.get("summary", []), "summary")
    summary_text = " ".join(text_of(item) for item in summary)
    limit = summary_limit(model, policy)
    if summary and len(re.findall(r"\b[\w’'-]+\b", summary_text)) > limit:
        raise ResumeError(f"summary exceeds the {limit}-word limit")
    if summary:
        minimum_sentences = int(
            summary_policy.get("minimum_sentences", SUMMARY_MINIMUM_SENTENCES)
        )
        maximum_sentences = int(
            summary_policy.get("maximum_sentences", SUMMARY_MAXIMUM_SENTENCES)
        )
        if minimum_sentences < 1 or maximum_sentences < minimum_sentences:
            raise ResumeError(
                "policy.summary sentence bounds must be positive and ordered"
            )
        sentence_count = summary_sentence_count(summary_text)
        if not minimum_sentences <= sentence_count <= maximum_sentences:
            raise ResumeError(
                "summary must contain "
                f"{minimum_sentences} to {maximum_sentences} complete sentences; "
                f"found {sentence_count}"
            )
        claims: list[tuple[dict[str, Any], re.Match[str]]] = []
        for item in summary:
            claims.extend((item, match) for match in SUMMARY_EXPERIENCE_PATTERN.finditer(text_of(item)))
        if len(claims) != 1:
            raise ResumeError(
                "summary must contain exactly one N+ years of experience figure"
            )
        claim_item, claim_match = claims[0]
        first_sentence_end = re.search(r"[.!?]", summary_text)
        if first_sentence_end and claim_match.group(0) not in summary_text[: first_sentence_end.end()]:
            raise ResumeError("the years-of-experience figure must appear in the first summary sentence")
        refs = (
            [claim_item.get("source_ref")]
            if claim_item.get("source_ref")
            else list(claim_item.get("source_refs") or [])
        )
        if not any(str(ref).startswith("profile-experience-") for ref in refs):
            raise ResumeError(
                "the years-of-experience figure must cite at least one profile-experience source"
            )
    if target["mode"] == "job-targeted":
        lead = target.get("summary_lead")
        if not lead:
            raise ResumeError("job-targeted resumes require target.summary_lead")
        # The source checker anchors the lead to the profile identity, not a tailored header.
        if not summary:
            raise ResumeError("job-targeted resumes with target.summary_lead require a summary")
        if not summary_text.casefold().startswith(lead.casefold()):
            raise ResumeError(
                "job-targeted summary must begin with target.summary_lead "
                f"({lead!r})"
            )

    experience = model["experience"]
    if not isinstance(experience, list) or not experience:
        raise ResumeError("experience must contain at least one entry")
    experience_keys = {"organization", "title", "location", "start", "end", "bullets"}
    budget = (policy or {}).get("experience_budget", {})
    engagements_max = int(budget.get("engagements_max", 4))
    engagement_bullets_max = int(budget.get("engagement_bullets_max", 2))
    for index, entry in enumerate(experience):
        path = f"experience[{index}]"
        if not isinstance(entry, dict) or not experience_keys <= set(entry):
            raise ResumeError(f"{path} has invalid keys")
        if set(entry) - experience_keys - {"engagements", "bullets_position"}:
            raise ResumeError(f"{path} has invalid keys")
        if entry.get("bullets_position", "before_engagements") not in {
            "before_engagements",
            "after_engagements",
        }:
            raise ResumeError(
                f"{path}.bullets_position must be before_engagements or after_engagements"
            )
        for key in ("organization", "title", "start", "end"):
            sourced(entry[key], f"{path}.{key}")
        sourced(entry["location"], f"{path}.location", nullable=True)
        bullets = sourced_list(entry["bullets"], f"{path}.bullets", 1)
        if len(bullets) > 4:
            raise ResumeError(f"{path} has more than four bullets")

        # Named engagements. Structural bounds only; how many is an editorial
        # decision surfaced through warnings, because the whole point of this
        # structure is to stop policy from truncating a dense role.
        if "engagements" in entry:
            engagements = entry["engagements"]
            if not isinstance(engagements, list) or not engagements:
                raise ResumeError(f"{path}.engagements must be a non-empty array when present")
            if len(engagements) > engagements_max + 1:
                raise ResumeError(
                    f"{path} has {len(engagements)} engagements; "
                    f"{engagements_max} is the editorial maximum and "
                    f"{engagements_max + 1} the structural limit"
                )
            for position, engagement in enumerate(engagements):
                sub = f"{path}.engagements[{position}]"
                if not isinstance(engagement, dict) or not {"name", "bullets"} <= set(engagement):
                    raise ResumeError(f"{sub} must contain name and bullets")
                if set(engagement) - {"name", "context", "bullets"}:
                    raise ResumeError(f"{sub} has invalid keys")
                sourced(engagement["name"], f"{sub}.name")
                # A name is a label, not a sentence. Overlong ones only surfaced
                # as an unexplained page overflow, so say what actually happened.
                if len(text_of(engagement["name"])) > 60:
                    raise ResumeError(
                        f"{sub}.name is {len(text_of(engagement['name']))} characters; an "
                        "engagement name is a short project label, not a bullet"
                    )
                sourced(engagement.get("context"), f"{sub}.context", nullable=True)
                sub_bullets = sourced_list(engagement["bullets"], f"{sub}.bullets", 1)
                if len(sub_bullets) > engagement_bullets_max + 1:
                    raise ResumeError(
                        f"{sub} has {len(sub_bullets)} bullets; "
                        f"{engagement_bullets_max} is the editorial maximum"
                    )

    if not isinstance(model["skills"], list):
        raise ResumeError("skills must be an array")
    for index, group in enumerate(model["skills"]):
        if not isinstance(group, dict) or set(group) != {"name", "items"} or not isinstance(group["name"], str) or not group["name"].strip():
            raise ResumeError(f"skills[{index}] must contain a non-empty name and items")
        sourced_list(group["items"], f"skills[{index}].items", 1)

    entry_keys = {"primary", "secondary", "date", "details"}
    minimum_projects = int(
        (policy or {}).get("selected_projects", {}).get("minimum_distinct_projects", 0)
    )
    if not isinstance(model["projects"], list) or len(model["projects"]) < minimum_projects:
        raise ResumeError(
            f"projects must contain at least {minimum_projects} Freelance Projects entries"
        )
    for section in ("projects", "education", "certifications", "awards", "activities"):
        entries = model.get(section, [])
        if not isinstance(entries, list):
            raise ResumeError(f"{section} must be an array")
        for index, entry in enumerate(entries):
            path = f"{section}[{index}]"
            if not isinstance(entry, dict) or set(entry) != entry_keys:
                raise ResumeError(f"{path} has invalid keys")
            sourced(entry["primary"], f"{path}.primary")
            sourced(entry["secondary"], f"{path}.secondary", nullable=True)
            sourced(entry["date"], f"{path}.date", nullable=True)
            sourced_list(entry["details"], f"{path}.details")
    for section in ("languages", "hobbies"):
        sourced_list(model.get(section, []), section)
    for index, entry in enumerate(model.get("career_breaks", [])):
        path = f"career_breaks[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"label", "start", "end", "details"}:
            raise ResumeError(f"{path} has invalid keys")
        for key in ("label", "start", "end"):
            sourced(entry[key], f"{path}.{key}")
        sourced_list(entry["details"], f"{path}.details")

    alignment = model["alignment"]
    if (not isinstance(alignment, dict) or set(alignment) - {"requirement_map_sha256"} != {"requirements"}
            or not isinstance(alignment["requirements"], list)):
        raise ResumeError("alignment must contain requirements")
    mapped_alignment = "requirement_map_sha256" in alignment
    if mapped_alignment and not re.fullmatch(r"[a-f0-9]{64}", str(alignment["requirement_map_sha256"])):
        raise ResumeError("alignment.requirement_map_sha256 must identify the reviewed map revision")
    for index, requirement in enumerate(alignment["requirements"]):
        path = f"alignment.requirements[{index}]"
        required_keys = {"term", "aliases", "priority", "critical", "status", "evidence_refs"}
        if mapped_alignment:
            required_keys.add("requirement_id")
        optional_keys = {"emphasize", "selection_reason"}
        if not isinstance(requirement, dict) or set(requirement) - optional_keys != required_keys:
            raise ResumeError(f"{path} has invalid keys")
        if "emphasize" in requirement and not isinstance(requirement["emphasize"], bool):
            raise ResumeError(f"{path}.emphasize must be true or false")
        if "selection_reason" in requirement and (
            not isinstance(requirement["selection_reason"], str)
            or not requirement["selection_reason"].strip()
        ):
            raise ResumeError(f"{path}.selection_reason must be a non-empty string")
        if not isinstance(requirement["term"], str) or not requirement["term"].strip():
            raise ResumeError(f"{path}.term must be non-empty")
        if not isinstance(requirement["aliases"], list) or not all(isinstance(item, str) and item.strip() for item in requirement["aliases"]):
            raise ResumeError(f"{path}.aliases must be non-empty strings")
        if requirement["priority"] not in {"required", "preferred"} or not isinstance(requirement["critical"], bool):
            raise ResumeError(f"{path} priority or critical value is invalid")
        statuses = {"matched", "not_emphasized"} if mapped_alignment else {"matched", "supported_not_selected", "unsupported"}
        if requirement["status"] not in statuses:
            raise ResumeError(f"{path}.status is invalid")
        if mapped_alignment and not re.fullmatch(r"req-[a-f0-9]{16}", str(requirement["requirement_id"])):
            raise ResumeError(f"{path}.requirement_id is invalid")
        if not isinstance(requirement["evidence_refs"], list) or not all(isinstance(item, str) and item.strip() for item in requirement["evidence_refs"]):
            raise ResumeError(f"{path}.evidence_refs must be an array of IDs")
        has_evidence = bool(requirement["evidence_refs"])
        if has_evidence != (requirement["status"] in {"matched", "supported_not_selected"}):
            raise ResumeError(f"{path} has inconsistent evidence_refs for {requirement['status']}")
        # `selection_reason` records why a selection decision was made, and that
        # applies to every status. An earlier version banned it on `unsupported`
        # on the theory that there is nothing to explain when no evidence exists.
        # That was wrong, and it deadlocked against the understatement gate: a
        # requirement can be `unsupported` BECAUSE the available evidence was
        # judged insufficient to claim it, which is precisely the decision most
        # worth recording. The Capgemini banking-domain requirement is the case
        # that exposed it. The checker demanded a reason; this rule forbade one.
        #
        # No status restriction remains. The field is validated as a non-empty
        # string above, and a reason on a genuinely empty requirement is
        # harmless documentation rather than a defect.
        if (
            target["mode"] == "job-targeted"
            and requirement["priority"] == "required"
            and requirement["status"] == "supported_not_selected"
            and "selection_reason" not in requirement
        ):
            raise ResumeError(
                f"{path} is a supported required job requirement and needs selection_reason"
            )
    quantifiers = model["quantifier_review"]
    if not isinstance(quantifiers, dict) or set(quantifiers) != {"used", "available_not_used", "opportunities"}:
        raise ResumeError("quantifier_review must contain used, available_not_used, and opportunities")
    for key in quantifiers:
        if not isinstance(quantifiers[key], list) or not all(isinstance(item, str) and item.strip() for item in quantifiers[key]):
            raise ResumeError(f"quantifier_review.{key} must be an array of non-empty strings")
    validate_writing_style(model, policy)
    validate_number_format(model, policy)
    validate_quantifier_quality(model, policy)
    validate_bullet_quality(model, policy)


def run_source_check(
    model: Path,
    profile: Path,
    projects: Path,
    ranking: Path | None = None,
    index: Path | None = None,
    policy: Path | None = None,
    require_claim_reviews: bool = False,
    editorial_packet: bool = False,
    decisions: dict | None = None,
) -> dict[str, Any]:
    checker = Path(__file__).with_name("resume_source_check.rb")
    command = ["ruby", str(checker), "--model", str(model), "--profile", str(profile), "--projects", str(projects)]
    if require_claim_reviews:
        command.append("--require-claim-reviews")
    if editorial_packet:
        command.append("--editorial-packet")
    if ranking is not None and ranking.is_file():
        command += ["--ranking", str(ranking)]
    # The evidence index powers the understatement gate. Default to the one
    # beside the repository root so callers do not have to pass it.
    if index is None:
        index = profile.parent.parent / "index" / "evidence-index.yaml"
    if index.is_file():
        command += ["--index", str(index)]
    rubric = Path(config_path("review-rubric.json", str(projects.parent)))
    if rubric.is_file():
        command += ["--rubric", str(rubric)]
    if policy is None:
        policy = Path(config_path("resume-policy.json", str(projects.parent)))
    if policy.is_file():
        command += ["--policy", str(policy)]
    with tempfile.TemporaryDirectory(prefix="ekb-source-check-") as directory:
        if decisions is not None:
            decision_path = Path(directory) / "requirements.json"
            decision_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
            command += ["--decision-map", str(decision_path)]
        process = subprocess.run(
            command, text=True, capture_output=True, check=False,
            env={**os.environ, "EKB_PYTHON": sys.executable},
        )
    if not process.stdout.strip():
        raise ResumeError(f"source validation failed: {process.stderr.strip() or 'no report produced'}")
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ResumeError(f"source validator returned invalid JSON: {exc}") from exc
    if process.returncode not in (0, 1):
        raise ResumeError(process.stderr.strip() or "source validator could not run")
    return report


def coverage_section(source_report: dict[str, Any]) -> str:
    """One-line coverage summary for the validation report header.

    `demonstrated` means an achievement shows the capability; `stated` means the
    resume only claims it, usually through the Skills list. The distinction is
    what a reviewer scores, so it belongs above the fold."""
    counts = source_report.get("coverage", {}).get("counts") or {}
    if not counts:
        return ""
    order = sorted(counts) if source_report.get("requirement_map") else ["demonstrated", "stated", "unsupported"]
    parts = [f"{counts[key]} {key}" for key in order if counts.get(key)]
    line = f"- Requirement coverage: {', '.join(parts)}\n"
    if not source_report.get("requirement_map") and not source_report.get("checks", {}).get("evidence_index_loaded", True):
        line += "- Evidence index: not loaded (understatement gate inactive)\n"
    return line


def selection_score_section(source_report: dict[str, Any]) -> str:
    """Private selection score against `config/review-rubric.json`.

    Scores how well the resume used the evidence available to it, NOT the
    candidate's fit. Requirements with no eligible evidence are excluded, so an
    honest gap cannot lower it, and it is not a prediction of any external
    reviewer's number."""
    score = source_report.get("selection_score")
    if not score:
        return ""
    parts = []
    for name, entry in (score.get("dimensions") or {}).items():
        value = entry.get("value")
        parts.append(f"{name} {value if value is not None else 'n/a'}")
    line = (
        f"- Selection score: {score['score']}/100 "
        f"(rubric v{score.get('rubric_version')}; "
        f"{score.get('scoreable_required')} scoreable required requirements, "
        f"{score.get('excluded_no_evidence')} excluded as genuine gaps)\n"
    )
    if parts:
        line += f"  - {', '.join(parts)}\n"
    return line


def external_signals_section(source_report: dict[str, Any]) -> str:
    """What the separate resume-review prompt is likely to penalize.

    Reported apart from the selection score on purpose. The selection score
    excludes requirements the knowledge base cannot answer, because those are
    not the toolkit's failure; the external reviewer weighs them anyway, so its
    blind spot is exactly what belongs here."""
    signals = source_report.get("external_signals")
    if not signals:
        return ""
    lines = ["\n## Likely external review findings\n"]
    seniority = signals.get("seniority")
    if seniority:
        verdict = "meets" if seniority["status"] == "met" else "below"
        lines.append(
            f"- Seniority: posting asks {seniority['required_years']}+ years, "
            f"confirmed timeline is {seniority['confirmed_years']} years ({verdict}). "
            "State this plainly; never narrow it in the document.\n"
        )
    if signals.get("unsupported_critical"):
        lines.append(
            f"- {signals['unsupported_critical']} critical requirement(s) have no eligible evidence.\n"
        )
    gap = signals.get("keyword_gap") or []
    if gap:
        fixable = signals.get("keyword_gap_fixable", 0)
        lines.append(
            f"\nKeyword gap ({len(gap)} terms, {fixable} fixable from existing evidence). "
            "A reviewer's missing-keyword list will draw from these:\n\n"
        )
        lines.append("| Term | Coverage | Priority | Fixable here |\n| --- | --- | --- | --- |\n")
        for entry in gap:
            priority = entry["priority"] + (", critical" if entry.get("critical") else "")
            fix = "yes, evidence exists" if entry.get("fixable") else "no, real gap"
            lines.append(f"| {entry['term']} | {entry['coverage']} | {priority} | {fix} |\n")
    return "".join(lines)


def coverage_table(source_report: dict[str, Any]) -> str:
    """Per-requirement detail.

    Critical stated capabilities show their strongest unused project evidence.
    Non-critical stated tools remain visible as `claimed` without pressuring the
    draft to turn a routine matching record into an achievement.
    """
    requirements = source_report.get("coverage", {}).get("requirements") or []
    if not requirements:
        return ""
    if source_report.get("requirement_map"):
        def cell(value):
            return str(value).replace("|", "&#124;").replace("\n", " ")

        rows = ["| " + " | ".join(cell(entry[key]) for key in
                ("id", "term", "priority", "fit", "disposition", "reason")) + " |"
                for entry in requirements]
        return (
            "\n## Requirement coverage\n\n"
            "| ID | Requirement | Priority | Reviewed fit | Disposition | Reason |\n"
            "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
        )
    rows = []
    for entry in requirements:
        unused = ", ".join(entry.get("unused_candidates") or []) or "-"
        reason = entry.get("selection_reason") or ""
        marker = {"demonstrated": "shown", "stated": "claimed", "unsupported": "absent"}.get(
            entry.get("coverage", ""), entry.get("coverage", "")
        )
        rows.append(
            f"| {entry.get('term', '')} | {entry.get('priority', '')} | {marker} | "
            f"{unused} | {reason} |"
        )
    return (
        "\n## Requirement coverage\n\n"
        "| Requirement | Priority | Coverage | Strongest unused | Reason |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    )


def text_of(value: dict[str, str] | None) -> str:
    return "" if value is None else value["text"].strip()


def resume_lines(model: dict[str, Any]) -> list[str]:
    basics = model["basics"]
    lines = [text_of(basics["name"]), text_of(basics["title"])]
    contact = [text_of(item) for item in basics["contact"] + basics["links"]]
    if contact:
        lines.append(" | ".join(contact))
    if basics["mobility"] is not None:
        lines.append(text_of(basics["mobility"]))
    summary = model.get("summary", [])
    if summary:
        lines.append("SUMMARY")
        lines.append(" ".join(text_of(item) for item in summary))
    lines.append("EXPERIENCE")
    for entry in model["experience"]:
        lines.append(" | ".join(part for part in (text_of(entry["organization"]), text_of(entry["title"])) if part))
        date_location = " | ".join(
            part
            for part in (f"{text_of(entry['start'])} - {text_of(entry['end'])}", text_of(entry["location"]))
            if part
        )
        lines.append(date_location)
        role_bullets_after = entry.get("bullets_position") == "after_engagements"
        if not role_bullets_after:
            lines.extend(f"• {text_of(item)}" for item in entry["bullets"])
        engagements = engagements_of(entry)
        if engagements:
            lines.append(f"  {ROLE_PROJECTS_HEADING}")
        for engagement in engagements:
            lines.append(
                "    " + " | ".join(
                    part
                    for part in (text_of(engagement["name"]), text_of(engagement.get("context")))
                    if part
                )
            )
            lines.extend(f"      • {text_of(item)}" for item in engagement["bullets"])
        if role_bullets_after:
            lines.extend(f"• {text_of(item)}" for item in entry["bullets"])
    if model.get("projects"):
        lines.append("FREELANCE PROJECTS")
        for entry in model["projects"]:
            main = " | ".join(
                part
                for part in (text_of(entry["primary"]), text_of(entry["secondary"]), text_of(entry["date"]))
                if part
            )
            lines.append(main)
            lines.extend(f"• {text_of(item)}" for item in entry["details"])
    if model.get("career_breaks"):
        lines.append("CAREER BREAKS")
        for entry in model["career_breaks"]:
            lines.append(text_of(entry["label"]))
            lines.append(f"{text_of(entry['start'])} - {text_of(entry['end'])}")
            lines.extend(text_of(item) for item in entry["details"])
    if model["skills"]:
        lines.append("SKILLS")
        for group in model["skills"]:
            lines.append(f"{group['name']}: {', '.join(text_of(item) for item in group['items'])}")
    if model.get("languages"):
        lines.append("LANGUAGES")
        lines.append(", ".join(text_of(item) for item in model["languages"]))
    for key, heading in supporting_sections(model):
        if model.get(key):
            lines.append(heading.upper())
            for entry in model[key]:
                main = " | ".join(part for part in (text_of(entry["primary"]), text_of(entry["secondary"]), text_of(entry["date"])) if part)
                lines.append(main)
                lines.extend(text_of(item) for item in entry["details"])
    if model.get("hobbies"):
        lines.append("INTERESTS")
        lines.append(", ".join(text_of(item) for item in model["hobbies"]))
    return [line for line in lines if line]


def text_export_lines(model: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Plain-text export. TXT has no annotation layer, so a hyperlink either
    becomes a visible address or is lost; `policy.links.text_export` decides.
    """
    if policy.get("links", {}).get("text_export") != "append-url" or not links_enabled(model):
        return resume_lines(model)

    def bare(value: str) -> str:
        return re.sub(r"^(https://|mailto:|tel:)", "", normalize(value)).rstrip("/")

    targets: list[tuple[str, str]] = []
    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if "text" in value and ("source_ref" in value or "source_refs" in value):
                url = url_of(value)
                label = link_text_of(value) or text_of(value)
                # Skip anything whose visible text already is the address. This
                # remains useful for custom policies even though the shipped
                # policy keeps profile addresses behind labels.
                if url and bare(url) != bare(label):
                    targets.append((label, url))
                return
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(model)
    lines = resume_lines(model)
    for label, url in targets:
        needle = normalize(label)
        for index, line in enumerate(lines):
            if needle and needle in normalize(line) and url not in line:
                lines[index] = re.sub(
                    rf"({re.escape(label)})(?! \()", rf"\1 ({url})", line, count=1
                )
                break
    return lines


def page_size(model: dict[str, Any], policy: dict[str, Any]) -> tuple[float, float]:
    sizes = policy.get("page_sizes", {})
    market = model["target"]["market"]
    name = sizes.get(market)
    if name == "A4":
        return A4
    if name == "LETTER":
        return LETTER
    raise ResumeError(f"policy has no page size for {market}")


def continuation_contact(model: dict[str, Any]) -> str:
    basics = model["basics"]
    values = [text_of(basics["name"])] + [text_of(item) for item in basics["contact"] + basics["links"]]
    return " | ".join(value for value in values if value)


def add_docx_hyperlink(
    paragraph: Any,
    text: str,
    url: str,
    font: str,
    size: float,
    bold: bool = False,
    color: str = "0563C1",
    underline: bool = True,
) -> None:
    """Append a clickable run. python-docx has no hyperlink API, so build the
    OOXML w:hyperlink element and its external relationship directly.

    The visible text is whatever the model supplies; keep it meaningful, because
    text-only ATS parsers read the run text and discard the relationship target.
    """
    r_id = paragraph.part.relate_to(url, DOCX_RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "Hyperlink")
    properties.append(style)
    link_color = OxmlElement("w:color")
    link_color.set(qn("w:val"), color)
    properties.append(link_color)
    if underline:
        link_underline = OxmlElement("w:u")
        link_underline.set(qn("w:val"), "single")
        properties.append(link_underline)
    hyperlink.append(run)
    run.append(properties)
    append_docx_text(run, text)
    paragraph._p.append(hyperlink)
    # Re-apply every visible property rather than depending on a viewer's
    # Hyperlink style, which is not consistent across Word-compatible apps.
    rpr_font = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rpr_font.set(qn(attr), font)
    properties.append(rpr_font)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    properties.append(sz)
    if bold:
        properties.append(OxmlElement("w:b"))


def add_docx_sourced_runs(
    paragraph: Any,
    model: dict[str, Any],
    item: dict[str, str],
    policy: dict[str, Any],
    emphasizer: Emphasizer | None = None,
    bold: bool = False,
) -> None:
    """Render one sourced item, retaining emphasis inside an optional link."""
    font = policy["fonts"]["primary"]
    size = policy["sizes_pt"]["body"]
    target = link_of(model, item)
    color, underline = link_appearance(policy)
    phrases = protected_line_phrases(model, policy)
    for link_fragment, is_linked in link_fragments(item):
        protected_fragment = protect_phrase_spaces(link_fragment, phrases)
        fragments = (
            emphasizer.split(protected_fragment)
            if emphasizer
            else [(protected_fragment, False)]
        )
        for fragment, emphasized in fragments:
            if not fragment:
                continue
            fragment_bold = bold or emphasized
            if target and is_linked:
                add_docx_hyperlink(
                    paragraph,
                    fragment,
                    target,
                    font,
                    size,
                    bold=fragment_bold,
                    color=color,
                    underline=underline,
                )
            else:
                set_run_font(paragraph.add_run(fragment), font, size, bold=fragment_bold)


def append_docx_text(run_element: Any, text: str) -> None:
    """Append portable non-breaking compounds and protected phrase spaces.

    Some viewers omit OOXML's special ``w:noBreakHyphen`` element entirely,
    producing visible typos such as ``customerfacing``. A literal non-breaking
    hyphen is more portable in DOCX; the PDF renderer continues to use the
    source model's ASCII hyphen.
    """
    visible = text.replace(NO_BREAK_SPACE_MARKER, "\u00a0")
    visible = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", "\u2011", visible)
    node = OxmlElement("w:t")
    node.text = visible
    node.set(qn("xml:space"), "preserve")
    run_element.append(node)


def protect_docx_run_words(run: Any) -> None:
    text = run.text
    if NO_BREAK_SPACE_MARKER not in text and not re.search(
        r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", text
    ):
        return
    run.clear()
    append_docx_text(run._r, text)


def set_run_font(run: Any, name: str, size: float, bold: bool | None = None, color: RGBColor | None = None) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    protect_docx_run_words(run)


def add_docx_section_heading(document: Document, label: str, policy: dict[str, Any]) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(policy["spacing_pt"]["section_before"])
    paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["section_after"])
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(label.upper())
    set_run_font(run, policy["fonts"]["primary"], policy["sizes_pt"]["section"], bold=True)
    paragraph._p.get_or_add_pPr().append(_bottom_border())


def _bottom_border(*, color: str = "666666", size: str = "4") -> Any:
    from docx.oxml import OxmlElement

    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    return borders


def configure_docx_bullet_marker(document: Document, policy: dict[str, Any]) -> None:
    """Use a portable round glyph for real Word list numbering.

    The default python-docx template uses a private-use Symbol-font character
    for List Bullet. Some Word installations cannot map that character and
    render a hollow rectangle. Keep the list as real numbering, but replace the
    marker with U+2022 in the document font so it is portable across viewers.
    """
    layout = bullet_layout(policy)
    numbering = document.part.numbering_part.element
    for abstract_numbering in numbering.findall(qn("w:abstractNum")):
        for level in abstract_numbering.findall(qn("w:lvl")):
            paragraph_style = level.find(qn("w:pStyle"))
            if (
                paragraph_style is None
                or paragraph_style.get(qn("w:val")) != "ListBullet"
            ):
                continue
            run_properties = level.find(qn("w:rPr"))
            if run_properties is None:
                run_properties = OxmlElement("w:rPr")
                level.append(run_properties)

            level_text = level.find(qn("w:lvlText"))
            if level_text is None:
                level_text = OxmlElement("w:lvlText")
                level.append(level_text)
            level_text.set(qn("w:val"), "•")

            run_fonts = run_properties.find(qn("w:rFonts"))
            if run_fonts is None:
                run_fonts = OxmlElement("w:rFonts")
                run_properties.append(run_fonts)
            for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                run_fonts.set(qn(attribute), policy["fonts"]["primary"])

            marker_size = str(round(layout["marker_font_size_pt"] * 2))
            for tag in ("w:sz", "w:szCs"):
                size = run_properties.find(qn(tag))
                if size is None:
                    size = OxmlElement(tag)
                    run_properties.append(size)
                size.set(qn("w:val"), marker_size)

            position = run_properties.find(qn("w:position"))
            if position is None:
                position = OxmlElement("w:position")
                run_properties.append(position)
            position.set(
                qn("w:val"),
                str(round(layout["marker_vertical_offset_pt"] * 2)),
            )
            return
    raise ResumeError("DOCX template does not contain the List Bullet numbering definition")


def render_docx(model: dict[str, Any], policy: dict[str, Any], output: Path) -> Emphasizer:
    emphasizer = Emphasizer(model, policy)
    hyperlink_color, hyperlink_underline = link_appearance(policy)
    document = Document()
    section = document.sections[0]
    width, height = page_size(model, policy)
    section.page_width = Inches(width / inch)
    section.page_height = Inches(height / inch)
    margins = policy["margins_inches"]
    section.top_margin = Inches(margins.get("docx_top", margins["top"]))
    section.right_margin = Inches(margins["right"])
    # LibreOffice paginates the final supporting line more conservatively than
    # ReportLab.  A format-specific bottom margin keeps the one-page DOCX in
    # parity with the validated PDF without shrinking the shared type scale.
    section.bottom_margin = Inches(margins.get("docx_bottom", margins["bottom"]))
    section.left_margin = Inches(margins["left"])
    # A continuation header has no purpose in a one-page resume. Omitting the
    # header part entirely also prevents Word-compatible viewers and ATS tools
    # from exposing the contact line twice on page one.
    if model["layout"]["page_target"] == 2:
        section.different_first_page_header_footer = True
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        header.paragraph_format.space_after = Pt(0)
        set_run_font(
            header.add_run(continuation_contact(model)),
            policy["fonts"]["primary"],
            policy["sizes_pt"]["small"],
        )

    normal = document.styles["Normal"]
    normal.font.name = policy["fonts"]["primary"]
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), policy["fonts"]["primary"])
    normal.font.size = Pt(policy["sizes_pt"]["body"])
    normal.paragraph_format.space_after = Pt(policy["spacing_pt"]["paragraph_after"])
    normal.paragraph_format.line_spacing = float(
        policy["spacing_pt"].get(
            "docx_line_spacing_multiple",
            policy["spacing_pt"].get("line_spacing_multiple", 1.0),
        )
    )
    configure_docx_bullet_marker(document, policy)
    bullets = bullet_layout(policy)

    name = document.add_paragraph()
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name.paragraph_format.space_after = Pt(1)
    set_run_font(name.add_run(text_of(model["basics"]["name"])), policy["fonts"]["primary"], policy["sizes_pt"]["name"], bold=True)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(2)
    set_run_font(
        title.add_run(text_of(model["basics"]["title"])),
        policy["fonts"]["primary"],
        policy["sizes_pt"]["body"],
    )

    contact_items = model["basics"]["contact"] + model["basics"]["links"]
    if contact_items:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(4)
        font, size = policy["fonts"]["primary"], policy["sizes_pt"]["small"]
        for index, item in enumerate(contact_items):
            if index:
                set_run_font(paragraph.add_run(" | "), font, size)
            target = link_of(model, item)
            if target:
                add_docx_hyperlink(
                    paragraph,
                    text_of(item),
                    target,
                    font,
                    size,
                    color=hyperlink_color,
                    underline=hyperlink_underline,
                )
            else:
                set_run_font(paragraph.add_run(text_of(item)), font, size)

    mobility = model["basics"]["mobility"]
    if mobility is not None:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(4)
        set_run_font(
            paragraph.add_run(text_of(mobility)),
            policy["fonts"]["primary"],
            policy["sizes_pt"]["small"],
        )

    summary = model.get("summary", [])
    if summary:
        emphasizer.enter("Summary")
        add_docx_section_heading(document, "Summary", policy)
        paragraph = document.add_paragraph()
        for index, item in enumerate(summary):
            if index:
                set_run_font(
                    paragraph.add_run(" "),
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                )
            add_docx_sourced_runs(paragraph, model, item, policy, emphasizer)
        paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["paragraph_after"])

    emphasizer.enter("Experience")
    add_docx_section_heading(document, "Experience", policy)
    for entry_index, entry in enumerate(model["experience"]):
        heading = document.add_paragraph()
        heading.paragraph_format.keep_with_next = True
        heading.paragraph_format.space_before = Pt(
            policy["spacing_pt"].get("experience_entry_before", 0) if entry_index else 0
        )
        heading.paragraph_format.space_after = Pt(
            policy["spacing_pt"].get("entry_heading_after", 0)
        )
        organization_url = link_of(model, entry["organization"])
        if organization_url:
            add_docx_hyperlink(
                heading,
                text_of(entry["organization"]),
                organization_url,
                policy["fonts"]["primary"],
                policy["sizes_pt"]["body"],
                bold=True,
                color=hyperlink_color,
                underline=hyperlink_underline,
            )
        else:
            set_run_font(heading.add_run(text_of(entry["organization"])), policy["fonts"]["primary"], policy["sizes_pt"]["body"], bold=True)
        set_run_font(heading.add_run(f" | {text_of(entry['title'])}"), policy["fonts"]["primary"], policy["sizes_pt"]["body"], bold=True)
        meta = document.add_paragraph()
        meta.paragraph_format.keep_with_next = True
        meta.paragraph_format.space_after = Pt(
            policy["spacing_pt"].get("entry_meta_after", 1)
        )
        date_location = " | ".join(
            part
            for part in (f"{text_of(entry['start'])} - {text_of(entry['end'])}", text_of(entry["location"]))
            if part
        )
        set_run_font(meta.add_run(date_location), policy["fonts"]["primary"], policy["sizes_pt"]["small"])
        def add_role_bullets() -> None:
            for item in entry["bullets"]:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.left_indent = Pt(bullets["text_indent_pt"])
                paragraph.paragraph_format.first_line_indent = Pt(-bullets["hanging_pt"])
                paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["bullet_after"])
                add_docx_sourced_runs(paragraph, model, item, policy, emphasizer)

        role_bullets_after = entry.get("bullets_position") == "after_engagements"
        if not role_bullets_after:
            add_role_bullets()

        engagements = engagements_of(entry)
        if engagements:
            group = document.add_paragraph()
            group.paragraph_format.keep_with_next = True
            group.paragraph_format.left_indent = Pt(bullets["text_indent_pt"])
            group.paragraph_format.space_before = Pt(5)
            group.paragraph_format.space_after = Pt(1)
            set_run_font(group.add_run(ROLE_PROJECTS_HEADING), policy["fonts"]["primary"],
                         policy["sizes_pt"]["section"], bold=True)
            group._p.get_or_add_pPr().append(_bottom_border(color="A0A0A0", size="3"))

        for engagement in engagements:
            title = document.add_paragraph()
            title.paragraph_format.keep_with_next = True
            title.paragraph_format.left_indent = Pt(bullets["engagement_title_indent_pt"])
            title.paragraph_format.space_before = Pt(
                policy["spacing_pt"].get("engagement_before", 1)
            )
            title.paragraph_format.space_after = Pt(
                policy["spacing_pt"].get("entry_heading_after", 0)
            )
            name_url = link_of(model, engagement["name"])
            if name_url:
                add_docx_hyperlink(
                    title,
                    text_of(engagement["name"]),
                    name_url,
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                    bold=True,
                    color=hyperlink_color,
                    underline=hyperlink_underline,
                )
            else:
                set_run_font(
                    title.add_run(text_of(engagement["name"])),
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                    bold=True,
                )
            context = text_of(engagement.get("context"))
            if context:
                set_run_font(
                    title.add_run(f" | {context}"),
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["small"],
                )
            for item in engagement["bullets"]:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.left_indent = Pt(bullets["engagement_text_indent_pt"])
                paragraph.paragraph_format.first_line_indent = Pt(-bullets["hanging_pt"])
                paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["bullet_after"])
                add_docx_sourced_runs(paragraph, model, item, policy, emphasizer)

        if role_bullets_after:
            add_role_bullets()

    if model.get("projects"):
        emphasizer.enter("Freelance Projects")
        if model["layout"].get("page_break_before") == "selected-projects":
            document.add_page_break()
        add_docx_section_heading(document, "Freelance Projects", policy)
        for entry in model["projects"]:
            heading = document.add_paragraph()
            heading.paragraph_format.keep_with_next = True
            heading.paragraph_format.space_before = Pt(
                policy["spacing_pt"].get("project_entry_before", 0)
            )
            heading.paragraph_format.space_after = Pt(
                policy["spacing_pt"].get("entry_meta_after", 1)
            )
            primary = entry["primary"]
            primary_url = link_of(model, primary)
            if primary_url:
                add_docx_hyperlink(
                    heading,
                    text_of(primary),
                    primary_url,
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                    bold=True,
                    color=hyperlink_color,
                    underline=hyperlink_underline,
                )
            else:
                set_run_font(
                    heading.add_run(text_of(primary)),
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                    bold=True,
                )
            tail = " | ".join(
                part for part in (text_of(entry["secondary"]), text_of(entry["date"])) if part
            )
            if tail:
                heading.add_run(f" | {tail}")
            for detail in entry["details"]:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.left_indent = Pt(bullets["text_indent_pt"])
                paragraph.paragraph_format.first_line_indent = Pt(-bullets["hanging_pt"])
                paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["bullet_after"])
                add_docx_sourced_runs(paragraph, model, detail, policy, emphasizer)

    if model.get("career_breaks"):
        add_docx_section_heading(document, "Career Breaks", policy)
        for entry in model["career_breaks"]:
            heading = document.add_paragraph()
            heading.paragraph_format.keep_with_next = True
            heading.paragraph_format.space_after = Pt(0)
            set_run_font(heading.add_run(text_of(entry["label"])), policy["fonts"]["primary"], policy["sizes_pt"]["body"], bold=True)
            meta = document.add_paragraph(f"{text_of(entry['start'])} - {text_of(entry['end'])}")
            meta.paragraph_format.keep_with_next = True
            meta.paragraph_format.space_after = Pt(1)
            for detail in entry["details"]:
                document.add_paragraph(text_of(detail))

    if model["skills"]:
        emphasizer.enter("Skills")
        add_docx_section_heading(document, "Skills", policy)
        for group in model["skills"]:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(policy["spacing_pt"]["paragraph_after"])
            set_run_font(paragraph.add_run(f"{group['name']}: "), policy["fonts"]["primary"], policy["sizes_pt"]["body"], bold=True)
            # The group label is already bold, so spend each term's one
            # occurrence on it rather than repeating the same word two words
            # later ("Flutter and Dart: Flutter, Dart").
            if not emphasizer.reviewed:
                emphasizer.split(group["name"])
            for index, item in enumerate(group["items"]):
                if index:
                    set_run_font(paragraph.add_run(", "), policy["fonts"]["primary"], policy["sizes_pt"]["body"])
                add_docx_sourced_runs(paragraph, model, item, policy, emphasizer)

    if model.get("languages"):
        add_docx_section_heading(document, "Languages", policy)
        document.add_paragraph(", ".join(text_of(item) for item in model["languages"]))

    for key, heading_label in supporting_sections(model):
        if not model.get(key):
            continue
        add_docx_section_heading(document, heading_label, policy)
        if key == "activities":
            # Keep the gap before Volunteering identical to every other
            # section. Compact only the heading-to-entry interior so Word and
            # LibreOffice do not push the complete volunteer block to page 2.
            activity_heading = document.paragraphs[-1]
            activity_heading.paragraph_format.space_before = Pt(
                policy["spacing_pt"]["section_before"]
            )
            activity_heading.paragraph_format.space_after = Pt(1)
        for entry in model[key]:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.keep_with_next = bool(entry["details"])
            paragraph.paragraph_format.space_before = Pt(
                0
                if key == "activities"
                else policy["spacing_pt"].get("supporting_entry_before", 0)
            )
            paragraph.paragraph_format.space_after = Pt(
                0
                if key == "activities"
                else policy["spacing_pt"].get("paragraph_after", 0)
            )
            primary_url = link_of(model, entry["primary"])
            if primary_url:
                add_docx_hyperlink(
                    paragraph,
                    text_of(entry["primary"]),
                    primary_url,
                    policy["fonts"]["primary"],
                    policy["sizes_pt"]["body"],
                    bold=True,
                    color=hyperlink_color,
                    underline=hyperlink_underline,
                )
            else:
                set_run_font(paragraph.add_run(text_of(entry["primary"])), policy["fonts"]["primary"], policy["sizes_pt"]["body"], bold=True)
            tail = " | ".join(part for part in (text_of(entry["secondary"]), text_of(entry["date"])) if part)
            if tail:
                paragraph.add_run(f" | {tail}")
            for detail in entry["details"]:
                detail_paragraph = document.add_paragraph(
                    style="List Bullet" if key == "activities" else None
                )
                if key == "activities":
                    detail_paragraph.paragraph_format.left_indent = Pt(
                        bullets["text_indent_pt"]
                    )
                    detail_paragraph.paragraph_format.first_line_indent = Pt(
                        -bullets["hanging_pt"]
                    )
                detail_paragraph.paragraph_format.space_after = Pt(
                    policy["spacing_pt"].get(
                        "bullet_after" if key == "activities" else "paragraph_after",
                        0,
                    )
                )
                add_docx_sourced_runs(detail_paragraph, model, detail, policy)

    if model.get("hobbies"):
        add_docx_section_heading(document, "Interests", policy)
        document.add_paragraph(", ".join(text_of(item) for item in model["hobbies"]))

    document.core_properties.title = f"Resume: {text_of(model['basics']['name'])}"
    document.core_properties.subject = f"Application for {model['target']['role']} at {model['target']['company']}"
    document.save(output)
    return emphasizer


def protect_pdf_markup(markup: str) -> str:
    """Keep hyphenated compounds intact without altering visible punctuation.

    Phrase spaces have already become ``&nbsp;``. ReportLab can still treat an
    ASCII hyphen as a wrap opportunity, so wrap only compound tokens in
    ``nobr`` while leaving inline markup and link attributes untouched.
    """
    chunks = re.split(r"(<[^>]+>)", markup)
    return "".join(
        chunk
        if chunk.startswith("<") and chunk.endswith(">")
        else re.sub(
            r"(?<![\w])([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![\w])",
            lambda match: f"<nobr>{match.group(1)}</nobr>",
            chunk,
        )
        for chunk in chunks
    )


def render_pdf(
    model: dict[str, Any], policy: dict[str, Any], output: Path, *,
    compact_projects: bool = False,
) -> Emphasizer:
    emphasizer = Emphasizer(model, policy)
    phrases = protected_line_phrases(model, policy)
    hyperlink_color, hyperlink_underline = link_appearance(policy)
    margins = policy["margins_inches"]
    document = SimpleDocTemplate(
        str(output),
        pagesize=page_size(model, policy),
        rightMargin=margins["right"] * inch,
        leftMargin=margins["left"] * inch,
        topMargin=margins["top"] * inch,
        bottomMargin=margins.get("pdf_bottom", margins["bottom"]) * inch,
        title=f"Resume: {text_of(model['basics']['name'])}",
        subject=f"Application for {model['target']['role']} at {model['target']['company']}",
    )
    sample = getSampleStyleSheet()
    font = policy["fonts"]["pdf_primary"]
    body_size = policy["sizes_pt"]["body"]
    bullet_tokens = bullet_layout(policy)
    line_spacing = float(policy["spacing_pt"].get("line_spacing_multiple", 1.12))
    styles = {
        "name": ParagraphStyle("EKBName", parent=sample["Normal"], fontName=f"{font}-Bold", fontSize=policy["sizes_pt"]["name"], leading=policy["sizes_pt"]["name"] + 2, alignment=TA_CENTER, spaceAfter=1, splitLongWords=False, embeddedHyphenation=0),
        "title": ParagraphStyle("EKBTitle", parent=sample["Normal"], fontName=font, fontSize=body_size, leading=body_size + 1.5, alignment=TA_CENTER, spaceAfter=2, splitLongWords=False, embeddedHyphenation=0),
        "contact": ParagraphStyle("EKBContact", parent=sample["Normal"], fontName=font, fontSize=policy["sizes_pt"]["small"], leading=policy["sizes_pt"]["small"] + 1.5, alignment=TA_CENTER, spaceAfter=2, splitLongWords=False, embeddedHyphenation=0),
        "mobility": ParagraphStyle("EKBMobility", parent=sample["Normal"], fontName=font, fontSize=policy["sizes_pt"]["small"], leading=policy["sizes_pt"]["small"] + 1.5, alignment=TA_CENTER, spaceAfter=5, splitLongWords=False, embeddedHyphenation=0),
        "section": ParagraphStyle("EKBSection", parent=sample["Normal"], fontName=f"{font}-Bold", fontSize=policy["sizes_pt"]["section"], leading=policy["sizes_pt"]["section"] + 1, spaceBefore=policy["spacing_pt"]["section_before"], spaceAfter=1, borderWidth=0, borderPadding=0, keepWithNext=True, splitLongWords=False, embeddedHyphenation=0),
        "entry": ParagraphStyle("EKBEntry", parent=sample["Normal"], fontName=font, fontSize=body_size, leading=body_size * line_spacing, spaceAfter=policy["spacing_pt"].get("entry_heading_after", 0), keepWithNext=True, splitLongWords=False, embeddedHyphenation=0),
        "body": ParagraphStyle("EKBBody", parent=sample["Normal"], fontName=font, fontSize=body_size, leading=body_size * line_spacing, spaceAfter=policy["spacing_pt"]["paragraph_after"], splitLongWords=False, embeddedHyphenation=0),
        "meta": ParagraphStyle("EKBMeta", parent=sample["Normal"], fontName=font, fontSize=policy["sizes_pt"]["small"], leading=policy["sizes_pt"]["small"] * line_spacing, spaceAfter=policy["spacing_pt"].get("entry_meta_after", 1), keepWithNext=True, splitLongWords=False, embeddedHyphenation=0),
    }

    def safe_paragraph(markup: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(protect_pdf_markup(markup), style)

    def pdf_text_markup(text: str) -> str:
        protected = protect_phrase_spaces(text, phrases)
        return html.escape(protected).replace(NO_BREAK_SPACE_MARKER, "&nbsp;")

    def paragraph(text: str, style: str = "body") -> Paragraph:
        return safe_paragraph(pdf_text_markup(text), styles[style])

    def section(label: str) -> list[Any]:
        rule = HRFlowable(
            width="100%",
            thickness=0.4,
            color=colors.HexColor("#666666"),
            spaceBefore=0,
            spaceAfter=policy["spacing_pt"]["section_after"],
        )
        rule.keepWithNext = True
        return [paragraph(label.upper(), "section"), rule]

    story: list[Any] = [
        paragraph(text_of(model["basics"]["name"]), "name"),
        paragraph(text_of(model["basics"]["title"]), "title"),
    ]

    def anchor(body: str, target: str) -> str:
        if hyperlink_underline:
            body = f"<u>{body}</u>"
        return (
            f'<a href="{html.escape(target, quote=True)}" '
            f'color="#{hyperlink_color}">{body}</a>'
        )

    def linked(item: dict[str, str]) -> str:
        target = link_of(model, item)
        if not target:
            return pdf_text_markup(text_of(item))
        return "".join(
            anchor(pdf_text_markup(fragment), target)
            if is_linked
            else pdf_text_markup(fragment)
            for fragment, is_linked in link_fragments(item)
        )

    def linked_emphasized_markup(item: dict[str, str]) -> str:
        target = link_of(model, item)
        return "".join(
            anchor(emphasizer.markup(protect_phrase_spaces(fragment, phrases)), target)
            if target and is_linked
            else emphasizer.markup(protect_phrase_spaces(fragment, phrases))
            for fragment, is_linked in link_fragments(item)
        )

    def linked_emphasized(item: dict[str, str], style: str = "body") -> Paragraph:
        return safe_paragraph(linked_emphasized_markup(item), styles[style])

    contact_items = model["basics"]["contact"] + model["basics"]["links"]
    if contact_items:
        story.append(safe_paragraph(" | ".join(linked(item) for item in contact_items), styles["contact"]))
    mobility = model["basics"]["mobility"]
    if mobility is not None:
        story.append(paragraph(text_of(mobility), "mobility"))

    summary = model.get("summary", [])
    if summary:
        emphasizer.enter("Summary")
        story.extend(section("Summary"))
        story.append(
            safe_paragraph(
                " ".join(linked_emphasized_markup(item) for item in summary),
                styles["body"],
            )
        )

    emphasizer.enter("Experience")
    story.extend(section("Experience"))
    for entry_index, entry in enumerate(model["experience"]):
        organization = linked(entry["organization"])
        entry_style = styles["entry"].clone("experienceEntry")
        entry_style.spaceBefore = (
            policy["spacing_pt"].get("experience_entry_before", 0) if entry_index else 0
        )
        heading = safe_paragraph(
            f"<b>{organization} | {pdf_text_markup(text_of(entry['title']))}</b>",
            entry_style,
        )
        date_location = " | ".join(
            part
            for part in (f"{text_of(entry['start'])} - {text_of(entry['end'])}", text_of(entry["location"]))
            if part
        )
        bullets = ListFlowable(
            [ListItem(linked_emphasized(item)) for item in entry["bullets"]],
            bulletType="bullet",
            start="circle",
            leftIndent=bullet_tokens["text_indent_pt"],
            bulletDedent=bullet_tokens["hanging_pt"],
            bulletFontName=font,
            bulletFontSize=bullet_tokens["marker_font_size_pt"],
            bulletOffsetY=bullet_tokens["marker_vertical_offset_pt"],
            spaceAfter=2,
        )
        role_bullets_after = entry.get("bullets_position") == "after_engagements"
        story.extend([heading, paragraph(date_location, "meta")])
        if not role_bullets_after:
            story.append(bullets)

        engagements = engagements_of(entry)
        if engagements:
            group_style = styles["section"].clone("projectGroup")
            group_style.leftIndent = bullet_tokens["text_indent_pt"]
            group_style.spaceBefore = 2 if compact_projects else 5
            group_style.spaceAfter = 0
            # SimpleDocTemplate's body frame has 6 pt padding on each side.
            rule = HRFlowable(
                width=max(1, document.width - 12 - group_style.leftIndent),
                hAlign="RIGHT",
                thickness=0.35,
                color=colors.HexColor("#a0a0a0"),
                spaceAfter=0 if compact_projects else 1,
            )
            rule.keepWithNext = True
            story.extend([safe_paragraph(ROLE_PROJECTS_HEADING, group_style), rule])

        engagement_spacing = policy["spacing_pt"].get("engagement_before", 1)
        project_indent = bullet_tokens["engagement_title_indent_pt"]
        project_bullet_indent = bullet_tokens["engagement_text_indent_pt"]
        project_bullet_hang = bullet_tokens["hanging_pt"]
        if compact_projects:
            project_bullet_indent = min(project_bullet_indent, project_indent + 8)
            project_bullet_hang = min(project_bullet_hang, project_bullet_indent - project_indent)

        for engagement in engagements:
            name = linked(engagement["name"])
            context = text_of(engagement.get("context"))
            label = f"<b>{name}</b>"
            if context:
                label += f" | {pdf_text_markup(context)}"
            engagement_heading = safe_paragraph(label, styles["entry"])
            engagement_heading.style = styles["entry"].clone("engagementEntry")
            engagement_heading.style.leftIndent = project_indent
            engagement_heading.style.spaceBefore = min(0.75, engagement_spacing) if compact_projects else engagement_spacing
            story.append(engagement_heading)
            story.append(
                ListFlowable(
                    [ListItem(linked_emphasized(item)) for item in engagement["bullets"]],
                    bulletType="bullet",
                    start="circle",
                    leftIndent=project_bullet_indent,
                    bulletDedent=project_bullet_hang,
                    bulletFontName=font,
                    bulletFontSize=bullet_tokens["marker_font_size_pt"],
                    bulletOffsetY=bullet_tokens["marker_vertical_offset_pt"],
                    spaceAfter=0 if compact_projects else 2,
                )
            )

        if role_bullets_after:
            story.append(bullets)

    if model.get("projects"):
        emphasizer.enter("Freelance Projects")
        if model["layout"].get("page_break_before") == "selected-projects":
            story.append(PageBreak())
        story.extend(section("Freelance Projects"))
        for entry in model["projects"]:
            primary = linked(entry["primary"])
            tail = " | ".join(
                part for part in (text_of(entry["secondary"]), text_of(entry["date"])) if part
            )
            main = f"<b>{primary}</b>"
            if tail:
                main += f" | {pdf_text_markup(tail)}"
            project_style = styles["entry"].clone("freelanceProjectEntry")
            project_style.spaceBefore = policy["spacing_pt"].get("project_entry_before", 0)
            project_style.spaceAfter = policy["spacing_pt"].get("entry_meta_after", 1)
            flowables: list[Any] = [safe_paragraph(main, project_style)]
            if entry["details"]:
                flowables.append(
                    ListFlowable(
                        [ListItem(linked_emphasized(item)) for item in entry["details"]],
                        bulletType="bullet",
                        start="circle",
                        leftIndent=bullet_tokens["text_indent_pt"],
                        bulletDedent=bullet_tokens["hanging_pt"],
                        bulletFontName=font,
                        bulletFontSize=bullet_tokens["marker_font_size_pt"],
                        bulletOffsetY=bullet_tokens["marker_vertical_offset_pt"],
                        spaceAfter=2,
                    )
                )
            story.append(KeepTogether(flowables))

    if model.get("career_breaks"):
        story.extend(section("Career Breaks"))
        for entry in model["career_breaks"]:
            story.extend([
                safe_paragraph(f"<b>{pdf_text_markup(text_of(entry['label']))}</b>", styles["entry"]),
                paragraph(f"{text_of(entry['start'])} - {text_of(entry['end'])}", "meta"),
            ])
            story.extend(paragraph(text_of(item)) for item in entry["details"])

    if model["skills"]:
        emphasizer.enter("Skills")
        story.extend(section("Skills"))
        for group in model["skills"]:
            if not emphasizer.reviewed:
                emphasizer.split(group["name"])  # see the DOCX renderer for why
            items = ", ".join(
                linked_emphasized_markup(item) for item in group["items"]
            )
            story.append(safe_paragraph(f"<b>{pdf_text_markup(group['name'])}:</b> {items}", styles["body"]))

    if model.get("languages"):
        story.extend(section("Languages"))
        story.append(paragraph(", ".join(text_of(item) for item in model["languages"])))

    for key, heading_label in supporting_sections(model):
        if not model.get(key):
            continue
        story.extend(section(heading_label))
        for entry in model[key]:
            tail = " | ".join(part for part in (text_of(entry["secondary"]), text_of(entry["date"])) if part)
            main = f"<b>{linked(entry['primary'])}</b>"
            if tail:
                main += f" | {pdf_text_markup(tail)}"
            supporting_style = styles["body"].clone("supportingEntry")
            supporting_style.spaceBefore = policy["spacing_pt"].get("supporting_entry_before", 0)
            flowables: list[Any] = [safe_paragraph(main, supporting_style)]
            if key == "activities" and entry["details"]:
                flowables.append(
                    ListFlowable(
                        [ListItem(safe_paragraph(linked(item), styles["body"])) for item in entry["details"]],
                        bulletType="bullet",
                        start="circle",
                        leftIndent=bullet_tokens["text_indent_pt"],
                        bulletDedent=bullet_tokens["hanging_pt"],
                        bulletFontName=font,
                        bulletFontSize=bullet_tokens["marker_font_size_pt"],
                        bulletOffsetY=bullet_tokens["marker_vertical_offset_pt"],
                        spaceAfter=2,
                    )
                )
            else:
                flowables.extend(
                    safe_paragraph(linked(item), styles["body"])
                    for item in entry["details"]
                )
            story.append(KeepTogether(flowables))

    if model.get("hobbies"):
        story.extend(section("Interests"))
        story.append(paragraph(", ".join(text_of(item) for item in model["hobbies"])))

    def later_page(canvas: Any, _document: Any) -> None:
        canvas.saveState()
        header_style = ParagraphStyle(
            "EKBContinuation",
            parent=sample["Normal"],
            fontName=font,
            fontSize=policy["sizes_pt"]["small"],
            leading=policy["sizes_pt"]["small"] + 1,
            alignment=TA_CENTER,
        )
        header = safe_paragraph(pdf_text_markup(continuation_contact(model)), header_style)
        available_width = page_size(model, policy)[0] - (margins["left"] + margins["right"]) * inch
        _, header_height = header.wrap(available_width, 0.45 * inch)
        header.drawOn(
            canvas,
            margins["left"] * inch,
            page_size(model, policy)[1] - 0.18 * inch - header_height,
        )
        canvas.restoreState()

    document.build(story, onFirstPage=lambda _canvas, _document: None, onLaterPages=later_page)
    if (not compact_projects and document.page > model["layout"]["page_target"]
            and any(engagements_of(entry) for entry in model["experience"])):
        # Give the Projects subsection one compact pass before flowing onto
        # another page. Keep all wording, type sizes and margins.
        return render_pdf(model, policy, output, compact_projects=True)
    return emphasizer


def docx_paragraph_text(paragraph: Any) -> str:
    """Extract visible paragraph text, including OOXML no-break hyphens."""
    parts: list[str] = []
    for node in paragraph._p.iter():
        if node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag == qn("w:noBreakHyphen"):
            parts.append("-")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.tag in {qn("w:br"), qn("w:cr")}:
            parts.append("\n")
    return "".join(parts)


def extract_docx(path: Path) -> tuple[str, dict[str, Any]]:
    document = Document(path)
    paragraphs = [
        docx_paragraph_text(paragraph)
        for paragraph in document.paragraphs
        if docx_paragraph_text(paragraph).strip()
    ]
    header_footer_text: list[str] = []
    for section in document.sections:
        header_footer_text.extend(
            docx_paragraph_text(p)
            for p in section.header.paragraphs
            if docx_paragraph_text(p).strip()
        )
        header_footer_text.extend(
            docx_paragraph_text(p)
            for p in section.footer.paragraphs
            if docx_paragraph_text(p).strip()
        )
    structure = {
        "tables": len(document.tables),
        "inline_shapes": len(document.inline_shapes),
        "header_footer_text": header_footer_text,
        "sections": len(document.sections),
        "section_types": [str(section.start_type) for section in document.sections],
    }
    return "\n".join(paragraphs), structure


def pdf_content_fill_ratio(page: Any, policy: dict[str, Any]) -> float:
    """Measure visible text against the PDF renderer's actual text frame."""
    height = float(page.mediabox.height)
    margins = policy["margins_inches"]
    # ReportLab's Frame reserves six points on every side by default.  The PDF
    # renderer uses that default, so counting the top and bottom frame padding
    # as unused document space permanently understates page fill by about 1.6%.
    frame_padding_pt = 6.0
    usable_bottom = float(margins.get("pdf_bottom", margins["bottom"])) * 72 + frame_padding_pt
    usable_top = height - float(margins["top"]) * 72 - frame_padding_pt
    extents: list[tuple[float, float]] = []

    def visitor(text: str, cm: list[float], _tm: list[float], _font: Any, font_size: float) -> None:
        if not text or not text.strip():
            return
        baseline = float(cm[5])
        size = float(font_size or 0)
        if baseline < usable_bottom - 12 or baseline > usable_top + 24:
            return
        extents.append((baseline, baseline + size))

    page.extract_text(visitor_text=visitor)
    if not extents or usable_top <= usable_bottom:
        return 0.0
    content_bottom = max(min(low for low, _high in extents), usable_bottom)
    content_top = min(max(high for _low, high in extents), usable_top)
    return round(max(0.0, min(1.0, (content_top - content_bottom) / (usable_top - usable_bottom))), 3)


def pdf_orphaned_wraps(page: Any) -> list[str]:
    """Return one-word final lines created by PDF paragraph wrapping.

    These are not extraction errors, but they are a frequent visual-quality
    defect in dense resumes: a short bullet leaves its final noun alone on a
    second line even though a tighter phrasing would fit cleanly.  Non-breaking
    spaces remain available for a genuinely inseparable phrase, but rewriting
    the sentence is the preferred fix.
    """
    orphans: list[str] = []

    def visitor(text: str, _cm: list[float], _tm: list[float], _font: Any, _size: float) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return
        final_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'./+-]*", lines[-1])
        preceding_words = re.findall(
            r"[A-Za-z0-9][A-Za-z0-9'./+-]*", " ".join(lines[:-1])
        )
        if len(final_words) == 1 and len(preceding_words) >= 5:
            orphans.append(lines[-1])

    page.extract_text(visitor_text=visitor)
    return orphans


def pdf_broken_word_wraps(page: Any) -> list[str]:
    """Return compounds split after an internal hyphen at a rendered line end."""
    broken: list[str] = []

    def visitor(text: str, _cm: list[float], _tm: list[float], _font: Any, _size: float) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for previous, following in zip(lines, lines[1:]):
            left = re.search(r"([A-Za-z0-9]+)-$", previous)
            right = re.match(r"([A-Za-z0-9]+)", following)
            if left and right:
                broken.append(f"{left.group(1)}-{right.group(1)}")

    page.extract_text(visitor_text=visitor)
    return broken


def pdf_protected_phrase_wraps(page: Any, phrases: Iterable[str]) -> list[str]:
    """Return configured phrases whose words cross a rendered PDF line."""
    try:
        layout_text = page.extract_text(extraction_mode="layout") or ""
    except TypeError:
        layout_text = page.extract_text() or ""
    lines = [line.strip() for line in layout_text.splitlines() if line.strip()]
    broken: list[str] = []
    for previous, following in zip(lines, lines[1:]):
        left = normalize(previous)
        right = normalize(following)
        combined = f"{left} {right}"
        for phrase in phrases:
            needle = normalize(phrase)
            if needle in combined and needle not in left and needle not in right:
                broken.append(phrase)
    return sorted(set(broken), key=str.casefold)


def extract_pdf(
    path: Path, policy: dict[str, Any], protected_phrases: Iterable[str]
) -> tuple[
    str,
    int,
    str,
    list[float],
    list[list[str]],
    list[list[str]],
    list[list[str]],
]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ResumeError("PDF is password-protected; application resumes must open without a password")
    pages = [(page.extract_text() or "") for page in reader.pages]
    first = reader.pages[0].mediabox
    width, height = round(float(first.width)), round(float(first.height))
    detected = "A4" if abs(width - 595) <= 2 and abs(height - 842) <= 2 else "LETTER" if (width, height) == (612, 792) else f"{width}x{height}pt"
    fill_ratios = [pdf_content_fill_ratio(page, policy) for page in reader.pages]
    orphaned_wraps = [pdf_orphaned_wraps(page) for page in reader.pages]
    broken_word_wraps = [pdf_broken_word_wraps(page) for page in reader.pages]
    protected_phrase_wraps = [
        pdf_protected_phrase_wraps(page, protected_phrases) for page in reader.pages
    ]
    return (
        "\n".join(pages),
        len(reader.pages),
        detected,
        fill_ratios,
        orphaned_wraps,
        broken_word_wraps,
        protected_phrase_wraps,
    )


def normalize(value: str) -> str:
    value = (
        value.replace("•", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("‑", "-")
    )
    return re.sub(r"\s+", " ", value).strip().casefold()


def verify_order(expected: Iterable[str], extracted: str, label: str) -> list[str]:
    haystack = normalize(extracted)
    cursor = 0
    errors: list[str] = []
    for fragment in expected:
        needle = normalize(fragment.lstrip("• "))
        position = haystack.find(needle, cursor)
        if position < 0:
            errors.append(f"{label} is missing or reorders: {fragment}")
        else:
            cursor = position + len(needle)
    return errors


def rendered_typography_errors(
    expected: Iterable[str],
    extracted: str,
    label: str,
    policy: dict[str, Any],
) -> list[str]:
    """Flag known typos or duplicated words introduced in rendered output."""
    expected_text = normalize(" ".join(expected))
    rendered_text = normalize(extracted)
    errors: list[str] = []
    typo_fixes = policy.get("proofreading", {}).get("forbidden_typos", {})
    for typo, replacement in typo_fixes.items():
        if (
            re.search(rf"(?<!\w){re.escape(typo.casefold())}(?!\w)", rendered_text)
            and normalize(replacement) in expected_text
        ):
            errors.append(
                f"{label} rendered probable typo {typo!r}; expected {replacement!r}"
            )
    for match in re.finditer(r"(?<!\w)([a-z][a-z0-9'+./-]*)\s+\1(?!\w)", rendered_text):
        repeated = match.group(1)
        if not re.search(
            rf"(?<!\w){re.escape(repeated)}\s+{re.escape(repeated)}(?!\w)",
            expected_text,
        ):
            errors.append(f"{label} duplicates the word {repeated!r}")
    return errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filename_tokens(value: str) -> list[str]:
    """Portable filename words without guessing or adding resume facts."""
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.findall(r"[A-Za-z0-9]+", ascii_value)


def delivery_stem(model: dict[str, Any], policy: dict[str, Any]) -> str:
    """Human-facing filename recommended for the application attachment.

    The stable ``resume.*`` files remain available for tooling. The additional
    attachment copies make the output directory directly usable without a
    manual rename such as ``CV_FINAL_v3.pdf``.
    """
    name = filename_tokens(text_of(model["basics"]["name"]))
    role = filename_tokens(model["target"]["role"])
    values = {
        "FirstName": name[0] if name else "Resume",
        "LastName": "_".join(name[1:]),
        "TargetRole": "_".join(role) if role else "Role",
    }
    pattern = str(
        policy.get("delivery", {}).get(
            "attachment_pattern", "FirstName_LastName_TargetRole_CV.pdf"
        )
    )
    pattern = re.sub(r"\.(?:pdf|docx)$", "", pattern, flags=re.IGNORECASE)
    for key, value in values.items():
        pattern = pattern.replace(key, value)
    stem = "_".join(filename_tokens(pattern))
    return stem or "Resume_CV"


def count_links(model: dict[str, Any]) -> int:
    """Sourced items that render as a live link in this document."""
    if not links_enabled(model):
        return 0
    total = 0

    def walk(value: Any) -> None:
        nonlocal total
        if isinstance(value, dict):
            if "text" in value and ("source_ref" in value or "source_refs" in value):
                total += 1 if url_of(value) else 0
                return
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(model)
    return total


def link_warnings(model: dict[str, Any], *, reviewed: bool = False) -> list[str]:
    """Hyperlinking is the default, so a rendered entity with no link is worth
    reporting — the address may simply be missing from the profile."""
    warnings: list[str] = []
    if not links_enabled(model):
        return ["Hyperlink annotations are disabled for this document (layout.hyperlinks=off)"]
    for entry in model["experience"]:
        if not url_of(entry["organization"]):
            warnings.append(f"No hyperlink on employer: {text_of(entry['organization'])}")
        for engagement in engagements_of(entry):
            if not reviewed and not url_of(engagement["name"]):
                warnings.append(f"No hyperlink on engagement: {text_of(engagement['name'])}")
    for entry in model.get("projects", []):
        if not url_of(entry["primary"]):
            warnings.append(f"No hyperlink on freelance project: {text_of(entry['primary'])}")
    for entry in model.get("certifications", []):
        if not url_of(entry["primary"]):
            warnings.append(f"No hyperlink on certification: {text_of(entry['primary'])}")
    return warnings


def emphasis_warnings(model: dict[str, Any], policy: dict[str, Any], emphasizer: Emphasizer) -> list[str]:
    warnings: list[str] = []
    matched = [
        requirement for requirement in model["alignment"]["requirements"]
        if requirement["status"] == "matched"
    ]
    if model["layout"].get("emphasis", "matched-requirements") == "none":
        if matched:
            warnings.append(f"Keyword emphasis is off while {len(matched)} requirements are matched")
        return warnings
    if matched and not any(requirement.get("emphasize", True) for requirement in matched):
        warnings.append("Every matched requirement has emphasize=false, so nothing is highlighted")
    elif matched and emphasizer.count == 0:
        warnings.append("No emphasis term was found in the emphasized sections; check the aliases")
    if emphasizer.dropped:
        warnings.append(
            f"Emphasis capped at {policy['emphasis']['max_terms']} requirements; not highlighted: "
            + ", ".join(emphasizer.dropped)
        )
    # Skills is a list of terms, so bolding there is inherently dense and says
    # nothing about readability. Judge density on the prose sections only.
    prose = sum(
        count for section, count in emphasizer.per_section.items()
        if section in {"Summary", "Experience", "Freelance Projects"}
    )
    bullets = len(experience_items(model)) + sum(
        len(entry["details"]) for entry in model.get("projects", [])
    )
    if bullets and prose > 1.5 * bullets:
        warnings.append(
            f"{prose} emphasized fragments across {bullets} bullets reads as heavily bolded; "
            "reduce the term set"
        )
    return warnings


def application_guidance_warnings(model: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Report presentation guidance that cannot safely be auto-corrected.

    Contact types and language levels are user facts. A renderer may point out
    a missing convention, but it must never invent a phone number, classify an
    employer email, or translate a proficiency label into CEFR by itself.
    """
    warnings: list[str] = []
    contact_policy = policy.get("contact_hygiene", {})
    contact = model["basics"]["contact"]
    links = model["basics"]["links"]
    visible_contact = [text_of(item).strip() for item in contact]
    urls = [url_of(item) for item in contact]

    if contact_policy.get("require_email", True) and not any(
        "@" in text or url.startswith("mailto:")
        for text, url in zip(visible_contact, urls)
    ):
        warnings.append("Header has no recognizable professional email address")
    if contact_policy.get("recommend_phone", True) and not any(
        url.startswith("tel:") or len(re.sub(r"\D", "", text)) >= 7
        for text, url in zip(visible_contact, urls)
    ):
        warnings.append("Header has no phone number; add one only from confirmed profile data")
    if contact_policy.get("recommend_profile_link", True) and not any(
        url_of(item) for item in links
    ):
        warnings.append(
            "Header has no confirmed professional profile link; never guess or construct one"
        )

    language_policy = policy.get("languages", {})
    cefr_pattern = language_policy.get("cefr_pattern", r"\b(?:A1|A2|B1|B2|C1|C2)\b")
    if language_policy.get("prefer_cefr", True):
        try:
            cefr = re.compile(str(cefr_pattern), flags=re.IGNORECASE)
        except re.error as exc:
            raise ResumeError(f"policy.languages.cefr_pattern is invalid: {exc}") from exc
        for index, item in enumerate(model.get("languages", []), 1):
            if not cefr.search(text_of(item)):
                warnings.append(
                    f"Language entry {index} has no CEFR level (A1-C2); preserve the recorded "
                    "proficiency unless the user confirms a CEFR mapping"
                )
    return warnings


def editorial_warnings(model: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    visible = " ".join(resume_lines(model)).casefold()
    warnings: list[str] = []
    experience_budget = policy.get("experience_budget", {})
    master = model["target"].get("mode") == "master"
    role_bullets_max = int(
        experience_budget.get(
            "master_role_bullets_max" if master else "role_bullets_max", 4
        )
    )
    role_bullets_with_engagements_max = int(
        experience_budget.get(
            "master_role_bullets_with_engagements_max"
            if master
            else "role_bullets_with_engagements_max",
            4 if master else 2,
        )
    )
    historical_role_bullets_max = int(
        experience_budget.get(
            "master_historical_role_bullets_max" if master else "historical_role_bullets_max",
            4 if master else 2,
        )
    )
    engagements_max = int(experience_budget.get("engagements_max", 4))
    engagement_bullets_max = int(
        experience_budget.get(
            "master_engagement_bullets_max" if master else "engagement_bullets_max",
            3 if master else 2,
        )
    )
    for phrase in ("excellent problem solver", "results-driven professional", "proven track record", "dynamic professional", "passionate engineer"):
        if phrase in visible:
            warnings.append(f"Avoid generic resume phrase: {phrase}")
    all_bullets = [text_of(item) for item in experience_items(model)]
    reviewed = "requirement_map_sha256" in model.get("alignment", {})
    for index, entry in enumerate(model["experience"], 1):
        count = len(entry["bullets"])
        current = text_of(entry["end"]).casefold() == "present"
        engagements = engagements_of(entry)
        if reviewed:
            for label, items in [(text_of(entry["organization"]), entry["bullets"]),
                                 *((text_of(group["name"]), group["bullets"]) for group in engagements)]:
                openings = [text_of(item).casefold().split()[:1] for item in items]
                if openings.count(["contributed"]) > 1:
                    warnings.append(
                        f"{label}: repeated 'Contributed' openings. Specify the distinct contributions "
                        "while keeping their collaborative scope."
                    )
        if engagements:
            # The role delegates its detail to named engagements, so the
            # role-level bullets are framing lines and the flat targets do not
            # apply. What matters here is that the framing stays short and the
            # engagements stay readable.
            if count > role_bullets_with_engagements_max:
                warnings.append(
                    f"Role {index} has {count} role-level bullets alongside "
                    f"{len(engagements)} engagements; "
                    f"{role_bullets_with_engagements_max} framing lines is the maximum"
                )
            if len(engagements) > engagements_max:
                warnings.append(
                    f"Role {index} has {len(engagements)} engagements; "
                    f"{engagements_max} is the default maximum"
                )
            for position, engagement in enumerate(engagements, 1):
                if len(engagement["bullets"]) > engagement_bullets_max:
                    warnings.append(
                        f"Role {index} engagement {position} "
                        f"({text_of(engagement['name'])}) has {len(engagement['bullets'])} "
                        f"bullets; {engagement_bullets_max} is the default maximum"
                    )
        elif current and master and count > role_bullets_max:
            warnings.append(
                f"Current role {index} has {count} bullets; {role_bullets_max} is the master-resume maximum"
            )
        elif current and not master and count != 3:
            warnings.append(f"Current role {index} has {count} bullets; three is the default target")
        elif not current and count > historical_role_bullets_max:
            warnings.append(
                f"Historical role {index} has {count} bullets; "
                f"{historical_role_bullets_max} is the maximum"
            )
    starts = [re.sub(r"^[^a-z]*([a-z]+).*", r"\1", bullet.casefold()) for bullet in all_bullets]
    repeated = sorted({verb for verb in starts if verb and starts.count(verb) > 2})
    if repeated:
        warnings.append("Repeated bullet openings: " + ", ".join(repeated))
    for index, bullet in enumerate(all_bullets, 1):
        if bullet and bullet[-1] not in ".!?":
            warnings.append(f"Bullet {index} does not end with consistent punctuation")
    return warnings


def ai_visibility_warnings(model: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Flag AI keywords that have no supported engineering example on the page."""
    terms = policy.get("ai_experience", {}).get("terms", [])
    if not isinstance(terms, list) or not all(
        isinstance(item, str) and item.strip() for item in terms
    ):
        raise ResumeError("policy ai_experience.terms must contain non-empty strings")
    if not terms:
        return []

    patterns = [
        re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)
        for term in terms
    ]
    skills_text = " ".join(
        [group.get("name", "") for group in model.get("skills", [])]
        + [
            text_of(item)
            for group in model.get("skills", [])
            for item in group.get("items", [])
        ]
    )
    if not any(pattern.search(skills_text) for pattern in patterns):
        return []

    achievement_items = [*model.get("summary", []), *experience_items(model)]
    achievement_items.extend(
        detail for entry in model.get("projects", []) for detail in entry.get("details", [])
    )
    achievement_text = " ".join(text_of(item) for item in achievement_items)
    if any(pattern.search(achievement_text) for pattern in patterns):
        return []
    return [
        "AI tools appear in Skills but not in Summary, Experience, or Freelance Projects; "
        "use a supported engineering achievement when eligible evidence exists"
    ]


def content_density_findings(
    model: dict[str, Any],
    policy: dict[str, Any],
    pdf_pages: int,
    fill_ratios: list[float],
    *,
    enforce_minimum: bool,
) -> tuple[list[str], list[str]]:
    if pdf_pages != 1 or not fill_ratios:
        return [], []
    threshold = float(
        policy.get("content_density", {}).get("single_page_minimum_usable_height_ratio", 0)
    )
    master_target = float(
        policy.get("content_density", {}).get(
            "master_single_page_target_usable_height_ratio", 0
        )
    )
    ratio = fill_ratios[0]
    if threshold and ratio < threshold:
        finding = [
            f"Single-page resume is underfilled: content uses {ratio:.1%} of printable height, "
            f"below the {threshold:.1%} minimum; restore strong non-redundant Experience "
            "evidence or add a relevant independent project"
        ]
        return (finding, []) if enforce_minimum else ([], finding)
    if (
        model["target"].get("mode") == "master"
        and master_target
        and ratio < master_target
    ):
        return [], [
            f"Single-page master resume uses {ratio:.1%} of printable height, below the "
            f"{master_target:.1%} master target; add only strong non-redundant evidence or a "
            "confirmed compact section while preserving normal section spacing"
        ]
    return [], []


def allowed_continuation_header(model: dict[str, Any], texts: list[str]) -> bool:
    expected = normalize(continuation_contact(model))
    return all(normalize(text) == expected for text in texts)


def apply_plain_mode(model: dict[str, Any]) -> None:
    """Strip both presentation layers for a maximally conservative export.

    Neither hyperlinks nor bold changes a single visible word, so a plain export
    is the same resume with the annotations removed — never a different document.
    """
    model["layout"]["hyperlinks"] = "off"
    model["layout"]["emphasis"] = "none"


def application_decisions(root, model, *, legacy_replay=False):
    application = require_screening(root, model["application_id"], model["target"])
    if model["target"]["mode"] == "master" or application.get("schema_version", 1) == 1:
        if "requirement_map_sha256" in model["alignment"]:
            raise ResumeError("mapped alignment requires a version 2 job-targeted intake")
    if model["target"]["mode"] == "master":
        return application, None
    if application.get("schema_version", 1) == 1:
        if not legacy_replay:
            raise ResumeError("version 1 target requires explicit --legacy-replay or a newly screened version 2 intake")
        return application, None
    decisions = load_decisions(root, application)
    if model["alignment"] != alignment_projection(decisions):
        raise ResumeError("model alignment differs from the reviewed map; use ekb requirement-map ID --alignment")
    return application, decisions


def render(args: argparse.Namespace) -> int:
    output = Path(args.output_dir).absolute()
    output = output.parent.resolve() / output.name
    with publication_lock(output):
        if output.is_symlink():
            raise ResumeError("resume output cannot be a symlink")
        return render_locked(args, output)


def render_locked(args: argparse.Namespace, output_dir: Path) -> int:
    model_path = Path(args.draft or args.model).resolve()
    profile_path = Path(args.profile).resolve()
    projects_path = Path(args.projects).resolve()
    policy_path = Path(args.policy).resolve() if args.policy else Path(config_path("resume-policy.json", str(projects_path.parent)))
    ranking_path = Path(args.ranking).resolve() if args.ranking else profile_path.with_name("project-ranking.yaml")

    # Snapshot the draft once. The source checker and renderer must see the
    # same bytes even when an editor modifies the original during rendering.
    draft_bytes = model_path.read_bytes()
    model = json.loads(draft_bytes)
    if not isinstance(model, dict):
        raise ResumeError("resume draft must contain a JSON object")
    policy = load_json(policy_path)
    validate_model(model, policy)
    application_id = model["application_id"]
    if args.application_id and args.application_id != application_id:
        raise ResumeError("draft application ID does not match the requested application")
    posting, decisions = application_decisions(projects_path.parent, model, legacy_replay=args.legacy_replay)
    if args.ats_plain:
        apply_plain_mode(model)
        draft_bytes = (json.dumps(model, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    compatible_models = policy.get("compatible_model_versions", [policy.get("version")])
    if model["schema_version"] not in compatible_models:
        raise ResumeError(
            f"policy version {policy.get('version')} is not compatible with "
            f"resume model v{model['schema_version']}"
        )
    if len(set(policy.get("sizes_pt", {}).values())) > 2:
        raise ResumeError("ATS policy must use no more than two font sizes")

    pdf_name = previous_pdf(output_dir, args.pdf_name, args.base_generation, require_base=True)
    if not isinstance(pdf_name, str) or not re.fullmatch(r"[^/\\]+\.pdf", pdf_name) or pdf_name.startswith("."):
        raise ResumeError("--pdf-name must be a visible PDF filename without a path")
    if args.legacy_formats and pdf_name != "resume.pdf":
        raise ResumeError("--legacy-formats requires the resume.pdf path")
    require_atomic_update(output_dir)
    generation = uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".ekb-resume-", dir=output_dir.parent) as temporary:
        temp_dir = Path(temporary) / "bundle"
        temp_dir.mkdir(mode=0o700)
        staged_model = temp_dir / "resume.json"
        staged_model.write_bytes(draft_bytes)
        source_report = run_source_check(
            staged_model, profile_path, projects_path, ranking_path, policy=policy_path,
            require_claim_reviews=True, editorial_packet=True, decisions=decisions,
        )
        if not source_report.get("valid"):
            raise ResumeError("source validation failed:\n- " + "\n- ".join(source_report.get("errors", [])))

        docx_path = temp_dir / "resume.docx"
        pdf_path = temp_dir / pdf_name
        emphasizer = render_pdf(model, policy, pdf_path)
        docx_structure = None
        if args.legacy_formats:
            render_docx(model, policy, docx_path)
            docx_text, docx_structure = extract_docx(docx_path)

        expected = resume_lines(model)
        phrases = protected_line_phrases(model, policy)
        (
            pdf_text,
            pdf_pages,
            detected_page_size,
            fill_ratios,
            orphaned_wraps,
            broken_word_wraps,
            protected_phrase_wraps,
        ) = extract_pdf(pdf_path, policy, phrases)
        errors: list[str] = []
        warnings = editorial_warnings(model, policy)
        warnings.extend(ai_visibility_warnings(model, policy))
        warnings.extend(application_guidance_warnings(model, policy))
        current_workflow = decisions is not None or (
            model["schema_version"] == 2 and model["target"]["mode"] == "master"
            and (posting.get("schema_version", 1) == 2 or not args.legacy_replay)
        )
        density_errors, density_warnings = content_density_findings(
            model, policy, pdf_pages, fill_ratios,
            enforce_minimum=current_workflow,
        )
        errors.extend(density_errors)
        warnings.extend(density_warnings)
        for page_number, page_orphans in enumerate(orphaned_wraps, 1):
            for orphan in page_orphans:
                warnings.append(
                    f"PDF page {page_number} has a one-word wrapped final line ({orphan}); "
                    "shorten or rewrite the sentence before using a non-breaking space"
                )
        for page_number, page_breaks in enumerate(broken_word_wraps, 1):
            for word in page_breaks:
                errors.append(
                    f"PDF page {page_number} splits the word {word} across lines; "
                    "rewrite the line or fix the renderer before delivery"
                )
        for page_number, page_breaks in enumerate(protected_phrase_wraps, 1):
            for phrase in page_breaks:
                errors.append(
                    f"PDF page {page_number} splits the protected phrase {phrase!r} "
                    "across lines; keep the complete phrase together"
                )
        presentation_findings = link_warnings(model, reviewed=bool(decisions))
        presentation_findings.extend(emphasis_warnings(model, policy, emphasizer))
        warnings.extend(presentation_findings)
        warnings.extend(source_report.get("warnings", []))
        errors.extend(verify_order(expected, pdf_text, "PDF"))
        errors.extend(rendered_typography_errors(expected, pdf_text, "PDF", policy))
        if docx_structure is not None:
            errors.extend(verify_order(expected, docx_text, "DOCX"))
            errors.extend(rendered_typography_errors(expected, docx_text, "DOCX", policy))
            if docx_structure["tables"]:
                errors.append("DOCX contains tables")
            if docx_structure["inline_shapes"]:
                errors.append("DOCX contains inline images or shapes")
            if not allowed_continuation_header(model, docx_structure["header_footer_text"]):
                errors.append("DOCX contains non-permitted factual header/footer text")
        if len(normalize(pdf_text)) < 50:
            errors.append("PDF does not contain enough selectable text")
        expected_page_size = "A4" if model["target"]["market"] == "europe" else "LETTER"
        if detected_page_size != expected_page_size:
            errors.append(f"PDF page size is {detected_page_size}, expected {expected_page_size}")
        if pdf_pages > 2:
            errors.append("PDF exceeds the two-page maximum")
        if pdf_pages > model["layout"]["page_target"]:
            warnings.append(f"PDF exceeds the preferred {model['layout']['page_target']}-page target")

        attachment_stem = pdf_path.stem
        recommended_attachment = pdf_path.name
        outputs = {pdf_path.name: pdf_path, "resume.json": staged_model}
        if args.legacy_formats:
            attachment_stem = delivery_stem(model, policy)
            attachment_docx = temp_dir / f"{attachment_stem}.docx"
            attachment_pdf = temp_dir / f"{attachment_stem}.pdf"
            shutil.copyfile(docx_path, attachment_docx)
            shutil.copyfile(pdf_path, attachment_pdf)
            outputs.update({
                "resume.docx": docx_path,
                attachment_docx.name: attachment_docx,
                attachment_pdf.name: attachment_pdf,
            })
            recommended_attachment = attachment_pdf.name
        if args.include_text:
            text_path = temp_dir / "resume.txt"
            text_path.write_text("\n".join(text_export_lines(model, policy)) + "\n", encoding="utf-8")
            outputs["resume.txt"] = text_path

        packet_path = temp_dir / "editorial.json"
        packet = source_report.pop("editorial_packet")
        packet.update({
            "delivery_status": DELIVERY_STATUS, "generation": generation,
            "posting_sha256": posting_digest(posting), "primary_pdf": pdf_name,
            "pdf_sha256": sha256(pdf_path), "model_sha256": sha256(staged_model),
            "semantic_review": source_report["semantic_review"],
        })
        packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        outputs["editorial.json"] = packet_path
        findings = [
            {"severity": "presentation" if warning in presentation_findings else "editorial",
             "message": warning}
            for warning in warnings
        ]
        findings.extend(source_report.get("link_findings", []))
        if decisions:
            for row in source_report["coverage"]["requirements"]:
                if (row["disposition"] in {"unresolved", "gap"}
                        or (row.get("discovery", {}).get("question") and row["priority"] == "required")):
                    findings.append({
                        "severity": "editorial", "requirement_id": row["id"],
                        "message": f"{row['term']} ({row['disposition']}). {row['reason']}",
                    })
        findings.extend({"severity": "blocking", "message": error} for error in errors)
        report = {
            "valid": not errors,
            "delivery_status": DELIVERY_STATUS,
            "generation": generation,
            "primary_pdf": pdf_name,
            "posting_sha256": posting_digest(posting),
            "policy_version": policy["version"],
            "application_id": model["application_id"],
            "resume_mode": model["target"]["mode"],
            "source_validation": source_report,
            "presentation": {
                "hyperlinks": model["layout"].get("hyperlinks", "auto"),
                "hyperlink_color": f"#{link_appearance(policy)[0]}",
                "hyperlink_underline": link_appearance(policy)[1],
                "emphasis": model["layout"].get("emphasis", "matched-requirements"),
                "emphasis_terms": emphasizer.terms,
                "emphasis_applied": emphasizer.count,
                "linked_items": count_links(model),
                "bullet_layout": bullet_layout(policy),
                "spacing_pt": policy["spacing_pt"],
                "attachment_stem": attachment_stem,
            },
            "document_validation": {
                "errors": errors,
                "warnings": warnings,
                "findings": findings,
                "docx_structure": docx_structure,
                "pdf_pages": pdf_pages,
                "page_size": detected_page_size,
                "pdf_password_protected": False,
                "content_fill_ratios": fill_ratios,
                "orphaned_wraps": orphaned_wraps,
                "broken_word_wraps": broken_word_wraps,
                "protected_phrase_wraps": protected_phrase_wraps,
                "expected_lines": len(expected),
            },
            "outputs": {
                name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                for name, path in outputs.items()
            },
        }
        validation_json = temp_dir / "validation.json"
        named_freelance = source_report.get("project_selection", {}).get(
            "named_in_freelance_projects",
            source_report.get("project_selection", {}).get("named_in_selected_projects", []),
        )
        validation_md = temp_dir / "validation.md"
        validation_md.write_text(
            "# Resume validation\n\n"
            f"- Technical validation: {'PASS' if report['valid'] else 'FAIL'}\n"
            "- Delivery status: private draft. Human editorial approval and full PDF inspection are required.\n"
            f"- Application: `{model['application_id']}`\n"
            f"- Resume mode: {report['resume_mode']}\n"
            f"- ATS policy: v{policy['version']}\n"
            f"- Generation: `{generation}`\n"
            f"- PDF SHA-256: `{sha256(pdf_path)}`\n"
            f"- Draft attachment filename: `{recommended_attachment}`\n"
            f"- Selected sources: {', '.join(source_report['selected_sources'])}\n"
            f"- Hyperlinks: {report['presentation']['hyperlinks']} "
            f"({report['presentation']['linked_items']} linked items; "
            f"{report['presentation']['hyperlink_color']}, "
            f"{'underlined' if report['presentation']['hyperlink_underline'] else 'not underlined'})\n"
            f"- Emphasis: {report['presentation']['emphasis']} "
            f"({len(emphasizer.terms)} terms, {emphasizer.count} applied)\n"
            + (
                f"- Project evidence used anywhere: "
                f"{', '.join(source_report['project_selection']['evidence_used'])}"
                f" (ranks {', '.join(str(rank) for rank in source_report['project_selection']['evidence_ranks'])})\n"
                if source_report.get("project_selection", {}).get("evidence_used")
                else ""
            )
            + (
                f"- Named in Freelance Projects: "
                f"{', '.join(named_freelance)}"
                f" (ranks {', '.join(str(rank) for rank in source_report['project_selection']['named_ranks'])})\n"
                if named_freelance
                else "- Named in Freelance Projects: none\n"
            )
            + (f"- Requirement map revision: `{decisions['revision_sha256']}`\n" if decisions else "")
            + coverage_section(source_report)
            + selection_score_section(source_report)
            + f"- PDF pages: {pdf_pages}\n"
            f"- Content fill by page: {', '.join(f'{ratio:.1%}' for ratio in fill_ratios)}\n"
            + (
                f"- DOCX tables: {docx_structure['tables']}\n"
                f"- DOCX images/shapes: {docx_structure['inline_shapes']}\n"
                if docx_structure is not None else ""
            )
            + f"- Extraction/order errors: {len(errors)}\n"
            f"- Editorial findings: {sum(item['severity'] == 'editorial' for item in findings)}\n"
            + coverage_table(source_report)
            + external_signals_section(source_report)
            + (("\n## Findings\n\n" + "\n".join(f"- **{item['severity']}** — {item['message']}" for item in findings) + "\n") if findings else ""),
            encoding="utf-8",
        )
        report["report_sha256"] = sha256(validation_md)
        validation_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        outputs["validation.json"] = validation_json
        outputs["validation.md"] = validation_md

        if errors:
            raise ResumeError("document validation failed:\n- " + "\n- ".join(errors))

        # Recheck mutable evidence and screening immediately before the swap.
        final_report = run_source_check(
            staged_model, profile_path, projects_path, ranking_path, policy=policy_path,
            require_claim_reviews=True, editorial_packet=True, decisions=decisions,
        )
        if not final_report.get("valid") or final_report["semantic_review"] != source_report["semantic_review"]:
            raise ResumeError("evidence or review rules changed during rendering; validate the draft again")
        current_posting, current_decisions = application_decisions(
            projects_path.parent, model, legacy_replay=args.legacy_replay
        )
        if posting_digest(current_posting) != posting_digest(posting) or current_decisions != decisions:
            raise ResumeError("frozen opportunity or requirement map changed during rendering")
        publish(temp_dir, output_dir, set(outputs))

    print(json.dumps({
        "valid": True,
        "delivery_status": DELIVERY_STATUS,
        "generation": generation,
        "output_dir": str(output_dir),
        "selected_sources": source_report["selected_sources"],
    }, indent=2))
    return 0


def validate(args: argparse.Namespace) -> int:
    model_path = Path(args.draft or args.model).resolve()
    profile_path = Path(args.profile).resolve()
    draft_bytes = model_path.read_bytes()
    model = json.loads(draft_bytes)
    projects_path = Path(args.projects).resolve()
    policy_path = (
        Path(args.policy).resolve()
        if args.policy
        else Path(config_path("resume-policy.json", str(projects_path.parent)))
    )
    validate_model(model, load_json(policy_path))
    if args.application_id and args.application_id != model["application_id"]:
        raise ResumeError("draft application ID does not match the requested application")
    decisions = None
    application_path = projects_path.parent / "applications" / f"{model['application_id']}.yaml"
    if args.editorial_packet or application_path.is_file():
        if args.editorial_packet or frozen_application(projects_path.parent, model["application_id"]).get("schema_version") == 2:
            _, decisions = application_decisions(projects_path.parent, model, legacy_replay=args.legacy_replay)
    ranking_path = Path(args.ranking).resolve() if args.ranking else profile_path.with_name("project-ranking.yaml")
    with tempfile.TemporaryDirectory(prefix="ekb-validate-") as directory:
        draft = Path(directory) / "resume.json"
        draft.write_bytes(draft_bytes)
        report = run_source_check(
            draft, profile_path, projects_path, ranking_path, policy=policy_path,
            editorial_packet=args.editorial_packet, decisions=decisions,
        )
    if decisions and application_decisions(projects_path.parent, model)[1] != decisions:
        raise ResumeError("requirement map changed during validation")
    report["validation_scope"] = "reviewed_application_draft" if decisions else "source_diagnostic_only"
    report["delivery_status"] = DELIVERY_STATUS
    print(json.dumps(report, indent=2))
    return 0 if report.get("valid") else 1


def verify_review(args):
    output = Path(args.output_dir).absolute()
    if not output.is_dir() or output.is_symlink():
        raise ResumeError("no published bundle to verify")
    with publication_lock(output):
        pdf = previous_pdf(output, None)
        manifest_path = output / "validation.json"
        report = load_json(manifest_path)
        packet = load_json(output / "editorial.json")
        model = load_json(output / "resume.json")
        if args.application_id and args.application_id != model["application_id"]:
            raise ResumeError("bundle application ID does not match the requested application")
        projects = Path(args.projects).resolve()
        posting, decisions = application_decisions(projects.parent, model, legacy_replay=args.legacy_replay)
        profile = Path(args.profile).resolve()
        ranking = Path(args.ranking).resolve() if args.ranking else profile.with_name("project-ranking.yaml")
        current = run_source_check(
            output / "resume.json", profile, projects, ranking,
            require_claim_reviews=True, editorial_packet=True, decisions=decisions,
            policy=Path(args.policy).resolve() if args.policy else None,
        )
        saved_source = report["source_validation"]
        identity = {
            "application_id": model["application_id"], "generation": report["generation"],
            "posting_sha256": posting_digest(posting), "primary_pdf": pdf,
            "pdf_sha256": sha256(output / pdf),
        }
        if (not current["valid"] or current["semantic_review"] != saved_source["semantic_review"]
                or current["coverage"] != saved_source["coverage"]
                or saved_source.get("requirement_map") != decisions
                or report["posting_sha256"] != identity["posting_sha256"]
                or any(packet.get(key) != value for key, value in identity.items())
                or packet["model_sha256"] != sha256(output / "resume.json")
                or packet["semantic_review"] != current["semantic_review"]
                or any(packet.get(key) != value for key, value in current["editorial_packet"].items())):
            raise ResumeError("published approval packet no longer matches current evidence or bundle")
        current_posting, current_decisions = application_decisions(projects.parent, model, legacy_replay=args.legacy_replay)
        if posting_digest(current_posting) != identity["posting_sha256"] or current_decisions != decisions:
            raise ResumeError("application inputs changed during approval verification")
        expected = identity | {
            "validation_sha256": sha256(manifest_path),
            "editorial_sha256": sha256(output / "editorial.json"),
            "requirement_map_sha256": decisions["revision_sha256"] if decisions else None,
        }
        receipt = load_json(Path(args.approval))
        from ekb_capabilities import valid_date

        if (any(key not in receipt or receipt[key] != value for key, value in expected.items())
                or not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip()
                or not valid_date(receipt.get("reviewed_at"))
                or any(receipt.get(key) is not True for key in
                       ("material_claims_approved", "exact_pdf_inspected", "gaps_reviewed"))):
            raise ResumeError("human approval receipt is incomplete or refers to a different PDF or generation")
        print(json.dumps({"approval_receipt_matches": True, **expected}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Validate and render evidence-linked EKB resumes")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "render", "verify-review"):
        command = commands.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--legacy-replay", action="store_true", help="use an explicitly screened historical intake")
        command.add_argument("--draft", help="separate draft model to validate or publish")
        command.add_argument("--application-id", help=argparse.SUPPRESS)
        command.add_argument("--profile", required=True)
        command.add_argument("--projects", required=True)
        command.add_argument(
            "--ranking",
            help="global project ranking; defaults to project-ranking.yaml beside the profile",
        )
        if name == "render":
            command.add_argument(
                "--policy",
                help="writing and structure policy; defaults to config/resume-policy.json or its workspace override",
            )
            command.add_argument("--output-dir", required=True)
            command.add_argument("--base-generation", help="refuse to overwrite a newer published generation")
            command.add_argument("--include-text", action="store_true")
            command.add_argument("--pdf-name", help="stable PDF filename; defaults to the existing published name")
            command.add_argument("--legacy-formats", action="store_true", help="also export DOCX and named attachment copies")
            command.add_argument(
                "--ats-plain",
                action="store_true",
                help="render the same text with no hyperlink annotations and no bold emphasis",
            )
        elif name == "verify-review":
            command.add_argument("--output-dir", required=True)
            command.add_argument("--approval", required=True, help="human-authored JSON review receipt")
            command.add_argument("--policy", help="same explicit policy used to render the bundle")
        else:
            command.add_argument(
                "--editorial-packet", action="store_true",
                help="include private excerpts and evidence locations for cited records after screening",
            )
            command.add_argument(
                "--policy",
                help="writing and structure policy; defaults to config/resume-policy.json",
            )
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return {"render": render, "validate": validate, "verify-review": verify_review}[args.command](args)
    except (ResumeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"EKB Resume: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
