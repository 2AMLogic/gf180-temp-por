"""Fail-closed behaviour of the artifact-store evidence writer (DR-030)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import cliutil, evidence_store as es, report  # noqa: E402

URI = "artifact:evidence/owner__repo/ab/" + "ab" * 32


def fake_put(fail_on=None):
    """A stand-in for ``klt artifact put`` that appends to the --manifest file."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "--help":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        name = cmd[cmd.index("--name") + 1]
        if fail_on and fail_on in name:
            return subprocess.CompletedProcess(cmd, 1, "", "broker unreachable")
        path = Path(cmd[cmd.index("--manifest") + 1])
        doc = json.loads(path.read_text()) if path.exists() else {"schema_version": 1, "entries": []}
        doc["entries"].append({"sha256": "ab" * 32, "size": 1, "name": name, "uri": URI})
        path.write_text(json.dumps(doc, indent=2))
        return subprocess.CompletedProcess(cmd, 0, "stored", "")

    run.calls = calls
    return run


class PreflightTests(unittest.TestCase):
    def test_broker_unset_refuses(self):
        with self.assertRaisesRegex(es.EvidenceStoreError, "KLT_ARTIFACT_BROKER"):
            es.preflight(env={}, run=fake_put())

    def test_klt_without_artifact_put_refuses(self):
        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 2, "", "invalid choice")

        with self.assertRaisesRegex(es.EvidenceStoreError, "artifact put"):
            es.preflight(klt=sys.executable, env={es.BROKER_ENV: "x"}, run=run)

    def test_ok(self):
        es.preflight(klt=sys.executable, env={es.BROKER_ENV: "x"}, run=fake_put())


class PublishTests(unittest.TestCase):
    def stage(self, tmp):
        root = Path(tmp) / "repo"
        stage = Path(tmp) / "work" / "stage" / "exp" / "rid"
        (stage / "corners").mkdir(parents=True)
        (stage / "corners" / "tt.log").write_text("a")
        (stage / "corners" / "ss.log").write_text("b")
        root.mkdir()
        return root, stage

    def test_installs_manifest_of_artifact_uris(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, stage = self.stage(tmp)
            path = es.publish(stage, root, "exp", "rid", run=fake_put())
            self.assertEqual(path, root / "manifests/artifacts/exp-rid.manifest.json")
            entries = json.loads(path.read_text())["entries"]
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(e["uri"].startswith("artifact:") for e in entries))
            self.assertTrue(entries[0]["name"].startswith("exp/rid/corners/"))

    def test_partial_put_installs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, stage = self.stage(tmp)
            with self.assertRaisesRegex(es.EvidenceStoreError, "nothing recorded"):
                es.publish(stage, root, "exp", "rid", run=fake_put(fail_on="tt.log"))
            self.assertFalse((root / "manifests").exists())

    def test_non_artifact_uri_from_klt_is_not_installed(self):
        def run(cmd, **kw):
            Path(cmd[cmd.index("--manifest") + 1]).write_text(
                json.dumps({"schema_version": 1, "entries": [{"uri": "https://x/y"}]})
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            root, stage = self.stage(tmp)
            with self.assertRaises(es.EvidenceStoreError):
                es.publish(stage, root, "exp", "rid", run=run)
            self.assertFalse((root / "manifests").exists())

    def test_empty_stage_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "s"
            empty.mkdir()
            with self.assertRaises(es.EvidenceStoreError):
                es.publish(empty, Path(tmp), "exp", "rid", run=fake_put())


class ProvisionTests(unittest.TestCase):
    def test_broker_unset_leaves_tree_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "exp"
            (experiment / report.RECORDS_DIR).mkdir(parents=True)
            work = Path(tmp) / "work"
            with mock.patch.dict("os.environ", {}, clear=False) as env:
                env.pop(es.BROKER_ENV, None)
                with self.assertRaises(es.EvidenceStoreError):
                    cliutil.provision_record(
                        SIM_DIR, work, experiment / report.RECORDS_DIR, experiment,
                        "exp", False, stage=True,
                    )
            self.assertFalse((experiment / report.CORNERS_DIR).exists())
            self.assertFalse(work.exists())
            self.assertEqual(list(experiment.rglob("*.md")), [])

    def test_staged_run_reserves_nothing_in_tracked_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "exp"
            (experiment / report.RECORDS_DIR).mkdir(parents=True)
            work = Path(tmp) / "work"
            with mock.patch.object(es, "preflight"):
                a = cliutil.provision_record(
                    SIM_DIR, work, experiment / report.RECORDS_DIR, experiment, "exp", False, stage=True)
                b = cliutil.provision_record(
                    SIM_DIR, work, experiment / report.RECORDS_DIR, experiment, "exp", False, stage=True)
            self.assertNotEqual(a[0], b[0])
            self.assertTrue(a[2].is_dir() and a[2].name == es.STAGE_CORNERS)
            self.assertTrue(str(a[2]).startswith(str(work)))
            self.assertFalse((experiment / report.CORNERS_DIR).exists())


if __name__ == "__main__":
    unittest.main()
