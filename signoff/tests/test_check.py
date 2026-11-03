#!/usr/bin/env python3
"""Tests for signoff/check.py's freshness gates (supply ERC, anchored items 1/2/9/10).

No klt/PDK needed.

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


import inventories  # noqa: E402

COPY_PATHS = [
    "design",
    "layout/cells",
    "layout/build_cells.py",
    "sim/pdk.json",
    "sim/harness/README.md",
    "sim/por-iq/analyze_por_iq.py",
    "sim/temp-accuracy-vt/analyze_derived.py",
    "README.md",
    "LICENSE",
    "spec/target-spec.md",
    ".github/workflows/ci.yml",
    "layout/reports/temp_por_top/stats.json",
    "signoff/block-manifest.json",
    "signoff/evidence",
]


def populate(tmp: Path) -> None:
    """A disposable copy of every file the anchored-evidence audit reads."""
    for rel in COPY_PATHS:
        src, dst = REPO_ROOT / rel, tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    for sim_dir in (REPO_ROOT / "sim").iterdir():
        if not sim_dir.is_dir():
            continue
        (tmp / "sim" / sim_dir.name).mkdir(parents=True, exist_ok=True)
        for sub in ("testbench", "testbench-postlayout"):
            if (sim_dir / sub).is_dir():
                shutil.copytree(sim_dir / sub, tmp / "sim" / sim_dir.name / sub)


class AnchoredEvidenceTest(unittest.TestCase):
    """Items 1, 2, 9, 10: a bound artifact edited without refreshing fails."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        populate(self.tmp)

    def run_check(self) -> tuple[bool, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ok = check.check_anchored_evidence(self.tmp)
        return ok, err.getvalue()

    def assert_fails(self, *needles):
        ok, err = self.run_check()
        self.assertFalse(ok, err)
        for needle in needles:
            self.assertIn(needle, err)

    def edit_json(self, rel, fn):
        path = self.tmp / rel
        data = json.loads(path.read_text())
        fn(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def test_committed_tree_passes(self):
        self.assertTrue(check.check_anchored_evidence())

    def test_copy_passes(self):
        ok, err = self.run_check()
        self.assertTrue(ok, err)

    def test_every_anchored_item_cites_generic_not_native(self):
        manifest = json.loads((REPO_ROOT / "signoff/block-manifest.json").read_text())
        for item, rel in inventories.ITEM_ENVELOPES.items():
            self.assertEqual(manifest["evidence"][str(item)]["file"], rel)
            envelope = json.loads((REPO_ROOT / rel).read_text())
            self.assertEqual(envelope["kind"], "generic")
            self.assertEqual(envelope["t1_item"], item)
            self.assertEqual(
                envelope["provenance"]["input"]["path"],
                {"path": envelope["source"], "scope": "repo"},
            )

    # --- member drift: inventory bytes unchanged, a described file moved ---
    def test_schematic_edit_fails(self):
        with (self.tmp / "design/bias_core.sch").open("a") as f:
            f.write("\n")
        self.assert_fails("design/bias_core.sch", "changed since it was inventoried")

    def test_netlist_delete_fails(self):
        (self.tmp / "design/netlist/temp_core.spice").unlink()
        self.assert_fails("temp_core", "disagree")

    def test_new_schematic_fails(self):
        shutil.copy(self.tmp / "design/bias_core.sch", self.tmp / "design/extra.sch")
        self.assert_fails("extra", "disagree")

    def test_testbench_edit_fails(self):
        tb = next((self.tmp / "sim/por-vth/testbench").glob("*.spice"))
        with tb.open("a") as f:
            f.write("* edit\n")
        self.assert_fails("changed since it was inventoried")

    def test_testbench_delete_fails(self):
        next((self.tmp / "sim/por-vth/testbench").glob("*.spice")).unlink()
        self.assert_fails("no longer in the tree")

    def test_new_testbench_file_fails(self):
        (self.tmp / "sim/por-vth/testbench/new.spice").write_text("* new\n")
        self.assert_fails("sim/por-vth/testbench/new.spice", "absent from the inventory")

    def test_new_unclassified_experiment_fails(self):
        new = self.tmp / "sim/brand-new/testbench"
        new.mkdir(parents=True)
        (new / "tb.json").write_text("{}")
        self.assert_fails("absent from the inventory")

    def test_experiment_without_testbench_must_be_classified(self):
        (self.tmp / "sim/unclassified").mkdir()
        self.assert_fails("NO_TESTBENCH_DIRS")

    def test_measured_row_without_testbench_fails(self):
        shutil.rmtree(self.tmp / "sim/por-ramp-rate")
        self.assert_fails("por-ramp-rate", "committed testbench")

    def test_unclassified_spec_row_fails(self):
        spec = self.tmp / "spec/target-spec.md"
        spec.write_text(spec.read_text() + '\n| <a id="brand-new-row"></a>`brand-new-row` |\n')
        self.assert_fails("brand-new-row")

    def test_pdk_pin_removed_fails(self):
        ci = self.tmp / ".github/workflows/ci.yml"
        ci.write_text(ci.read_text().replace("volare enable --pdk gf180mcu", "volare enable"))
        self.assert_fails("volare")

    def test_hygiene_member_edit_fails(self):
        with (self.tmp / "README.md").open("a") as f:
            f.write("\nmore\n")
        self.assert_fails("README.md", "changed since it was inventoried")

    def test_license_replaced_fails(self):
        (self.tmp / "LICENSE").write_text("proprietary\n")
        self.assert_fails("Apache")

    # --- item 2: bound directly to the GDS ---
    def test_gds_change_fails(self):
        with (self.tmp / inventories.GDS_TOP).open("ab") as f:
            f.write(b"\0")
        self.assert_fails("pins", "stale")

    def test_new_gds_cell_fails(self):
        shutil.copy(self.tmp / "layout/cells/bias_core.gds", self.tmp / "layout/cells/extra.gds")
        self.assert_fails("differs from the envelope derived from the tree")

    def test_missing_artifact_fails(self):
        (self.tmp / inventories.ITEM_ARTIFACTS[9]).unlink()
        self.assert_fails("bound artifact is missing")

    # --- citation plumbing ---
    def test_missing_manifest_pin_fails(self):
        self.edit_json("signoff/block-manifest.json", lambda m: m["evidence"]["1"].pop("content_hash"))
        self.assert_fails("manifest item 1")

    def test_missing_manifest_citation_fails(self):
        self.edit_json("signoff/block-manifest.json", lambda m: m["evidence"].pop("10"))
        self.assert_fails("manifest item 10")

    def test_stale_manifest_hash_fails(self):
        self.edit_json(
            "signoff/block-manifest.json",
            lambda m: m["evidence"]["9"].update(content_hash="sha256:" + "0" * 64),
        )
        self.assert_fails("pins sha256:" + "0" * 8)

    def test_stale_envelope_hash_fails(self):
        self.edit_json(
            "signoff/evidence/t1-item-1-design-sources.json",
            lambda e: e["provenance"]["input"].update(content_hash="sha256:" + "0" * 64),
        )
        self.assert_fails("provenance.input.content_hash is stale")

    def test_wrong_t1_item_fails(self):
        self.edit_json("signoff/evidence/t1-item-9-testbenches.json", lambda e: e.update(t1_item=10))
        self.assert_fails("t1_item is 10, expected 9")

    def test_string_t1_item_fails(self):
        self.edit_json("signoff/evidence/t1-item-9-testbenches.json", lambda e: e.update(t1_item="9"))
        self.assert_fails("t1_item")

    def test_source_and_input_path_mismatch_fails(self):
        self.edit_json(
            "signoff/evidence/t1-item-10-repo-hygiene.json",
            lambda e: e["provenance"]["input"].update(path={"path": "README.md", "scope": "repo"}),
        )
        self.assert_fails("same artifact")

    def test_native_kind_fails(self):
        self.edit_json("signoff/evidence/t1-item-2-layout.json", lambda e: e.update(kind="drc"))
        self.assert_fails("kind must be 'generic'")

    def test_hand_edited_summary_fails(self):
        self.edit_json(
            "signoff/evidence/t1-item-9-testbenches.json",
            lambda e: e.update(summary=e["summary"] + " Everything passes."),
        )
        self.assert_fails("differs from the envelope derived from the tree")


class RegenTest(unittest.TestCase):
    def test_regen_is_idempotent_and_refuses_failed_audit(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        populate(tmp)
        before = (tmp / inventories.ITEM_ENVELOPES[9]).read_text()
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertTrue(check.regen_anchored_evidence(tmp))
        self.assertEqual((tmp / inventories.ITEM_ENVELOPES[9]).read_text(), before)
        # A failed audit writes nothing.
        shutil.rmtree(tmp / "sim/por-ramp-rate")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertFalse(check.regen_anchored_evidence(tmp))
        self.assertEqual((tmp / inventories.ITEM_ENVELOPES[9]).read_text(), before)
        self.assertIn("audit failed", err.getvalue())


class CitationHashDriftTest(unittest.TestCase):
    """Same verdicts, stale cited hash: check_drift must still fail."""

    @staticmethod
    def report(digest: str) -> dict:
        return {
            "block": "b", "kind": "k", "tier": None,
            "t1_item_count": 1, "t1_met_count": 1,
            "items": [{
                "tier": "T1", "id": 10, "partition": None,
                "status": "met", "reason": None,
                "citation": {
                    "content_hash": digest,
                    "artifact_binding": {"content_hash": digest},
                },
            }],
        }

    def run_drift(self, committed: dict, graded: dict):
        tmp = Path(tempfile.mkdtemp(dir=REPO_ROOT))
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "tier-report.json"
        path.write_text(json.dumps(committed))
        err = io.StringIO()
        saved = check.REPORT
        check.REPORT = path
        self.addCleanup(setattr, check, "REPORT", saved)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            ok = check.check_drift(graded)
        return ok, err.getvalue()

    def test_stale_citation_hash_fails(self):
        ok, err = self.run_drift(self.report("sha256:aa"), self.report("sha256:bb"))
        self.assertFalse(ok)
        self.assertIn("sha256:aa", err)
        self.assertIn("--regen", err)

    def test_matching_hashes_pass(self):
        ok, _ = self.run_drift(self.report("sha256:aa"), self.report("sha256:aa"))
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
