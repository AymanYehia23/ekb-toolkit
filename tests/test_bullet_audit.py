#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
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
                "level": "impact",
                "result_type": "reliability",
            }
        ]

    def test_keeps_an_exact_ranked_bullet(self) -> None:
        status, replacement = replacement_for(
            {"text": "Built one validated import path.", "sources": ["example-001"]},
            self.banks,
        )
        self.assertEqual("kept", status)
        self.assertEqual(1, replacement["rank"])

    def test_supersedes_weaker_wording_for_selected_evidence(self) -> None:
        status, replacement = replacement_for(
            {"text": "Worked on imports.", "sources": ["example-001"]}, self.banks
        )
        self.assertEqual("improved", status)
        self.assertEqual("Built one validated import path.", replacement["text"])

    def test_retires_evidence_not_selected_into_a_bank(self) -> None:
        status, replacement = replacement_for(
            {"text": "Updated a dependency.", "sources": ["example-009"]}, self.banks
        )
        self.assertEqual("removed", status)
        self.assertIsNone(replacement)


if __name__ == "__main__":
    unittest.main()
