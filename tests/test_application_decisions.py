"""End-to-end decisions, exact PDF approval, and independent draft wording."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from pypdf import PdfReader
import yaml

from test_capability_matching import declaration
from test_resume_workflow import SCRIPTS
from ekb_screening import posting_digest

EXAMPLE = SCRIPTS.parent / "examples/sample-workspace"
SAMPLE_ID = "2026-03-14-northwind-flutter-engineer"
HARDWARE = "2026-08-01-device-labs-flutter-engineer"
OFFLINE = "2026-08-02-trail-maps-flutter-engineer"


def write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sign_fixture_claims(report):
    """Fixture authors stipulate source support. Real claims require review."""
    return {
        path: {"basis_sha256": item["basis_sha256"],
               "clauses": [{"wording": item["wording"], "refs": item["refs"],
                            "basis": "Fictional reviewed scope for this test case."}]}
        for path, item in report["semantic_review"]["claims"].items()
    }


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApplicationDecisionsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.addCleanup(self.keep_fictional_artifacts)
        for directory in ("profile", "projects", "context"):
            shutil.copytree(EXAMPLE / directory, self.root / directory)
        (self.root / "applications").mkdir()
        self.profile_path = self.root / "profile/profile.yaml"
        self.profile = yaml.safe_load(self.profile_path.read_text())
        self.profile["capabilities"] = [
            declaration("familiarity", basis="study"),
            declaration("practical-experience", name="Python", basis="practice"),
            declaration("working-knowledge", name="Rust", confirmation_required=True),
        ]
        write_yaml(self.profile_path, self.profile)
        mealmate = self.root / "projects/mealmate.yaml"
        older = yaml.safe_load(mealmate.read_text())
        older["records"].append({
            "id": "mealmate-101", "kind": "repo-verified", "involvement": "contributed",
            "statement": "Helped with receipt printing.",
            "tags": ["bluetooth", "flutter"],
            "evidence": [{"at": "ace1234", "path": "lib/receipt_transport.dart",
                          "note": "The team transport chunks receipts at the negotiated BLE MTU and waits for acknowledgments. "
                                  "The candidate contributed the acknowledged write path."}],
            "limitations": "Shared transport work. End-to-end printer reliability was unmeasured.",
        })
        write_yaml(mealmate, older)
        self.model = read_json(EXAMPLE / f"artifacts/applications/{SAMPLE_ID}/resume.json")

    def keep_fictional_artifacts(self):
        destination = os.environ.get("EKB_FICTIONAL_TEST_OUTPUT")
        source = self.root / "artifacts/applications"
        if destination and source.is_dir():
            for path in source.glob("*/validation.json"):
                shutil.copytree(path.parent, Path(destination) / self._testMethodName / path.parent.name,
                                dirs_exist_ok=True)

    def run_ekb(self, *args, error=None):
        result = subprocess.run([str(SCRIPTS / "ekb"), *map(str, args)], text=True, capture_output=True,
                                cwd=self.root, env={**os.environ, "EKB_WORKSPACE": str(self.root)})
        if error:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(error, result.stdout + result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def application(self, app_id=HARDWARE):
        hardware = app_id == HARDWARE
        company = "Device Labs" if hardware else "Trail Maps"
        model = copy.deepcopy(self.model)
        model["application_id"] = app_id
        model["target"]["company"] = company
        model["target"]["role"] = "Flutter Engineer"
        model["skills"] += [
            {"name": "Familiarity", "items": [{"text": "Zig", "source_ref": "profile-capability-zig"}]},
            {"name": "Practical Experience", "items": [{"text": "Python", "source_ref": "profile-capability-python"}]},
        ]
        model["experience"][0]["bullets"] = model["experience"][0]["bullets"][:2]
        model["experience"][1]["bullets"] = ([{
            "text": "Contributed to Bluetooth LE receipt transport with MTU-aware chunks and acknowledged writes.",
            "source_ref": "mealmate-101",
        }] if hardware else []) + model["experience"][1]["bullets"][:1]
        # Keep the candidate's timeline stable. Change which proof gets opening space.
        if hardware:
            model["summary"] = [
                {"text": "Flutter Mobile Engineer with 3+ years of experience across device integration and offline tracking.",
                 "source_refs": ["mealmate-101", "fittrack-002", "profile-experience-001", "profile-experience-002"]},
                {"text": "Contributed the acknowledged write path for Bluetooth LE receipt printing.",
                 "source_ref": "mealmate-101"},
                self.model["summary"][1],
            ]
        else:
            model["experience"][0]["bullets"].reverse()
            model["summary"] = [self.model["summary"][0], self.model["summary"][1], self.model["summary"][2]]
        model["quantifier_review"]["used"] = ["31 ms", "9 ms"]

        def requirement(term, excerpt, category="technical", minimum=None):
            return {"term": term, "posting_excerpt": excerpt, "aliases": [term], "category": category,
                    "minimum_proficiency": minimum, "priority": "required", "critical": term in ("Bluetooth", "Offline")}

        selected = [
            (requirement("Flutter", "Build mobile applications with Flutter."), "directly-demonstrated",
             "included", ["fittrack-002"], ["resume.summary[0]"], "Shipped Flutter workflow; use its offline proof."),
            (requirement("Python", "Use Python for local tools.", minimum="practical-experience"), "practical",
             "included", ["profile-capability-python"], ["resume.skills[3].items[0]"], "Confirmed local tools practice."),
            (requirement("Zig", "Professional Zig experience required.", minimum="professional-experience"), "partial",
             "included", ["profile-capability-zig"], ["resume.skills[2].items[0]"], "Study only. Professional bar remains unmet."),
            (requirement("low-end Android performance", "Tune low-end Android performance."), "partial",
             "included", ["fittrack-003"], [f"resume.experience[0].bullets[{0 if hardware else 1}]"],
             "Measured on a mid-range device. No low-end benchmark."),
            (requirement("Rust", "Troubleshoot native Rust integrations."), "needs-confirmation",
             "unresolved", ["profile-capability-rust"], [], "Prior note is inferred and awaiting confirmation."),
        ]
        selected.append((
            requirement("10 years of mobile employment", "At least 10 years of mobile employment.", "qualification"),
            "formal-eligibility-gap", "gap", ["profile-experience-001", "profile-experience-002"], [],
            "Confirmed mobile roles do not span ten years.",
        ))
        selected.insert(0, (
            requirement("Bluetooth", "Develop Bluetooth LE device integrations.") if hardware else
            requirement("Offline", "Build offline workflows for field devices."),
            "directly-demonstrated", "included", ["mealmate-101" if hardware else "fittrack-002"],
            ["resume.experience[1].bullets[0]" if hardware else "resume.experience[0].bullets[0]"],
            "Older collaborative transport is the strongest mechanism for this role." if hardware else
            "Persisted queue and conflict rule are stronger than a generic framework mention.",
        ))
        application = {
            "schema_version": 2, "id": app_id, "company": company, "role": "Flutter Engineer",
            "job_description": "\n".join(row[0]["posting_excerpt"] for row in selected),
            "targeting": {"resume_mode": "job-targeted", "requirements": [row[0] for row in selected]},
        }
        app_path = self.root / f"applications/{app_id}.yaml"
        write_yaml(app_path, application)
        write_yaml(app_path.with_suffix(".screening.yaml"), {
            "kind": "screening", "id": app_id, "decision": {"status": "proceed", "decided_at": "2026-08-01",
                                                          "posting_sha256": posting_digest(application)},
            "findings": [{"id": "finding-001", "basis": "At least 10 years of mobile employment.",
                          "qualification_fit": "formal-eligibility-gap",
                          "profile_basis": ["profile-experience-001", "profile-experience-002"]}],
        })
        # Compare current whole-candidate and live curated retrieval through the normal CLI.
        leads = yaml.safe_load(self.run_ekb("shortlist", app_id, "--stdout"))
        shortlist = {row["term"]: row for row in leads["requirements"]}
        self.assertEqual(shortlist["Flutter"]["profile_candidates"][0]["ref"], "profile-skill-001")
        self.assertEqual(shortlist["Zig"]["mapping"]["matches"][0]["fit"], "partial")
        if hardware:
            self.assertEqual(shortlist["Bluetooth"]["candidates"][0]["ref"], "mealmate-101")
        review = yaml.safe_load(self.run_ekb("requirement-map", app_id, "--skeleton"))
        review.update(reviewed_by="Fictional editorial fixture", inventory_review="Compared each posting sentence.",
                      positioning=selected[0][-1])
        for row, (_, fit, disposition, refs, paths, reason) in zip(review["requirements"], selected):
            row.update(fit=fit, disposition=disposition, refs=refs, claim_paths=paths, reason=reason)
            if fit == "formal-eligibility-gap":
                row["screening_finding"] = "finding-001"
        for path, item in [
            *[(f"resume.summary[{i}]", item) for i, item in enumerate(model["summary"])],
            *[(f"resume.experience[{i}].bullets[{j}]", item) for i, role in enumerate(model["experience"])
              for j, item in enumerate(role["bullets"])],
            *[(f"resume.skills[{i}].items[{j}]", item) for i, group in enumerate(model["skills"])
              for j, item in enumerate(group["items"])],
        ]:
            review["claim_plan"][path] = {"refs": item.get("source_refs") or [item["source_ref"]],
                                         "scope": item["text"]}
        write_yaml(app_path.with_suffix(".requirements.yaml"), review)
        model["alignment"] = json.loads(self.run_ekb("requirement-map", app_id, "--alignment"))
        return model, app_path

    def render(self, model, draft, *args):
        write_json(draft, model)
        app_id = model["application_id"]
        legacy = ("--legacy-replay",) if "--legacy-replay" in args else ()
        review = json.loads(self.run_ekb("validate", app_id, "--draft", draft, "--editorial-packet", *legacy))
        model["claim_reviews"] = sign_fixture_claims(review)
        write_json(draft, model)
        self.run_ekb("render", app_id, "--draft", draft, *args)
        return self.root / f"artifacts/applications/{app_id}"

    def verify_artifacts(self, out, app_id):
        report = read_json(out / "validation.json")
        packet = read_json(out / "editorial.json")
        reviewed = json.loads(self.run_ekb("requirement-map", app_id))
        self.assertEqual(packet["requirement_map"], reviewed)
        self.assertEqual(report["source_validation"]["requirement_map"], reviewed)
        self.assertEqual(packet["requirement_coverage"], report["source_validation"]["coverage"]["requirements"])
        self.assertEqual(report["outputs"]["editorial.json"]["sha256"], sha(out / "editorial.json"))
        self.assertEqual(packet["pdf_sha256"], sha(out / report["primary_pdf"]))
        self.assertEqual(packet["model_sha256"], sha(out / "resume.json"))
        alignment = read_json(out / "resume.json")["alignment"]
        self.assertEqual(alignment["requirement_map_sha256"], reviewed["revision_sha256"])
        self.assertEqual([row["requirement_id"] for row in alignment["requirements"]],
                         [row["id"] for row in reviewed["requirements"]])
        markdown = (out / "validation.md").read_text()
        self.assertIn(reviewed["revision_sha256"], markdown)
        for row in reviewed["requirements"]:
            self.assertIn(row["id"], markdown)
            self.assertIn(row["fit"], markdown)
        self.assertEqual(report["document_validation"]["errors"], [])
        pages = PdfReader(out / report["primary_pdf"]).pages
        self.assertEqual(len(pages), 1)
        text = " ".join(pages[0].extract_text().split())
        self.assertIn("Familiarity: Zig", text)
        self.assertIn("Practical Experience: Python", text)
        self.assertNotIn("Rust", text)
        self.assertNotIn("10 years of mobile employment", text)
        self.assertIn("mid-range Android device", text)
        self.assertNotIn("low-end Android", text)
        return report, packet, text

    def test_independent_wording_repeat_and_different_employer(self):
        model, _ = self.application()
        draft_a, draft_b = self.root / "a.json", self.root / "b.json"
        out = self.render(copy.deepcopy(model), draft_a)
        first, packet_a, text_a = self.verify_artifacts(out, HARDWARE)
        self.assertIn("MTU-aware chunks and acknowledged writes", text_a)
        self.assertNotIn("Helped with receipt printing", text_a)
        self.assertIn("Contributed", text_a)
        self.assertEqual(packet_a["sources"]["mealmate-101"]["involvement"], "contributed")
        second_model = copy.deepcopy(model)
        second_model["experience"][1]["bullets"][0]["text"] = (
            "Contributed to Bluetooth LE receipt printing with acknowledged writes sized to the negotiated MTU."
        )
        self.render(second_model, draft_b, "--base-generation", first["generation"])
        second, packet_b, text_b = self.verify_artifacts(out, HARDWARE)
        self.assertNotEqual(text_a, text_b)
        self.assertEqual(packet_a["requirement_map"], packet_b["requirement_map"])
        self.assertEqual(packet_a["requirement_coverage"], packet_b["requirement_coverage"])
        self.run_ekb("render", HARDWARE, "--draft", draft_b, "--base-generation", second["generation"])
        _, _, repeated = self.verify_artifacts(out, HARDWARE)
        self.assertEqual(text_b, repeated)

        offline, _ = self.application(OFFLINE)
        offline_out = self.render(offline, self.root / "offline.json")
        _, packet, offline_text = self.verify_artifacts(offline_out, OFFLINE)
        self.assertNotIn("Bluetooth", offline_text)
        self.assertIn("persisted replay queue", offline_text)
        self.assertEqual(packet["requirement_map"]["requirements"][0]["term"], "Offline")

    def test_stale_source_missing_requirement_wrong_level_and_claim_scope(self):
        model, app_path = self.application()
        draft = self.root / "draft.json"
        out = self.render(copy.deepcopy(model), draft)
        saved = sha(out / "validation.json")
        broken = copy.deepcopy(model)
        broken["alignment"]["requirements"].pop()
        write_json(draft, broken)
        self.run_ekb("render", HARDWARE, "--draft", draft, error="alignment differs")
        broken = copy.deepcopy(model)
        broken["skills"][2]["name"] = "Working Knowledge"
        write_json(draft, broken)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="proficiency heading")
        broken = copy.deepcopy(model)
        broken["experience"][1]["bullets"][0]["text"] = "Solely implemented Bluetooth LE receipt printing."
        write_json(draft, broken)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="overstates contributed source")
        broken = copy.deepcopy(model)
        broken["skills"][0]["name"] = "Expert Production Technologies"
        write_json(draft, broken)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="must use a neutral heading")
        broken = copy.deepcopy(model)
        broken["experience"][1]["bullets"][0]["text"] = (
            "Contributed to Bluetooth LE receipt transport that lifted repeat purchase rates."
        )
        write_json(draft, broken)
        report = json.loads(self.run_ekb("validate", HARDWARE, "--draft", draft))
        broken["claim_reviews"] = sign_fixture_claims(report)
        write_json(draft, broken)
        self.run_ekb("render", HARDWARE, "--draft", draft, "--base-generation", read_json(out / "validation.json")["generation"],
                     error="Verify the observed repeat-purchase outcome")
        broken = copy.deepcopy(model)
        broken["experience"][0]["bullets"].reverse()
        write_json(draft, broken)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="differ from the reviewed claim plan")
        write_json(draft, model)

        reviewed_path = app_path.with_suffix(".requirements.yaml")
        reviewed = yaml.safe_load(reviewed_path.read_text())
        changed = copy.deepcopy(reviewed)
        changed["requirements"].pop()
        write_yaml(reviewed_path, changed)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="every frozen requirement")
        changed = copy.deepcopy(reviewed)
        changed["requirements"][3]["fit"] = "working-knowledge"
        write_yaml(reviewed_path, changed)
        model["alignment"] = json.loads(self.run_ekb("requirement-map", HARDWARE, "--alignment"))
        write_json(draft, model)
        self.run_ekb("validate", HARDWARE, "--draft", draft, error="lacks support at the required scope")
        changed = copy.deepcopy(reviewed)
        changed["requirements"][-1].update(fit="formal-eligibility-met", disposition="omitted")
        write_yaml(reviewed_path, changed)
        self.run_ekb("requirement-map", HARDWARE, error="matching screening finding")
        write_yaml(reviewed_path, reviewed)
        frozen = yaml.safe_load(app_path.read_text())
        modified = copy.deepcopy(frozen)
        modified["targeting"]["requirements"][1]["aliases"].append("hardware")
        write_yaml(app_path, modified)
        self.run_ekb("requirement-map", HARDWARE, error="reviewed requirement map is stale")
        write_yaml(app_path, frozen)
        self.profile["capabilities"][0]["interview_readiness"] = "needs-preparation"
        write_yaml(self.profile_path, self.profile)
        self.run_ekb("requirement-map", HARDWARE, error="reviewed requirement map is stale")
        self.assertEqual(sha(out / "validation.json"), saved)

    def test_conflicts_are_rejected_by_matching_checking_and_diagnostics(self):
        model, _ = self.application()
        duplicate = declaration("professional-experience", name="Ziglang", context="professional", basis="employment")
        duplicate["aliases"] = ["ZIG"]
        duplicate["last_confirmed"] = "2026-02-01"
        self.profile["capabilities"].append(duplicate)
        write_yaml(self.profile_path, self.profile)
        self.run_ekb("shortlist", HARDWARE, "--stdout", error="conflicting capability identity")
        self.run_ekb("check", "--root", self.root, error="conflicting capability identity")
        self.run_ekb("requirement-map", HARDWARE, "--skeleton", error="conflicting capability identity")
        duplicate["supersedes"] = ["profile-capability-zig"]
        write_yaml(self.profile_path, self.profile)
        leads = yaml.safe_load(self.run_ekb("shortlist", HARDWARE, "--stdout"))
        zig = next(row for row in leads["requirements"] if row["term"] == "Zig")
        self.assertEqual([row["ref"] for row in zig["mapping"]["matches"]], [duplicate["id"]])
        self.assertEqual(zig["mapping"]["matches"][0]["proficiency"], "professional-experience")
        duplicate["last_confirmed"] = "2099-01-01"
        write_yaml(self.profile_path, self.profile)
        self.run_ekb("shortlist", HARDWARE, "--stdout", error="invalid capability declaration")

    def test_original_clean_example_route_renders_in_disposable_copy(self):
        for path in (EXAMPLE / "applications").glob(f"{SAMPLE_ID}.*yaml"):
            shutil.copyfile(path, self.root / "applications" / path.name)
        self.run_ekb("index")
        self.run_ekb("check", "--root", self.root)
        self.run_ekb("shortlist", SAMPLE_ID, "--refresh")
        draft = self.root / "example.json"
        write_json(draft, self.model)
        self.run_ekb("render", SAMPLE_ID, "--draft", draft, error="requires explicit --legacy-replay")
        out = self.render(self.model, draft, "--legacy-replay")
        report = read_json(out / "validation.json")
        self.assertEqual(report["document_validation"]["errors"], [])
        self.assertEqual(len(PdfReader(out / "resume.pdf").pages), 1)

    def test_exact_receipt_and_tampered_pdf_report_or_missing_generation(self):
        model, _ = self.application()
        draft = self.root / "reviewed.json"
        out = self.render(model, draft)
        report, packet, _ = self.verify_artifacts(out, HARDWARE)
        receipt_path = self.root / "receipt.json"
        receipt = {key: packet[key] for key in ("application_id", "generation", "posting_sha256", "primary_pdf", "pdf_sha256")}
        receipt.update(validation_sha256=sha(out / "validation.json"), editorial_sha256=sha(out / "editorial.json"),
                       requirement_map_sha256=packet["requirement_map"]["revision_sha256"],
                       reviewer="Fictional reviewer", reviewed_at="2026-01-01",
                       material_claims_approved=True, exact_pdf_inspected=True, gaps_reviewed=True)
        write_json(receipt_path, receipt)
        self.run_ekb("verify-review", HARDWARE, "--approval", receipt_path)
        self.run_ekb("render", HARDWARE, "--draft", draft, error="requires --base-generation")

        for name in ("resume.pdf", "validation.md", "editorial.json"):
            path = out / name
            original = path.read_bytes()
            path.write_bytes(original + b"\ntampered")
            self.run_ekb("verify-review", HARDWARE, "--approval", receipt_path, error="integrity check")
            path.write_bytes(original)
        self.run_ekb("render", HARDWARE, "--draft", draft, "--base-generation", report["generation"])
        self.run_ekb("verify-review", HARDWARE, "--approval", receipt_path, error="different PDF or generation")
