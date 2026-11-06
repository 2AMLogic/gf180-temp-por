#!/usr/bin/env python3
"""Tests for signoff/yield_samples.py. No klt/PDK needed.

    python3 -m unittest discover -s signoff/tests -t signoff/tests
"""

from __future__ import annotations

import re
import statistics
import sys
import unittest
from pathlib import Path

SIGNOFF_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIGNOFF_DIR.parent
sys.path.insert(0, str(SIGNOFF_DIR))

import yield_samples as ys  # noqa: E402


class SampleSetTest(unittest.TestCase):
    def test_temperature_counts_and_matches_record(self):
        doc = ys.build_sample_set("temp-accuracy-mc")
        self.assertEqual(len(doc["measurements"]), 8)  # 2 rows x 4 binding points
        record = (REPO_ROOT / "sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md").read_text()
        for m in doc["measurements"]:
            self.assertEqual(len(m["samples"]), 500, m["name"])
            name, label = m["name"].split("@")
            row = re.search(
                rf"\| `{label}` \| `{name}` \| 500 \| (\S+) \| (\S+) \|.*\| ([\d.]+)% \|", record
            )
            self.assertIsNotNone(row, m["name"])
            self.assertAlmostEqual(statistics.fmean(m["samples"]), float(row[1]), delta=abs(float(row[1])) * 1e-5 + 1e-5)
            self.assertAlmostEqual(statistics.stdev(m["samples"]), float(row[2]), delta=float(row[2]) * 1e-5)
            lo, hi = m["limits"]["min"], m["limits"]["max"]
            inside = sum(lo <= v <= hi for v in m["samples"]) / 500 * 100
            self.assertAlmostEqual(inside, float(row[3]), places=2)

    def test_por_rows_and_limits(self):
        doc = ys.build_sample_set("por-threshold-mc")
        self.assertEqual(len(doc["measurements"]), 15)  # 3 rows x 5 binding points
        self.assertEqual({m["spec_row"] for m in doc["measurements"]}, {"por-vth-rise", "por-vth-fall", "por-hysteresis"})
        for m in doc["measurements"]:
            self.assertEqual(len(m["samples"]), 500)
            self.assertEqual(m["limits"]["target_yield"], ys.TARGET_YIELD)

    def test_committed_sample_sets_are_current(self):
        for experiment in ys.CAMPAIGNS:
            self.assertEqual(ys.out_path(experiment).read_text(), ys.render(ys.build_sample_set(experiment)))


if __name__ == "__main__":
    unittest.main()
