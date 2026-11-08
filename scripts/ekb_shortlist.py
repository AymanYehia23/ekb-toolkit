#!/usr/bin/env python3
"""Generate applications/<id>.evidence.yaml: the per-requirement evidence
shortlist.

WHY THIS EXISTS
    The pipeline externalizes the target (applications/<id>.yaml), the output
    (resume.json), and the verification (validation.json). Between "262 curated
    records" and "this resume" it externalized nothing, so the single decision
    that determines quality, which evidence answers which requirement, happened
    implicitly and left no trace. Nothing could review it, check it, or improve
    it.

    This file is that missing artifact. The CANDIDATES are derived
    mechanically from the frozen requirements and the evidence index. The
    DECISIONS are authored: which candidate won, and why it beat the runner-up.

    Writing the comparison down is most of the value. In the 2026-07-28 review
    a `required` performance requirement was answered by a skills-list line
    while two strength-10 records with the portfolio's only before/after
    measurement sat unused. On paper, side by side, that choice is visibly
    wrong.

USAGE
    ekb shortlist <id>
    ekb shortlist <id> --refresh   # keep decisions

Decisions already recorded are preserved across a refresh; only the candidate
lists are recomputed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
import os
from pathlib import Path
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ekb_paths import workspace_root, evidence_policy  # noqa: E402
from ekb_capabilities import MEETS_MINIMUM, capability_matches, read_capabilities  # noqa: E402
from ekb_index import build as build_index  # noqa: E402
from ekb_requirements import decision_basis, frozen_requirements  # noqa: E402
from ekb_screening import ScreeningError, posting_digest, require_screening  # noqa: E402

ROOT = workspace_root()

# Mirrors resume_source_check.rb so the shortlist and the understatement gate
# agree on what counts as a candidate. Keep the two in step.
ALIAS_STOPWORDS = {
    "the", "and", "for", "with", "app", "apps", "code", "data", "new", "use",
    "using", "team", "work", "years", "year",
}


class NoAliasDumper(yaml.SafeDumper):
    """Emit repeated values inline instead of as YAML anchors.

    The Ruby source checker loads YAML with `aliases: false` on purpose, so an
    anchor emitted here becomes a hard parse failure downstream. Repeated empty
    lists and identical strings are exactly what PyYAML would otherwise
    deduplicate.
    """

    def ignore_aliases(self, data):
        return True


def dump_yaml(payload) -> str:
    return yaml.dump(
        payload, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True, width=100
    )


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def usable_alias(value: str) -> bool:
    text = str(value or "").strip().lower()
    if len(text) < 3 and text not in {"c", "r", "go", "c#"}:
        return False
    if re.fullmatch(r"[\d\s+.]+", text):
        return False
    return text not in ALIAS_STOPWORDS


def term_present(haystack: str, term: str) -> bool:
    return re.search(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])", haystack, re.I) is not None


RETRIEVAL = json.loads(
    (Path(__file__).resolve().parent.parent / "config" / "retrieval.json").read_text(encoding="utf-8")
)
GENERIC_TERMS = set(RETRIEVAL["generic_terms"])


def requirement_terms(requirement, aliases):
    exact = {str(value).strip().lower() for value in [requirement, *aliases] if usable_alias(value)}
    return exact | {
        term for group in RETRIEVAL["equivalent_terms"] if exact.intersection(group)
        for term in group
    }


def candidates_for(index: dict, aliases: list, limit: int | None, *, requirement: str = "", role: str = "") -> list:
    terms = requirement_terms(requirement, aliases)
    if not terms:
        return []
    focus = {
        term for focus_rule in RETRIEVAL["role_focus"]
        if requirement.lower() in focus_rule["requirements"] and
        any(term_present(role, term) for term in focus_rule["role_terms"])
        for term in focus_rule["evidence_terms"]
    }
    capabilities = index.get("capabilities") or {}
    bridge_details = {}
    for bridge in index.get("evidence_bridges") or []:
        bridge_text = " ".join(str(value) for value in (bridge.get("aliases") or []))
        matched = {term for term in terms if term_present(bridge_text, term)}
        if not matched:
            continue
        for record_id in bridge.get("records") or []:
            bridge_details.setdefault(record_id, []).append({
                "profile_ref": bridge.get("profile_ref"),
                "required_public_phrases": bridge.get("required_public_phrases") or [],
                "cap": bridge.get("cap"),
                "terms": sorted(matched),
            })

    rows = []
    for row in index.get("records") or []:
        if not row.get("eligible"):
            continue
        statement = row.get("statement") or row.get("claim", "")
        tags = row.get("tags") or []
        matches = {
            term for term in terms | focus
            if term in tags or row["id"] in (capabilities.get(term) or []) or term_present(statement, term)
        }
        bridges = bridge_details.get(row["id"], [])
        if not matches and not bridges:
            continue
        specific = (matches | {term for bridge in bridges for term in bridge["terms"]}) - GENERIC_TERMS
        # Count fit by level, not by keyword volume. A specific evidence bridge
        # is stronger than a generic bridge, and a role-specific hit beats both
        # a generic framework match and any global rank bonus.
        tier = 3 if matches & focus else 2 if specific else 1
        rows.append({
            **row,
            "profile_bridges": bridges,
            "match_terms": sorted(matches),
            "match_tier": tier,
            "match_reason": {3: "role-specific evidence", 2: "specific requirement evidence", 1: "general stack evidence"}[tier],
        })

    rows.sort(key=lambda row: (
        -row["match_tier"],
        not bool(row["profile_bridges"]),
        -float(row.get("strength") or 0),
        row.get("project_rank") or 999,
        row["id"],
    ))
    # Give different projects a chance to demonstrate a broad requirement
    # before spending every slot on one project. Never mix specificity tiers.
    positions = {}
    for row in rows:
        bucket = (row["match_tier"], row["project"])
        row["_project_position"] = positions.get(bucket, 0)
        positions[bucket] = row["_project_position"] + 1
    rows.sort(key=lambda row: (-row["match_tier"], row["_project_position"]))
    return rows[:limit]


def profile_candidates_for(index: dict, terms: list) -> list:
    """Retrieve confirmed responsibilities and legacy skills at their stated scope."""
    out = []
    for entry in index.get("profile_sources") or []:
        values = [entry.get("label", ""), entry.get("covers", ""), *entry.get("phrasings", [])]
        items = [
            item for item in entry.get("items", [])
            if any(term_present(str(item.get("name", "")), term) for term in terms)
        ]
        if items or any(term_present(value, term) for value in values for term in terms):
            out.append({
                "ref": entry["id"],
                "origin": entry["origin"],
                "kind": entry["kind"],
                "label": entry.get("label", ""),
                "basis": items or entry.get("covers", ""),
                "cap": entry.get("cap"),
            })
    return out


def requirement_mapping(requirement, direct, profile_rows, capabilities, index, limit, policy, employers):
    term = requirement.get("term") or ""
    category = requirement.get("category") or "unclassified"
    assessment = requirement.get("assessment") or {}
    formal = category == "qualification"
    if formal:
        status = assessment.get("status")
        if status not in ("qualification supported", "formal eligibility gap") or not assessment.get("basis"):
            status = "needs confirmation"
        return {
            "classification": status,
            "why_it_matters": requirement.get("why_it_matters"),
            "posting_excerpt": requirement.get("posting_excerpt"),
            "assessment_basis": assessment.get("basis"),
            "matches": [],
            "discovery": "Use the frozen screening findings and confirmed qualification facts.",
        }

    minimum = requirement.get("minimum_proficiency")
    if minimum is not None and (not isinstance(minimum, str) or minimum not in MEETS_MINIMUM):
        raise ValueError(f"{term}: invalid minimum proficiency")
    terms = requirement_terms(term, requirement.get("aliases") or [])
    related = [rule for rule in RETRIEVAL["related_requirements"] if terms.intersection(rule["requirements"])]
    examples = {value for rule in related for value in rule.get("example_terms", [])}
    transfer = {value for rule in related for value in rule.get("transfer_terms", [])}
    matches = [
        {
            "ref": row["id"],
            "classification": "direct professional evidence" if row["project"] in employers else "direct project evidence",
            "label": row["project"],
            "kind": row["kind"],
            "involvement": row["involvement"],
            "basis": row["statement"],
            "matched_terms": row["match_terms"],
            "limitations": row.get("cautions") or [],
            "confidence": "verify relevance",
            "needs_confirmation": False,
            "resume_use": "Use a concrete accomplishment if the curated record supports this requirement.",
        }
        for row in direct
    ]
    matches.extend({
        **row,
        "classification": "broader professional capability" if row["origin"] == "responsibility" else "profile skill (proficiency unspecified)",
        "confidence": "verify relevance",
        "needs_confirmation": False,
        "resume_use": "Use supported profile wording and retain its limitations.",
    } for row in profile_rows)
    matches.extend(capability_matches(capabilities, terms, transfer, policy, term_present, minimum))

    # Directional cues identify examples worth reading. They do not make a
    # related technology an alias or force the understatement gate to count it.
    direct_refs = {row["id"] for row in direct}
    related_rows = candidates_for(index, sorted(examples | transfer), limit + len(direct_refs))
    matches.extend({
        "ref": row["id"],
        "label": row["project"],
        "classification": "transferable experience" if set(row["match_terms"]) & transfer else "related engineering example",
        "kind": row["kind"],
        "involvement": row["involvement"],
        "basis": row["statement"],
        "matched_terms": row["match_terms"],
        "limitations": row.get("cautions") or [],
        "confidence": "verify relevance",
        "needs_confirmation": False,
        "resume_use": "Describe the evidenced work and explain the connection privately.",
    } for row in [item for item in related_rows if item["id"] not in direct_refs][:limit])

    supported = [row for row in matches if not row["needs_confirmation"]]
    priority = (
        "direct professional evidence", "broader professional capability", "direct project evidence",
        "practical non-professional experience", "working knowledge", "familiarity",
        "profile skill (proficiency unspecified)", "related engineering example",
        "transferable experience", "genuine gap",
    )
    ranks = {value: rank for rank, value in enumerate(priority)}
    matches.sort(key=lambda row: (
        row["needs_confirmation"], row.get("fit") == "gap", row.get("fit") == "partial",
        ranks.get(row["classification"], len(ranks)),
    ))
    classification = matches[0]["classification"] if supported else "needs confirmation"
    if not supported and assessment.get("status") == "genuine gap" and assessment.get("basis"):
        classification = "genuine gap"
    discovery = None
    if classification in ("needs confirmation", "transferable experience") and requirement.get("priority") == "required":
        discovery = (
            f"After checking previous answers, ask if still material: what have you used or learned about "
            f"{term}, in which context, and what could you demonstrate in an interview?"
        )
    return {
        "classification": classification,
        "minimum_proficiency": minimum,
        "why_it_matters": requirement.get("why_it_matters"),
        "posting_excerpt": requirement.get("posting_excerpt"),
        "assessment_basis": assessment.get("basis"),
        "matches": matches,
        "discovery": discovery,
    }


def build(root: str, application_id: str, limit: int, requirement_filter: str | None = None) -> dict:
    application = require_screening(Path(root), application_id)
    targeting = application.get("targeting") or {}
    current_workflow = application.get("schema_version") == 2 and targeting.get("resume_mode") != "master"
    input_digest = decision_basis(Path(root), application) if current_workflow else None
    # Rebuild in memory from the current records. The persisted index can
    # predate curation and is not part of the requirement decision.
    index = build_index(root)
    policy = evidence_policy(root)
    profile_path = Path(root) / "profile" / "profile.yaml"
    profile = load_yaml(profile_path) if profile_path.is_file() else {}
    capabilities = read_capabilities(profile)
    employers = {project for entry in profile.get("experience") or [] for project in entry.get("projects") or []}
    requirements = frozen_requirements(application) if current_workflow else targeting.get("requirements") or []
    if requirement_filter is not None:
        requirements = [item for item in requirements if item.get("term") == requirement_filter]
        if not requirements:
            raise ValueError(f"no frozen requirement named {requirement_filter!r}")

    # Preserve authored decisions across a refresh.
    out_path = os.path.join(root, "applications", f"{application_id}.evidence.yaml")
    previous = {}
    if not current_workflow and os.path.isfile(out_path):
        for entry in (load_yaml(out_path).get("requirements") or []):
            if isinstance(entry, dict) and entry.get("term"):
                previous[entry["term"]] = {
                    "selected": entry.get("selected") or [],
                    "reason": entry.get("reason") or "",
                }

    def sort_key(requirement):
        priority = 0 if requirement.get("priority") == "required" else 1
        return (priority, 0 if requirement.get("critical") else 1)

    rows = []
    for requirement in sorted(requirements, key=sort_key):
        aliases = requirement.get("aliases") or []
        term = requirement.get("term") or ""
        formal = requirement.get("category") == "qualification"
        leads = [] if formal else candidates_for(
            index, aliases, None if current_workflow else limit,
            requirement=term, role=application.get("role") or "",
        )
        found = leads[:limit]
        project_leads = {}
        if current_workflow:
            for lead in leads:
                project_leads.setdefault(lead["project"], []).append({
                    "ref": lead["id"], "match_tier": lead["match_tier"],
                })
        profile_rows = [] if formal else profile_candidates_for(index, sorted(requirement_terms(term, aliases)))
        mapping = requirement_mapping(requirement, found, profile_rows, capabilities, index, limit, policy, employers)
        if current_workflow:
            for match in mapping["matches"]:
                match["suggested_classification"] = match.pop("classification")
            mapping["suggested_classification"] = mapping.pop("classification")
            mapping["review_state"] = "unreviewed retrieval leads"
        decision = previous.get(requirement.get("term"), {"selected": [], "reason": ""})
        rows.append(
            {
                "term": requirement.get("term"),
                "priority": requirement.get("priority"),
                "critical": bool(requirement.get("critical")),
                "aliases": aliases,
                "category": requirement.get("category"),
                "mapping": mapping,
                "candidates": [
                    {
                        "ref": row["id"],
                        "project": row["project"],
                        "strength": row["strength"],
                        "match_terms": row["match_terms"],
                        "match_reason": row["match_reason"],
                        "signals": row.get("signals") or [],
                        "claim": row.get("bullet") or row.get("claim", ""),
                        "cautions": row.get("cautions") or [],
                        **(
                            {"profile_bridges": row["profile_bridges"]}
                            if row.get("profile_bridges")
                            else {}
                        ),
                    }
                    for row in found
                ],
                # Profile entries that could state this requirement. A project
                # record demonstrates; these only claim. Kept separate so the
                # difference stays visible while deciding.
                "profile_candidates": profile_rows,
                # Authored. Empty means the decision has not been made yet.
                **({"id": requirement["id"], "project_leads": project_leads}
                   if current_workflow else decision),
            }
        )

    covered = sum(1 for row in rows if row["candidates"])
    profile_only = sum(1 for row in rows if not row["candidates"] and row["profile_candidates"])
    return {
        "schema_version": 2 if current_workflow else 1,
        "kind": "evidence-shortlist",
        "application": application_id,
        "generated_at": dt.date.today().isoformat(),
        "generator": "scripts/ekb_shortlist.py",
        "basis": {
            "posting_sha256": posting_digest(application),
            **({"decision_basis_sha256": input_digest} if current_workflow else {}),
            "requirements": len(rows),
            "requirements_with_candidates": covered,
            "requirements_with_profile_sources_only": profile_only,
            "requirements_with_broader_capability_matches": sum(
                any(match.get("proficiency") and match.get("resume_use")
                    for match in row["mapping"]["matches"])
                for row in rows
            ),
            "index_records": len((index.get("records") or [])),
            "candidate_limit_per_requirement": limit,
        },
        "requirements": rows,
    }


HEADER = """# EVIDENCE SHORTLIST. Candidates are generated; decisions are authored.
#
# Rebuild candidates with: ekb shortlist <id> --refresh
# (a refresh preserves every `selected` and `reason` already recorded)
#
# HOW TO USE IT
#   Work top down. Required and critical requirements come first. For each one,
#   read the candidates, put the winning record IDs in `selected`, and write in
#   `reason` why that beats the runner-up. When the winner is NOT the strongest
#   candidate listed, the reason must say what outranked strength: a page-limit
#   cut, a counting rule, non-redundant coverage that matters more.
#   A keyword match is retrieval, not an instruction to publish the record. For
#   non-critical commodity tools such as Git, prefer a supported profile source
#   unless the project candidate is independently worth resume space. Never add
#   an internal recovery or maintenance anecdote solely to raise coverage from
#   `stated` to `demonstrated`.
#   Read every candidate's `cautions` before selecting it. They are copied from
#   the curated record's limitations and bind both the decision and the wording.
#
# WHAT IT IS NOT
#   Not evidence. `strength` and `claim` are derived from the curated record and
#   license nothing. Every visible resume line still cites the record itself and
#   still passes the source check. Read `mapping` for broader capabilities,
#   examples, transfer and discovery. Empty retrieval means the match remains open.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", required=True, help="application id")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--limit", type=int, default=6, help="candidates per requirement")
    parser.add_argument("--refresh", action="store_true", help="recompute candidates, keep decisions")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--requirement", help="exact frozen requirement to inspect with --stdout")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.requirement and not args.stdout:
        parser.error("--requirement requires --stdout")
    try:
        shortlist = build(args.root, args.application, args.limit, args.requirement)
        current = require_screening(Path(args.root), args.application)
        if posting_digest(current) != shortlist["basis"]["posting_sha256"]:
            raise ScreeningError("frozen posting changed during shortlisting")
        if shortlist["schema_version"] == 2 and decision_basis(Path(args.root), current) != shortlist["basis"]["decision_basis_sha256"]:
            raise ScreeningError("application inputs changed during shortlisting")
    except (ScreeningError, ValueError) as exc:
        parser.exit(1, f"EKB shortlist: {exc}\n")
    header = HEADER if shortlist["schema_version"] == 1 else (
        "# RETRIEVAL LEADS. Review the exact record and limitations.\n"
        "# Author fit and selection only in applications/ID.requirements.yaml.\n"
    )
    rendered = header + dump_yaml(shortlist)

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    out_path = os.path.join(args.root, "applications", f"{args.application}.evidence.yaml")
    if os.path.exists(out_path) and not args.refresh:
        print(f"{os.path.relpath(out_path, args.root)} exists; pass --refresh to recompute", file=sys.stderr)
        return 1

    try:
        if not args.refresh:
            with open(out_path, "x", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            with tempfile.NamedTemporaryFile(mode="w", dir=Path(out_path).parent, delete=False, encoding="utf-8") as handle:
                staged = Path(handle.name)
                try:
                    handle.write(rendered)
                    handle.flush()
                    os.replace(staged, out_path)
                finally:
                    staged.unlink(missing_ok=True)
    except (OSError, ScreeningError) as exc:
        parser.exit(1, f"EKB shortlist: {exc}\n")
    basis = shortlist["basis"]
    if shortlist["schema_version"] == 2:
        print(f"wrote {os.path.relpath(out_path, args.root)}: retrieval leads for {basis['requirements']} requirements")
        return 0
    undecided = sum(1 for r in shortlist["requirements"] if not r.get("selected") and not r.get("reason"))
    print(
        f"wrote {os.path.relpath(out_path, args.root)}: "
        f"{basis['requirements']} requirements, "
        f"{basis['requirements_with_candidates']} with eligible candidates, "
        f"{undecided} awaiting a decision"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
