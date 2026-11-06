#!/usr/bin/env python3
"""Audit every rendered resume bullet against the ranked project banks.

Historical snapshots stay intact. This command reports factual relationships
to the banks and leaves wording quality and retirement to editorial review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bullet_quality import parse_bullet_bank  # noqa: E402
from ekb_paths import workspace_root  # noqa: E402


BULLET_PATH = re.compile(
    r"^(?:experience\[\d+\]\.bullets\[\d+\]|"
    r"experience\[\d+\]\.engagements\[\d+\]\.bullets\[\d+\]|"
    r"projects\[\d+\]\.details\[\d+\])$"
)
CLASSIFICATIONS = (
    "exact_match", "approved_variant", "alternative_wording", "overlapping_sources", "absent_from_bank"
)


def source_refs(value: dict[str, Any]) -> list[str]:
    if isinstance(value.get("source_ref"), str):
        return [value["source_ref"]]
    return [str(item) for item in value.get("source_refs") or []]


def rendered_bullets(model: Any, path: str = "") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(model, dict):
        if BULLET_PATH.fullmatch(path) and isinstance(model.get("text"), str):
            found.append({"path": path, "text": model["text"], "sources": source_refs(model)})
        for key, value in model.items():
            child = f"{path}.{key}" if path else key
            found.extend(rendered_bullets(value, child))
    elif isinstance(model, list):
        for index, value in enumerate(model):
            found.extend(rendered_bullets(value, f"{path}[{index}]"))
    return found


def load_banks(workspace: Path) -> list[dict[str, Any]]:
    banks: list[dict[str, Any]] = []
    for filename in sorted(glob.glob(str(workspace / "artifacts" / "bullets" / "*.md"))):
        path = Path(filename)
        for rank, entry in enumerate(parse_bullet_bank(path.read_text(encoding="utf-8")), start=1):
            review = entry["quality_reviews"][0] if len(entry["quality_reviews"]) == 1 else {}
            banks.append(
                {
                    "bank": path.name,
                    "rank": rank,
                    "text": entry["text"],
                    "sources": entry["sources"],
                    "variants": entry["variants"],
                    "level": review.get("level"),
                    "result_type": review.get("result_type"),
                }
            )
    return banks


def replacement_for(item: dict[str, Any], banks: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    refs = set(item["sources"])
    if not refs:
        return "absent_from_bank", None
    exact_sources = [entry for entry in banks if set(entry["sources"]) == refs]
    for entry in exact_sources:
        if entry["text"] == item["text"]:
            return "exact_match", entry
    for entry in exact_sources:
        if item["text"] in entry.get("variants", []):
            return "approved_variant", entry
    if exact_sources:
        return "alternative_wording", exact_sources[0]

    overlaps = [entry for entry in banks if refs.intersection(entry["sources"])]
    if overlaps:
        best = min(overlaps, key=lambda entry: (-len(refs.intersection(entry["sources"])), entry["rank"]))
        return "overlapping_sources", best
    return "absent_from_bank", None


def build_audit(workspace: Path) -> dict[str, Any]:
    banks = load_banks(workspace)
    instances: list[dict[str, Any]] = []
    for filename in sorted(glob.glob(str(workspace / "artifacts" / "applications" / "*" / "resume.json"))):
        path = Path(filename)
        model = json.loads(path.read_text(encoding="utf-8"))
        for item in rendered_bullets(model):
            status, replacement = replacement_for(item, banks)
            instances.append(
                {
                    "artifact": str(path.relative_to(workspace)),
                    **item,
                    "classification": status,
                    "bank_match": replacement,
                }
            )

    counts = {name: sum(item["classification"] == name for item in instances) for name in CLASSIFICATIONS}
    variants = {
        (item["text"], tuple(sorted(item["sources"])), item["classification"])
        for item in instances
    }
    distinct_counts = {
        f"distinct_{name}": sum(decision == name for _, _, decision in variants)
        for name in CLASSIFICATIONS
    }
    selected = [
        {
            "bank": entry["bank"],
            "rank": entry["rank"],
            "text": entry["text"],
            "sources": entry["sources"],
            "level": entry["level"],
            "result_type": entry["result_type"],
        }
        for entry in banks
    ]
    return {
        "generated_at": dt.date.today().isoformat(),
        "method": (
            "Historical model bullets were compared with the ranked banks. "
            "These classifications describe text and source relationships. "
            "Editorial quality and retirement require a separate decision."
        ),
        "summary": {
            "reviewed_instances": len(instances),
            "distinct_text_source_variants": len(variants),
            "canonical_selected_bullets": len(selected),
            **counts,
            **distinct_counts,
        },
        "canonical_rankings": selected,
        "instances": instances,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=workspace_root())
    parser.add_argument("--output")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    audit = build_audit(workspace)
    text = json.dumps(audit, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(text, end="")
        return 0
    output = Path(args.output).resolve() if args.output else workspace / "artifacts" / "bullets" / "impact-audit.json"
    output.write_text(text, encoding="utf-8")
    print(
        f"wrote {output}: {audit['summary']['reviewed_instances']} instances, "
        f"{audit['summary']['canonical_selected_bullets']} canonical bullets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
