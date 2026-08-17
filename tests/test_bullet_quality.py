#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from bullet_quality import bullet_text_findings, parse_bullet_bank  # noqa: E402
from ekb_index import BulletQualityError, collect_curated_bullets  # noqa: E402


POLICY = {
    "bullet_quality": {
        "maximum_words": 36,
        "require_terminal_punctuation": True,
        "forbidden_openings": ["responsible for", "worked on", "helped with"],
    },
    "writing_style": {
        "forbidden_symbols": {"—": "em dash"},
        "forbidden_terms": ["seamless"],
        "forbidden_phrases": ["results-driven professional"],
    },
}


class BulletQualityTest(unittest.TestCase):
    def test_accepts_concise_bullets_across_development_stacks(self) -> None:
        bullets = [
            "Reduced first-content time from 5.0 seconds to 0.9 seconds by limiting rebuild scope.",
            "Consolidated four backend lookups into one typed endpoint shared by catalog and checkout flows.",
            "Introduced idempotent infrastructure rollouts with health checks and automatic rollback on failed deployments.",
            "Built a partitioned data-ingestion path that isolates malformed records and preserves valid batches for processing.",
        ]
        for bullet in bullets:
            self.assertEqual([], bullet_text_findings(bullet, POLICY))

    def test_rejects_vague_duty_openings(self) -> None:
        findings = bullet_text_findings(
            "Worked on a Flutter application using Riverpod and Dio.", POLICY
        )
        self.assertTrue(any("vague duty wording" in finding for finding in findings))

    def test_rejects_overlong_bullets(self) -> None:
        bullet = " ".join(["word"] * 37) + "."
        findings = bullet_text_findings(bullet, POLICY)
        self.assertTrue(any("37 words" in finding for finding in findings))

    def test_rejects_missing_terminal_punctuation_and_generic_style(self) -> None:
        findings = bullet_text_findings(
            "Built a seamless import flow — with retries", POLICY
        )
        self.assertTrue(any("terminal punctuation" in finding for finding in findings))
        self.assertTrue(any("forbidden em dash" in finding for finding in findings))
        self.assertTrue(any("generic wording" in finding for finding in findings))

    def test_parses_inline_and_following_source_comments(self) -> None:
        text = """# Example: resume bullet bank

- Built a typed import pipeline. <!-- src: example-001 -->

- Added rollback-safe deployment checks.
  <!-- src: example-002 -->
  <!-- src: example-003 -->
  <!-- variant concise: Added rollback-safe deployment checks for failed releases. -->

## Not selected

- Lower relevance: example-004
"""
        entries = parse_bullet_bank(text)
        self.assertEqual(2, len(entries))
        self.assertEqual("Built a typed import pipeline.", entries[0]["text"])
        self.assertEqual(["example-001"], entries[0]["sources"])
        self.assertEqual(["example-002", "example-003"], entries[1]["sources"])
        self.assertEqual(
            ["Added rollback-safe deployment checks for failed releases."],
            entries[1]["variants"],
        )

    def test_evidence_index_refuses_an_invalid_bank(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ekb-bullet-quality-") as directory:
            bank_dir = Path(directory) / "artifacts" / "bullets"
            bank_dir.mkdir(parents=True)
            (bank_dir / "example.md").write_text(
                "# Example\n\n- Worked on an API.\n  <!-- src: example-001 -->\n",
                encoding="utf-8",
            )
            with self.assertRaises(BulletQualityError):
                collect_curated_bullets(directory)


if __name__ == "__main__":
    unittest.main()
