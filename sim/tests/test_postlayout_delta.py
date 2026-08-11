#!/usr/bin/env python3
"""Unit tests for sim/postlayout_delta.py (#83). No PDK, no ngspice.

The load-bearing property is the regression verdict: a check that PASSES on
the schematic-level record and FAILS on the post-layout one has to be
reported as `ok -> MISS`, because CLAUDE.md says such a row goes back to its
owning design issue rather than being absorbed. The other direction --
a miss the schematic record already carried -- must NOT be reported as a
post-layout regression, or every re-run of an already-failing row would
manufacture a false alarm.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

import postlayout_delta as pld  # noqa: E402

CHECKS = {"vout": {"min": 0.0, "max": 1.0}}


def _points(values: dict[str, float]) -> dict[str, dict[str, float]]:
    return {corner_id: {"vout": v} for corner_id, v in values.items()}


GOOD = _points({"tt_27c_3.30v": 0.5, "ss_-40c_2.97v": 0.4, "ff_125c_3.63v": 0.6})
BAD = _points({"tt_27c_3.30v": 0.5, "ss_-40c_2.97v": 0.4, "ff_125c_3.63v": 1.7})


class ParasiticReadoutTests(unittest.TestCase):
    """layout/postlayout.py's stub model, read back per net."""

    NETLIST = """\
* a post-layout netlist
.subckt cell VDD VSS OUT
X1 OUT NG VSS VSS nfet_03v3 L=1u W=1u
R_1 OUT OUT__par 120.5
C_1 OUT__par VSS 4e-15
R_2 OUT OUT__par 79.5
C_2 OUT__par VSS 6e-15
R_3 NG NG__par 10
C_3 NG__par VSS 1e-15
.ends
"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "cell.spice"
        self.path.write_text(self.NETLIST)

    def test_stub_cards_are_summed_onto_the_schematic_net_name(self):
        nets = pld.parasitics_by_net(self.path)
        self.assertAlmostEqual(nets["OUT"]["c_f"], 10e-15)
        self.assertAlmostEqual(nets["OUT"]["r_ohm"], 200.0)
        self.assertAlmostEqual(nets["NG"]["c_f"], 1e-15)

    def test_device_cards_are_not_mistaken_for_parasitics(self):
        nets = pld.parasitics_by_net(self.path)
        self.assertEqual(sorted(nets), ["NG", "OUT"])

    def test_the_repo_netlist_totals_match_the_audit(self):
        """layout/postlayout/AUDIT.md records temp_core at 1552.3 fF."""
        netlist = SIM_DIR.parent / "layout" / "postlayout" / "temp_core.spice"
        if not netlist.is_file():  # pragma: no cover - layout not built
            self.skipTest("layout/postlayout/temp_core.spice not present")
        nets = pld.parasitics_by_net(netlist)
        total_ff = sum(v["c_f"] for v in nets.values()) * 1e15
        self.assertAlmostEqual(total_ff, 1552.3, places=1)


class VerdictTransitionTests(unittest.TestCase):
    def _transition(self, schematic, extracted) -> str:
        rows = pld.compare(schematic, extracted, CHECKS)["rows"]
        return next(r["transition"] for r in rows if r["measurement"] == "vout")

    def test_a_check_that_still_passes_is_not_a_regression(self):
        self.assertEqual(self._transition(GOOD, GOOD), "ok -> ok")

    def test_a_check_that_starts_failing_post_layout_is_a_regression(self):
        self.assertEqual(self._transition(GOOD, BAD), "ok -> MISS")

    def test_a_miss_the_schematic_record_already_carried_is_not_a_regression(self):
        self.assertEqual(self._transition(BAD, BAD), "MISS -> MISS")

    def test_a_miss_the_extraction_removes_is_reported_as_an_improvement(self):
        self.assertEqual(self._transition(BAD, GOOD), "MISS -> ok")

    def test_the_worst_per_corner_delta_names_its_corner(self):
        rows = pld.compare(GOOD, BAD, CHECKS)["rows"]
        row = next(r for r in rows if r["measurement"] == "vout")
        self.assertAlmostEqual(row["worst_delta"], 1.1)
        self.assertEqual(row["worst_delta_at"], "ff_125c_3.63v")

    def test_only_corners_present_in_both_records_are_compared(self):
        extra = dict(GOOD)
        extra["bjt_ss_27c_3.30v"] = {"vout": 0.55}
        delta = pld.compare(GOOD, extra, CHECKS)
        self.assertEqual(len(delta["shared_corners"]), 3)
        self.assertEqual(delta["extracted_only"], ["bjt_ss_27c_3.30v"])
        self.assertEqual(delta["schematic_only"], [])


class MonteCarloRefusalTests(unittest.TestCase):
    """An MC record has no PVT-grid correspondence to difference."""

    def test_a_monte_carlo_experiment_is_refused_not_silently_differenced(self):
        rc = pld.main(
            [
                "temp-accuracy-mc",
                "20260811-064418-3e6b1f3",
                "--against",
                "20260802-082345-989ce7a",
            ]
        )
        self.assertEqual(rc, 2)

    def test_monte_carlo_sample_ids_are_not_grid_points(self):
        """The premise of the refusal: parse_corner_id rejects them."""
        self.assertEqual(pld.as_results({"mc_tt_-40c_2.97v_s7": {"vout": 1.0}}), [])


class RenderingTests(unittest.TestCase):
    def _render(self, schematic, extracted, high_z=("OUT",)) -> str:
        return pld.render(
            experiment="an-experiment",
            extracted_id="20260811-000000-abcdef1",
            schematic_id="20260801-000000-1234567",
            delta=pld.compare(schematic, extracted, CHECKS),
            parasitics={"OUT": {"c_f": 1e-14, "r_ohm": 200.0}},
            high_z=list(high_z),
            sources=["layout/postlayout/cell.spice"],
            when="2026-08-11T00:00:00+00:00",
            author="tests",
            argv=["sim/postlayout_delta.py"],
        )

    def test_a_regression_is_called_out_by_name(self):
        text = self._render(GOOD, BAD)
        self.assertIn("**REGRESSION**", text)
        self.assertIn("Regressions (`ok -> MISS`): 1", text)
        self.assertIn("not relaxed", text)

    def test_a_clean_re_run_says_so_without_hedging(self):
        text = self._render(GOOD, GOOD)
        self.assertIn("Regressions (`ok -> MISS`): 0", text)
        self.assertNotIn("**REGRESSION**", text)

    def test_a_named_high_z_net_with_no_interconnect_is_not_silently_dropped(self):
        text = self._render(GOOD, GOOD, high_z=("OUT", "NOWHERE"))
        self.assertIn("`NOWHERE`", text)
        self.assertIn("no drawn interconnect of its own", text)

    def test_the_derived_record_claims_nothing_and_supersedes_nothing(self):
        text = self._render(GOOD, GOOD)
        self.assertIn("**Claim**: none of its own", text)
        self.assertIn("**Supersedes**: (none", text)
        self.assertIn("append-only", text.lower())


if __name__ == "__main__":
    unittest.main()
