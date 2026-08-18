#!/usr/bin/env python3
"""Generate index/evidence-index.yaml from the curated knowledge base.

WHY THIS EXISTS
    Resume generation must choose roughly a dozen visible items out of 250+
    curated records spread across 15,000 lines of YAML. Doing that by reading
    every project file in one pass is how the strongest evidence gets missed:
    the 2026-07-28 review found a `required` performance requirement satisfied
    by a skills-list line while the portfolio's only before/after measurement
    sat unused two files away.

    This index is the retrieval table that makes the comparison mechanical. It
    is DERIVED and REGENERATED, never authored: every row carries the record ID
    it came from, and nothing here licenses a claim. A generated document still
    cites the curated record, never the index.

USAGE
    ekb index                 # write index/evidence-index.yaml
    ekb index --check         # exit 1 if the file is stale
    ekb index --stdout        # print instead of writing
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bullet_quality import (  # noqa: E402
    bullet_text_findings,
    parse_bullet_bank,
    semantic_review_findings,
)
from ekb_paths import workspace_root, load_config  # noqa: E402

ROOT = workspace_root()

ELIGIBLE_KINDS = {"repo-verified", "user-stated"}
ELIGIBLE_INVOLVEMENT = {"led", "implemented", "contributed"}
LEGACY_ATTRIBUTION = {"sole": "implemented", "shared": "contributed", "unclear": "unknown"}

# Tag synonyms, loaded from config/capability-tags.yaml so a role profile can
# fold its own vocabulary without editing this file. Left side is the canonical
# capability; the right side is the set of curated tags that fold into it. An
# empty or missing config simply means no folding, which is a valid setup for a
# small knowledge base.
def load_tag_synonyms() -> dict:
    data = load_config("capability-tags.yaml")
    out = {}
    for canonical, variants in (data.get("synonyms") or {}).items():
        out[str(canonical)] = {str(v) for v in (variants or [])}
    return out


TAG_SYNONYMS = load_tag_synonyms()

# Number shaped like a real quantity, used to flag a record whose statement
# already carries a verified figure. Mirrors the checker's own tokenizer.
NUMERIC = re.compile(
    r"(?<![A-Za-z0-9])(?:[$€£]\s*)?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s?[KMBkmb]\+?(?![A-Za-z]))?(?:\s?%)?"
)

# Source-code and test-volume counts are useful private evidence, but they are
# not material scale signals for a public resume: splitting a file, commit, or
# test changes the number without changing the delivered capability. Remove
# those quantities before deciding whether a statement deserves `measured`.
COUNT_TOKEN = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
GAMEABLE_COUNT = re.compile(
    rf"(?<![A-Za-z0-9]){COUNT_TOKEN}\s*\+?"
    rf"(?:\s*(?:to|of|[-–—])\s*{COUNT_TOKEN}\s*\+?)?"
    r"\s*[- ]?\s*(?:source[- ]code\s+|test[- ]code\s+)?"
    r"(?:lines?|loc|files?|commits?|test\s+cases?|test\s+files?|cases?)\b",
    flags=re.IGNORECASE,
)


def has_material_number(statement: str) -> bool:
    """Return true only when a number remains after gameable code-size counts
    are removed. Durations, users, money, workload, and other material units
    still receive the coarse measured signal."""
    return bool(NUMERIC.search(GAMEABLE_COUNT.sub(" ", statement)))


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


def normalize_involvement(record: dict) -> str:
    involvement = record.get("involvement")
    if involvement:
        return str(involvement)
    return LEGACY_ATTRIBUTION.get(str(record.get("attribution")), "unknown")


def build_synonym_lookup() -> dict:
    lookup = {}
    for canonical, variants in TAG_SYNONYMS.items():
        lookup[canonical] = canonical
        for variant in variants:
            lookup[variant] = canonical
    return lookup


SYNONYMS = build_synonym_lookup()


def canonical_tags(tags) -> list:
    out = []
    for tag in tags or []:
        key = str(tag).strip().lower()
        if not key:
            continue
        canonical = SYNONYMS.get(key, key)
        if canonical not in out:
            out.append(canonical)
    return sorted(out)


def first_sentence(text: str, limit: int = 220) -> str:
    flat = " ".join(str(text or "").split())
    if not flat:
        return ""
    # Split on a sentence end that is not an abbreviation or a decimal.
    match = re.search(r"(?<=[a-z0-9)\"'])\.\s+(?=[A-Z])", flat)
    if match and match.start() < limit:
        flat = flat[: match.start() + 1]
    if len(flat) > limit:
        flat = flat[:limit].rsplit(" ", 1)[0] + "..."
    return flat


# The bullet banks predate the direct-language rule in resume/policy.json, so
# most of them use em dashes and arrows the renderer now rejects. Normalizing
# the punctuation here keeps a suggestion directly usable instead of handing the
# agent prose that will fail validation. Punctuation only; no wording changes.
FORBIDDEN_PUNCTUATION = [
    (re.compile(r"\s*[—–]\s*"), ", "),
    (re.compile(r"\s*[→⇒]\s*"), " to "),
]


def normalize_punctuation(text: str) -> str:
    for pattern, replacement in FORBIDDEN_PUNCTUATION:
        text = pattern.sub(replacement, text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r",\s*([.;:])", r"\1", text)
    return " ".join(text.split())


SRC_MARKER = re.compile(r"<!--\s*src:\s*([a-z0-9_\-]+-\d{3})\s*-->", re.I)


class BulletQualityError(ValueError):
    """A public bullet bank is unsafe to lift into the retrieval index."""


def collect_curated_bullets(root: str) -> dict:
    """Resume-ready phrasings already written for each record in
    `artifacts/bullets/*.md`.

    Those banks are the distillation work: someone already reduced sixteen raw
    records to the five that survive a recruiter's read, and wrote them as
    prose. Re-deriving that from `statement` on every application throws it away.

    Boundary: a phrasing is a SUGGESTION, never evidence. `artifacts/` is
    disposable generated output, so a bullet here cannot license a claim, and
    text drawn from it still passes the normal source check against the curated
    record (numbers, involvement wording, profile support). If the bank and the
    record ever disagree, the record wins and the bank should be regenerated.
    """
    bullets: dict[str, dict] = {}
    policy = load_config("resume-policy.json")
    quality = policy.get("bullet_quality") or {}
    maximum_bullets = int(quality.get("maximum_selected_per_project", 5))
    maximum_sources = int(quality.get("maximum_sources", 4))
    for path in sorted(glob.glob(os.path.join(root, "artifacts", "bullets", "*.md"))):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        entries = parse_bullet_bank(text)
        if SRC_MARKER.search(text) and not entries:
            raise BulletQualityError(
                f"{path} cites records but has no parseable top-level Markdown bullets"
            )
        if len(entries) > maximum_bullets:
            raise BulletQualityError(
                f"{path} has {len(entries)} publishable bullets; maximum is {maximum_bullets}"
            )
        for entry in entries:
            location = f"{path}:{entry['line']}"
            findings = bullet_text_findings(entry["text"], policy)
            if findings:
                raise BulletQualityError(f"{location} {findings[0]}")
            for variant in entry["variants"]:
                findings = bullet_text_findings(variant, policy)
                if findings:
                    raise BulletQualityError(f"{location} variant {findings[0]}")
            if not entry["sources"]:
                raise BulletQualityError(f"{location} has no source comment")
            if len(entry["sources"]) > maximum_sources:
                raise BulletQualityError(
                    f"{location} cites {len(entry['sources'])} sources; maximum is {maximum_sources}"
                )
            if entry["quality_errors"]:
                raise BulletQualityError(f"{location} {entry['quality_errors'][0]}")
            if len(entry["quality_reviews"]) != 1:
                raise BulletQualityError(
                    f"{location} must contain exactly one quality review comment"
                )
            semantic_findings = semantic_review_findings(entry["quality_reviews"][0])
            if semantic_findings:
                raise BulletQualityError(f"{location} {semantic_findings[0]}")
        for parsed in entries:
            refs = parsed["sources"]
            # A bullet citing two records cannot be used under the one-source
            # contract, so it is not offered as a phrasing for either.
            if len(set(refs)) != 1:
                continue
            record_id = refs[0]
            body = parsed["text"]
            if not body or len(body) < 40:
                continue
            review = parsed["quality_reviews"][0]
            entry = {
                "bullet": normalize_punctuation(body),
                "bullet_level": review["level"],
                "result_type": review["result_type"],
            }
            if parsed["variants"]:
                short = parsed["variants"][0]
                if short:
                    entry["bullet_short"] = normalize_punctuation(short)
            bullets[record_id] = entry
    return bullets


# Sub-headings inside a story, and the one heading that marks work the user must
# describe rather than claim.
STORY_SUBHEADINGS = re.compile(
    r"trade-?offs?|result|likely motivation|follow-?up|feature context|"
    r"evidence to re-?read|decision and action|participation",
    re.I,
)
SYSTEM_CONTEXT_HEADING = re.compile(r"system context", re.I)

# A story heading always carries a number, in one of two layouts the artifacts
# use interchangeably:
#   ## Story 1 — Title      (markers appear at the END of the story, under its
#                            own sub-headings)
#   ### Story 1: Title      (markers appear immediately beneath the heading)
#   ### 1. Title
# Requiring the number is what keeps "Supporting fact bank" and "Honesty
# guard-rails" from being mistaken for stories.
STORY_TITLE = re.compile(r"^(#{2,3})\s+(?:Story\s+)?\d+\s*[—:.)\-]\s*(.+?)\s*$")
ANY_HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$")


def collect_interview_stories(root: str) -> dict:
    """Story titles from `artifacts/interview/*.md`.

    A record with an interview story is one that survived a pass asking whether
    it holds up under fifteen minutes of questioning. That is a different
    judgement from the ranking's `best_evidence`, and a useful one for a resume:
    a bullet that gets asked about should have a prepared answer behind it.

    The title is also a better scanning label than the first sentence of a
    statement. "Who is allowed to say an order was paid?" says more than the
    opening clause of the record it came from.

    Same boundary as the bullet banks: a suggestion and a signal, never
    evidence. Records under a "System context" heading are deliberately skipped,
    because that heading marks work the user may describe but not claim.
    """
    stories: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(root, "artifacts", "interview", "*.md"))):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()

        # Walk heading blocks in order, carrying the current story forward. A
        # sub-heading inside a story does not reset it, which is what lets the
        # layout with trailing markers attribute them correctly; any other
        # top-level heading does, so a fact bank cannot inherit a story label.
        current = None
        for block in re.split(r"\n(?=#{2,3}\s)", text):
            heading = block.split("\n", 1)[0]
            match = STORY_TITLE.match(heading)
            if match:
                title = normalize_punctuation(match.group(2)).strip(" :.-")
                current = title if len(title) >= 8 else None
            else:
                other = ANY_HEADING.match(heading)
                if other and not STORY_SUBHEADINGS.search(other.group(2)):
                    # A new top-level section, or a heading that names work the
                    # user may describe but not claim.
                    if len(other.group(1)) == 2 or SYSTEM_CONTEXT_HEADING.search(other.group(2)):
                        current = None
            if not current:
                continue
            # A story may cover several records; each one gets the same label.
            for record_id in set(SRC_MARKER.findall(block)):
                stories.setdefault(record_id, current)
    return stories


def collect_before_after_records(profile_text: str) -> set:
    """Record IDs the professional profile ties to an out-of-repository
    before/after artifact. These are the rarest evidence in the knowledge base
    and must never be silently skipped."""
    found = set()
    for block in re.split(r"\n(?=\s{0,6}[a-z_]+:)", profile_text):
        if "demonstration_evidence" not in block and "derived_measurement" not in block:
            continue
        found.update(re.findall(r"\b([a-z0-9_\-]+-\d{3})\b", block))
    return found


def collect_profile_sources(profile: dict) -> list:
    """Citable entries from profile.yaml: responsibilities and skill groups.

    These are NOT curated project records and they are deliberately kept in a
    separate section rather than mixed into `records`. A project record can
    DEMONSTRATE a capability; a profile entry can only STATE it, which is the
    distinction the coverage grade turns on, and `strength` scoring is
    meaningless for them.

    They belong in the index anyway because leaving them out was actively
    misleading. Two applications in a row showed "no eligible evidence" against
    requirements that profile-responsibility-004 answers perfectly well, which
    reads as a portfolio gap when it is really an indexing gap.
    """
    sources = []
    for entry in profile.get("responsibilities") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        sources.append(
            {
                "id": entry["id"],
                "origin": "responsibility",
                "label": entry.get("label", ""),
                "covers": " ".join(str(entry.get("value", "")).split()),
                # Pre-approved sentences. The source checker requires generated
                # text to reuse only words present in the entry, so these are
                # what a line should be drawn from.
                "phrasings": [" ".join(str(p).split()) for p in (entry.get("phrasings") or [])],
                "cap": " ".join(str(entry.get("cap", "")).split()) or None,
            }
        )
    for entry in profile.get("skills") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        items = []
        for item in entry.get("items") or []:
            if isinstance(item, dict) and item.get("name"):
                label = str(item["name"])
                if item.get("depth"):
                    label += f" ({item['depth']})"
                items.append(label)
        sources.append(
            {
                "id": entry["id"],
                "origin": "skill-group",
                "label": entry.get("group", ""),
                "covers": ", ".join(items),
                "cap": " ".join(str(entry.get("cap", "")).split()) or None,
            }
        )
    return sources


def collect_evidence_bridges(profile: dict) -> list:
    """Return explicit profile-to-record retrieval bridges.

    A bridge does not change project provenance or make the profile derived
    evidence. It only tells retrieval that a confirmed profile fact supplies a
    target-facing attribute for named curated records whose repository
    statements demonstrate the delivered output. Public wording must still
    co-cite the profile fact where that attribute is claimed.
    """
    bridges = []
    for entry in profile.get("responsibilities") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        for bridge in entry.get("evidence_bridges") or []:
            if not isinstance(bridge, dict):
                continue
            aliases = [
                str(value) for value in bridge.get("aliases") or [] if str(value).strip()
            ]
            records = [
                str(value) for value in bridge.get("records") or [] if str(value).strip()
            ]
            required_public_phrases = [
                str(value)
                for value in bridge.get("required_public_phrases") or []
                if str(value).strip()
            ]
            if not aliases or not records:
                continue
            bridges.append(
                {
                    "profile_ref": str(entry["id"]),
                    "aliases": aliases,
                    "records": records,
                    "required_public_phrases": required_public_phrases,
                    "cap": " ".join(str(bridge.get("cap", "")).split()) or None,
                }
            )
    return bridges


def collect_store_projects(profile: dict) -> set:
    shipped = set()
    for entry in profile.get("project_links") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("link_status") != "confirmed":
            continue
        if entry.get("play_store") or entry.get("app_store"):
            shipped.add(str(entry.get("project")))
    return shipped


def collect_ranking(ranking: dict) -> tuple:
    ranks, tiers, best = {}, {}, set()
    for entry in ranking.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("project"))
        ranks[key] = entry.get("rank")
        tiers[key] = entry.get("tier")
        for ref in entry.get("best_evidence") or []:
            best.add(str(ref))
    return ranks, tiers, best


TIER_POINTS = {"flagship": 2.0, "strong": 1.0, "supporting": 0.5, "situational": 0.0}
INVOLVEMENT_POINTS = {"led": 3.0, "implemented": 2.0, "contributed": 1.0}


def score_record(
    *, involvement, tier, is_best, material_number, shipped, before_after, tags
):
    """Deterministic strength score. Coarse on purpose: it orders candidates for
    a human or agent to choose between, and is never a claim about the work."""
    signals = []
    score = INVOLVEMENT_POINTS.get(involvement, 0.0)
    if involvement == "led":
        signals.append("led")
    if is_best:
        score += 3.0
        signals.append("best-evidence")
    if before_after:
        score += 3.0
        signals.append("before-after")
    elif material_number:
        score += 1.0
        signals.append("measured")
    score += TIER_POINTS.get(str(tier), 0.0)
    if str(tier) == "flagship":
        signals.append("flagship")
    if shipped:
        score += 1.0
        signals.append("shipped")
    if "testing" in tags:
        signals.append("tested")
    return round(score, 1), signals


def build(root: str) -> dict:
    profile_path = os.path.join(root, "profile", "profile.yaml")
    ranking_path = os.path.join(root, "profile", "project-ranking.yaml")
    prof_profile_path = os.path.join(root, "profile", "professional-profile.yaml")

    profile = load_yaml(profile_path) if os.path.isfile(profile_path) else {}
    ranking = load_yaml(ranking_path) if os.path.isfile(ranking_path) else {}
    prof_text = ""
    if os.path.isfile(prof_profile_path):
        with open(prof_profile_path, encoding="utf-8") as handle:
            prof_text = handle.read()

    ranks, tiers, best_evidence = collect_ranking(ranking)
    shipped_projects = collect_store_projects(profile)
    before_after = collect_before_after_records(prof_text)
    profile_sources = collect_profile_sources(profile)
    evidence_bridges = collect_evidence_bridges(profile)
    curated_bullets = collect_curated_bullets(root)
    interview_stories = collect_interview_stories(root)

    rows = []
    project_files = sorted(
        path
        for path in glob.glob(os.path.join(root, "projects", "*.yaml"))
        if not path.endswith(".candidates.yaml")
    )

    for path in project_files:
        data = load_yaml(path)
        project = str(data.get("project") or os.path.basename(path)[:-5])
        for record in data.get("records") or []:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            record_id = str(record["id"])
            involvement = normalize_involvement(record)
            kind = str(record.get("kind") or "")
            resume_eligible = record.get("resume_eligible", True) is not False
            tags = canonical_tags(record.get("tags"))
            statement = str(record.get("statement") or "")
            raw_limitations = record.get("limitations") or []
            if isinstance(raw_limitations, str):
                cautions = [raw_limitations.strip()] if raw_limitations.strip() else []
            else:
                cautions = [
                    str(value).strip()
                    for value in raw_limitations
                    if str(value).strip()
                ]
            material_number = has_material_number(statement)
            score, signals = score_record(
                involvement=involvement,
                tier=tiers.get(project),
                is_best=record_id in best_evidence,
                material_number=material_number,
                shipped=project in shipped_projects,
                before_after=record_id in before_after,
                tags=tags,
            )
            phrasing = dict(curated_bullets.get(record_id, {}))
            if phrasing:
                signals = signals + ["curated-bullet"]
            story = interview_stories.get(record_id)
            if story:
                # Signal only, no score change. Defensibility is decision-relevant
                # but must not outrank measured evidence, and it overlaps heavily
                # with best-evidence already.
                signals = signals + ["interview-story"]
                phrasing["story"] = story
            rows.append(
                {
                    "id": record_id,
                    "project": project,
                    "project_rank": ranks.get(project),
                    "tier": tiers.get(project),
                    "involvement": involvement,
                    "kind": kind,
                    "resume_eligible": resume_eligible,
                    "eligible": (
                        resume_eligible
                        and kind in ELIGIBLE_KINDS
                        and involvement in ELIGIBLE_INVOLVEMENT
                    ),
                    "strength": score,
                    "signals": signals,
                    "tags": tags,
                    "claim": first_sentence(statement),
                    # Selection must see the same boundaries that bind the
                    # eventual public wording. Keeping them beside the derived
                    # claim prevents a strong keyword match from hiding a
                    # migration-away note, participation cap, or other reason
                    # the record needs different framing.
                    "cautions": cautions,
                    **phrasing,
                }
            )

    rows.sort(key=lambda row: (-row["strength"], row["project_rank"] or 999, row["id"]))

    capabilities = {}
    for row in rows:
        if not row["eligible"]:
            continue
        for tag in row["tags"]:
            capabilities.setdefault(tag, []).append(row["id"])
    capabilities = {
        tag: ids for tag, ids in sorted(capabilities.items()) if len(ids) > 0
    }

    eligible_rows = [row for row in rows if row["eligible"]]
    return {
        "schema_version": 1,
        "kind": "evidence-index",
        "generated_at": dt.date.today().isoformat(),
        "generator": "ekb index",
        "basis": {
            "projects": len(project_files),
            "records": len(rows),
            "eligible_records": len(eligible_rows),
            "records_with_curated_bullets": sum(1 for row in rows if row.get("bullet")),
            "records_with_interview_stories": sum(1 for row in rows if row.get("story")),
            "capabilities": len(capabilities),
            "profile_sources": len(profile_sources),
            "sources": [
                "projects/*.yaml (curated records, involvement, kind, tags)",
                "profile/project-ranking.yaml (rank, tier, best_evidence)",
                "profile/profile.yaml (confirmed store links, responsibilities, skill groups)",
                "profile/professional-profile.yaml (before/after demonstration evidence)",
                "artifacts/bullets/*.md (resume-ready phrasings; suggestions, never evidence)",
                "artifacts/interview/*.md (story titles; a defensibility signal, never evidence)",
            ],
        },
        "scoring": {
            "note": (
                "Coarse and deterministic. Orders candidates so the strongest "
                "eligible evidence for a requirement is visible before selection. "
                "A score licenses nothing and never appears in a document."
            ),
            "involvement": INVOLVEMENT_POINTS,
            "tier": TIER_POINTS,
            "best_evidence": 3.0,
            "before_after": 3.0,
            "material_number": 1.0,
            "shipped": 1.0,
        },
        "capabilities": capabilities,
        "evidence_bridges": evidence_bridges,
        # Kept separate from `records` on purpose: a profile entry can state a
        # capability but never demonstrate one, and `strength` does not apply.
        "profile_sources": profile_sources,
        "records": rows,
    }


HEADER = """# GENERATED FILE. Do not hand-edit.
#
# Rebuild with: ekb index
# Verify freshness with: ekb index --check
#
# WHAT THIS IS
#   A retrieval table over the curated knowledge base, so requirement-to-evidence
#   matching can be MECHANICAL instead of a 15,000-line read. Each row points at
#   one curated record and carries only signals derived from it.
#
# WHAT THIS IS NOT
#   Not a source of facts and not a claim. `strength` orders candidates for
#   selection; it is private, never printed, and never wording. Every visible
#   line in a generated document still cites the curated record itself.
#   `cautions` repeats the curated record's limitations so selection cannot
#   assess a convenient claim while missing the boundaries that govern it.
"""


def dump(index: dict) -> str:
    body = dump_yaml(index)
    return HEADER + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 if the index is stale")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    try:
        index = build(args.root)
    except (BulletQualityError, TypeError, ValueError) as exc:
        print(f"cannot build evidence index: {exc}", file=sys.stderr)
        return 1
    rendered = dump(index)
    out_dir = os.path.join(args.root, "index")
    out_path = os.path.join(out_dir, "evidence-index.yaml")

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    if args.check:
        if not os.path.isfile(out_path):
            print(f"evidence index missing: {out_path}", file=sys.stderr)
            return 1
        with open(out_path, encoding="utf-8") as handle:
            current = handle.read()
        # Ignore the generation date so a same-content rebuild is not "stale".
        strip = lambda text: re.sub(r"^generated_at:.*$", "", text, flags=re.M)
        if strip(current) != strip(rendered):
            print(
                "evidence index is stale; run ekb index",
                file=sys.stderr,
            )
            return 1
        print("evidence index is current")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    basis = index["basis"]
    print(
        f"wrote {os.path.relpath(out_path, args.root)}: "
        f"{basis['records']} records ({basis['eligible_records']} eligible) "
        f"across {basis['projects']} projects, {basis['capabilities']} capabilities"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
