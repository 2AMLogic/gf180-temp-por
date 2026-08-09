#!/usr/bin/env python3
"""Unit tests for the Monte Carlo mismatch harness (issue #15).

No PDK and no ngspice required -- these test deck composition, binding-point
parsing, seed assignment and the summarization/derivation math, exactly the
same "no PDK required" bar sim/tests/test_harness.py holds itself to.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import mc_report, montecarlo, testbench  # noqa: E402
from harness.montecarlo import BindingPoint, ManifestError, McPoint  # noqa: E402
from harness.runner import PointResult  # noqa: E402
from testutil import fake_pdk  # noqa: E402


class BindingPointTests(unittest.TestCase):
    def _write_tb(self, tmp: Path, mc: dict) -> testbench.Testbench:
        tb_dir = tmp / "an-mc-experiment" / "testbench"
        tb_dir.mkdir(parents=True)
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        manifest = {
            "name": "x",
            "netlist": "x.spice",
            "measure": {"vout": "v(out)"},
            "mc": mc,
        }
        import json

        (tb_dir / "tb.json").write_text(json.dumps(manifest))
        return testbench.load(tb_dir)

    def test_missing_mc_block_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tb_dir = Path(tmp) / "plain" / "testbench"
            tb_dir.mkdir(parents=True)
            (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
            import json

            (tb_dir / "tb.json").write_text(
                json.dumps({"name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)"}})
            )
            tb = testbench.load(tb_dir)
            with self.assertRaises(ManifestError):
                montecarlo.load_binding_points(tb)

    def test_binding_points_resolve_named_corners(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tb = self._write_tb(
                Path(tmp),
                {
                    "n": 500,
                    "seed_base": 1,
                    "binding_points": [
                        {"label": "a", "corner": "ss", "temp_c": -40, "vdd": 3.63},
                        {"label": "b", "corner": "bjt_ff", "temp_c": 125, "vdd": 2.97},
                    ],
                },
            )
            points = montecarlo.load_binding_points(tb)
            self.assertEqual([p.label for p in points], ["a", "b"])
            self.assertEqual(points[0].corner.name, "ss")
            self.assertEqual(points[1].corner.name, "bjt_ff")

    def test_unknown_corner_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tb = self._write_tb(
                Path(tmp),
                {"binding_points": [{"label": "a", "corner": "nope", "temp_c": 27, "vdd": 3.3}]},
            )
            with self.assertRaises(ManifestError):
                montecarlo.load_binding_points(tb)

    def test_duplicate_labels_are_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tb = self._write_tb(
                Path(tmp),
                {
                    "binding_points": [
                        {"label": "a", "corner": "tt", "temp_c": 27, "vdd": 3.3},
                        {"label": "a", "corner": "ss", "temp_c": -40, "vdd": 3.63},
                    ]
                },
            )
            with self.assertRaises(ManifestError):
                montecarlo.load_binding_points(tb)


class GridTests(unittest.TestCase):
    def setUp(self):
        from harness.corners import CORNERS

        self.bp = [
            BindingPoint(label="a", corner=CORNERS["tt"], temp_c=-40.0, vdd=2.97),
            BindingPoint(label="b", corner=CORNERS["ss"], temp_c=125.0, vdd=3.63),
        ]

    def test_below_floor_n_is_rejected_by_default(self):
        with self.assertRaises(ManifestError):
            montecarlo.build_mc_grid(self.bp, n=5, seed_base=1)

    def test_no_write_debugging_allows_a_small_n(self):
        points = montecarlo.build_mc_grid(self.bp, n=5, seed_base=1, enforce_min=False)
        self.assertEqual(len(points), 10)

    def test_grid_has_n_samples_per_binding_point(self):
        points = montecarlo.build_mc_grid(self.bp, n=500, seed_base=1)
        self.assertEqual(len(points), 1000)
        self.assertEqual(sum(1 for p in points if p.label == "a"), 500)
        self.assertEqual(sum(1 for p in points if p.label == "b"), 500)

    def test_seeds_are_unique_across_the_whole_grid(self):
        points = montecarlo.build_mc_grid(self.bp, n=500, seed_base=1)
        seeds = {p.seed for p in points}
        self.assertEqual(len(seeds), len(points))

    def test_seed_is_a_pure_function_of_seed_base(self):
        """Re-running the same manifest with the same seed_base reproduces
        the identical sample set -- what the record's Statistical
        convention field promises."""
        first = montecarlo.build_mc_grid(self.bp, n=500, seed_base=42)
        second = montecarlo.build_mc_grid(self.bp, n=500, seed_base=42)
        self.assertEqual([p.seed for p in first], [p.seed for p in second])

    def test_corner_id_is_unique_and_traceable(self):
        points = montecarlo.build_mc_grid(self.bp, n=500, seed_base=1)
        ids = {p.corner_id for p in points}
        self.assertEqual(len(ids), len(points))
        self.assertIn("a_tt_-40c_2.97v_s0000", ids)
        self.assertIn("b_ss_125c_3.63v_s0499", ids)


class DeckCompositionTests(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        tb_dir = root / "tb"
        tb_dir.mkdir()
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps(
                {
                    "name": "x",
                    "netlist": "x.spice",
                    "measure": {"vout": "v(out)"},
                    "analyses": ["dc temp %(temp_c)g %(temp_c)g 1"],
                    "mc": {
                        "n": 500,
                        "seed_base": 1,
                        "binding_points": [{"label": "a", "corner": "ss", "temp_c": -40, "vdd": 3.63}],
                    },
                }
            )
        )
        self.tb = testbench.load(tb_dir)
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.point = montecarlo.build_mc_grid(
            montecarlo.load_binding_points(self.tb), n=500, seed_base=1
        )[0]
        self.deck = montecarlo.compose_mc_deck(self.tb, self.pdk, self.point)

    def test_mismatch_override_follows_the_lib_includes(self):
        """Load-bearing ordering: ngspice keeps the LAST duplicate .param,
        and design.ngspice's own sw_stat_mismatch=0 lives inside the
        .include -- see montecarlo.py's module docstring."""
        lib_at = self.deck.index("sm141064.ngspice")
        override_at = self.deck.index(".param sw_stat_mismatch=1")
        self.assertLess(lib_at, override_at)

    def test_seed_option_is_set(self):
        self.assertIn(f".option seed={self.point.seed}", self.deck)

    def test_analysis_line_gets_percent_formatted(self):
        self.assertIn("dc temp -40 -40 1", self.deck)
        self.assertNotIn("%(temp_c)g", self.deck)

    def test_process_corner_sections_are_the_named_deterministic_bundle(self):
        for section in self.point.corner.sections:
            self.assertIn(f'sm141064.ngspice" {section}', self.deck)

    def test_deck_still_sets_the_pvt_point(self):
        self.assertIn(".param vdd_val=3.63", self.deck)
        self.assertIn(".temp -40", self.deck)


class DeriveTempTrimTests(unittest.TestCase):
    def test_zero_curvature_zero_die_gives_only_quantisation(self):
        # K25 = vptat25_v / 298.15; pick vptattgt_v so curvature is exactly 0.
        t_k = 233.15  # -40 C
        k25 = 4.3e-3
        vptat25 = k25 * 298.15
        vptattgt = k25 * t_k
        out = montecarlo.derive_temp_trim(
            {"vptat25_v": vptat25, "vptattgt_v": vptattgt, "vtktgt_k": t_k}
        )
        self.assertAlmostEqual(out["terr_trim_c"], (montecarlo._TRIM_LSB_FRAC / 2.0) * t_k)

    def test_missing_inputs_return_empty(self):
        self.assertEqual(montecarlo.derive_temp_trim({"vptat25_v": 1.0}), {})

    def test_derive_hook_dispatch_updates_results_in_place(self):
        results = [
            PointResult(
                point=McPoint(label="a", corner=None, temp_c=-40.0, vdd=3.63, sample=0, seed=1),
                status="ok",
                measurements={"vptat25_v": 1.283, "vptattgt_v": 1.0, "vtktgt_k": 233.15},
            )
        ]

        class _FakeTb:
            mc = {"derive": "temp_trim"}

        added = montecarlo.apply_derive_hook(_FakeTb(), results)
        self.assertIn("terr_trim_c", added)
        self.assertIn("terr_trim_c", results[0].measurements)

    def test_unknown_hook_is_rejected(self):
        class _FakeTb:
            mc = {"derive": "not-a-real-hook"}

        with self.assertRaises(ManifestError):
            montecarlo.apply_derive_hook(_FakeTb(), [])


class SummarizeTests(unittest.TestCase):
    def _result(self, label, value):
        return PointResult(
            point=McPoint(label=label, corner=None, temp_c=27.0, vdd=3.3, sample=0, seed=1),
            status="ok",
            measurements={"terr_c": value},
        )

    def test_mean_and_stdev_are_computed_per_binding_point(self):
        results = [self._result("a", v) for v in (1.0, 2.0, 3.0)]
        summary = montecarlo.summarize_mc(results, ["terr_c"], {})
        stats = summary["a"]["terr_c"]
        self.assertEqual(stats["n"], 3)
        self.assertAlmostEqual(stats["mean"], 2.0)
        self.assertAlmostEqual(stats["stdev"], 1.0)

    def test_parametric_3sigma_bound_and_pass_fail(self):
        results = [self._result("a", v) for v in (-1.0, 0.0, 1.0)]
        summary = montecarlo.summarize_mc(results, ["terr_c"], {"terr_c": {"min": -3.0, "max": 3.0}})
        stats = summary["a"]["terr_c"]
        self.assertAlmostEqual(stats["sigma3_lo"], stats["mean"] - 3 * stats["stdev"])
        self.assertAlmostEqual(stats["sigma3_hi"], stats["mean"] + 3 * stats["stdev"])
        self.assertTrue(stats["parametric_3sigma_pass"])

    def test_a_tight_spec_fails_the_parametric_bound(self):
        results = [self._result("a", v) for v in (-5.0, 0.0, 5.0)]
        summary = montecarlo.summarize_mc(results, ["terr_c"], {"terr_c": {"min": -3.0, "max": 3.0}})
        self.assertFalse(summary["a"]["terr_c"]["parametric_3sigma_pass"])

    def test_empirical_yield_counts_in_bound_samples(self):
        results = [self._result("a", v) for v in (-4.0, 0.0, 4.0)]
        summary = montecarlo.summarize_mc(results, ["terr_c"], {"terr_c": {"min": -3.0, "max": 3.0}})
        self.assertAlmostEqual(summary["a"]["terr_c"]["empirical_yield"], 1.0 / 3.0)

    def test_groups_by_binding_point_label(self):
        results = [self._result("a", 1.0), self._result("b", 2.0), self._result("a", 3.0)]
        summary = montecarlo.summarize_mc(results, ["terr_c"], {})
        self.assertEqual(set(summary), {"a", "b"})
        self.assertEqual(summary["a"]["terr_c"]["n"], 2)
        self.assertEqual(summary["b"]["terr_c"]["n"], 1)


class RecordRenderingTests(unittest.TestCase):
    """The rendered MC record carries the same ratified field set report.py's
    deterministic-grid record does (sim/README.md), plus the MC-specific
    binding-point/statistical-convention content."""

    RATIFIED_FIELDS = (
        "Record ID",
        "Claim",
        "Netlist provenance",
        "Corner matrix run",
        "Statistical convention",
        "Result",
        "Links",
        "Timestamp / author",
        "Supersedes",
    )

    def setUp(self):
        import json
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        tb_dir = root / "mc-experiment" / "testbench"
        tb_dir.mkdir(parents=True)
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps(
                {
                    "name": "mc-experiment",
                    "netlist": "x.spice",
                    "measure": {"vout": "v(out)"},
                    "checks": {"vout": {"min": 0.0, "max": 10.0}},
                    "mc": {
                        "n": 500,
                        "seed_base": 1,
                        "binding_points": [{"label": "a", "corner": "tt", "temp_c": 27, "vdd": 3.3}],
                    },
                }
            )
        )
        self.tb = testbench.load(tb_dir)
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.binding_points = montecarlo.load_binding_points(self.tb)
        self.points = montecarlo.build_mc_grid(self.binding_points, n=500, seed_base=1)
        self.results = [
            PointResult(point=p, status="ok", measurements={"vout": 1.0 + 0.001 * i})
            for i, p in enumerate(self.points)
        ]
        self.summary = montecarlo.summarize_mc(self.results, ["vout"], self.tb.checks)
        self.record = mc_report.build_mc_record(
            tb=self.tb,
            pdk=self.pdk,
            binding_points=self.binding_points,
            points=self.points,
            results=self.results,
            summary=self.summary,
            ngspice="ngspice-46",
            repo_root=SIM_DIR,
            record_id="20260802-153000-1a7ef75",
            started_utc="2026-08-02T15:30:00+00:00",
            wall_seconds=120.0,
            n_per_point=500,
            seed_base=1,
            derived_measures=[],
            claim="spec/target-spec.md#example",
        )

    def test_every_ratified_field_is_present_and_in_order(self):
        text = mc_report.render_mc_record(self.record, "mc-experiment")
        positions = []
        for field in self.RATIFIED_FIELDS:
            marker = f"**{field}**"
            self.assertIn(marker, text, f"missing ratified field {field!r}")
            positions.append(text.index(marker))
        self.assertEqual(positions, sorted(positions), "fields are out of ratified order")

    def test_binding_points_are_named_not_a_grid(self):
        text = mc_report.render_mc_record(self.record, "mc-experiment")
        self.assertIn("`a`: corner `tt`", text)
        self.assertIn("not the full 81-point deterministic grid", text)

    def test_statistical_convention_names_n_and_the_seed_mechanism(self):
        text = mc_report.render_mc_record(self.record, "mc-experiment")
        self.assertIn("N=500", text)
        self.assertIn(".option seed=", text)

    def test_overall_verdict_is_pass_when_every_binding_point_closes(self):
        text = mc_report.render_mc_record(self.record, "mc-experiment")
        self.assertIn("**Overall: PASS**", text)

    def test_links_point_at_the_ratified_paths(self):
        text = mc_report.render_mc_record(self.record, "mc-experiment")
        self.assertIn("sim/mc-experiment/testbench/x.spice", text)
        self.assertIn("sim/mc-experiment/netlist-snapshots/20260802-153000-1a7ef75.spice", text)
        self.assertIn("sim/mc-experiment/corners/20260802-153000-1a7ef75/", text)


if __name__ == "__main__":
    unittest.main()
