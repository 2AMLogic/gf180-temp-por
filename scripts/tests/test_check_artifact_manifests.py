"""Unit tests for scripts/check_artifact_manifests.py (no broker, no klt)."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_artifact_manifests as chk  # noqa: E402

BODY = b"* ngspice log\nvout = 1.23\n"
SHA = hashlib.sha256(BODY).hexdigest()


def entry(**kw):
    e = {
        "sha256": SHA, "size": len(BODY), "kind": "evidence", "name": "x/y.log",
        "uri": f"artifact:evidence/owner__repo/{SHA[:2]}/{SHA}",
    }
    e.update(kw)
    return e


class CheckArtifactManifests(unittest.TestCase):
    def repo(self, tmp, entries, extra=None):
        root = Path(tmp)
        d = root / chk.MANIFEST_DIR
        d.mkdir(parents=True)
        (d / "bench-run.manifest.json").write_text(
            json.dumps({"schema_version": 1, "entries": entries})
        )
        for name, data in (extra or {}).items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(data)
        return root

    def test_clean_manifest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp, [entry()], {"sim/a.md": b"summary\n"})
            self.assertEqual(chk.check(root), [])

    def test_no_manifests_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(chk.check(Path(tmp)), [])

    def test_non_artifact_uri_fails(self):
        for uri in ("https://example.invalid/x", "s3://bucket/key", "file:/x", ""):
            with self.subTest(uri=uri), tempfile.TemporaryDirectory() as tmp:
                root = self.repo(tmp, [entry(uri=uri)])
                self.assertTrue(any("uri" in e or "storage" in e for e in chk.check(root)))

    def test_storage_location_string_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp, [entry(name="arn:aws:s3:::b/k")])
            self.assertTrue(any("storage location" in e for e in chk.check(root)))

    def test_bad_schema_fails(self):
        cases = [entry(sha256="XYZ"), entry(size=-1), entry(size="3"), entry(name="")]
        for bad in cases:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                self.assertTrue(chk.check(self.repo(tmp, [bad])))

    def test_committed_bytes_of_stored_object_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp, [entry()], {"sim/x/corners/r/tt.log": BODY})
            errors = chk.check(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("sim/x/corners/r/tt.log", errors[0])

    def test_same_size_different_bytes_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = bytes(reversed(BODY))
            root = self.repo(tmp, [entry()], {"sim/other.log": other})
            self.assertEqual(chk.check(root), [])

    def test_manifest_dir_itself_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp, [entry()], {"manifests/copy.log": BODY})
            self.assertEqual(chk.check(root), [])

    def test_this_repository_is_clean(self):
        self.assertEqual(chk.check(Path(chk.__file__).resolve().parent.parent), [])


if __name__ == "__main__":
    unittest.main()
