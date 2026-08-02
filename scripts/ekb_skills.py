#!/usr/bin/env python3
"""EKB skills evidence — recompute the counts behind profile.yaml `skills`.

The skills section is DERIVED output living in a curated file: each item states
a `basis` such as "11 projects, 44 records", and those counts go stale as soon
as curated records change. This script recomputes the evidence and reports drift.
It never writes; fixing a stale entry is a profile-session edit.

Two things it deliberately does NOT do:

  1. It does not grep record prose. Substring searches over projects/*.yaml
     report `firebase` and `ci` in nearly every project because the EXCLUSIONS
     boilerplate names them in every analysis header. Only authored `tags` are
     counted, because a tag is a deliberate act.
  2. It does not invent skills. It reports what the tags support; deciding what
     belongs in the section stays a human call.

Usage:

    ekb skills            # drift check against profile.yaml
    ekb skills --tags     # full tag census, most-used first
    ekb skills --tags 3   # tags present in 3+ projects

Exit 0 = no drift, 1 = at least one basis count no longer matches.
"""

import glob
import os
import re
import sys
from collections import defaultdict

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ekb_paths import workspace_root  # noqa: E402

DEPTH_BANDS = (("core", 10, None), ("working", 4, 9), ("exposure", 1, 3))


def load_records():
    """project name -> list of records, for every curated project."""
    out = {}
    for path in sorted(glob.glob("projects/*.yaml")):
        if path.endswith(".candidates.yaml"):
            continue
        name = os.path.basename(path)[: -len(".yaml")]
        with open(path) as fh:
            out[name] = (yaml.safe_load(fh) or {}).get("records") or []
    return out


def tag_census(records_by_project):
    projects = defaultdict(set)
    counts = defaultdict(int)
    for project, records in records_by_project.items():
        for rec in records:
            for tag in rec.get("tags") or []:
                projects[tag].add(project)
                counts[tag] += 1
    return projects, counts


def depth_for(n_projects):
    for label, lo, hi in DEPTH_BANDS:
        if n_projects >= lo and (hi is None or n_projects <= hi):
            return label
    return None


def main():
    os.chdir(workspace_root())
    if not os.path.isdir("projects"):
        print(f"no projects/ directory in workspace {workspace_root()}", file=sys.stderr)
        return 2

    records_by_project = load_records()
    projects, counts = tag_census(records_by_project)
    total_projects = len(records_by_project)
    total_records = sum(len(r) for r in records_by_project.values())

    if "--tags" in sys.argv:
        try:
            floor = int(sys.argv[sys.argv.index("--tags") + 1])
        except (IndexError, ValueError):
            floor = 1
        rows = sorted(projects.items(), key=lambda kv: (-len(kv[1]), -counts[kv[0]]))
        print(f"{'tag':<34}{'projects':>9}{'records':>9}  depth")
        for tag, projs in rows:
            if len(projs) < floor:
                continue
            print(f"{tag:<34}{len(projs):>9}{counts[tag]:>9}  {depth_for(len(projs))}")
        print(f"\n{len(rows)} distinct tags over {total_projects} projects, "
              f"{total_records} records")
        return 0

    # ---- drift check against the stated basis counts ----------------------
    with open("profile/profile.yaml") as fh:
        profile = yaml.safe_load(fh) or {}
    groups = profile.get("skills") or []
    if not groups:
        print("profile/profile.yaml has no `skills` section")
        return 1

    stale, checked, manual = [], 0, []
    for group in groups:
        for item in group.get("items") or []:
            name = item["name"]
            basis = str(item.get("basis", ""))
            source = item.get("basis_source")
            m = re.search(r"(\d+)\s*(?:of\s*\d+\s*)?projects?", basis)
            if not m or source == "strength":
                manual.append((name, source or "unspecified"))
                continue
            claimed = int(m.group(1))

            if source == "tags":
                tag = item.get("tag")
                if not tag or tag not in projects:
                    manual.append((name, "tag missing or unknown"))
                    continue
                actual = len(projects[tag])
            elif source == "record-text":
                # Not machine-resolvable to one term; verify by hand.
                manual.append((name, "record-text"))
                continue
            else:
                manual.append((name, "unspecified basis_source"))
                continue

            checked += 1
            if actual != claimed:
                stale.append((name, item.get("tag"), claimed, actual))
            expected_depth = depth_for(actual)
            if expected_depth and expected_depth != item.get("depth"):
                stale.append((name + " [depth]", item.get("tag"),
                              item.get("depth"), expected_depth))

    for name, tag, claimed, actual in stale:
        print(f"DRIFT: {name!r} states {claimed}; tag {tag!r} now gives {actual}")

    print(f"\n{checked} tag-based counts verified, {len(stale)} stale.")
    if manual:
        print(f"{len(manual)} entries need a human check "
              f"(record-text or strength basis):")
        for name, why in manual:
            print(f"    - {name}  [{why}]")
    print(f"\ncorpus: {total_projects} curated projects, {total_records} records")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
