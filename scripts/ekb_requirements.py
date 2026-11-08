"""Load one reviewed decision set for a screened application."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from ekb_capabilities import MEETS_MINIMUM, read_capabilities
from ekb_paths import config_path, workspace_root
from ekb_screening import ScreeningError, posting_digest, read_record, require_screening


FULL_FITS = {
    "directly-demonstrated", "broader-professional", "practical",
    "working-knowledge", "familiarity", "formal-eligibility-met",
}
FIT_VALUES = FULL_FITS | {
    "transferable", "partial", "needs-confirmation", "skill-gap", "formal-eligibility-gap",
}
FORMAL_FITS = {"formal-eligibility-met", "formal-eligibility-gap", "needs-confirmation"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def decision_basis(root, application):
    files = [root / name for name in (
        "profile/profile.yaml", "profile/project-ranking.yaml", "profile/screening-criteria.yaml",
        "config/toolkit.yaml", f"applications/{application['id']}.screening.yaml",
    )]
    files += sorted(path for path in (root / "projects").glob("*.yaml") if not path.name.endswith(".candidates.yaml"))
    policy = Path(__file__).resolve().parents[1] / "config"
    return digest({
        "posting": posting_digest(application),
        "targeting": application.get("targeting"),
        "workspace_inputs": {str(path.relative_to(root)): file_digest(path) for path in files},
        "contracts": {name: file_digest(policy / name) for name in
                      ("capabilities.json", "retrieval.json", "toolkit.yaml")},
        "presentation_policy": file_digest(Path(config_path("resume-policy.json", str(root)))),
        "decision_contract": file_digest(Path(__file__)),
    })


def text(value):
    return isinstance(value, str) and bool(value.strip())


def ids(values):
    return (isinstance(values, list) and all(text(value) for value in values)
            and len(values) == len(set(values)))


def excerpt_text(value):
    return " ".join(str(value or "").split())


def frozen_requirements(application):
    targeting = application.get("targeting") or {}
    rows = targeting.get("requirements")
    posting = excerpt_text(application.get("job_description"))
    if not isinstance(rows, list) or not rows:
        raise ScreeningError("record the complete frozen requirement inventory before planning")
    seen = set()
    output = []
    for row in rows:
        if not isinstance(row, dict):
            raise ScreeningError("frozen requirement must be a mapping")
        term, excerpt = row.get("term"), excerpt_text(row.get("posting_excerpt"))
        minimum = row.get("minimum_proficiency")
        assessment = row.get("assessment")
        if (not text(term) or term.casefold().strip() in seen or not excerpt or excerpt not in posting
                or row.get("priority") not in ("required", "preferred") or type(row.get("critical")) is not bool
                or not ids(row.get("aliases", []))
                or row.get("category") not in ("technical", "engineering", "professional", "domain", "qualification")
                or (minimum is not None and (not isinstance(minimum, str) or minimum not in MEETS_MINIMUM))
                or (assessment is not None and not isinstance(assessment, dict))):
            raise ScreeningError(f"invalid requirement or excerpt outside the frozen posting: {term!r}")
        seen.add(term.casefold().strip())
        output.append({"id": "req-" + digest([term.casefold().strip(), excerpt])[:16], **{
            key: row[key] for key in ("term", "priority", "critical", "category")
        }, "posting_excerpt": excerpt, "aliases": row.get("aliases", []),
            "minimum_proficiency": minimum, "assessment": assessment,
            "why_it_matters": row.get("why_it_matters")})
    return output


def skeleton(root, application):
    basis = decision_basis(root, application)
    rows = frozen_requirements(application)
    profile = read_record(root / "profile/profile.yaml")
    read_capabilities(profile)
    if decision_basis(root, application) != basis:
        raise ScreeningError("application inputs changed while preparing the decision map")
    return {
        "schema_version": 1, "application": application["id"], "basis_sha256": basis,
        "reviewed_by": "", "inventory_review": "", "positioning": "",
        "claim_plan": {}, "project_review": {},
        "requirements": [{"id": row["id"], "term": row["term"], "fit": "",
                          "disposition": "", "refs": [], "claim_paths": [], "reason": ""} for row in rows],
    }


def load_decisions(root, application):
    if application.get("schema_version") != 2:
        return None
    path = root / "applications" / f"{application['id']}.requirements.yaml"
    if not path.is_file():
        raise ScreeningError("reviewed requirement map missing; run ekb requirement-map ID --skeleton")
    reviewed = read_record(path)
    if (reviewed.get("schema_version") != 1 or reviewed.get("application") != application["id"]
            or reviewed.get("basis_sha256") != decision_basis(root, application)):
        raise ScreeningError("reviewed requirement map is stale; reassess the current posting and candidate sources")
    if not all(text(reviewed.get(key)) for key in ("reviewed_by", "inventory_review", "positioning")):
        raise ScreeningError("review the full posting inventory and record the application positioning")
    plan = reviewed.get("claim_plan")
    if not isinstance(plan, dict) or not plan or any(
        not re.fullmatch(r"resume\.(?:summary|experience|projects|skills)\[.+\]", path)
        or not isinstance(claim, dict) or set(claim) != {"refs", "scope"}
        or not ids(claim["refs"]) or not claim["refs"] or not text(claim["scope"])
        for path, claim in plan.items()
    ):
        raise ScreeningError("record an ordered source plan for the summary, accomplishments and skills")
    authored = reviewed.get("requirements")
    inventory = frozen_requirements(application)
    if (not isinstance(authored, list) or not all(isinstance(row, dict) for row in authored)
            or [row.get("id") for row in authored] != [row["id"] for row in inventory]):
        raise ScreeningError("reviewed map must include every frozen requirement exactly once, in order")

    requirements = []
    for frozen, row in zip(inventory, authored):
        fit, disposition = row.get("fit"), row.get("disposition")
        refs, reason, claim_paths = row.get("refs"), row.get("reason"), row.get("claim_paths")
        formal = frozen["category"] == "qualification"
        if (not text(fit) or fit not in FIT_VALUES
                or (fit in FORMAL_FITS - {"needs-confirmation"} and not formal)
                or (formal and fit not in FORMAL_FITS)
                or not text(reason) or not ids(refs) or not ids(claim_paths)):
            raise ScreeningError(f"{frozen['term']}: review the fit, sources and decision rationale")
        expected = {"needs-confirmation": "unresolved", "skill-gap": "gap", "formal-eligibility-gap": "gap"}
        allowed = {expected[fit]} if fit in expected else {"included", "omitted"}
        if disposition not in allowed or (fit != "needs-confirmation" and not refs):
            raise ScreeningError(f"{frozen['term']}: invalid disposition or missing supporting references")
        if formal and fit != "needs-confirmation":
            finding = formal_finding(root, application, frozen, row)
        else:
            finding = None
        if (bool(claim_paths) != (disposition == "included" and not formal)
                or any(path not in plan or not set(refs).intersection(plan[path]["refs"]) for path in claim_paths)):
            raise ScreeningError(f"{frozen['term']}: included requirement must name its planned claims and sources")
        discovery = row.get("discovery")
        if "discovery" in row and (
            not isinstance(discovery, dict) or set(discovery) not in ({"reason"}, {"question", "reason"})
            or not all(text(value) for value in discovery.values())
            or ("question" in discovery and fit in {"skill-gap", "formal-eligibility-gap"})
        ):
            raise ScreeningError(f"{frozen['term']}: record a focused discovery question and reason, or a reason to skip")
        requirements.append(frozen | {"fit": fit, "disposition": disposition,
                                      "refs": refs, "claim_paths": claim_paths,
                                      "reason": reason, "screening_finding": finding}
                            | ({"discovery": discovery} if discovery else {}))

    project_review = reviewed.get("project_review", {})
    requirement_ids = {row["id"] for row in requirements}
    if not isinstance(project_review, dict) or any(
        not text(project) or not isinstance(row, dict)
        or set(row) != {"disposition", "reason", "refs", "requirement_ids"}
        or row["disposition"] not in ("selected", "reserve", "omitted")
        or not text(row["reason"]) or not ids(row["refs"]) or not row["refs"]
        or not ids(row["requirement_ids"]) or not row["requirement_ids"]
        or set(row["requirement_ids"]) - requirement_ids
        for project, row in project_review.items()
    ):
        raise ScreeningError("project review must record each compared project's disposition, rationale, sources and requirement IDs")
    payload = {key: reviewed[key] for key in (
        "schema_version", "application", "basis_sha256", "reviewed_by", "inventory_review", "positioning",
    )} | {"claim_plan": plan, "requirements": requirements}
    if project_review:
        payload["project_review"] = project_review
    # The order of substantive claims is material.
    payload["revision_sha256"] = digest([payload, list(plan)])
    return payload


def formal_finding(root, application, frozen, row):
    screen = read_record(root / "applications" / f"{application['id']}.screening.yaml")
    finding = next((entry for entry in screen.get("findings") or []
                    if entry.get("id") == row.get("screening_finding")), None)
    if (not finding or not text(finding.get("basis"))
            or excerpt_text(finding["basis"]).strip('"') != frozen["posting_excerpt"].strip('"')
            or finding.get("qualification_fit") != row["fit"]
            or sorted(finding.get("profile_basis") or []) != sorted(row["refs"])):
        raise ScreeningError(f"{frozen['term']}: formal decision requires a matching screening finding and profile basis")
    return finding["id"]


def alignment_projection(decisions):
    rows = []
    for row in decisions["requirements"]:
        included = row["disposition"] == "included" and row["fit"] in FULL_FITS and row["category"] != "qualification"
        rows.append({key: row[key] for key in ("term", "priority", "critical")} | {
            "aliases": row["aliases"] or [row["term"]],
            "status": "matched" if included else "not_emphasized",
            "requirement_id": row["id"],
            "evidence_refs": row["refs"] if included else [],
            "emphasize": included, "selection_reason": row["reason"],
        })
    return {"requirement_map_sha256": decisions["revision_sha256"], "requirements": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application")
    parser.add_argument("--root", type=Path, default=Path(workspace_root()))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--skeleton", action="store_true", help="print an unsigned decision-map skeleton")
    group.add_argument("--alignment", action="store_true", help="print the derived model alignment")
    args = parser.parse_args()
    try:
        application = require_screening(args.root, args.application)
        if application.get("schema_version") != 2 or (application.get("targeting") or {}).get("resume_mode") == "master":
            raise ScreeningError("requirement maps apply to version 2 job-targeted intakes")
        if args.skeleton:
            import yaml
            print(yaml.safe_dump(skeleton(args.root, application), sort_keys=False), end="")
        else:
            reviewed = load_decisions(args.root, application)
            print(json.dumps(alignment_projection(reviewed) if args.alignment else reviewed, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"EKB requirement map: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
