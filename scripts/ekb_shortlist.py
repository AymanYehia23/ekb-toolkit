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
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ekb_paths import workspace_root, load_config  # noqa: E402

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
    if len(text) < 3:
        return False
    if re.fullmatch(r"[\d\s+.]+", text):
        return False
    return text not in ALIAS_STOPWORDS


def term_present(haystack: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack, re.I) is not None


def candidates_for(index: dict, aliases: list, limit: int) -> list:
    terms = [str(a).strip().lower() for a in aliases if usable_alias(a)]
    if not terms:
        return []
    capabilities = index.get("capabilities") or {}
    tagged = set()
    for term in terms:
        tagged.update(capabilities.get(term) or [])
    bridged = set()
    bridge_details = {}
    for bridge in index.get("evidence_bridges") or []:
        bridge_text = " ".join(str(value) for value in (bridge.get("aliases") or []))
        if any(term_present(bridge_text, term) for term in terms):
            for value in bridge.get("records") or []:
                record_id = str(value)
                bridged.add(record_id)
                bridge_details.setdefault(record_id, []).append(
                    {
                        "profile_ref": bridge.get("profile_ref"),
                        "required_public_phrases": bridge.get("required_public_phrases") or [],
                        "cap": bridge.get("cap"),
                    }
                )

    rows = []
    for row in index.get("records") or []:
        if not row.get("eligible"):
            continue
        if (
            row["id"] in tagged
            or row["id"] in bridged
            or any(term_present(row.get("claim", ""), t) for t in terms)
        ):
            candidate = dict(row)
            if row["id"] in bridge_details:
                candidate["profile_bridges"] = bridge_details[row["id"]]
            rows.append(candidate)
    # An explicit profile bridge is target-specific retrieval evidence. Surface
    # it before generic alias/tag matches so a low global project score cannot
    # push the very records named by the confirmed fact beyond the shortlist
    # limit.
    rows.sort(
        key=lambda r: (
            0 if r["id"] in bridged else 1,
            -float(r.get("strength") or 0),
            r.get("project_rank") or 999,
            r["id"],
        )
    )
    return rows[:limit]


def profile_candidates_for(index: dict, aliases: list) -> list:
    """Profile responsibilities and skill groups whose text an alias matches.

    Listed separately from project candidates because they answer a requirement
    differently: a project record DEMONSTRATES a capability, a profile entry only
    STATES it. Without this section a requirement that
    profile-responsibility-004 answers well showed as "no eligible evidence",
    which reads as a portfolio gap rather than the indexing gap it was.
    """
    terms = [str(a).strip().lower() for a in aliases if usable_alias(a)]
    if not terms:
        return []
    out = []
    for entry in index.get("profile_sources") or []:
        haystack = " ".join(
            [entry.get("label", ""), entry.get("covers", "")] + (entry.get("phrasings") or [])
        )
        if any(term_present(haystack, t) for t in terms):
            out.append(
                {
                    "ref": entry["id"],
                    "origin": entry["origin"],
                    "label": entry.get("label", ""),
                    "cap": entry.get("cap"),
                }
            )
    return out


def build(root: str, application_id: str, limit: int) -> dict:
    app_path = os.path.join(root, "applications", f"{application_id}.yaml")
    if not os.path.isfile(app_path):
        sys.exit(f"no frozen application at {app_path}")
    index_path = os.path.join(root, "index", "evidence-index.yaml")
    if not os.path.isfile(index_path):
        sys.exit("no evidence index; run ekb index first")

    application = load_yaml(app_path)
    index = load_yaml(index_path)
    targeting = application.get("targeting") or {}
    requirements = targeting.get("requirements") or []

    # Preserve authored decisions across a refresh.
    out_path = os.path.join(root, "applications", f"{application_id}.evidence.yaml")
    previous = {}
    if os.path.isfile(out_path):
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
        found = candidates_for(index, aliases, limit)
        decision = previous.get(requirement.get("term"), {"selected": [], "reason": ""})
        rows.append(
            {
                "term": requirement.get("term"),
                "priority": requirement.get("priority"),
                "critical": bool(requirement.get("critical")),
                "aliases": aliases,
                "candidates": [
                    {
                        "ref": row["id"],
                        "project": row["project"],
                        "strength": row["strength"],
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
                "profile_candidates": profile_candidates_for(index, aliases),
                # Authored. Empty means the decision has not been made yet.
                "selected": decision["selected"],
                "reason": decision["reason"],
            }
        )

    covered = sum(1 for row in rows if row["candidates"])
    profile_only = sum(1 for row in rows if not row["candidates"] and row["profile_candidates"])
    return {
        "schema_version": 1,
        "kind": "evidence-shortlist",
        "application": application_id,
        "generated_at": dt.date.today().isoformat(),
        "generator": "scripts/ekb_shortlist.py",
        "basis": {
            "requirements": len(rows),
            "requirements_with_candidates": covered,
            "requirements_with_profile_sources_only": profile_only,
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
#   still passes the source check. An empty `candidates` list means no eligible
#   project record matched the aliases; that is a real gap, not a search failure
#   to work around.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", required=True, help="application id")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--limit", type=int, default=6, help="candidates per requirement")
    parser.add_argument("--refresh", action="store_true", help="recompute candidates, keep decisions")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    shortlist = build(args.root, args.application, args.limit)
    rendered = HEADER + dump_yaml(shortlist)

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    out_path = os.path.join(args.root, "applications", f"{args.application}.evidence.yaml")
    if os.path.exists(out_path) and not args.refresh:
        print(f"{os.path.relpath(out_path, args.root)} exists; pass --refresh to recompute", file=sys.stderr)
        return 1

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    basis = shortlist["basis"]
    undecided = sum(1 for r in shortlist["requirements"] if not r["selected"] and not r["reason"])
    print(
        f"wrote {os.path.relpath(out_path, args.root)}: "
        f"{basis['requirements']} requirements, "
        f"{basis['requirements_with_candidates']} with eligible candidates, "
        f"{undecided} awaiting a decision"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
