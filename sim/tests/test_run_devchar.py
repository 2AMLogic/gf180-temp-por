#!/usr/bin/env python3
"""Unit tests for sim/devchar/run_devchar.py's CsvWriter (#24). No PDK and
no ngspice required -- these exercise the append-time row-count
verification in isolation from the ngspice-driven deck runs.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
DEVCHAR_DIR = SIM_DIR / "devchar"
sys.path.insert(0, str(DEVCHAR_DIR))

import run_devchar as rd  # noqa: E402


def _blank_row(fields: list[str]) -> dict:
    return {f: f"v_{f}" for f in fields}


class CsvWriterVerificationTests(unittest.TestCase):
    """CsvWriter must verify actual on-disk row count against what it
    believes it appended, for every deck that uses it (#24)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    # -- normal / no-false-positive cases -----------------------------

    def test_fresh_file_writes_header_once_and_verifies_clean(self):
        path = self.dir / "pnp_vbe.csv"
        w = rd.CsvWriter(path, rd.PNP_FIELDS)
        for _ in range(10):
            w.write(_blank_row(rd.PNP_FIELDS))
        w.close()  # must not raise
        self.assertEqual(rd._count_data_rows(path), 10)
        self.assertEqual(w.rows_written, 10)
        with open(path, newline="") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header, rd.PNP_FIELDS)

    def test_zero_writes_on_a_fresh_file_does_not_raise(self):
        path = self.dir / "mos_vt_sub.csv"
        w = rd.CsvWriter(path, rd.MOS_FIELDS)
        w.close()
        self.assertEqual(rd._count_data_rows(path), 0)

    def test_normal_append_across_two_runs_matches_expected_total(self):
        """existing rows + new rows = expected total on an already
        populated CSV -- no false positive on the ordinary append case."""
        path = self.dir / "pnp_vbe.csv"

        first = rd.CsvWriter(path, rd.PNP_FIELDS)
        for _ in range(5):
            first.write(_blank_row(rd.PNP_FIELDS))
        first.close()  # must not raise

        second = rd.CsvWriter(path, rd.PNP_FIELDS)
        for _ in range(7):
            second.write(_blank_row(rd.PNP_FIELDS))
        second.close()  # must not raise

        self.assertEqual(rd._count_data_rows(path), 12)
        self.assertEqual(second.rows_written, 7)

    def test_resistor_deck_style_append_verifies_clean(self):
        """Same guarantee for the RES deck's field set/row shape -- proving
        the fix isn't PNP-specific."""
        path = self.dir / "res_tc.csv"
        w = rd.CsvWriter(path, rd.RES_FIELDS)
        for _ in range(8):  # one row per RES_FLAVOR_MAP entry per point
            w.write(_blank_row(rd.RES_FIELDS))
        w.close()
        self.assertEqual(rd._count_data_rows(path), 8)

    # -- mismatch detection --------------------------------------------

    def test_pnp_style_lost_rows_are_detected(self):
        """A write() that silently fails to persist (e.g. truncation/FS
        race) must be caught, not reported as success (issue #24: PNP rows
        went missing from disk while stdout still reported full success)."""
        path = self.dir / "pnp_vbe.csv"
        w = rd.CsvWriter(path, rd.PNP_FIELDS)
        for _ in range(10):  # PNP deck writes 10 rows per corner/temp point
            w.write(_blank_row(rd.PNP_FIELDS))
        w._fh.flush()

        # Simulate rows that were believed written but never actually
        # landed on disk: drop the last 2 whole physical rows out from
        # under the writer before it verifies.
        with open(path, newline="") as fh:
            lines = fh.readlines()
        with open(path, "w", newline="") as fh:
            fh.writelines(lines[:-2])

        with self.assertRaises(rd.CsvWriteVerificationError):
            w.close()

    def test_resistor_deck_style_lost_rows_are_detected(self):
        """Same guard for the RES deck (not just the PNP path that was
        observed) -- the class of failure applies uniformly (#24)."""
        path = self.dir / "res_tc.csv"
        w = rd.CsvWriter(path, rd.RES_FIELDS)
        for _ in range(8):
            w.write(_blank_row(rd.RES_FIELDS))
        w._fh.flush()

        with open(path, newline="") as fh:
            lines = fh.readlines()
        with open(path, "w", newline="") as fh:
            fh.writelines(lines[:-2])

        with self.assertRaises(rd.CsvWriteVerificationError):
            w.close()

    def test_mos_deck_style_extra_rows_from_a_concurrent_writer_are_detected(self):
        """A concurrent appender to the same evidence file (two overlapping
        run_devchar.py invocations) must also be caught -- the check is
        symmetric, not just a lost-write detector."""
        path = self.dir / "mos_vt_sub.csv"
        w = rd.CsvWriter(path, rd.MOS_FIELDS)
        for _ in range(3):
            w.write(_blank_row(rd.MOS_FIELDS))
        w._fh.flush()

        # A second process appends directly to the same file while our
        # writer is still open.
        with open(path, "a", newline="") as extra:
            csv.writer(extra).writerow(["intruder"] * len(rd.MOS_FIELDS))

        with self.assertRaises(rd.CsvWriteVerificationError):
            w.close()

    def test_verification_error_message_names_the_file_and_counts(self):
        path = self.dir / "pnp_vbe.csv"
        w = rd.CsvWriter(path, rd.PNP_FIELDS)
        w.write(_blank_row(rd.PNP_FIELDS))
        w._fh.flush()
        with open(path, "w", newline=""):
            pass  # blow away everything, including the header
        with self.assertRaises(rd.CsvWriteVerificationError) as ctx:
            w.close()
        message = str(ctx.exception)
        self.assertIn("pnp_vbe.csv", message)
        self.assertIn("append-only", message)

    def test_a_verification_failure_does_not_rewrite_prior_rows(self):
        """This is append-time verification only -- close() must not
        retroactively rewrite already-recorded rows even when it raises."""
        path = self.dir / "pnp_vbe.csv"
        first = rd.CsvWriter(path, rd.PNP_FIELDS)
        first.write(_blank_row(rd.PNP_FIELDS))
        first.close()
        before = path.read_text()

        second = rd.CsvWriter(path, rd.PNP_FIELDS)
        second.write(_blank_row(rd.PNP_FIELDS))
        second._fh.flush()
        with open(path, "a", newline="") as extra:
            csv.writer(extra).writerow(["intruder"] * len(rd.PNP_FIELDS))
        with self.assertRaises(rd.CsvWriteVerificationError):
            second.close()

        after = path.read_text()
        self.assertTrue(after.startswith(before))


if __name__ == "__main__":
    unittest.main()
