#!/usr/bin/env python3
"""Compare competing resume drafts for one application and name a winner.

WHY THIS EXISTS
    Every application until now produced exactly one draft. A single draft with
    no rival is unfalsifiable: nothing establishes it was the best resume the
    evidence could support, only that it passed every gate. "Was this the best
    available selection?" stayed a rhetorical question.

    This makes it measurable. Draft two models with genuinely different
    selection strategies, compare them on the machinery that already exists,
    keep the winner, and record why.

    It re-implements no scoring. Each model is handed to
    scripts/resume_source_check.rb and the comparison reads its report, so the
    verdict uses exactly the rubric and coverage grades a normal render uses.

USAGE
    scripts/ekb_compare.py --profile profile/profile.yaml --projects projects \\
      --models depth:draft-a.json breadth:draft-b.json

    A model may be given as `name:path` or bare `path`, in which case the
    filename stem becomes its name.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_check(model: str, profile: str, projects: str, ranking: str | None) -> dict:
    checker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume_source_check.rb")
    command = ["ruby", checker, "--model", model, "--profile", profile, "--projects", projects]
    if ranking and os.path.isfile(ranking):
        command += ["--ranking", ranking]
    done = subprocess.run(command, capture_output=True, text=True)
    if not done.stdout.strip():
        sys.exit(f"source check produced no output for {model}: {done.stderr.strip()}")
    return json.loads(done.stdout)


def summarize(report: dict) -> dict:
    counts = (report.get("coverage") or {}).get("counts") or {}
    score = report.get("selection_score") or {}
    dims = score.get("dimensions") or {}
    return {
        "valid": report.get("valid"),
        "score": score.get("score"),
        "demonstrated": counts.get("demonstrated", 0),
        "stated": counts.get("stated", 0),
        "unsupported": counts.get("unsupported", 0),
        "strongest": (dims.get("strongest_evidence_used") or {}).get("value"),
        "errors": len(report.get("errors") or []),
        "warnings": len(report.get("warnings") or []),
        "coverage": {
            entry["term"]: entry.get("coverage")
            for entry in ((report.get("coverage") or {}).get("requirements") or [])
        },
        "sources": set(report.get("selected_sources") or []),
    }


def verdict(rows: list) -> tuple:
    """Winner by selection score, then demonstrated count, then fewer errors.

    Deliberately simple and deliberately not the only input: a draft can win on
    score and still be the wrong document, which is why the caller is asked to
    record a reason rather than accept the number.
    """
    valid = [r for r in rows if r[1]["valid"]]
    pool = valid or rows
    ranked = sorted(
        pool,
        key=lambda r: (
            -(r[1]["score"] or 0),
            -r[1]["demonstrated"],
            r[1]["errors"],
            r[1]["warnings"],
        ),
    )
    best = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    return best, runner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True, help="name:path or path")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--projects", required=True)
    parser.add_argument("--ranking")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if len(args.models) < 2:
        sys.exit("comparison needs at least two models; one draft cannot be compared to itself")

    rows = []
    for spec in args.models:
        if ":" in spec and not os.path.isfile(spec):
            name, path = spec.split(":", 1)
        else:
            name, path = os.path.splitext(os.path.basename(spec))[0], spec
        if not os.path.isfile(path):
            sys.exit(f"no such model: {path}")
        rows.append((name, summarize(run_check(path, args.profile, args.projects, args.ranking))))

    best, runner = verdict(rows)

    if args.json:
        payload = {
            "drafts": {n: {k: v for k, v in s.items() if k not in ("coverage", "sources")}
                       for n, s in rows},
            "winner": best[0],
        }
        print(json.dumps(payload, indent=2))
        return 0

    names = [n for n, _ in rows]
    width = max(12, max(len(n) for n in names) + 2)
    def line(label, values):
        print(f"  {label:<26}" + "".join(f"{str(v):>{width}}" for v in values))

    print(f"\nComparing {len(rows)} drafts\n")
    line("selection score", [s["score"] for _, s in rows])
    line("required demonstrated", [s["demonstrated"] for _, s in rows])
    line("stated", [s["stated"] for _, s in rows])
    line("unsupported", [s["unsupported"] for _, s in rows])
    line("strongest evidence used", [f'{s["strongest"]}%' if s["strongest"] is not None else "n/a"
                                     for _, s in rows])
    line("errors", [s["errors"] for _, s in rows])
    line("warnings", [s["warnings"] for _, s in rows])
    line("valid", ["PASS" if s["valid"] else "FAIL" for _, s in rows])
    print("  " + " " * 26 + "".join(f"{n:>{width}}" for n in names))

    # Where the drafts actually disagree. This is the part worth reading: two
    # drafts can score the same and answer different requirements.
    first = rows[0][1]
    diffs = []
    for term, grade in first["coverage"].items():
        others = [s["coverage"].get(term) for _, s in rows[1:]]
        if any(o != grade for o in others):
            diffs.append((term, [grade] + others))
    if diffs:
        print("\n  Requirements graded differently:")
        for term, grades in diffs:
            print(f"    {term:<44}" + "".join(f"{str(g):>{width}}" for g in grades))

    only = {}
    all_sources = set().union(*[s["sources"] for _, s in rows])
    for name, s in rows:
        unique = s["sources"] - set().union(*[o["sources"] for n2, o in rows if n2 != name])
        if unique:
            only[name] = sorted(unique)
    if only:
        print("\n  Evidence unique to one draft:")
        for name, refs in only.items():
            print(f"    {name}: {', '.join(refs)}")

    print(f"\n  Winner on the numbers: {best[0]}")
    if runner:
        b, r = best[1], runner[1]
        gap = (b["score"] or 0) - (r["score"] or 0)
        print(f"    {gap:+d} selection score, "
              f"{b['demonstrated'] - r['demonstrated']:+d} demonstrated against {runner[0]}")
    print("\n  The number does not decide it. A draft can win on score and still be the")
    print("  wrong document for the target. Record which you kept and why.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
