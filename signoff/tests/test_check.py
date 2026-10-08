#!/usr/bin/env python3
"""Tests for signoff/check.py's supply-ERC freshness gate. No klt/PDK needed.

    python3 -m unittest discover -s signoff/tests -t signoff/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SIGNOFF_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIGNOFF_DIR.parent
sys.path.insert(0, str(SIGNOFF_DIR))

import check  # noqa: E402

GDS = "layout/cells/temp_por_top.gds"
SPEC = "layout/cells/temp_por_top.erc-supply-spec.json"
REPORT = "layout/reports/temp_por_top/erc_supply.json"
MANIFEST = "signoff/block-manifest.json"


class ErcFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for rel in (GDS, SPEC, REPORT, MANIFEST):
            dst = self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / rel, dst)

    def run_check(self) -> tuple[bool, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ok = check.check_erc_supply_freshness(self.tmp)
        return ok, err.getvalue()

    def edit_report(self, fn):
        path = self.tmp / REPORT
        data = json.loads(path.read_text())
        fn(data)
        path.write_text(json.dumps(data))

    def test_unchanged_passes(self):
        self.assertEqual(self.run_check()[0], True)

    def test_committed_tree_passes(self):
        self.assertTrue(check.check_erc_supply_freshness())

    def test_spec_mutation_fails(self):
        with (self.tmp / SPEC).open("a") as f:
            f.write("\n")
        ok, err = self.run_check()
        self.assertFalse(ok)
        self.assertIn("supply spec", err)

    def test_gds_change_fails(self):
        with (self.tmp / GDS).open("ab") as f:
            f.write(b"\0")
        ok, err = self.run_check()
        self.assertFalse(ok)
        self.assertIn("GDS", err)

    def test_envelope_gds_hash_mutation_fails(self):
        self.edit_report(
            lambda d: d["provenance"]["input"].update(content_hash="sha256:" + "0" * 64)
        )
        self.assertFalse(self.run_check()[0])

    def test_missing_recorded_hash_fails(self):
        self.edit_report(lambda d: d["provenance"]["spec"].pop("content_hash"))
        ok, err = self.run_check()
        self.assertFalse(ok)
        self.assertIn("provenance.spec.content_hash", err)

    def test_missing_input_fails(self):
        (self.tmp / SPEC).unlink()
        ok, err = self.run_check()
        self.assertFalse(ok)
        self.assertIn("missing or unreadable", err)

    def test_missing_report_fails(self):
        (self.tmp / REPORT).unlink()
        ok, err = self.run_check()
        self.assertFalse(ok)
        self.assertIn("unreadable", err)


if __name__ == "__main__":
    unittest.main()
