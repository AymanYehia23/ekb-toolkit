"""Adversarial publication and retrieval tests using fictional workspaces."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
from ekb_screening import posting_digest
from ekb_shortlist import candidates_for
from resume_publish import previous_pdf
from test_capability_matching import declaration


class ResumeWorkflowTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.projects = self.root / "projects"
        shutil.copytree(FIXTURES / "projects", self.projects)
        self.profile = self.root / "profile/profile.yaml"
        self.profile.parent.mkdir()
        shutil.copyfile(FIXTURES / "profile.yaml", self.profile)
        self.model = json.loads((FIXTURES / "resume.json").read_text())
        self.id = self.model["application_id"]
        self.draft = self.root / "draft.json"
        self.out = self.root / "artifacts/applications" / self.id
        self.app = self.root / "applications" / f"{self.id}.yaml"
        self.app.parent.mkdir()
        self.screen = self.app.with_suffix(".screening.yaml")
        self.posting = {
            "id": self.id, "company": "Target Company", "role": "Software Engineer",
            "job_description": "Fictional software role.",
            "targeting": {"resume_mode": "job-targeted", "requirements": []},
        }
        self.write_yaml(self.app, self.posting)
        self.decision("proceed")
        self.save()

    def write_yaml(self, path, value):
        path.write_text(yaml.safe_dump(value), encoding="utf-8")

    def decision(self, status, *, digest=True):
        decision = {"status": status, "decided_at": "2026-07-21"}
        if digest:
            decision["posting_sha256"] = posting_digest(self.posting)
        self.write_yaml(self.screen, {"id": self.id, "kind": "screening", "decision": decision})

    def save(self):
        self.draft.write_text(json.dumps(self.model), encoding="utf-8")

    def run_cmd(self, *args):
        return subprocess.run(
            list(map(str, args)), capture_output=True, text=True,
            env={**os.environ, "EKB_WORKSPACE": str(self.root), "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def tool(self, mode, *args, scripts=SCRIPTS):
        options = ["--model", self.draft, "--profile", self.profile, "--projects", self.projects]
        options += ["--legacy-replay"]
        if mode == "render":
            options += ["--output-dir", self.out]
            manifest = self.out / "validation.json"
            if manifest.is_file() and "--base-generation" not in args:
                generation = json.loads(manifest.read_text()).get("generation")
                if generation:
                    options += ["--base-generation", generation]
        return self.run_cmd(sys.executable, scripts / "resume_render.py", mode, *options, *args)

    def review(self):
        result = self.tool("validate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        claims = json.loads(result.stdout)["semantic_review"]["claims"]
        self.model["claim_reviews"] = {
            path: {
                "basis_sha256": claim["basis_sha256"],
                "clauses": [{
                    "wording": claim["wording"], "refs": claim["refs"],
                    "basis": "Fictional fixture scope checked against the cited test record.",
                }],
            } for path, claim in claims.items()
        }
        self.save()

    def blocked(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stdout + result.stderr)

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.out.iterdir() if path.is_file()}

    def assert_generation(self, path):
        report = json.loads((self.out / "validation.json").read_bytes())
        self.assertEqual(report["primary_pdf"], path)
        for name, item in report["outputs"].items():
            self.assertEqual(hashlib.sha256((self.out / name).read_bytes()).hexdigest(), item["sha256"])
        report_bytes = (self.out / "validation.md").read_bytes()
        self.assertEqual(hashlib.sha256(report_bytes).hexdigest(), report["report_sha256"])
        self.assertIn(report["generation"], (self.out / "validation.md").read_text())
        self.assertEqual(previous_pdf(self.out, None), path)
        return report["generation"]

    @property
    def bullet(self):
        return self.model["experience"][0]["bullets"][0]

    def test_private_editorial_packet_contains_exact_curated_evidence_and_requires_proceed(self):
        result = self.run_cmd(SCRIPTS / "ekb", "validate", self.id, "--draft", self.draft, "--editorial-packet", "--legacy-replay")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["delivery_status"], "private_draft_human_approval_required")
        packet = report["editorial_packet"]
        self.assertEqual(packet["target"], self.model["target"])
        claim = next(item for item in report["semantic_review"]["claims"].values()
                     if item["wording"] == self.bullet["text"])
        ref = claim["refs"][0]
        source = packet["sources"][ref]
        project = yaml.safe_load((self.root / source["record_path"]).read_text())
        curated = next(record for record in project["records"] if record["id"] == ref)
        for field in ("kind", "involvement", "statement", "evidence", "limitations"):
            self.assertEqual(source[field], curated.get(field))
        self.assertEqual(set(packet["sources"]), set(report["selected_sources"]))
        self.assertNotIn("editorial_packet", json.loads(self.tool("validate").stdout))
        self.decision("declined")
        self.blocked(self.tool("validate", "--editorial-packet"), "opportunity was declined")
        self.assertFalse(self.out.exists())

    def test_capability_skills_keep_level_basis_and_review_freshness(self):
        profile = yaml.safe_load(self.profile.read_text())
        capability = declaration()
        profile["capabilities"] = [capability]
        self.write_yaml(self.profile, profile)
        group = {"name": "Working Knowledge", "items": [{"text": "Zig", "source_ref": capability["id"]}]}
        self.model["skills"].append(group)
        self.save()

        result = self.tool("validate", "--editorial-packet")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        source = json.loads(result.stdout)["editorial_packet"]["sources"][capability["id"]]
        self.assertEqual(source["capability"], capability)
        self.assertEqual(source["skill_heading"], "Working Knowledge")
        interview = json.loads(result.stdout)["editorial_packet"]["capability_interview"]
        self.assertEqual(len(interview), 1)
        self.assertEqual(interview[0]["wording"], "Zig")
        self.assertEqual(interview[0]["ref"], capability["id"])
        self.assertEqual(interview[0]["answer_basis"]["basis"], capability["basis"])
        self.assertEqual(interview[0]["answer_basis"]["context"], "non-professional")
        self.review()
        result = self.tool("render")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_generation("resume.pdf")

        capability["interview_readiness"] = "needs-preparation"
        self.write_yaml(self.profile, profile)
        self.blocked(self.tool("render"), "requires a fresh claim review")

        group["name"] = "Professional Skills"
        self.save()
        self.blocked(self.tool("validate"), "proficiency heading")
        group["name"] = "Working Knowledge"
        group["items"][0]["text"] = "Built a production service in Zig"
        self.save()
        self.blocked(self.tool("validate"), "exact skill name")

    def test_private_capabilities_and_capability_sourced_accomplishments_are_blocked(self):
        profile = yaml.safe_load(self.profile.read_text())
        capability = declaration("learning-target", basis="learning-goal")
        profile["capabilities"] = [capability]
        self.write_yaml(self.profile, profile)
        self.model["skills"].append({
            "name": "Working Knowledge", "items": [{"text": "Zig", "source_ref": capability["id"]}],
        })
        self.save()
        self.blocked(self.tool("validate"), "confirmed capability")

        self.model["skills"].pop()
        profile["capabilities"] = [declaration()]
        self.write_yaml(self.profile, profile)
        self.bullet["source_ref"] = capability["id"]
        self.save()
        self.blocked(self.tool("validate"), "confirmed capability")

    def test_collaboration_reuses_current_reviews_and_unsupported_ownership_is_blocked(self):
        self.bullet["text"] = "Contributed to a data import pipeline built by the team with Ruby and PostgreSQL."
        self.save()
        self.review()
        self.assertEqual(self.tool("render").returncode, 0)
        self.assertEqual(self.tool("render").returncode, 0)
        for wording in (
            "Was the only engineer on the data import pipeline with Ruby and PostgreSQL.",
            "Contributed to the team-built pipeline and independently built its checkout.",
        ):
            with self.subTest(wording=wording):
                self.bullet["text"] = wording
                self.save()
                self.blocked(self.tool("render"), "independent-ownership wording")

    def test_distinct_clauses_can_use_distinct_participation_levels(self):
        left = "Contributed to a team-built data import pipeline"
        right = "and implemented a CSV export utility with Ruby."
        fixture = self.projects / "fixture.yaml"
        records = yaml.safe_load(fixture.read_text())
        records["records"].append({
            "id": "fixture-export", "kind": "repo-verified", "involvement": "implemented",
            "statement": "Implemented a CSV export utility with Ruby.",
        })
        self.write_yaml(fixture, records)
        self.bullet.clear()
        self.bullet.update(text=f"{left} {right}", source_refs=["fixture-001", "fixture-export"])
        self.save()
        diagnostic = self.tool("validate")
        self.assertNotEqual(diagnostic.returncode, 0)
        manifest = json.loads(diagnostic.stdout)["semantic_review"]["claims"]
        self.model["claim_reviews"] = {
            path: {"basis_sha256": row["basis_sha256"], "clauses": [{
                "wording": row["wording"], "refs": row["refs"], "basis": "Fictional evidence checked.",
            }]} for path, row in manifest.items()
        }
        self.model["claim_reviews"]["resume.experience[0].bullets[0]"]["clauses"] = [
            {"wording": left, "refs": ["fixture-001"], "basis": "Shared import-pipeline contribution."},
            {"wording": right, "refs": ["fixture-export"], "basis": "Separate implementation of the export utility."},
        ]
        self.save()
        result = self.tool("render")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_editorial_metadata_does_not_clear_known_unsupported_outcomes(self):
        for wording in (
            "Contributed to a data import pipeline that eliminated production outages.",
            "Contributed to a data import pipeline that improved customer retention.",
            "Contributed to a data import pipeline that kept customers from leaving.",
        ):
            with self.subTest(wording=wording):
                self.bullet["text"] = wording
                self.save()
                self.review()
                self.blocked(self.tool("render"), "Verify the observed")
                self.assertFalse(self.out.exists())

    def test_review_clause_boundaries_cannot_hide_leadership_or_management(self):
        self.review()
        self.assertEqual(self.tool("render").returncode, 0)
        before = self.snapshot()
        for left, right in (
            ("Led", "the delivery of a data import pipeline with Ruby and PostgreSQL."),
            ("Managed", "the team delivering a data import pipeline with Ruby and PostgreSQL."),
        ):
            with self.subTest(left=left):
                self.bullet["text"] = f"{left} {right}"
                self.model.pop("claim_reviews", None)
                self.save()
                diagnostic = json.loads(self.tool("validate").stdout)
                self.model["claim_reviews"] = {
                    path: {"basis_sha256": item["basis_sha256"], "clauses": [
                        {"wording": wording, "refs": item["refs"], "basis": "Fictional review."}
                        for wording in ([left, right] if item["wording"] == self.bullet["text"] else [item["wording"]])
                    ]}
                    for path, item in diagnostic["semantic_review"]["claims"].items()
                }
                self.save()
                self.blocked(self.tool("render"), "must review the complete")
                self.assertEqual(self.snapshot(), before)

    def test_changed_wording_and_references_need_fresh_reviews(self):
        self.review()
        original = copy.deepcopy(self.model)
        self.bullet["text"] = "Contributed to a team-built data import pipeline."
        self.save()
        self.blocked(self.tool("render"), "fresh claim review (stale_or_invalid)")
        self.model = original
        self.bullet["text"] = "Contributed to a background job integration using Redis."
        self.bullet["source_ref"] = "fixture-legacy-shared-001"
        self.save()
        self.blocked(self.tool("render"), "fresh claim review (stale_or_invalid)")

    def test_changed_evidence_and_participation_need_fresh_reviews(self):
        self.review()
        project = self.projects / "fixture.yaml"
        original = yaml.safe_load(project.read_text())
        for changes in ({"limitations": ["No deployment evidence."]}, {"involvement": "implemented"}):
            with self.subTest(changes=changes):
                data = copy.deepcopy(original)
                data["records"][0].update(changes)
                self.write_yaml(project, data)
                self.blocked(self.tool("render"), "fresh claim review (stale_or_invalid)")

    def test_policy_and_validator_revisions_need_fresh_reviews(self):
        self.review()
        config = self.root / "config"
        config.mkdir()
        policy = config / "toolkit.yaml"
        self.write_yaml(policy, {"evidence": {"eligible_involvement": ["implemented", "contributed"]}})
        self.blocked(self.tool("render"), "fresh claim review (stale_or_invalid)")
        policy.unlink()
        fork = self.root / "rules"
        shutil.copytree(SCRIPTS, fork / "scripts")
        shutil.copytree(ROOT / "schema", fork / "schema")
        shutil.copytree(ROOT / "config", fork / "config")
        validator = fork / "scripts/resume_claim_review.rb"
        with validator.open("a") as handle:
            handle.write("\n# Fictional validator revision.\n")
        self.blocked(self.tool("render", scripts=fork / "scripts"), "fresh claim review (stale_or_invalid)")

    def test_screening_blocks_every_normal_route_even_with_cached_data_and_prior_generation(self):
        self.review()
        self.assertEqual(self.run_cmd(sys.executable, SCRIPTS / "ekb_index.py").returncode, 0)
        self.assertEqual(self.run_cmd(SCRIPTS / "ekb", "shortlist", self.id).returncode, 0)
        self.assertEqual(self.tool("render").returncode, 0)
        old = self.snapshot()
        cached = self.app.with_suffix(".evidence.yaml").read_bytes()
        self.decision("declined")
        declined = self.screen.read_bytes()
        for command in (
            [SCRIPTS / "ekb", "shortlist", self.id, "--refresh"],
            [SCRIPTS / "ekb", "shortlist", self.id, "--stdout"],
            [sys.executable, SCRIPTS / "ekb_shortlist.py", "--application", self.id],
            [SCRIPTS / "ekb", "render", self.id],
            [SCRIPTS / "ekb", "render", self.id, "--draft", self.draft],
        ):
            with self.subTest(command=command):
                self.blocked(self.run_cmd(*command), "opportunity was declined")
        self.blocked(self.tool("render", "--legacy-formats"), "opportunity was declined")
        self.assertEqual(self.screen.read_bytes(), declined)
        self.assertEqual(self.app.with_suffix(".evidence.yaml").read_bytes(), cached)
        self.assertEqual(self.snapshot(), old)

    def test_unbound_changed_pending_deferred_and_unscreened_decisions_block(self):
        self.review()
        for status, message in (("pending", "pending explicit"), ("deferred", "pending clarification")):
            self.decision(status)
            self.blocked(self.tool("render"), message)
        self.decision("proceed", digest=False)
        self.blocked(self.tool("render"), "unbound or stale")
        self.decision("proceed")
        self.posting["job_description"] += " Changed intake."
        self.write_yaml(self.app, self.posting)
        self.blocked(self.tool("render"), "unbound or stale")
        self.screen.unlink()
        self.blocked(self.tool("render"), "not been screened")

    def test_update_is_stable_and_validation_and_render_failure_preserve_all_artifacts(self):
        self.review()
        initial = self.tool("render", "--pdf-name", "Stable CV.pdf")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        old = self.snapshot()
        first = self.assert_generation("Stable CV.pdf")
        self.bullet["text"] = "Contributed to a data import pipeline built by the team with Ruby and PostgreSQL."
        self.save()
        self.blocked(self.tool("render"), "stale_or_invalid")
        self.assertEqual(self.snapshot(), old)
        self.review()
        injected = (
            "from unittest.mock import patch; import resume_render as r; "
            "p=patch.object(r, 'render_pdf', side_effect=OSError('injected PDF failure')); "
            "p.start(); raise SystemExit(r.main())"
        )
        failure = self.run_cmd(
            sys.executable, "-c", f"import sys; sys.path.insert(0,{str(SCRIPTS)!r}); {injected}",
            "render", "--model", self.draft, "--profile", self.profile,
            "--projects", self.projects, "--output-dir", self.out, "--legacy-replay", "--base-generation", first,
        )
        self.blocked(failure, "injected PDF failure")
        self.assertEqual(self.snapshot(), old)
        self.blocked(self.tool("render", "--pdf-name", "Different.pdf"), "published PDF path")
        final = self.run_cmd(SCRIPTS / "ekb", "render", self.id, "--draft", self.draft,
                             "--legacy-replay", "--base-generation", first)
        self.assertEqual(final.returncode, 0, final.stderr)
        self.assertEqual(json.loads(final.stdout)["delivery_status"], "private_draft_human_approval_required")
        self.assertEqual(json.loads((self.out / "validation.json").read_text())["delivery_status"],
                         "private_draft_human_approval_required")
        self.assertIn("Human editorial approval", (self.out / "validation.md").read_text())
        self.assertNotEqual(first, self.assert_generation("Stable CV.pdf"))
        published = json.loads((self.out / "resume.json").read_bytes())
        self.assertEqual(published["education"], json.loads(old["resume.json"])["education"])
        self.assertEqual(published["experience"], self.model["experience"])
        self.blocked(self.tool("render", "--base-generation", first), "published generation changed")
        self.assertEqual(list(self.out.glob("*.pdf")), [self.out / "Stable CV.pdf"])

    def test_interruptions_before_and_after_exchange_expose_one_complete_generation(self):
        self.review()
        self.assertEqual(self.tool("render").returncode, 0)
        before = self.snapshot()
        first = self.assert_generation("resume.pdf")
        self.bullet["text"] = "Contributed to a data import pipeline built by the team with Ruby and PostgreSQL."
        self.save()
        self.review()
        for moment in ("before", "after"):
            code = f"""
import os, sys
sys.path.insert(0, {str(SCRIPTS)!r})
import resume_publish as p
import resume_render as r
exchange = p.exchange_directories
def interrupt(staged, output):
    if output.name != {self.id!r}:
        return exchange(staged, output)
    if {moment!r} == 'after':
        exchange(staged, output)
    os._exit(77)
p.exchange_directories = interrupt
raise SystemExit(r.main())
"""
            result = self.run_cmd(sys.executable, "-c", code, "render", "--model", self.draft,
                                  "--profile", self.profile, "--projects", self.projects, "--output-dir", self.out,
                                  "--legacy-replay", "--base-generation", first)
            self.assertEqual(result.returncode, 77, result.stderr)
            self.assertEqual(self.assert_generation("resume.pdf") == first, moment == "before")
            if moment == "before":
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.tool("render").returncode, 0)  # lock recovered after both exits

    def test_exchange_probe_failure_stops_before_staging(self):
        self.review()
        initial = self.tool("render")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        before = self.snapshot()
        first = self.assert_generation("resume.pdf")
        code = f"""
import errno, sys
sys.path.insert(0, {str(SCRIPTS)!r})
import resume_publish as p
import resume_render as r

def unsupported(staged, output):
    assert staged.name == "left" and output.name == "right"
    raise OSError(errno.ENOTSUP, "test filesystem rejects exchange")

def unexpected(*args, **kwargs):
    raise AssertionError("candidate work must not start after a rejected probe")

p.exchange_directories = unsupported
r.run_source_check = unexpected
raise SystemExit(r.main())
"""
        result = self.run_cmd(sys.executable, "-c", code, "render", "--model", self.draft,
                              "--profile", self.profile, "--projects", self.projects, "--output-dir", self.out,
                                  "--legacy-replay", "--base-generation", first)
        self.blocked(result, "resume update refused before staging; existing bundle retained")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.assert_generation("resume.pdf"), first)
        self.assertEqual(list(self.out.parent.glob(".ekb-*")), [])

    def test_late_report_path_collision_never_replaces_old_pdf_or_report(self):
        self.out.mkdir(parents=True)
        (self.out / "resume.pdf").write_bytes(b"prior PDF")
        (self.out / "validation.json").write_text("{}")
        (self.out / "validation.md").mkdir()
        self.review()
        old = self.snapshot()
        self.blocked(self.tool("render"), "cannot replace validation.md")
        self.assertEqual(self.snapshot(), old)


class RelevanceTest(unittest.TestCase):
    def test_device_native_commerce_and_general_queries_rank_before_cutoff(self):
        def row(ref, project, strength, statement, tags=()):
            return {"id": ref, "project": project, "strength": strength,
                    "statement": statement, "tags": list(tags), "eligible": True}
        index = {"records": [
            row("demo", "recent", 10, "Flutter demo using Android and iOS.", ("flutter",)),
            row("transport", "older", 1, "Acknowledged BLE transport in Flutter."),
            row("swift", "older", 1, "Native Swift APNs-to-FCM bridging."),
            row("payment", "travel", 2, "Checkout states included partial booking and paid-but-unbooked outcomes."),
            row("cart", "shop", 3, "Offer checkout with a server-priced cart and Flutter."),
            row("platform", "recent", 9, "Implemented reusable Flutter architecture."),
        ]}
        def refs(aliases, limit, **kwargs):
            return [row["id"] for row in candidates_for(index, aliases, limit, **kwargs)]
        self.assertEqual(refs(["Bluetooth", "Flutter"], 1), ["transport"])
        self.assertEqual(refs(["wireless device transport"], 1), ["transport"])
        self.assertEqual(refs(["native iOS", "Flutter"], 1), ["swift"])
        self.assertEqual(
            refs(["Flutter", "Riverpod"], 2, requirement="Complex frontend logic", role="App Engineer - Purchase"),
            ["cart", "payment"],
        )
        self.assertEqual(refs(["Flutter"], 3), ["demo", "cart", "transport"])
        self.assertIn("platform", refs(["Flutter"], 4))
