"""Read candidate declarations and classify private requirement matches."""

from datetime import date
import json
from pathlib import Path
import re
import unicodedata

POLICY = json.loads((Path(__file__).resolve().parents[1] / "config/capabilities.json").read_text())
CLASSIFICATION = {
    "professional-experience": "broader professional capability",
    "practical-experience": "practical non-professional experience",
    "working-knowledge": "confirmed technical knowledge",
    "familiarity": "confirmed technical knowledge",
    "transferable": "transferable experience",
    "learning-target": "genuine gap",
}


def valid_date(value):
    try:
        parsed = date.fromisoformat(str(value))
        return parsed.isoformat() == str(value) and parsed <= date.today()
    except ValueError:
        return False


def read_capabilities(profile):
    """Read the optional, user-maintained capabilities in profile.yaml."""
    rows = profile.get("capabilities", [])
    if not isinstance(rows, list):
        raise ValueError("profile.capabilities must be a list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("profile.capabilities entries must be mappings")
        ref = row.get("id")
        if not isinstance(ref, str) or not re.fullmatch(r"profile-capability-[a-z0-9]+(?:-[a-z0-9]+)*", ref) or ref in seen:
            raise ValueError(f"invalid or duplicate capability ID: {ref!r}")
        seen.add(ref)
        level = row.get("proficiency")
        basis = row.get("basis")
        if (
            not isinstance(level, str)
            or row.get("category") not in POLICY["categories"]
            or row.get("context") not in POLICY["contexts"].get(level, [])
            or not isinstance(basis, dict)
            or basis.get("type") not in POLICY["basis_types"].get(level, [])
            or not isinstance(basis.get("detail"), str)
            or not basis["detail"].strip()
            or not isinstance(row.get("name"), str)
            or not row["name"].strip()
            or row.get("confidence") not in POLICY["confidence"]
            or row.get("interview_readiness") not in POLICY["interview_readiness"]
            or row.get("kind") not in ("inferred", "user-stated")
            or ("gap_confirmed" in row and (
                row["gap_confirmed"] is not True or level != "learning-target"
                or row.get("kind") != "user-stated" or row.get("confirmation_required") is not False
            ))
            or type(row.get("confirmation_required")) is not bool
            or (not row["confirmation_required"] and row["kind"] != "user-stated")
            or (row["kind"] == "user-stated" and not valid_date(row.get("last_confirmed")))
            or any(
                not isinstance(row.get(field, []), list)
                or any(not isinstance(item, str) or not item.strip() for item in row.get(field, []))
                for field in ("aliases", "examples", "limitations")
            )
        ):
            raise ValueError(f"{ref}: invalid capability declaration")
    # Names and aliases identify a capability regardless of display spelling.
    # Keep earlier declarations in the profile as provenance. An explicit,
    # later confirmation can replace them. Dates alone never resolve a conflict.
    identities = {
        row["id"]: {capability_identity(name) for name in [row["name"], *row.get("aliases", [])]}
        for row in rows
    }
    by_id = {row["id"]: row for row in rows}
    superseded = set()
    for row in rows:
        replaced = row.get("supersedes", [])
        if not isinstance(replaced, list) or any(not isinstance(ref, str) for ref in replaced):
            raise ValueError(f"{row['id']}: supersedes must list prior declaration IDs")
        if replaced and (row["kind"] != "user-stated" or row["confirmation_required"]):
            raise ValueError(f"{row['id']}: only a confirmed declaration can supersede another")
        for ref in replaced:
            prior = by_id.get(ref)
            if (prior is None or ref in superseded or not identities[row["id"]] & identities[ref]
                    or prior["kind"] != "user-stated"
                    or str(prior["last_confirmed"]) >= str(row["last_confirmed"])):
                raise ValueError(f"{row['id']}: invalid supersession of {ref}")
            superseded.add(ref)
    active = [row for row in rows if row["id"] not in superseded]
    # Carry earlier aliases forward across an explicit correction.
    for row in sorted(rows, key=lambda entry: str(entry.get("last_confirmed"))):
        for ref in row.get("supersedes", []):
            identities[row["id"]].update(identities[ref])
    names = {}
    for row in active:
        for identity in sorted(identities[row["id"]]):
            if identity in names:
                raise ValueError(
                    f"conflicting capability identity {identity!r}: {names[identity]} and "
                    f"{row['id']}. Reconcile the scopes or record a confirmed supersession."
                )
            names[identity] = row["id"]
    return [
        row | {"aliases": sorted(set(row.get("aliases", [])) | (identities[row["id"]] - {
            capability_identity(name) for name in [row["name"], *row.get("aliases", [])]
        }))}
        if row.get("supersedes") else row
        for row in active
    ]


def capability_identity(name):
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


# Professional use is its own threshold. Practical non-professional use
# supports working knowledge, but cannot meet a professional-use requirement.
MEETS_MINIMUM = POLICY["meets_minimum"]


def capability_matches(capabilities, terms, related, policy, term_present, minimum=None):
    matches = []
    for row in capabilities:
        names = [row["name"], *row.get("aliases", [])]
        direct = any(term_present(name, term) for name in names for term in terms)
        if not direct and not any(term_present(name, term) for name in names for term in related):
            continue
        level = row["proficiency"]
        if level == "learning-target" and not direct:
            continue
        confirmed = row["kind"] == "user-stated" and not row["confirmation_required"]
        classification = (
            "needs confirmation" if not confirmed
            else ("needs confirmation" if level == "learning-target" and not row.get("gap_confirmed")
                  else CLASSIFICATION[level]) if direct
            else "transferable experience"
        )
        meets_level = level in MEETS_MINIMUM[minimum] if minimum else level != "familiarity"
        partial = not direct or not meets_level
        heading = POLICY["skill_headings"].get(level)
        public = confirmed and heading and "user-stated" in policy["eligible_kinds"]
        matches.append({
            "ref": row["id"],
            "label": row["name"],
            "classification": classification,
            "proficiency": level,
            "context": row["context"],
            "basis": row["basis"],
            "kind": row["kind"],
            "confidence": row["confidence"],
            "limitations": row.get("limitations", []),
            "examples": row.get("examples", []),
            "last_confirmed": row.get("last_confirmed"),
            "interview_readiness": row["interview_readiness"],
            "needs_confirmation": not confirmed or (level == "learning-target" and not row.get("gap_confirmed")),
            "fit": (
                "unconfirmed" if not confirmed or (level == "learning-target" and not row.get("gap_confirmed"))
                else "gap" if level == "learning-target"
                else "partial" if partial else "candidate match"
            ),
            "resume_use": (
                {"heading": heading, "text": row["name"], "partial": partial}
                if public else None
            ),
        })
    return matches


if __name__ == "__main__":
    import argparse
    import sys
    import yaml

    from ekb_index import collect_profile_sources
    from ekb_paths import workspace_root

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-view", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(workspace_root()))
    args = parser.parse_args()
    try:
        if args.workspace_view:
            profile_path = args.root / "profile/profile.yaml"
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            view = {
                "workspace": str(args.root.resolve()), "source": "profile/profile.yaml",
                "current_declarations": read_capabilities(profile),
                "legacy_skill_and_responsibility_leads": collect_profile_sources(profile),
                "confirmed_context": {key: profile.get(key, []) for key in (
                    "experience", "education", "certifications", "languages"
                )},
                "notes": [
                    "Legacy depth describes inventory support. Use a confirmed declaration for a proficiency label.",
                    "Read curated records for project scope and private context or interview guides for prior answers.",
                ],
            }
        else:
            profile = yaml.safe_load(sys.stdin.read()) or {}
            view = read_capabilities(profile)
        print(json.dumps(view, ensure_ascii=False, indent=2, default=str))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.exit(str(exc))
