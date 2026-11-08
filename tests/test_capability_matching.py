"""Whole-candidate retrieval regressions with fictional evidence."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ekb_capabilities import read_capabilities
from ekb_requirements import frozen_requirements
from ekb_shortlist import candidates_for, requirement_mapping


def declaration(level="working-knowledge", *, name="Zig", context="non-professional",
                basis="study", confirmation_required=False):
    return {
        "id": "profile-capability-" + name.lower(),
        "name": name,
        "category": "technical",
        "proficiency": level,
        "context": context,
        "basis": {"type": basis, "detail": "Fictional practice and knowledge confirmation."},
        "last_confirmed": "2026-01-01",
        "kind": "inferred" if confirmation_required else "user-stated",
        "confirmation_required": confirmation_required,
        "confidence": "high",
        "interview_readiness": "ready",
        "examples": ["Parsed byte buffers in local exercises."],
        "limitations": ["No shipped implementation."] if context == "non-professional" else [],
    }


def project_record(ref, statement, project="specialist", strength=5):
    return {
        "id": ref, "project": project, "statement": statement, "eligible": True,
        "kind": "repo-verified", "involvement": "contributed", "strength": strength,
    }


class CapabilityMatchingTest(unittest.TestCase):
    def mapping(self, term, *, projects=(), capabilities=(), **metadata):
        index = {"records": projects}
        requirement = {"term": term, "priority": "required", **metadata}
        direct = candidates_for(index, [], 6, requirement=term)
        return requirement_mapping(
            requirement, direct, [], read_capabilities({"capabilities": list(capabilities)}),
            index, 6, {"eligible_kinds": ["repo-verified", "user-stated"]}, {"specialist"},
        )

    def test_confirmation_without_project_reuses_the_actual_basis_and_level(self):
        for level, context, basis, classification, heading in (
            ("working-knowledge", "non-professional", "study", "working knowledge", "Working Knowledge"),
            ("professional-experience", "professional", "employment", "broader professional capability", "Professional Skills"),
            ("practical-experience", "non-professional", "practice", "practical non-professional experience", "Practical Experience"),
            ("familiarity", "non-professional", "declaration", "familiarity", "Familiarity"),
        ):
            with self.subTest(level=level):
                capability = declaration(level, context=context, basis=basis)
                mapping = self.mapping("Zig", capabilities=[capability])
                self.assertEqual(mapping["classification"], classification)
                self.assertIsNone(mapping["discovery"])
                match = mapping["matches"][0]
                self.assertEqual(match["basis"], capability["basis"])
                self.assertEqual(match["context"], context)
                self.assertEqual(match["proficiency"], level)
                self.assertEqual(match["resume_use"]["heading"], heading)
                self.assertEqual(match["resume_use"]["partial"], level == "familiarity")

    def test_study_remains_partial_when_posting_requires_professional_use(self):
        mapping = self.mapping("Zig", capabilities=[declaration()], minimum_proficiency="professional-experience")
        self.assertEqual(mapping["classification"], "working knowledge")
        self.assertEqual(mapping["matches"][0]["fit"], "partial")
        self.assertEqual(mapping["matches"][0]["resume_use"]["heading"], "Working Knowledge")
        self.assertIsNone(mapping["discovery"])  # reuse the existing answer about context

    def test_unknown_and_learning_targets_do_not_authorize_skills(self):
        unknown = self.mapping("Zig", capabilities=[declaration(confirmation_required=True)])
        self.assertEqual(unknown["classification"], "needs confirmation")
        self.assertIn("Zig", unknown["discovery"])
        self.assertIsNone(unknown["matches"][0]["resume_use"])

        target = declaration("learning-target", basis="learning-goal")
        self.assertEqual(self.mapping("Zig", capabilities=[target])["classification"], "needs confirmation")
        learning = self.mapping("Zig", capabilities=[target | {"gap_confirmed": True}])
        self.assertEqual(learning["classification"], "genuine gap")
        self.assertIsNone(learning["discovery"])
        self.assertIsNone(learning["matches"][0]["resume_use"])

    def test_role_specific_synonyms_examples_and_transfer(self):
        projects = [
            project_record("hardware-001", "Traced a race condition in the BLE response handler."),
            project_record("hardware-002", "Wrote a MethodChannel bridge for a device driver."),
            project_record("hardware-003", "Forwarded APNs tokens in a native Swift AppDelegate."),
            project_record("api-001", "Added retries for RESTful services."),
        ]
        for term, ref, classification in (
            ("Bluetooth", "hardware-001", "direct professional evidence"),
            ("REST APIs", "api-001", "direct professional evidence"),
            ("Analytical problem-solving", "hardware-001", "related engineering example"),
            ("Device communication", "hardware-001", "transferable experience"),
            ("Native Android integration", "hardware-002", "transferable experience"),
            ("Native iOS integration", "hardware-003", "direct professional evidence"),
        ):
            with self.subTest(term=term):
                mapping = self.mapping(term, projects=projects)
                self.assertEqual(mapping["classification"], classification)
                self.assertEqual(mapping["matches"][0]["ref"], ref)

    def test_post_purchase_focus_prefers_outcomes_over_checkout_keyword_volume(self):
        index = {"records": [
            project_record("cart-001", "Added offer checkout and cart validation.", strength=10),
            project_record("booking-001", "Distinguished paid-but-unbooked and partial booking states."),
        ]}
        candidates = candidates_for(index, ["checkout"], 6, requirement="post-purchase",
                                    role="Commerce mobile engineer")
        self.assertEqual([row["id"] for row in candidates], ["booking-001", "cart-001"])

    def test_short_language_names_respect_punctuation(self):
        cpp = declaration(name="Cpp") | {"name": "C++"}
        self.assertEqual(self.mapping("C", capabilities=[cpp])["classification"], "needs confirmation")
        self.assertEqual(self.mapping("C++", capabilities=[cpp])["classification"], "working knowledge")

    def test_formal_bar_never_uses_skill_retrieval_as_qualification(self):
        assessment = {"status": "formal eligibility gap", "basis": "Screened against confirmed timeline."}
        posting = "Three years of professional experience with Zig."
        requirement, = frozen_requirements({
            "job_description": posting,
            "targeting": {"requirements": [{
                "term": "Zig", "posting_excerpt": posting, "category": "qualification",
                "priority": "required", "critical": True, "assessment": assessment,
            }]},
        })
        mapping = self.mapping("Zig", category="qualification", assessment=requirement["assessment"],
                               capabilities=[declaration()])
        self.assertEqual(mapping["classification"], assessment["status"])
        self.assertEqual(mapping["matches"], [])

    def test_professional_experience_needs_employment_context_and_basis(self):
        with self.assertRaisesRegex(ValueError, "invalid capability declaration"):
            read_capabilities({"capabilities": [declaration("professional-experience")]})
