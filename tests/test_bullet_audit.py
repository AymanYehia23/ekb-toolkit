#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from bullet_audit import replacement_for  # noqa: E402


class BulletAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.banks = [
            {
                "bank": "example.md",
                "rank": 1,
                "text": "Built one validated import path.",
                "sources": ["example-001"],
                "variants": ["Consolidated the import paths."],
                "level": "impact",
                "result_type": "reliability",
            }
        ]

    def test_classifies_exact_ranked_bullet(self) -> None:
        status, replacement = replacement_for(
            {"text": "Built one validated import path.", "sources": ["example-001"]},
            self.banks,
        )
        self.assertEqual("exact_match", status)
        self.assertEqual(1, replacement["rank"])

    def test_classifies_different_text_with_same_evidence(self) -> None:
        status, replacement = replacement_for(
            {"text": "Worked on imports.", "sources": ["example-001"]}, self.banks
        )
        self.assertEqual("alternative_wording", status)
        self.assertEqual("Built one validated import path.", replacement["text"])

    def test_classifies_evidence_absent_from_bank(self) -> None:
        status, replacement = replacement_for(
            {"text": "Updated a dependency.", "sources": ["example-009"]}, self.banks
        )
        self.assertEqual("absent_from_bank", status)
        self.assertIsNone(replacement)

    def test_classifies_an_approved_variant(self) -> None:
        status, _ = replacement_for(
            {"text": "Consolidated the import paths.", "sources": ["example-001"]}, self.banks
        )
        self.assertEqual("approved_variant", status)

    def test_partial_sources_do_not_approve_a_variant(self) -> None:
        status, _ = replacement_for(
            {"text": "Consolidated the import paths.", "sources": ["example-001", "other-001"]},
            self.banks,
        )
        self.assertEqual("overlapping_sources", status)


if __name__ == "__main__":
    unittest.main()
