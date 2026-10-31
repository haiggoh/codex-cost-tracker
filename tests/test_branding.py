#!/usr/bin/env python3
"""Branding (rollout Task 17): the About mark 💸 leads the README h1 and the SKILL.md
invocation section; the README notes the deliberate 💸 share with cost-tracker.

Usage: python3 tests/test_branding.py [-v]
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class BrandingTests(unittest.TestCase):
    def test_readme_h1_exact(self):
        first = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, "# 💸 Codex Cost Tracker")

    def test_readme_notes_the_shared_mark(self):
        # 💸 is shared with cost-tracker by design — different runtimes, no collision
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("shares 💸 with cost-tracker", text)

    def test_skill_branding_section(self):
        text = (ROOT / "skills" / "codex-cost" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Branding (💸)", text)

    def test_plugin_description_leads_with_mark(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["description"].startswith("💸 "), manifest["description"][:40])


if __name__ == "__main__":
    unittest.main()
