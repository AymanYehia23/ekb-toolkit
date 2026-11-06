"""Bind an explicit screening decision to the frozen opportunity intake."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

from ekb_paths import workspace_root


class ScreeningError(ValueError):
    pass


APPLICATION_ID_PATTERN = r"\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*"


INTAKE_FIELDS = (
    "id", "created_at", "company", "role", "company_website",
    "posting_url", "job_description", "additional_notes",
)


def read_record(path: Path) -> dict:
    try:
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScreeningError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(record, dict):
        raise ScreeningError(f"{path.name} must contain a mapping")
    return record


def frozen_application(root: Path, application_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", application_id):
        raise ScreeningError("invalid application ID")
    path = root / "applications" / f"{application_id}.yaml"
    if not path.is_file():
        raise ScreeningError("no frozen application; screen the opportunity first")
    application = read_record(path)
    if application.get("schema_version") == 2 and not re.fullmatch(APPLICATION_ID_PATTERN, application_id):
        raise ScreeningError("version 2 application ID must be date-prefixed")
    if application.get("id") != application_id:
        raise ScreeningError(f"{path.name} does not match its application ID")
    return application


def posting_digest(application: dict) -> str:
    fields = {key: application.get(key) for key in INTAKE_FIELDS}
    if application.get("schema_version") == 2:
        fields["schema_version"] = 2
    serialized = json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def require_screening(root: Path, application_id: str, model_target: dict | None = None) -> dict:
    application = frozen_application(root, application_id)
    screening = root / "applications" / f"{application_id}.screening.yaml"
    if application.get("schema_version", 1) not in (1, 2):
        raise ScreeningError("unsupported application intake version")
    targeting = application.get("targeting") or {}
    if not isinstance(targeting, dict):
        raise ScreeningError("frozen application targeting must be a mapping")
    master = targeting.get("resume_mode") == "master"
    if master and (application.get("posting_url") or application.get("job_description") or screening.exists()):
        raise ScreeningError("a screened opportunity or job posting cannot be generated as a master résumé")
    if model_target is not None:
        expected_mode = "master" if master else "job-targeted"
        if model_target.get("mode") != expected_mode:
            raise ScreeningError("model mode does not match the frozen application")
        if not master and any(model_target.get(key) != application.get(key) for key in ("company", "role")):
            raise ScreeningError("model company or role does not match the frozen opportunity")
    if master:
        return application
    if application.get("schema_version") == 2 and model_target is not None:
        for key in ("market", "market_basis", "job_country", "job_country_code", "location_scope", "location_basis", "summary_lead"):
            if key in targeting and targeting[key] != model_target.get(key):
                raise ScreeningError(f"model {key} does not match the frozen targeting decision")

    if not screening.is_file():
        raise ScreeningError("opportunity has not been screened")
    review = read_record(screening)
    if review.get("id") != application_id or review.get("kind") != "screening":
        raise ScreeningError("screening record does not match the frozen application")
    decision = review.get("decision")
    if not isinstance(decision, dict):
        raise ScreeningError("screening has no explicit decision")
    status = decision.get("status")
    if status != "proceed":
        reason = {
            "pending": "screening is pending explicit authorization",
            "declined": "opportunity was declined",
            "deferred": "opportunity is blocked pending clarification",
        }.get(status, "screening has no explicit proceed decision")
        raise ScreeningError(reason)
    if not decision.get("decided_at") or decision.get("posting_sha256") != posting_digest(application):
        raise ScreeningError("proceed decision is unbound or stale for the frozen posting; record a current authorized decision")
    return application


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application")
    parser.add_argument("--root", type=Path, default=Path(workspace_root()))
    args = parser.parse_args()
    try:
        print(posting_digest(frozen_application(args.root, args.application)))
    except ScreeningError as exc:
        parser.exit(1, f"EKB screening: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
