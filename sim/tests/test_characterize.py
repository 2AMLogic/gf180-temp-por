#!/usr/bin/env python3
"""Unit tests for sim/characterize.py (`make characterize`'s driver, #292).

No PDK and no ngspice required -- these only exercise discovery, argument
handling, and the --list dry-run path, never a real ngspice invocation.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

import characterize  # noqa: E402
from harness import cliutil  # noqa: E402


class ExperimentDiscoveryTests(unittest.TestCase):
    def test_experiments_matches_run_corners_and_run_mc_discovery(self):
        """characterize.experiments() must partition the same set discover()
        returns, with the mc/grid split matching each testbench's own 'mc' key
        -- two independent driver scripts silently diverging on what "every
        experiment" means would be exactly the kind of gap #292 exists to
        close."""
        found = characterize.experiments()
        self.assertGreater(len(found), 0)

        slugs = {d.name for d, _ in found}
        self.assertIn("smoke-bias", slugs)
        self.assertIn("por-vth", slugs)

        mc_slugs = {d.name for d, mc in found if mc}
        self.assertEqual(mc_slugs, {"por-threshold-mc", "temp-accuracy-mc"})

        # testbench-postlayout/ re-runs are deliberately out of scope (module
        # docstring) -- discover() only walks testbench/, so no slug here
        # should ever resolve to a postlayout manifest.
        for directory, _ in found:
            self.assertTrue((directory / "testbench" / "tb.json").is_file())

    def test_list_mode_exits_zero_and_names_every_experiment(self):
        proc = subprocess.run(
            [sys.executable, str(SIM_DIR / "characterize.py"), "--list"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, cliutil.EXIT_OK, proc.stdout + proc.stderr)
        for directory, _ in characterize.experiments():
            self.assertIn(directory.name, proc.stdout)

    def test_only_restricts_to_the_named_slug(self):
        proc = subprocess.run(
            [sys.executable, str(SIM_DIR / "characterize.py"), "--list", "--only", "smoke-bias"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, cliutil.EXIT_OK, proc.stdout + proc.stderr)
        self.assertIn("smoke-bias", proc.stdout)
        self.assertNotIn("por-vth", proc.stdout)

    def test_unknown_only_slug_is_an_environment_error(self):
        proc = subprocess.run(
            [sys.executable, str(SIM_DIR / "characterize.py"), "--list", "--only", "not-a-real-experiment"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, cliutil.EXIT_ENVIRONMENT, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
