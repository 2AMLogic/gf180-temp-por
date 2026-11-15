#!/usr/bin/env python3
"""One definition per directory for the shared control-script helpers (#493).

No PDK, no ngspice: these parse and call Python only.

Three analysis helpers used to exist as two independently-maintained copies
inside a single ``sim/*/control/`` directory, each encoding one criterion that
two controls in that directory report under the same name in their respective
results files -- with nothing holding the definitions equal. Issue #493
consolidated each onto one definition. The guard that keeps it that way is
``test_each_shared_helper_has_exactly_one_definition_in_its_directory``
below: it fails if a second ``def`` of one of these names reappears anywhere
in the directory, at any nesting depth, which is exactly how all six copies
got there (five of them nested inside a ``write_results``).

The remaining tests pin the surviving definitions' *meaning*, because
consolidation only removes the risk of the copies disagreeing -- it does not
by itself stop the one definition from being changed. Each criterion decides
what a committed results file says, so the boundary values are the thing
worth asserting:

  * ``verdict`` decides what ``width_results.md`` and ``cdg_results.md`` each
    call ``rejected`` / ``partial`` / ``**through**``;
  * ``static_and_slope`` decides the zero-rate static limit that
    ``sim/por-vth/control/``'s two controls both publish;
  * ``us_after_dip`` decides the time origin of every "µs after the dip
    starts" column under ``sim/por-brownout-slew/control/``.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

#: (control directory, helper name, the module that must be its one home).
SHARED_HELPERS = [
    ("por-output-chain-deglitch/control", "verdict", "_deglitch_criterion.py"),
    ("por-vth/control", "static_and_slope", "run_ramp_rate_probe.py"),
    ("por-brownout-slew/control", "us_after_dip", "run_band_mechanism.py"),
]


def _defs_of(name: str, directory: Path) -> list[str]:
    """``file:line`` of every ``def <name>`` under ``directory``, nested or not."""
    found: list[str] = []
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return found


def _load(path: Path, name: str):
    """Import a control script by path -- it is a script, not a module."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OneDefinitionPerDirectoryTests(unittest.TestCase):
    """The #493 guard: a reintroduced copy must fail, not merely be noticed."""

    def test_each_shared_helper_has_exactly_one_definition_in_its_directory(self):
        for rel, helper, home in SHARED_HELPERS:
            with self.subTest(helper=helper, directory=rel):
                directory = SIM_DIR / rel
                sites = _defs_of(helper, directory)
                self.assertEqual(
                    len(sites), 1,
                    f"`{helper}` must have exactly one definition under "
                    f"sim/{rel}/ -- two controls in one directory report it "
                    f"under the same name, so copies can silently diverge "
                    f"(#493). Found: {sites or 'none'}",
                )
                self.assertTrue(
                    sites[0].endswith(f"/{home}:{sites[0].split(':')[1]}"),
                    f"`{helper}`'s one definition should live in {home}, "
                    f"found {sites[0]}",
                )

    def test_both_deglitch_controls_resolve_the_same_verdict_object(self):
        """Not merely "each imports something called verdict"."""
        d = SIM_DIR / "por-output-chain-deglitch/control"
        sys.path.insert(0, str(d))
        try:
            criterion = _load(d / "_deglitch_criterion.py", "_deglitch_criterion")
            for script in ("run_glitch_width_sweep.py", "run_cdg_tradeoff.py"):
                mod = _load(d / script, script[:-3])
                self.assertIs(
                    mod.verdict, criterion.verdict,
                    f"{script} must use the shared criterion, not a copy",
                )
        finally:
            sys.path.remove(str(d))


class VerdictBoundaryTests(unittest.TestCase):
    """What `width_results.md` / `cdg_results.md` mean by each word."""

    def setUp(self):
        d = SIM_DIR / "por-output-chain-deglitch/control"
        self.mod = _load(d / "_deglitch_criterion.py", "_deglitch_criterion")

    def lost(self, fraction: float) -> str:
        return self.mod.verdict({"timbefore": 1.0, "timafter": 1.0 - fraction})

    def test_the_two_boundaries_are_exclusive_so_a_run_exactly_on_one_is_the_milder_word(self):
        """`>` not `>=`: a run sitting exactly on a boundary gets the gentler
        word. The measurement pairs are chosen so the function's own division
        lands exactly on the constant -- 1.0/0.99 would not, it yields
        0.010000000000000009, which is genuinely over the boundary."""
        for timbefore, timafter, boundary, want in (
            (1.0, 0.5, self.mod.THROUGH_FRACTION, "partial"),
            (100.0, 99.0, self.mod.PARTIAL_FRACTION, "rejected"),
        ):
            with self.subTest(boundary=boundary):
                self.assertEqual(
                    (timbefore - timafter) / timbefore, boundary,
                    "fixture must land exactly on the boundary to test it",
                )
                self.assertEqual(
                    self.mod.verdict(
                        {"timbefore": timbefore, "timafter": timafter}
                    ),
                    want,
                )

    def test_losing_more_than_half_the_timer_charge_is_through(self):
        self.assertEqual(self.lost(0.5001), "**through**")
        self.assertEqual(self.lost(1.0), "**through**")

    def test_a_material_but_sub_half_loss_is_partial(self):
        self.assertEqual(self.lost(0.011), "partial")
        self.assertEqual(self.lost(0.4999), "partial")

    def test_keeping_the_charge_is_rejected(self):
        self.assertEqual(self.lost(0.0), "rejected")
        self.assertEqual(self.lost(0.009), "rejected")

    def test_tim_rising_during_rejection_is_not_read_as_a_loss(self):
        """TIM only ever *rises* while the filter rejects, so a negative
        "loss" is the normal rejecting case, not an out-of-range input."""
        self.assertEqual(self.lost(-0.25), "rejected")


class StaticAndSlopeTests(unittest.TestCase):
    """The zero-rate extrapolation both por-vth controls publish."""

    def setUp(self):
        d = SIM_DIR / "por-vth/control"
        self.mod = _load(d / "run_ramp_rate_probe.py", "run_ramp_rate_probe")

    @staticmethod
    def rows(*pairs, key="v_hys_mv"):
        return [{"rate_v_per_s": r, key: v} for r, v in pairs]

    def test_it_extrapolates_to_zero_rate_through_the_two_slowest_rows(self):
        # 100 mV at 10 V/s, 110 mV at 20 V/s -> slope 1 mV per V/s, 90 mV at 0.
        static, slope = self.mod.static_and_slope(self.rows((10.0, 100.0), (20.0, 110.0)))
        self.assertAlmostEqual(static, 90.0)
        self.assertAlmostEqual(slope, 1.0)

    def test_only_the_two_slowest_rows_are_used_whatever_order_they_arrive_in(self):
        """The selection rule is "the two slowest", not "the first two"."""
        fast_decoys = ((400.0, 900.0), (800.0, 1700.0))
        want = self.mod.static_and_slope(self.rows((10.0, 100.0), (20.0, 110.0)))
        for extra in (fast_decoys, tuple(reversed(fast_decoys))):
            got = self.mod.static_and_slope(
                self.rows(*extra, (20.0, 110.0), (10.0, 100.0))
            )
            self.assertEqual(got, want)

    def test_the_key_selects_which_column_is_extrapolated(self):
        """The parameter run_rate_ladder.py's deleted copy hard-coded."""
        rows = [
            {"rate_v_per_s": 10.0, "v_hys_mv": 100.0, "vref_err_up_mv": 3.0},
            {"rate_v_per_s": 20.0, "v_hys_mv": 110.0, "vref_err_up_mv": 5.0},
        ]
        self.assertAlmostEqual(self.mod.static_and_slope(rows)[0], 90.0)
        self.assertAlmostEqual(
            self.mod.static_and_slope(rows, "vref_err_up_mv")[0], 1.0
        )

    def test_v_hys_mv_is_the_default_column(self):
        """run_rate_ladder.py now relies on the default being its column."""
        rows = self.rows((10.0, 100.0), (20.0, 110.0))
        self.assertEqual(
            self.mod.static_and_slope(rows),
            self.mod.static_and_slope(rows, "v_hys_mv"),
        )


class UsAfterDipTests(unittest.TestCase):
    """The time origin of every "µs after the dip starts" column."""

    def setUp(self):
        d = SIM_DIR / "por-brownout-slew/control"
        self.mod = _load(d / "run_band_mechanism.py", "run_band_mechanism")

    def test_it_measures_microseconds_from_the_dip_start(self):
        self.assertAlmostEqual(self.mod.us_after_dip(self.mod.T_DIP_S), 0.0)
        self.assertAlmostEqual(
            self.mod.us_after_dip(self.mod.T_DIP_S + 45.0e-6), 45.0
        )

    def test_an_event_before_the_dip_reads_negative_rather_than_clamping(self):
        self.assertAlmostEqual(
            self.mod.us_after_dip(self.mod.T_DIP_S - 10.0e-6), -10.0
        )

    def test_an_absent_measurement_stays_absent(self):
        """None in, None out -- the callers render that as "**never**", which
        is a different statement from "at 0 µs"."""
        self.assertIsNone(self.mod.us_after_dip(None))


if __name__ == "__main__":
    unittest.main()
