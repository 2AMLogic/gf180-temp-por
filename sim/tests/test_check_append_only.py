"""Tests for sim/check_append_only.py (#353): temp git repos, no PDK.

Run: python3 -m unittest discover -s sim/tests -t sim/tests -v
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
import check_append_only as cao  # noqa: E402

PROTECTED = ["records/r.md", "corners/c.log", "netlist-snapshots/n.spice"]


class Repo:
    def __init__(self, root):
        self.root = root
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *a):
        subprocess.run(["git", "-C", self.root, *a], check=True,
                       capture_output=True)

    def write(self, rel, text="x\n"):
        p = Path(self.root, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg="c"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)


class CheckAppendOnly(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.r = Repo(self._tmp.name)
        for p in PROTECTED:
            self.r.write("sim/exp/" + p)
        self.r.write("sim/exp/control/logs/l.log")
        self.r.write("sim/devchar/results/d.csv")
        self.r.write("outside.txt")
        self.r.commit("base")
        self.r.git("branch", "base")
        self.r.git("checkout", "-q", "-b", "pr")

    def run_check(self, base="base"):
        return cao.main(["--base", base, "--repo", self.r.root])

    def test_nothing_changed_passes(self):
        self.assertEqual(self.run_check(), 0)

    def test_add_passes_in_each_protected_dir(self):
        for p in PROTECTED:
            self.r.write("sim/exp/" + p.replace(".", "2.", 1))
        self.r.write("sim/newexp/records/new.md")
        self.r.commit()
        self.assertEqual(self.run_check(), 0)

    def test_edit_fails_in_each_protected_dir(self):
        for p in PROTECTED:
            with self.subTest(p=p):
                self.r.git("checkout", "-q", "-B", "pr", "base")
                self.r.write("sim/exp/" + p, "changed\n")
                self.r.commit()
                self.assertEqual(self.run_check(), 1)

    def test_delete_fails_in_each_protected_dir(self):
        for p in PROTECTED:
            with self.subTest(p=p):
                self.r.git("checkout", "-q", "-B", "pr", "base")
                os.remove(Path(self.r.root, "sim/exp", p))
                self.r.commit()
                self.assertEqual(self.run_check(), 1)

    def test_rename_out_of_and_within_fails(self):
        for p in PROTECTED:
            d = p.split("/")[0]
            for dest in ("elsewhere/moved.txt", "sim/exp/%s/sub/moved" % d):
                with self.subTest(p=p, dest=dest):
                    self.r.git("checkout", "-q", "-B", "pr", "base")
                    Path(self.r.root, dest).parent.mkdir(parents=True,
                                                         exist_ok=True)
                    self.r.git("mv", "sim/exp/" + p, dest)
                    self.r.commit()
                    self.assertEqual(self.run_check(), 1)

    def test_mode_change_fails(self):
        self.r.git("update-index", "--chmod=+x", "sim/exp/records/r.md")
        self.r.git("commit", "-q", "-m", "mode")
        self.assertEqual(self.run_check(), 1)

    def test_unprotected_areas_may_change(self):
        self.r.write("sim/exp/control/logs/l.log", "rerun\n")
        self.r.write("sim/devchar/results/d.csv", "more\n")
        self.r.write("outside.txt", "edited\n")
        self.r.commit()
        self.assertEqual(self.run_check(), 0)

    def test_unresolvable_base_exits_2(self):
        self.assertEqual(self.run_check("no-such-ref"), 2)

    def test_base_advanced_after_branch_off_is_not_flagged(self):
        self.r.write("sim/exp/records/pr-only.md")
        self.r.commit("pr work")
        self.r.git("checkout", "-q", "base")
        self.r.write("sim/exp/records/base-new.md")
        self.r.write("sim/exp/corners/base-new.log")
        self.r.commit("base advanced")
        self.r.git("checkout", "-q", "pr")
        self.assertEqual(self.run_check(), 0)

    def test_failure_names_file_and_readme_section(self):
        self.r.write("sim/exp/records/r.md", "typo fix\n")
        self.r.commit()
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.run_check(), 1)
        self.assertIn("sim/exp/records/r.md", err.getvalue())
        self.assertIn("Append-only rule", err.getvalue())


if __name__ == "__main__":
    unittest.main()
