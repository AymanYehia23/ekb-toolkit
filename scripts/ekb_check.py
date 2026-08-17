#!/usr/bin/env python3
"""EKB consistency check — read-only.

Verifies the invariants that no single procedure owns, because they span files:

  1. Every curated project is assigned to exactly one career_map context.
  2. career_map project lists agree with profile.yaml experience[].projects.
  3. preferences.standalone_projects / academic_projects match their
     career_map buckets.
  4. Every record ID cited by professional-profile.yaml exists in a curated
     projects/*.yaml.
  5. Every project named anywhere resolves to a curated projects/<name>.yaml.
  6. Records referenced by a `supersedes:` field are gone from the curated file.
  7. profile-strength-010's stated domain and project counts match its list.
  8. No project appears in both a store-release count and its exclusion list.
  9. project-ranking.yaml ranks every curated project exactly once, with unique
     gapless ranks and each score equal to the sum of its dimensions.
 10. Every record ID cited by the ranking exists in the project it names.
 11. Link registry integrity: organization_links match employer names,
     project_links name curated projects, and every entry carries a known
     link_status.
 12. professional-profile.yaml states its current coverage, and that coverage
     matches the number of curated projects.
 13. Generated banks the evidence index quotes still cite live, eligible
     records, satisfy the public bullet policy, and exist for every project.

Exit 0 = clean, 1 = problems found. Nothing is written or modified.
Run:  ekb check
"""

import glob
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bullet_quality import bullet_text_findings, parse_bullet_bank  # noqa: E402
from ekb_paths import load_config, workspace_root  # noqa: E402

FAIL = []
WARN = []


def fail(msg):
    FAIL.append(msg)


def warn(msg):
    WARN.append(msg)


def load(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def address_like_label(label):
    text = str(label or "").strip()
    if not text:
        return False
    if re.search(r"(?:https?://|mailto:|tel:|www\.)", text, re.IGNORECASE):
        return True
    if "@" in text or re.fullmatch(r"\+?[\d\s().-]{7,}", text):
        return True
    return bool(re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#]|$)", text, re.IGNORECASE))


def main():
    os.chdir(workspace_root())
    if not os.path.isdir("projects"):
        print(f"no projects/ directory in workspace {workspace_root()}", file=sys.stderr)
        return 2

    # ---- load curated knowledge -------------------------------------------
    curated = {}      # project name -> set of record ids
    record_meta = {}  # record id -> provenance and participation
    superseded = {}   # record id -> superseding id
    for path in sorted(glob.glob("projects/*.yaml")):
        if path.endswith(".candidates.yaml"):
            continue
        name = os.path.basename(path)[: -len(".yaml")]
        data = load(path) or {}
        records = data.get("records") or []
        # `project_context` entries are curated ids too. They describe the
        # project rather than a personal contribution, but a generated bank may
        # legitimately cite one, so they belong in the known-id set.
        context_entries = data.get("project_context") or []
        curated[name] = {r["id"] for r in records} | {c["id"] for c in context_entries if c.get("id")}
        for record in [*records, *context_entries]:
            if record.get("id"):
                record_meta[record["id"]] = {
                    "kind": record.get("kind"),
                    "involvement": record.get("involvement"),
                }
        for r in records:
            if r.get("supersedes"):
                superseded[r["supersedes"]] = r["id"]
        if data.get("project") and data["project"] != name:
            fail(f"{path}: project key '{data['project']}' != filename '{name}'")

    all_records = {rid for ids in curated.values() for rid in ids}

    # 6. superseded records must no longer be present
    for old, new in sorted(superseded.items()):
        if old in all_records:
            fail(f"superseded record {old} is still present (replaced by {new})")

    profile = load("profile/profile.yaml") or {}
    pro = load("profile/professional-profile.yaml") or {}

    # ---- 1 + 2: career_map vs experience ----------------------------------
    cmap = {}  # project -> career_map id
    for ctx in pro.get("career_map") or []:
        for proj in ctx.get("projects") or []:
            if proj in cmap:
                fail(f"project '{proj}' assigned to two contexts: {cmap[proj]} and {ctx['id']}")
            cmap[proj] = ctx["id"]

    exp_projects = set()
    for exp in profile.get("experience") or []:
        exp_projects.update(exp.get("projects") or [])

    for proj in sorted(exp_projects):
        if proj not in cmap:
            fail(f"'{proj}' listed under experience but missing from career_map")

    for proj in sorted(curated):
        if proj not in cmap:
            warn(f"curated project '{proj}' is in no career_map context")

    # ---- 3: preference groups vs career_map -------------------------------
    prefs = profile.get("preferences") or {}
    for key, expect_ids in (
        ("standalone_projects", {"profile-employer-003"}),
        ("academic_projects", {"profile-employer-004"}),
    ):
        for proj in prefs.get(key) or []:
            got = cmap.get(proj)
            if got is None:
                fail(f"preferences.{key} names '{proj}', absent from career_map")
            elif got not in expect_ids:
                fail(
                    f"preferences.{key} names '{proj}' but career_map puts it in "
                    f"{got} (expected one of {sorted(expect_ids)})"
                )

    # ---- 4 + 5: references resolve ----------------------------------------
    blob = open("profile/professional-profile.yaml").read()

    # Require a letter in the project part, so prose ranges like "records
    # 001-011" are not mistaken for record IDs.
    for rid in sorted(set(re.findall(r"\b([a-z][a-z0-9_-]*[a-z]-\d{3})\b", blob))):
        if rid.startswith("profile-"):
            continue
        if rid in all_records:
            continue
        if rid in superseded:
            fail(f"professional-profile cites {rid}, which was superseded by {superseded[rid]}")
        else:
            project_guess = rid.rsplit("-", 1)[0]
            if project_guess in curated:
                fail(f"professional-profile cites {rid}, which does not exist in {project_guess}")
            else:
                warn(f"professional-profile cites unresolved id {rid}")

    named = set(cmap) | exp_projects
    for link in profile.get("project_links") or []:
        named.add(link.get("project"))
    for proj in sorted(p for p in named if p):
        if proj not in curated:
            warn(f"'{proj}' is referenced but has no curated projects/{proj}.yaml")

    # ---- 7: strength-010 counts match its own list -------------------------
    for st in pro.get("strengths") or []:
        if st["id"] != "profile-strength-010":
            continue
        domains = st.get("domains") or []
        projects = {p for d in domains for p in (d.get("projects") or [])}
        words = {
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
            "fourteen": 14, "fifteen": 15,
        }
        m = re.search(r"^\s*(\w+)\s+distinct business domains across (\d+) projects",
                      st.get("statement", ""), re.I)
        if not m:
            warn("profile-strength-010: could not parse the stated counts")
        else:
            stated_domains = words.get(m.group(1).lower())
            stated_projects = int(m.group(2))
            if stated_domains != len(domains):
                fail(
                    f"profile-strength-010 says {m.group(1)} domains "
                    f"but lists {len(domains)}"
                )
            if stated_projects != len(projects):
                fail(
                    f"profile-strength-010 says {stated_projects} projects "
                    f"but lists {len(projects)}"
                )

    # ---- 8: store count vs exclusions -------------------------------------
    for st in pro.get("strengths") or []:
        sr = st.get("store_releases")
        if not sr:
            continue
        excluded = " ".join(sr.get("excluded_from_the_count") or [])
        composition = sr.get("composition", "") + sr.get("verification", "")
        for proj in sorted(curated):
            in_excl = re.search(rf"\b{re.escape(proj)}\b", excluded)
            counted = re.search(rf"\b{re.escape(proj)}\b", sr.get("verification", ""))
            if in_excl and counted:
                fail(
                    f"{st['id']}: '{proj}' appears in both the counted listings "
                    f"and excluded_from_the_count"
                )

    # ---- 9 + 10: project ranking ------------------------------------------
    ranking_path = "profile/project-ranking.yaml"
    if not os.path.isfile(ranking_path):
        warn(f"{ranking_path} is absent; project selection has no global ranking")
    else:
        ranking = load(ranking_path) or {}
        entries = ranking.get("projects") or []
        ranked = [e.get("project") for e in entries]
        for proj in sorted(curated):
            if ranked.count(proj) == 0:
                not_ranked = {n.get("project") for n in (ranking.get("not_ranked") or [])}
                if proj not in not_ranked:
                    fail(f"curated project '{proj}' is absent from {ranking_path}")
            elif ranked.count(proj) > 1:
                fail(f"'{proj}' appears {ranked.count(proj)} times in {ranking_path}")

        ranks = [e.get("rank") for e in entries]
        if sorted(ranks) != list(range(1, len(entries) + 1)):
            fail(f"{ranking_path} ranks are not unique and gapless from 1 to {len(entries)}")

        dimensions = {
            "complexity", "architecture", "scale", "maturity", "ownership",
            "collaboration", "distinctiveness", "resume_value", "interview_value",
        }
        for entry in entries:
            proj = entry.get("project")
            dims = entry.get("dimensions") or {}
            if set(dims) != dimensions:
                fail(f"{ranking_path}: '{proj}' dimensions are {sorted(set(dims))}")
                continue
            # `rank_basis` explains a rank that departs from score order; it
            # never excuses a score that departs from its own dimensions.
            if sum(dims.values()) != entry.get("score"):
                fail(
                    f"{ranking_path}: '{proj}' score {entry.get('score')} != "
                    f"sum of dimensions {sum(dims.values())}"
                )
            for rid in entry.get("best_evidence") or []:
                if rid not in all_records:
                    fail(f"{ranking_path}: '{proj}' cites missing record {rid}")
                elif rid not in curated.get(proj, set()):
                    fail(f"{ranking_path}: '{proj}' cites {rid}, which belongs to another project")

    # ---- 11: link registry -------------------------------------------------
    known_status = {"confirmed", "unconfirmed", "uncurated"}
    for section in ("contact", "links"):
        for entry in profile.get(section) or []:
            if section == "contact" and entry.get("type") == "phone":
                value = str(entry.get("value") or "").strip()
                label = str(entry.get("label") or "").strip()
                owner = entry.get("id") or "phone contact"
                if entry.get("url"):
                    fail(f"{owner} is a phone contact and must not carry a url")
                if label != value:
                    fail(f"{owner} phone label must match its literal value")
                continue
            if not entry.get("url"):
                continue
            label = str(entry.get("label") or "").strip()
            owner = entry.get("id") or f"{section} entry"
            if not label:
                fail(f"{owner} has a url but no human-readable label")
            elif address_like_label(label):
                fail(f"{owner} label exposes an address; use a word such as Email, LinkedIn, GitHub, or Portfolio")
    employers = {e.get("organization") for e in (profile.get("experience") or [])}
    for entry in profile.get("organization_links") or []:
        name = entry.get("organization")
        if entry.get("link_status", "confirmed") not in known_status:
            fail(f"organization_links '{name}' has unknown link_status {entry.get('link_status')!r}")
        if name not in employers:
            warn(f"organization_links names '{name}', which is not an employer in profile.yaml")
        if not str(entry.get("url") or "").startswith("https://"):
            fail(f"organization_links '{name}' must carry an https:// url")
    for entry in profile.get("project_links") or []:
        proj = entry.get("project")
        status = entry.get("link_status", "confirmed")
        if status not in known_status:
            fail(f"project_links '{proj}' has unknown link_status {status!r}")
        if proj not in curated and status == "confirmed":
            fail(f"project_links '{proj}' is confirmed but has no curated projects/{proj}.yaml")
        if not any(entry.get(slot) for slot in ("play_store", "app_store", "repo", "docs", "portfolio")):
            fail(f"project_links '{proj}' has no address in any known slot")

    # ---- 12: professional profile coverage is stated -----------------------
    #
    # `validation_basis` deliberately records the last FULL validation, not
    # current coverage, so staleness cannot be read off it. Checks 1-5 above
    # already verify that references and career_map resolve; what they cannot
    # tell you is whether a curated project has ever been WEIGHED by a
    # validation session. `current_coverage` states that, and this check keeps
    # it honest.
    coverage = pro.get("current_coverage") or {}
    recorded = coverage.get("curated_projects")
    if recorded is None:
        warn(
            "professional-profile has no current_coverage block; coverage since "
            "the last full validation is unstated"
        )
    elif int(recorded) != len(curated):
        warn(
            f"professional-profile current_coverage says {recorded} curated projects "
            f"but {len(curated)} exist; run a validation session (prompts/profile.md)"
        )

    # ---- 13: generated artifacts the evidence index quotes -------------------
    #
    # index/evidence-index.yaml lifts resume phrasings out of artifacts/bullets/
    # and story titles out of artifacts/interview/, so those files are no longer
    # purely disposable: a stale one feeds stale prose into selection.
    #
    # A final resume has its own source checker, but weak generated wording should
    # not enter the retrieval index in the first place. Apply the same objective
    # bullet policy here for every development stack; the prompt remains
    # responsible for the semantic Outcome > Impact > Scope > Activity judgement.
    resume_policy = load_config("resume-policy.json")
    bullet_policy = resume_policy.get("bullet_quality") or {}
    maximum_bullets = int(bullet_policy.get("maximum_selected_per_project", 5))
    maximum_sources = int(bullet_policy.get("maximum_sources", 4))
    if maximum_bullets < 1:
        fail("resume-policy bullet_quality.maximum_selected_per_project must be positive")
    if maximum_sources < 1:
        fail("resume-policy bullet_quality.maximum_sources must be positive")

    for kind in ("bullets", "interview"):
        for path in sorted(glob.glob(f"artifacts/{kind}/*.md")):
            project = os.path.basename(path)[: -len(".md")]
            if project not in curated:
                warn(f"artifacts/{kind}/{project}.md has no curated projects/{project}.yaml")
                continue
            with open(path, encoding="utf-8") as fh:
                artifact_text = fh.read()
            cited = set(re.findall(r"<!--\s*src:\s*([a-z0-9_\-]+-\d{3})\s*-->", artifact_text, re.I))
            gone = sorted(cited - curated[project])
            if gone:
                warn(
                    f"artifacts/{kind}/{project}.md cites {len(gone)} record(s) that no longer "
                    f"exist ({', '.join(gone[:3])}{', ...' if len(gone) > 3 else ''}); "
                    f"regenerate it (prompts/{kind}.md with PROJECT={project})"
                )
            if kind != "bullets":
                continue

            entries = parse_bullet_bank(artifact_text)
            if cited and not entries:
                fail(
                    f"{path} cites records but has no parseable top-level Markdown bullets; "
                    f"regenerate it (prompts/bullets.md with PROJECT={project})"
                )
            if len(entries) > maximum_bullets:
                fail(
                    f"{path} has {len(entries)} publishable bullets; "
                    f"maximum is {maximum_bullets}"
                )
            for entry in entries:
                location = f"{path}:{entry['line']}"
                for finding in bullet_text_findings(entry["text"], resume_policy):
                    fail(f"{location} {finding}")
                for variant in entry["variants"]:
                    for finding in bullet_text_findings(variant, resume_policy):
                        fail(f"{location} variant {finding}")
                sources = entry["sources"]
                if not sources:
                    fail(f"{location} has no source comment")
                    continue
                if len(sources) > maximum_sources:
                    fail(
                        f"{location} cites {len(sources)} sources; "
                        f"maximum is {maximum_sources}"
                    )
                if len(set(sources)) != len(sources):
                    fail(f"{location} repeats a source comment")
                for source in sources:
                    meta = record_meta.get(source)
                    if meta is None:
                        continue
                    if meta.get("kind") not in {"repo-verified", "user-stated"}:
                        fail(
                            f"{location} cites ineligible kind {meta.get('kind')!r} "
                            f"from {source}"
                        )
                    if meta.get("involvement") not in {"led", "implemented", "contributed"}:
                        fail(
                            f"{location} cites ineligible involvement "
                            f"{meta.get('involvement')!r} from {source}"
                        )
        missing = [p for p in sorted(curated) if not os.path.isfile(f"artifacts/{kind}/{p}.md")]
        if missing:
            warn(
                f"{len(missing)} curated project(s) have no artifacts/{kind} bank, so their records "
                f"carry no {'phrasing' if kind == 'bullets' else 'story'} in the evidence index: "
                f"{', '.join(missing)}"
            )

    # ---- report ------------------------------------------------------------
    for w in WARN:
        print(f"warn: {w}")
    for f in FAIL:
        print(f"FAIL: {f}")
    print(
        f"\n{len(curated)} curated projects, {len(all_records)} records, "
        f"{len(FAIL)} failures, {len(WARN)} warnings"
    )
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
