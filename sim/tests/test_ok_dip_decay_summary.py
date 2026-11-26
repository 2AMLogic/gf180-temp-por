#!/usr/bin/env python3
"""Summary-derivation tests for the `ok_bo_dip_mv` decay control (#679).

No PDK, no ngspice: these parse the four ngspice logs committed under
``sim/bias-core-startup/control/logs/`` and exercise the generator's
summary against them. Issue #679 exists because that summary asserted
conclusions no sample supported -- a crossing time the window never
contains, a 9.02x figure called a time constant, and a tt/+27 C magnitude
claim contradicted by the schematic's own -7.668 mV reading. The summary is
now derived from the same samples the tables print, so these tests pin:

  * the tables reproduce the committed logs exactly (EXPECTED_TABLES is the
    committed block, transcribed from the logs at verification time -- if a
    re-run of the control changes the logs, this fixture must be refreshed
    in the same commit, on purpose);
  * every number the summary quotes traces to a committed log line;
  * a non-monotonic extracted curve produces a summary that reports that
    result instead of the monotonic wording;
  * the summary identifies the first sample at or below the schematic level.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

CONTROL_DIR = SIM_DIR / "bias-core-startup" / "control"
LOGS_DIR = CONTROL_DIR / "logs"

# The control script is a script, not a module -- load it by path, the same
# way test_control_shared_helpers.py loads its controls.
_spec = importlib.util.spec_from_file_location(
    "run_ok_dip_decay", CONTROL_DIR / "run_ok_dip_decay.py"
)
dip = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dip)

#: The measurement-table block of `dip_results.md` as committed at the
#: verification of #679: every cell transcribed from the four logs under
#: `logs/` (e.g. `m_ok350 = 3.3633580000e-02` -> "33.63 mV"). Regenerating
#: the report from those logs must reproduce it byte for byte.
EXPECTED_TABLES = """## V(BIAS_OK) with the rail held at 0 V

`t - 33 ms` is time since the rail reached 0 V. The row marked **parent** is the
instant `ok_bo_dip_mv` samples; the parent testbench's window ends at
36 ms and everything below that row is outside it.

### ss / -40 C  (the failing family)

| t | t − 33 ms | schematic export | klt-extracted | ratio |
| ---: | ---: | ---: | ---: | ---: |
| 33.5 ms | 0.5 ms | 53.56 mV | 327.8 mV | 6.12x |
| 34 ms | 1 ms | 45.64 mV | 317.6 mV | 6.96x |
| 35 ms **(parent)** | 2 ms | 33.63 mV | 303.4 mV | 9.02x |
| 36 ms | 3 ms | 25.6 mV | 291.7 mV | 11.4x |
| 38 ms | 5 ms | 16 mV | 270.9 mV | 16.9x |
| 40 ms | 7 ms | 10.81 mV | 252.1 mV | 23.3x |
| 45 ms | 12 ms | 5.356 mV | 210.8 mV | 39.4x |
| 50 ms | 17 ms | 3.554 mV | 176.4 mV | 49.6x |

V(VREF) on the same DUT over the same window, as the control that the *core* is discharging the same way on both netlists:

| t | schematic export | klt-extracted |
| ---: | ---: | ---: |
| 33.5 ms | 0.53176 V | 0.53036 V |
| 34 ms | 0.52643 V | 0.5259 V |
| 35 ms | 0.51838 V | 0.51888 V |
| 36 ms | 0.51228 V | 0.51341 V |
| 38 ms | 0.5031 V | 0.50499 V |
| 40 ms | 0.49609 V | 0.49848 V |
| 45 ms | 0.48304 V | 0.48628 V |
| 50 ms | 0.47313 V | 0.47701 V |

### tt / +27 C  (reference)

| t | t − 33 ms | schematic export | klt-extracted | ratio |
| ---: | ---: | ---: | ---: | ---: |
| 33.5 ms | 0.5 ms | -27.56 mV | -0.7336 mV | 0.0266x |
| 34 ms | 1 ms | -17.09 mV | -0.1594 mV | 0.00933x |
| 35 ms **(parent)** | 2 ms | -7.668 mV | -0.03528 mV | 0.0046x |
| 36 ms | 3 ms | -3.764 mV | -0.02831 mV | 0.00752x |
| 38 ms | 5 ms | -1.07 mV | -0.02804 mV | 0.0262x |
| 40 ms | 7 ms | -0.4061 mV | -0.02934 mV | n/a (both < 1 mV) |
| 45 ms | 12 ms | -0.17 mV | -0.03435 mV | n/a (both < 1 mV) |
| 50 ms | 17 ms | -0.15 mV | -0.0406 mV | n/a (both < 1 mV) |

V(VREF) on the same DUT over the same window, as the control that the *core* is discharging the same way on both netlists:

| t | schematic export | klt-extracted |
| ---: | ---: | ---: |
| 33.5 ms | 0.21779 V | 0.24372 V |
| 34 ms | 0.21046 V | 0.23386 V |
| 35 ms | 0.20453 V | 0.22518 V |
| 36 ms | 0.20122 V | 0.21999 V |
| 38 ms | 0.19644 V | 0.21262 V |
| 40 ms | 0.19257 V | 0.20701 V |
| 45 ms | 0.18471 V | 0.19661 V |
| 50 ms | 0.17838 V | 0.18895 V |
"""

#: A provenance stub for calling report_text() without a toolchain: the
#: tables and summary must not depend on it, only carry it through.
PROVENANCE_STUB = "ngspice: stub · PDK: stub · harness stub"


def _log_value(log: str, name: str) -> float:
    """One `m_<name> = <value>` line of a committed log, parsed by a regex
    written here rather than by the module under test."""
    text = (LOGS_DIR / f"{log}.log").read_text()
    match = re.search(rf"^m_{name} = (\S+)\s*$", text, re.MULTILINE)
    assert match, f"no m_{name} line in {log}.log"
    return float(match.group(1))


def _committed() -> tuple[dict, str, str]:
    """(results, full report, summary section) from the committed logs."""
    results = dip.load_results_from_logs()
    if results is None:
        raise FileNotFoundError(
            "the committed dip-*.log set under "
            "sim/bias-core-startup/control/logs/ is incomplete -- a re-run of "
            "the control must refresh the logs, the report and "
            "EXPECTED_TABLES together"
        )
    report = dip.report_text(results, PROVENANCE_STUB)
    return results, report, report[report.index("## What this settles"):]


class CommittedLogsTests(unittest.TestCase):
    """The four committed logs, through the generator, reproduce the report."""

    def setUp(self):
        self.results, self.report, self.summary = _committed()

    def test_load_results_from_logs_reads_all_four_logs_completely(self):
        self.assertEqual(
            sorted(self.results),
            sorted(
                [
                    ("schematic", "ss", -40.0),
                    ("extracted", "ss", -40.0),
                    ("schematic", "tt", 27.0),
                    ("extracted", "tt", 27.0),
                ]
            ),
        )
        for values in self.results.values():
            for ms in dip.SAMPLE_MS:
                self.assertIn(f"ok{dip._tag(ms)}", values)
                self.assertIn(f"vr{dip._tag(ms)}", values)

    def test_loader_matches_an_independent_parse_of_the_log_lines(self):
        # One spot value per committed log, parsed by _log_value's own regex.
        self.assertAlmostEqual(
            self.results[("schematic", "ss", -40.0)]["ok350"],
            _log_value("dip-schematic-ss_-40c", "ok350"),
        )
        self.assertAlmostEqual(
            self.results[("extracted", "ss", -40.0)]["ok500"],
            _log_value("dip-extracted-ss_-40c", "ok500"),
        )
        self.assertAlmostEqual(
            self.results[("schematic", "tt", 27.0)]["ok350"],
            _log_value("dip-schematic-tt_27c", "ok350"),
        )
        self.assertAlmostEqual(
            self.results[("extracted", "tt", 27.0)]["vr500"],
            _log_value("dip-extracted-tt_27c", "vr500"),
        )

    def test_measurement_tables_reproduce_exactly(self):
        self.assertIn(EXPECTED_TABLES, self.report)

    def test_committed_report_is_what_the_generator_produces_from_the_logs(self):
        # With the preserved provenance line -- the one describing the run
        # that minted the logs -- the generator's output is byte-identical
        # to the committed report: the file is generated, not hand-edited.
        provenance = dip.preserved_provenance()
        self.assertIsNotNone(provenance)
        self.assertEqual(
            dip.report_text(self.results, provenance),
            (CONTROL_DIR / "dip_results.md").read_text(),
        )

    def test_report_carries_the_provenance_line_through(self):
        self.assertIn(PROVENANCE_STUB, self.report)

    def test_report_only_preserves_the_provenance_of_the_run_that_minted_the_logs(self):
        line = dip.preserved_provenance()
        self.assertIsNotNone(line)
        self.assertRegex(line, r"^ngspice: .+ · PDK: .+ · harness ")


class SummaryFromCommittedSamplesTests(unittest.TestCase):
    """Every claim the summary makes is an observation the logs contain."""

    def setUp(self):
        _results, _report, self.summary = _committed()

    def test_monotonic_discharge_with_measured_endpoints(self):
        # 327.8 mV and 176.4 mV: m_ok335 / m_ok500 of dip-extracted-ss_-40c.log
        self.assertIn("monotonically falling across all 8 samples", self.summary)
        self.assertIn("from 327.8 mV at +0.5 ms to 176.4 mV at +17 ms", self.summary)

    def test_all_extracted_samples_are_above_the_schematic_reference(self):
        self.assertIn(
            "Every extracted sample through +17 ms is above the schematic "
            "+2 ms reference of 33.63 mV", self.summary
        )
        self.assertNotIn("does not reach", self.summary)

    def test_the_902_figure_is_labeled_a_voltage_ratio_at_the_instant(self):
        # 33.63 mV / 303.4 mV: m_ok350 of both ss_-40c logs; 9.02 = 303.4/33.63.
        self.assertIn("33.63 mV", self.summary)
        self.assertIn("303.4 mV", self.summary)
        self.assertIn("a voltage ratio of 9.02 at that instant", self.summary)
        self.assertNotIn("time constant", self.summary)
        self.assertNotIn("longer time", self.summary)

    def test_vref_gap_and_bias_ok_difference_are_the_committed_ones(self):
        self.assertIn("3.886 mV at +17 ms (ss/-40 C)", self.summary)
        self.assertIn("25.93 mV at +0.5 ms (tt/+27 C)", self.summary)
        self.assertIn(
            "At ss/-40 C and +2 ms, the differences are 0.5024 mV for V(VREF) "
            "and 269.8 mV for `BIAS_OK`", self.summary
        )

    def test_removed_claims_stay_removed(self):
        self.assertNotIn("sub-millivolt", self.summary)
        self.assertNotIn("parasitic RC", self.summary)
        self.assertNotIn("essentially the same rate", self.summary)
        self.assertNotIn("not a held stale valid", self.summary)


class ModifiedSamplesTests(unittest.TestCase):
    """A summary computed from samples must report what the samples say."""

    def setUp(self):
        self.results = dip.load_results_from_logs()
        if self.results is None:
            raise FileNotFoundError(
                "the committed dip-*.log set under "
                "sim/bias-core-startup/control/logs/ is incomplete"
            )

    def _summary(self) -> str:
        return "\n".join(dip.summary_lines(self.results))

    def test_a_rising_step_flips_the_monotonic_wording(self):
        # ok400 (the +7 ms sample) lifted above ok380 (+5 ms): non-monotonic.
        self.results[("extracted", "ss", -40.0)]["ok400"] = 0.29
        summary = self._summary()
        self.assertIn("8 extracted samples do not show a monotonic discharge", summary)
        self.assertIn("do not settle the stuck-vs-discharge question", summary)
        self.assertNotIn("monotonically falling across all 8 samples", summary)
        self.assertNotIn("**The extracted node is not stuck.**", summary)

    def test_non_monotonic_input_keeps_the_other_observations(self):
        self.results[("extracted", "ss", -40.0)]["ok400"] = 0.29
        summary = self._summary()
        self.assertIn("Every extracted sample through +17 ms is above", summary)
        self.assertIn("25.93 mV at +0.5 ms (tt/+27 C)", summary)

    def test_first_sample_at_or_below_the_reference(self):
        values = self.results[("extracted", "ss", -40.0)]
        reference = self.results[("schematic", "ss", -40.0)]["ok350"]
        values["ok500"] = 0.01  # A later sample also qualifies.
        for value, label in [(0.02, "20 mV"), (reference, "33.63 mV")]:
            with self.subTest(value=value):
                values["ok450"] = value
                summary = self._summary()
                self.assertIn(
                    "The first extracted sample at or below the schematic +2 ms "
                    f"reference is {label} at +12 ms", summary
                )
                self.assertNotIn("first reaches", summary)

    def test_flat_samples_report_no_measurable_fall(self):
        values = self.results[("extracted", "ss", -40.0)]
        for ms in dip.SAMPLE_MS:
            values[f"ok{dip._tag(ms)}"] = 0.300
        summary = self._summary()
        self.assertIn("flat across all 8 samples", summary)
        self.assertIn("300 mV at +0.5 ms to 300 mV at +17 ms", summary)
        self.assertNotIn("not stuck", summary)
        self.assertNotIn("monotonically falling", summary)

    def test_vref_peak_time_follows_the_samples(self):
        schematic = self.results[("schematic", "ss", -40.0)]
        self.results[("extracted", "ss", -40.0)]["vr350"] = schematic["vr350"] + 1.0
        summary = self._summary()
        self.assertIn("1000 mV at +2 ms (ss/-40 C)", summary)
        self.assertIn("At ss/-40 C and +2 ms, the differences are 1000 mV", summary)
        self.assertNotIn("core's own discharge is not what moved", summary.lower())

    def test_falling_trace_can_include_equal_neighbors(self):
        values = self.results[("extracted", "ss", -40.0)]
        values["ok500"] = values["ok450"]
        summary = self._summary()
        self.assertIn("monotonically falling across all 8 samples", summary)


if __name__ == "__main__":
    unittest.main()
