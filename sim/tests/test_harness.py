#!/usr/bin/env python3
"""Unit tests for the PVT harness. No PDK and no ngspice required.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import cli, cliutil, corners, report, runner, testbench  # noqa: E402
from testutil import fake_pdk  # noqa: E402


class CornerTests(unittest.TestCase):
    def test_pvt_axes_match_the_mandated_grid(self):
        self.assertEqual(corners.DEFAULT_TEMPERATURES_C, (-40.0, 27.0, 125.0))
        self.assertAlmostEqual(corners.DEFAULT_SUPPLY_TOLERANCE, 0.10)

    def test_supply_points_are_nominal_plus_minus_ten_percent(self):
        self.assertEqual(corners.supply_points(3.3, 0.10), [2.97, 3.3, 3.63])

    def test_zero_tolerance_collapses_the_voltage_axis(self):
        self.assertEqual(corners.supply_points(3.3, 0.0), [3.3])

    def test_every_corner_names_one_section_per_device_family(self):
        for name, corner in corners.CORNERS.items():
            with self.subTest(corner=name):
                self.assertEqual(len(corner.sections), 6, corner.sections)
                self.assertEqual(len(set(corner.sections)), 6, corner.sections)

    def test_corner_sets_expand_and_deduplicate(self):
        resolved = corners.resolve_corners(["mos", "tt"])
        self.assertEqual([c.name for c in resolved], ["tt", "ff", "ss", "fs", "sf"])

    def test_default_corner_set_covers_the_passive_corners(self):
        """DR-006: this repo defaults to `full`, not upstream's `mos`.

        Temperature accuracy and the POR threshold both ride on resistor sheet
        rho and BJT Is/beta, so a MOS-only default would silently under-cover
        the devices that set the spec.
        """
        self.assertEqual(corners.DEFAULT_CORNER_SET, "full")
        names = [c.name for c in corners.resolve_corners(None)]
        self.assertEqual(len(names), 9)
        for required in ("res_ff", "res_ss", "bjt_ff", "bjt_ss"):
            self.assertIn(required, names)

    def test_unknown_corner_is_rejected(self):
        with self.assertRaises(KeyError):
            corners.resolve_corners(["nope"])

    def test_grid_is_full_factorial_and_ordered(self):
        grid = corners.build_grid(corners.resolve_corners(["mos"]), (-40, 27, 125), [2.97, 3.3, 3.63])
        self.assertEqual(len(grid), 5 * 3 * 3)
        self.assertEqual(len({p.corner_id for p in grid}), 45)

    def test_corner_id_matches_the_ratified_naming(self):
        """sim/README.md: <corner-id> is <process>_<temp>c_<supply>v."""
        grid = corners.build_grid(
            corners.resolve_corners(["tt", "ss", "ff"]), (-40, 27, 125), [2.97, 3.3, 3.63]
        )
        ids = {p.corner_id for p in grid}
        self.assertIn("tt_27c_3.30v", ids)
        self.assertIn("ss_-40c_2.97v", ids)
        self.assertIn("ff_125c_3.63v", ids)

    def test_parse_corner_id_splits_the_ratified_naming(self):
        self.assertEqual(corners.parse_corner_id("tt_27c_3.30v"), ("tt", 27.0, "3.30"))
        self.assertEqual(corners.parse_corner_id("ss_-40c_2.97v"), ("ss", -40.0, "2.97"))
        self.assertEqual(corners.parse_corner_id("bjt_ff_125c_3.63v"), ("bjt_ff", 125.0, "3.63"))
        self.assertEqual(corners.parse_corner_id("tt_25.5c_3.30v"), ("tt", 25.5, "3.30"))

    def test_parse_corner_id_returns_the_supply_verbatim(self):
        """The supply stays a string: it is a grouping key and a table cell.

        PvtPoint.corner_id always writes two decimals, so `"3.30"` is what a
        real record carries -- but the parser hands back whatever the id
        spelled rather than normalising it to a float.
        """
        self.assertEqual(corners.parse_corner_id("tt_27c_3.30v"), ("tt", 27.0, "3.30"))
        self.assertEqual(corners.parse_corner_id("tt_27c_3.3v"), ("tt", 27.0, "3.3"))

    def test_parse_corner_id_round_trips_every_point_of_the_default_grid(self):
        """The parser is the exact inverse of PvtPoint.corner_id."""
        grid = corners.build_grid(
            corners.resolve_corners(None),
            corners.DEFAULT_TEMPERATURES_C,
            corners.supply_points(),
        )
        self.assertEqual(len(grid), 81)
        for point in grid:
            with self.subTest(corner_id=point.corner_id):
                parsed = corners.parse_corner_id(point.corner_id)
                self.assertIsNotNone(parsed)
                process, temp_c, supply = parsed
                self.assertEqual(process, point.corner.name)
                self.assertAlmostEqual(temp_c, point.temp_c)
                self.assertAlmostEqual(float(supply), point.vdd)

    def test_parse_corner_id_returns_none_for_foreign_ids(self):
        """Callers skip names in other shapes instead of catching an exception.

        The Monte Carlo per-sample id (`<label>_<corner>_<temp>c_<vdd>v_s<n>`,
        sim/temp-accuracy-mc/) is deliberately NOT a ratified corner id.
        """
        for foreign in (
            "",
            "tt_27c",
            "tt_27_3.30v",
            "tt_27c_3v",  # supply needs a decimal point
            "TT_27c_3.30v",  # process corners are lower case
            "mc_tt_27c_3.30v_s7",  # Monte Carlo per-sample id
            "summary.json",
        ):
            with self.subTest(corner_id=foreign):
                self.assertIsNone(corners.parse_corner_id(foreign))


class TestbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, netlist: str, manifest: dict | None = None) -> Path:
        """Lay out sim/<slug>/testbench/ the way sim/README.md specifies."""
        tb_dir = self.dir / "an-experiment" / "testbench"
        tb_dir.mkdir(parents=True, exist_ok=True)
        (tb_dir / "x.spice").write_text(netlist)
        base = {"name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)"}}
        base.update(manifest or {})
        (tb_dir / "tb.json").write_text(json.dumps(base))
        return tb_dir

    def test_loads_a_valid_manifest(self):
        tb = testbench.load(self._write("v1 out 0 dc {vdd_val}\n"))
        self.assertEqual(tb.name, "x")
        self.assertEqual(tb.measure, {"vout": "v(out)"})
        self.assertEqual(tb.temperatures_c, (-40.0, 27.0, 125.0))

    def test_experiment_slug_comes_from_the_directory_layout(self):
        tb_dir = self._write("v1 out 0 dc {vdd_val}\n")
        # Loadable by testbench dir *and* by experiment dir.
        for target in (tb_dir, tb_dir.parent):
            with self.subTest(target=target.name):
                tb = testbench.load(target)
                self.assertEqual(tb.experiment, "an-experiment")
                self.assertEqual(tb.experiment_dir.name, "an-experiment")

    def test_discover_finds_experiments_not_bare_manifest_dirs(self):
        self._write("v1 out 0 dc {vdd_val}\n")
        found = testbench.discover(self.dir)
        self.assertEqual([p.name for p in found], ["an-experiment"])

    def test_rejects_netlists_that_pin_the_temperature(self):
        with self.assertRaises(ValueError) as ctx:
            testbench.load(self._write("v1 out 0 dc 3.3\n.temp 27\n"))
        self.assertIn(".temp", str(ctx.exception))

    def test_rejects_netlists_that_include_models_themselves(self):
        with self.assertRaises(ValueError):
            testbench.load(self._write('.lib "models" typical\nv1 out 0 dc 3.3\n'))

    def test_rejects_a_manifest_without_measurements(self):
        with self.assertRaises(ValueError):
            testbench.load(self._write("v1 out 0 dc 3.3\n", {"measure": {}}))

    def test_the_repo_smoke_testbench_is_valid(self):
        tb = testbench.load(SIM_DIR / "smoke-bias")
        self.assertEqual(tb.nominal_supply_v, 3.3)  # DR-001: 3.3 V flavor
        self.assertEqual(tb.supply_tolerance, 0.1)  # DR-001: +/-10 %
        self.assertEqual(tb.temperatures_c, (-40.0, 27.0, 125.0))
        self.assertEqual(tb.experiment, "smoke-bias")
        self.assertIn("vbe", tb.measure)
        self.assertIn("vbe", tb.checks)

    def test_every_repo_experiment_sweeps_the_passive_corners(self):
        """DR-006: no experiment in this repo may quietly run MOS-only."""
        experiments = testbench.discover(SIM_DIR)
        self.assertTrue(experiments, "no experiments found under sim/")
        for directory in experiments:
            with self.subTest(experiment=directory.name):
                tb = testbench.load(directory)
                names = [c.name for c in corners.resolve_corners(list(tb.corners))]
                for required in ("res_ff", "res_ss", "bjt_ff", "bjt_ss"):
                    self.assertIn(required, names)

    def test_netlist_provenance_defaults_to_schematic(self):
        """sim/README.md: provenance is schematic unless the manifest says otherwise."""
        tb = testbench.load(self._write("v1 out 0 dc {vdd_val}\n"))
        self.assertEqual(tb.netlist_provenance, "schematic")
        self.assertEqual(tb.netlist_provenance_note, "")
        self.assertEqual(tb.provenance()["netlist_provenance"], "schematic")

    def test_netlist_provenance_extracted_is_accepted_with_its_note(self):
        tb = testbench.load(
            self._write(
                "v1 out 0 dc {vdd_val}\n",
                {
                    "netlist_provenance": "extracted",
                    "netlist_provenance_note": "see layout/postlayout/AUDIT.md",
                },
            )
        )
        self.assertEqual(tb.netlist_provenance, "extracted")
        self.assertEqual(tb.netlist_provenance_note, "see layout/postlayout/AUDIT.md")
        provenance = tb.provenance()
        self.assertEqual(provenance["netlist_provenance"], "extracted")
        self.assertEqual(provenance["netlist_provenance_note"], "see layout/postlayout/AUDIT.md")

    def test_netlist_provenance_rejects_unknown_values(self):
        with self.assertRaises(ValueError) as ctx:
            testbench.load(
                self._write("v1 out 0 dc {vdd_val}\n", {"netlist_provenance": "simulated"})
            )
        self.assertIn("netlist_provenance", str(ctx.exception))

    def test_every_postlayout_experiment_declares_extracted_provenance(self):
        """#86: sim/README.md requires an extracted record to say so and carry
        the layout/postlayout/AUDIT.md caveat -- this is the manifest half of
        that requirement, checked for every testbench-postlayout/ directory
        the repo commits (independent of testbench.discover(), which only
        looks under the schematic "testbench" dirname)."""
        postlayout_dirs = sorted(SIM_DIR.glob("*/testbench-postlayout/tb.json"))
        self.assertTrue(postlayout_dirs, "no testbench-postlayout/ manifests found under sim/")
        for manifest_path in postlayout_dirs:
            with self.subTest(experiment=manifest_path.parent.parent.name):
                tb = testbench.load(manifest_path)
                self.assertEqual(tb.netlist_provenance, "extracted")
                self.assertIn("layout/postlayout/AUDIT.md", tb.netlist_provenance_note)

    def test_extracted_provenance_requires_a_caveat_note(self):
        """sim/README.md: an 'extracted' record must carry the netlist header's caveat,
        so the manifest is rejected outright when the note is missing (#84) rather
        than silently rendering a bare 'extracted' provenance line."""
        with self.assertRaises(ValueError) as ctx:
            testbench.load(
                self._write("v1 out 0 dc {vdd_val}\n", {"netlist_provenance": "extracted"})
            )
        self.assertIn("netlist_provenance_note", str(ctx.exception))


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "tb").mkdir()
        (root / "tb" / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (root / "tb" / "tb.json").write_text(
            json.dumps(
                {
                    "name": "x",
                    "netlist": "x.spice",
                    "measure": {"vout": "v(out)", "iq": "-i(v1)"},
                    "params": {"cload": "1p"},
                    "options": ["reltol=1e-5"],
                }
            )
        )
        self.tb = testbench.load(root / "tb")
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.point = corners.build_grid(corners.resolve_corners(["ss"]), (125,), [3.63])[0]
        self.deck = runner.compose_deck(self.tb, self.pdk, self.point)

    def test_deck_sets_the_pvt_point(self):
        self.assertIn(".param vdd_val=3.63", self.deck)
        self.assertIn(".param vdd_nom=3.3", self.deck)
        self.assertIn(".temp 125", self.deck)

    def test_deck_includes_design_switches_before_model_sections(self):
        design_at = self.deck.index("design.ngspice")
        lib_at = self.deck.index("sm141064.ngspice")
        self.assertLess(design_at, lib_at)

    def test_deck_selects_every_section_of_the_corner(self):
        for section in self.point.corner.sections:
            self.assertIn(f'sm141064.ngspice" {section}', self.deck)

    def test_deck_carries_manifest_params_and_options(self):
        self.assertIn(".param cload=1p", self.deck)
        self.assertIn(".options reltol=1e-5", self.deck)

    def test_deck_emits_one_measurement_vector_per_measure_entry(self):
        self.assertIn("let m_vout = v(out)", self.deck)
        self.assertIn("let m_iq = -i(v1)", self.deck)
        self.assertIn("print m_vout", self.deck)
        self.assertTrue(self.deck.rstrip().endswith(".end"))


class SpiceinitTests(unittest.TestCase):
    """#216: ngspice's own OpenMP team (`num_threads`) fights this harness's
    process-level `-j` parallelism -- 22x slower on an 8-core host,
    bit-identical results. `run_point` forces single-threaded ngspice via a
    per-run `.spiceinit`, carrying forward whatever the host's own
    `$HOME/.spiceinit` sets (ngspice reads one or the other, never both)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_forces_single_threaded_ngspice(self):
        text = runner.spiceinit_text(home_spiceinit=self.root / "no-such-home-spiceinit")
        self.assertIn("set num_threads=1", text)

    def test_absent_home_spiceinit_carries_nothing_forward(self):
        text = runner.spiceinit_text(home_spiceinit=self.root / "no-such-home-spiceinit")
        self.assertNotIn("carried forward", text)

    def test_carries_forward_the_hosts_home_spiceinit(self):
        home = self.root / "home-spiceinit"
        home.write_text("set wnflag=1\n")
        text = runner.spiceinit_text(home_spiceinit=home)
        self.assertIn("set wnflag=1", text)
        self.assertIn("set num_threads=1", text)
        self.assertIn("carried forward", text)

    def test_empty_home_spiceinit_carries_nothing_forward(self):
        home = self.root / "home-spiceinit"
        home.write_text("")
        text = runner.spiceinit_text(home_spiceinit=home)
        self.assertNotIn("carried forward", text)
        self.assertIn("set num_threads=1", text)

    def test_write_run_spiceinit_writes_the_workdir_dotfile(self):
        workdir = self.root / "workdir"
        workdir.mkdir()
        home = self.root / "home-spiceinit"
        home.write_text("set wnflag=1\n")
        path = runner.write_run_spiceinit(workdir, home_spiceinit=home)
        self.assertEqual(path, workdir / ".spiceinit")
        self.assertEqual(path.read_text(), runner.spiceinit_text(home_spiceinit=home))

    def test_run_point_writes_a_spiceinit_alongside_the_deck(self):
        """The actual call site (`runner.py:415`'s `subprocess.run(...,
        cwd=workdir)`) writes `workdir/.spiceinit` before invoking ngspice --
        exercised here without a real ngspice by faking `subprocess.run`."""
        root = self.root
        (root / "tb").mkdir()
        (root / "tb" / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (root / "tb" / "tb.json").write_text(
            json.dumps({"name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)"}})
        )
        tb = testbench.load(root / "tb")
        pdk = fake_pdk(root / "gf180mcuD")
        point = corners.build_grid(corners.resolve_corners(["tt"]), (27,), [3.3])[0]
        workdir = root / "work"

        seen_cwd = []

        def fake_run(cmd, capture_output, text, timeout, cwd, check):
            seen_cwd.append(Path(cwd))
            self.assertTrue((Path(cwd) / ".spiceinit").is_file())
            proc = mock.Mock()
            proc.stdout = "m_vout = 1.0"
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with mock.patch.object(runner.subprocess, "run", side_effect=fake_run):
            result = runner.run_point(tb, pdk, point, workdir)

        self.assertEqual(result.status, "ok")
        self.assertTrue((workdir / ".spiceinit").is_file())
        self.assertIn("set num_threads=1", (workdir / ".spiceinit").read_text())

    def test_probe_num_threads_parses_the_echoed_value(self):
        with mock.patch.object(runner.shutil, "which", return_value="/usr/bin/ngspice"), \
             mock.patch.object(runner.subprocess, "run") as run_mock:
            proc = mock.Mock()
            proc.stdout = "   echo NUM_THREADS=1\nNUM_THREADS=1\n"
            proc.stderr = ""
            run_mock.return_value = proc
            self.assertEqual(runner.probe_num_threads(), 1)

    def test_probe_num_threads_raises_when_ngspice_is_missing(self):
        with mock.patch.object(runner.shutil, "which", return_value=None):
            with self.assertRaises(runner.NgspiceMissing):
                runner.probe_num_threads()

    def test_probe_num_threads_raises_when_output_is_unparseable(self):
        with mock.patch.object(runner.shutil, "which", return_value="/usr/bin/ngspice"), \
             mock.patch.object(runner.subprocess, "run") as run_mock:
            proc = mock.Mock()
            proc.stdout = "no useful output here"
            proc.stderr = ""
            run_mock.return_value = proc
            with self.assertRaises(RuntimeError):
                runner.probe_num_threads()


class ParseTests(unittest.TestCase):
    def test_parses_print_output(self):
        text = "\n".join(
            [
                "Circuit: * x",
                "m_vout = 1.2003456789e+00",
                "m_iq = -4.5e-05",
                "v(other) = 9.9",
                "m_bad = not_a_number",
            ]
        )
        self.assertEqual(
            runner.parse_measurements(text), {"vout": 1.2003456789, "iq": -4.5e-05}
        )


class ParsePrintsTests(unittest.TestCase):
    def test_parses_bare_print_output(self):
        # `print <expr>` (as opposed to `print m_<name>`, which
        # parse_measurements above covers): the raw expression is the key,
        # with no `m_` prefix.
        text = "\n".join(
            [
                "Circuit: * x",
                "@m.xdut.xmoka.m0[id] = 4.728e-09",
                "V(NOKO) = 1.643330117",
                "not a match at all",
                "V(bad) = not_a_number",
            ]
        )
        self.assertEqual(
            runner.parse_prints(text),
            {"@m.xdut.xmoka.m0[id]": 4.728e-09, "V(NOKO)": 1.643330117},
        )

    def test_empty_text_yields_no_values(self):
        self.assertEqual(runner.parse_prints(""), {})


class ParseBareMeasurementsTests(unittest.TestCase):
    def test_parses_find_when_output(self):
        # `.measure ... find`/`when` output: "name = value", no `at=` suffix.
        text = "\n".join(["t_vpor = 1.234500e-03", "vref_pre = 1.197791048"])
        self.assertEqual(
            runner.parse_bare_measurements(text),
            {"t_vpor": 1.2345e-03, "vref_pre": 1.197791048},
        )

    def test_parses_min_max_output_with_trailing_at(self):
        # `.measure ... min`/`max` output additionally appends "at= <time>",
        # which must not prevent the value from parsing.
        text = "praw_r_min = 4.500000e-01 at= 2.030000e-03"
        self.assertEqual(runner.parse_bare_measurements(text), {"praw_r_min": 0.45})

    def test_non_matching_and_non_numeric_lines_are_skipped(self):
        text = "\n".join(
            [
                "Circuit: * x",
                "rst_min = not_a_number",
                "t_rst = 5.0e-04",
            ]
        )
        self.assertEqual(runner.parse_bare_measurements(text), {"t_rst": 5.0e-04})

    def test_empty_text_yields_no_values(self):
        self.assertEqual(runner.parse_bare_measurements(""), {})


class FindCrossingsTests(unittest.TestCase):
    ROWS = [
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 2.0),  # rises through thresh=1 between t=1 and t=2
        (3.0, 2.0),
        (4.0, -1.0),  # falls through thresh=1 between t=3 and t=4
    ]

    def test_finds_rise_and_fall_with_no_t0(self):
        # run_chatter_probe.py's call shape: no t0, scan every row.
        self.assertEqual(
            runner.find_crossings(self.ROWS, 1, 1.0),
            [(2.0, "rise"), (4.0, "fall")],
        )

    def test_t0_skips_crossings_before_the_given_timestamp(self):
        # run_glitch_probe.py's call shape: skip until t0.
        self.assertEqual(
            runner.find_crossings(self.ROWS, 1, 1.0, t0=2.5),
            [(4.0, "fall")],
        )


class ParseWrdataTraceTests(unittest.TestCase):
    def test_parses_a_well_formed_multi_probe_trace(self):
        # wrdata emits "t v0 t v1 t v2 ..." -- one (t, value) pair per probe.
        text = "\n".join(
            [
                "0.000000e+00 1.0 0.000000e+00 2.0 0.000000e+00 3.0",
                "1.000000e-06 1.1 1.000000e-06 2.1 1.000000e-06 3.1",
            ]
        )
        self.assertEqual(
            runner.parse_wrdata_trace(text, 3),
            [(0.0, 1.0, 2.0, 3.0), (1e-6, 1.1, 2.1, 3.1)],
        )

    def test_skips_a_line_with_the_wrong_field_count(self):
        text = "\n".join(
            [
                "0.000000e+00 1.0 0.000000e+00 2.0",  # short: only 1 probe's worth
                "1.000000e-06 1.1 1.000000e-06 2.1 1.000000e-06 3.1",
            ]
        )
        self.assertEqual(runner.parse_wrdata_trace(text, 3), [(1e-6, 1.1, 2.1, 3.1)])

    def test_skips_a_line_with_a_non_numeric_field(self):
        text = "\n".join(
            [
                "0.000000e+00 not_a_number 0.000000e+00 2.0",
                "1.000000e-06 1.1 1.000000e-06 2.1",
            ]
        )
        self.assertEqual(runner.parse_wrdata_trace(text, 2), [(1e-6, 1.1, 2.1)])

    def test_empty_trace_text_yields_no_rows(self):
        self.assertEqual(runner.parse_wrdata_trace("", 3), [])

    def test_n_probes_genuinely_generalizes_arity(self):
        # A 2-probe caller (e.g. run_depth_sweep.py's 6-tuple PROBES) and a
        # 3-probe caller (run_glitch_probe.py / run_chatter_probe.py) must
        # both parse correctly from the same function, driven only by the
        # n_probes argument -- not a hardcoded arity.
        two_probe_line = "0.0 1.0 0.0 2.0"
        three_probe_line = "0.0 1.0 0.0 2.0 0.0 3.0"
        self.assertEqual(runner.parse_wrdata_trace(two_probe_line, 2), [(0.0, 1.0, 2.0)])
        self.assertEqual(
            runner.parse_wrdata_trace(three_probe_line, 3), [(0.0, 1.0, 2.0, 3.0)]
        )
        # Wrong arity for the given text is correctly rejected either way.
        self.assertEqual(runner.parse_wrdata_trace(two_probe_line, 3), [])
        self.assertEqual(runner.parse_wrdata_trace(three_probe_line, 2), [])


class RemoveNetlistDeviceTests(unittest.TestCase):
    # Mirrors the real convention: a device line optionally followed by
    # ngspice '+' continuation lines, embedded among unrelated lines.
    TEXT = (
        "* preamble\n"
        "XOTHER A B C nfet_03v3\n"
        "XMRLK ND1 RESETn VSS VSS nfet_03v3\n"
        "+ l=0.28u w=3u\n"
        "+ m=1\n"
        "XLAST D E F pfet_03v3\n"
    )

    def test_deletes_the_matching_line_and_its_continuations(self):
        self.assertEqual(
            runner.remove_netlist_device(self.TEXT, "XMRLK ND1 RESETn VSS VSS nfet_03v3", "dut.spice"),
            "* preamble\nXOTHER A B C nfet_03v3\nXLAST D E F pfet_03v3\n",
        )

    def test_a_line_with_no_continuations_is_deleted_alone(self):
        text = "A\nXHEAD rest of line\nB\n"
        self.assertEqual(
            runner.remove_netlist_device(text, "XHEAD", "dut.spice"), "A\nB\n"
        )

    def test_no_match_raises_with_the_source_named(self):
        with self.assertRaises(SystemExit) as ctx:
            runner.remove_netlist_device("no such device here\n", "XMRLK", "dut.spice")
        self.assertIn("found 0", str(ctx.exception))
        self.assertIn("dut.spice", str(ctx.exception))

    def test_multiple_matches_raises_with_the_count(self):
        text = "XMRLK one\nXMRLK two\n"
        with self.assertRaises(SystemExit) as ctx:
            runner.remove_netlist_device(text, "XMRLK", "dut.spice")
        self.assertIn("found 2", str(ctx.exception))


class _StubPoint:
    def __init__(self, corner_id):
        self.corner_id = corner_id


class _StubResult:
    def __init__(self, corner_id, measurements, status="ok"):
        self.point = _StubPoint(corner_id)
        self.measurements = measurements
        self.status = status


class ChecksTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            _StubResult("a", {"v": 1.0}),
            _StubResult("b", {"v": 1.2}),
            _StubResult("c", {"v": 0.8}),
        ]
        self.summary = report.summarize(self.results, ["v"])

    def test_summary_finds_the_extremes(self):
        stats = self.summary["v"]
        self.assertEqual((stats["min"], stats["min_at"]), (0.8, "c"))
        self.assertEqual((stats["max"], stats["max_at"]), (1.2, "b"))
        self.assertAlmostEqual(stats["spread_pct"], 40.0)

    def test_min_max_violations_are_reported_with_their_corner(self):
        failures = report.evaluate_checks({"v": {"min": 0.9}}, self.results, self.summary)
        self.assertEqual(len(failures), 1)
        self.assertEqual((failures[0]["kind"], failures[0]["at"]), ("min", "c"))

    def test_max_spread_violation(self):
        failures = report.evaluate_checks(
            {"v": {"max_spread_pct": 10.0}}, self.results, self.summary
        )
        self.assertEqual(failures[0]["kind"], "max_spread_pct")

    def test_min_spread_catches_a_grid_that_never_moved(self):
        flat = [_StubResult("a", {"v": 1.0}), _StubResult("b", {"v": 1.0})]
        summary = report.summarize(flat, ["v"])
        failures = report.evaluate_checks({"v": {"min_spread_pct": 5.0}}, flat, summary)
        self.assertEqual(failures[0]["kind"], "min_spread_pct")

    def test_passing_checks_produce_no_failures(self):
        self.assertEqual(
            report.evaluate_checks(
                {"v": {"min": 0.5, "max": 1.5, "max_spread_pct": 50.0}},
                self.results,
                self.summary,
            ),
            [],
        )


class RecordIdTests(unittest.TestCase):
    def test_record_id_matches_the_ratified_shape(self):
        """sim/README.md: <record-id> is <YYYYMMDD>-<HHMMSS>-<short-git-sha>."""
        when = datetime.datetime(2026, 7, 29, 15, 30, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(report.format_record_id("1a7ef75", when), "20260729-153000-1a7ef75")
        self.assertRegex(
            report.format_record_id("1a7ef75", when), r"^\d{8}-\d{6}-[0-9a-f]{7}$"
        )

    def test_allocation_never_reuses_an_existing_record_id(self):
        when = datetime.datetime(2026, 7, 29, 15, 30, 0, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp)
            first = report.allocate_record_id(SIM_DIR, records, when)
            (records / f"{first}.md").write_text("# first\n")
            second = report.allocate_record_id(SIM_DIR, records, when)
            self.assertNotEqual(first, second)
            self.assertRegex(second, r"^\d{8}-\d{6}-")
            # the existing record was not touched
            self.assertEqual((records / f"{first}.md").read_text(), "# first\n")

    def test_write_record_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "an-experiment"
            (experiment / report.RECORDS_DIR).mkdir(parents=True)
            (experiment / report.RECORDS_DIR / "20260729-153000-abc1234.md").write_text("keep\n")
            with self.assertRaises(report.RecordExists):
                report.write_record(
                    {"record_id": "20260729-153000-abc1234"}, experiment
                )


class MatrixConformanceTests(unittest.TestCase):
    """sim/README.md requires the full mandated matrix, or a stated reason."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tb_dir = Path(self.tmp.name) / "an-experiment" / "testbench"
        tb_dir.mkdir(parents=True)
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps({"name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)"}})
        )
        self.tb = testbench.load(tb_dir)

    def _grid(self, corner_names, temps, supplies):
        return corners.build_grid(corners.resolve_corners(corner_names), temps, supplies)

    def test_full_matrix_is_recognised(self):
        grid = self._grid(["mos"], (-40, 27, 125), corners.supply_points(3.3, 0.10))
        self.assertEqual(report.matrix_conformance(self.tb, grid), {"full": True, "missing": []})

    def test_missing_temperature_is_flagged(self):
        grid = self._grid(["mos"], (27,), corners.supply_points(3.3, 0.10))
        result = report.matrix_conformance(self.tb, grid)
        self.assertFalse(result["full"])
        self.assertTrue(any("temperature" in m for m in result["missing"]))

    def test_missing_supply_and_process_are_flagged(self):
        grid = self._grid(["tt"], (-40, 27, 125), [3.3])
        result = report.matrix_conformance(self.tb, grid)
        self.assertFalse(result["full"])
        self.assertTrue(any("supply" in m for m in result["missing"]))
        self.assertTrue(any("process" in m for m in result["missing"]))

    def test_full_grid_with_every_point_dead_is_still_a_full_matrix(self):
        """matrix_conformance (grid shape) and total_failure (point outcomes)
        are orthogonal -- a full-shaped grid where every point errored is
        still "full" here; it's report.total_failure() that catches it."""
        grid = self._grid(["full"], (-40, 27, 125), corners.supply_points(3.3, 0.10))
        result = report.matrix_conformance(self.tb, grid)
        self.assertTrue(result["full"])


class TotalFailureTests(unittest.TestCase):
    """#193: a run where every point died is an environment problem, not
    simulation evidence -- the same treatment an unjustified PVT subset
    already gets, via a distinct, orthogonal signal."""

    def test_every_point_errored_is_a_total_failure(self):
        results = [
            runner.PointResult(point=_StubPoint("a"), status="error", message="timed out"),
            runner.PointResult(point=_StubPoint("b"), status="error", message="timed out"),
        ]
        self.assertTrue(report.total_failure(results))

    def test_every_point_failed_or_errored_is_a_total_failure(self):
        """"failed" (ran, but no measurement parsed) counts the same as
        "error" (didn't run to completion) -- neither is "ok"."""
        results = [
            runner.PointResult(point=_StubPoint("a"), status="failed", message="no meas"),
            runner.PointResult(point=_StubPoint("b"), status="error", message="timed out"),
        ]
        self.assertTrue(report.total_failure(results))

    def test_one_ok_point_among_many_dead_ones_is_not_a_total_failure(self):
        """0 < points_ok < len(results) is the ordinary, recordable mixed
        case (status "error", exit 2) -- this guard must not over-tighten
        and refuse that too."""
        results = [
            runner.PointResult(point=_StubPoint("a"), status="ok", measurements={"v": 1.0}),
            runner.PointResult(point=_StubPoint("b"), status="error", message="timed out"),
            runner.PointResult(point=_StubPoint("c"), status="error", message="timed out"),
        ]
        self.assertFalse(report.total_failure(results))

    def test_all_points_ok_is_not_a_total_failure(self):
        results = [
            runner.PointResult(point=_StubPoint("a"), status="ok", measurements={"v": 1.0}),
            runner.PointResult(point=_StubPoint("b"), status="ok", measurements={"v": 1.1}),
        ]
        self.assertFalse(report.total_failure(results))

    def test_no_points_at_all_is_not_a_total_failure(self):
        """Nothing to have failed -- distinct from "ran and every point died"."""
        self.assertFalse(report.total_failure([]))


class RecordRenderingTests(unittest.TestCase):
    """The rendered record carries exactly the fields sim/README.md lists."""

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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        tb_dir = root / "smoke-bias" / "testbench"
        tb_dir.mkdir(parents=True)
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps(
                {
                    "name": "smoke-bias",
                    "netlist": "x.spice",
                    "measure": {"vout": "v(out)"},
                    "checks": {"vout": {"min": 0.0, "max": 10.0}},
                }
            )
        )
        self.tb = testbench.load(tb_dir)
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.points = corners.build_grid(
            corners.resolve_corners(["mos"]), (-40, 27, 125), corners.supply_points(3.3, 0.10)
        )
        self.results = [
            runner.PointResult(point=p, status="ok", measurements={"vout": 1.0 + i * 0.01})
            for i, p in enumerate(self.points)
        ]
        self.record = report.build_record(
            tb=self.tb,
            pdk=self.pdk,
            points=self.points,
            results=self.results,
            ngspice="ngspice-46",
            repo_root=SIM_DIR,
            record_id="20260729-153000-1a7ef75",
            started_utc="2026-07-29T15:30:00+00:00",
            wall_seconds=9.5,
            claim="spec/temp-por.md#example",
        )

    def test_every_ratified_field_is_present_and_in_order(self):
        text = report.render_record(self.record, "smoke-bias")
        positions = []
        for field in self.RATIFIED_FIELDS:
            marker = f"**{field}**"
            self.assertIn(marker, text, f"missing ratified field {field!r}")
            positions.append(text.index(marker))
        self.assertEqual(positions, sorted(positions), "fields are out of ratified order")

    def test_links_point_at_the_ratified_paths(self):
        text = report.render_record(self.record, "smoke-bias")
        self.assertIn("sim/smoke-bias/testbench/x.spice", text)
        self.assertIn("sim/smoke-bias/netlist-snapshots/20260729-153000-1a7ef75.spice", text)
        self.assertIn("sim/smoke-bias/corners/20260729-153000-1a7ef75/", text)

    def test_result_table_uses_corner_ids_and_reports_overall_verdict(self):
        text = report.render_record(self.record, "smoke-bias")
        self.assertIn("`tt_-40c_2.97v`", text)
        self.assertIn("`ff_125c_3.63v`", text)
        self.assertIn("**Overall: PASS**", text)

    def test_a_full_matrix_run_says_so(self):
        text = report.render_record(self.record, "smoke-bias")
        self.assertIn("Full PVT matrix per CLAUDE.md", text)

    def test_environment_section_names_the_real_pdk_provenance(self):
        text = report.render_record(self.record, "smoke-bias")
        provenance = self.pdk.provenance()
        self.assertIn(str(provenance["open_pdks_version"]), text)
        self.assertIn(provenance["variant"], text)
        self.assertNotIn("open_pdks `None`", text)

    def test_git_state_is_taken_from_the_caller_not_resampled(self):
        """The harness dirties the tree by writing logs; provenance is pre-run."""
        pre_run = {"commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": False}
        env = report.environment(self.pdk, "ngspice-46", SIM_DIR, pre_run)
        self.assertEqual(env["git"], pre_run)

    def test_a_dirty_tree_is_called_out_in_netlist_provenance(self):
        dirty = dict(self.record)
        dirty["environment"] = dict(self.record["environment"])
        dirty["environment"]["git"] = {
            "commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": True,
        }
        text = report.render_record(dirty, "smoke-bias")
        self.assertIn("dirty working tree", text)

    def test_a_derived_record_quotes_its_source_record_not_a_manifest(self):
        """Since #86 an experiment has two manifests; a derivation has one DUT.

        The source record is append-only, so quoting it is the only answer
        that cannot be retroactively changed by a later manifest.
        """
        experiment = self.tb.experiment_dir
        records = experiment / report.RECORDS_DIR
        records.mkdir(parents=True, exist_ok=True)
        (records / "20260729-153000-1a7ef75.md").write_text(
            "# Record 20260729-153000-1a7ef75\n\n"
            "- **Netlist provenance**: schematic (`sim/smoke-bias/testbench/x.spice`)\n"
        )
        self.assertEqual(
            report.source_provenance(experiment, "20260729-153000-1a7ef75"),
            "schematic (`sim/smoke-bias/testbench/x.spice`)",
        )

    def test_an_extracted_source_records_caveat_is_carried_through(self):
        experiment = self.tb.experiment_dir
        records = experiment / report.RECORDS_DIR
        records.mkdir(parents=True, exist_ok=True)
        (records / "20260811-120000-1a7ef75.md").write_text(
            "# Record\n\n- **Netlist provenance**: extracted "
            "(`sim/smoke-bias/testbench-postlayout/x.spice`) — XCC is IDEAL, "
            "not drawn; 4 body nets tied per AUDIT.md\n"
        )
        got = report.source_provenance(experiment, "20260811-120000-1a7ef75")
        self.assertTrue(got.startswith("extracted"))
        self.assertIn("XCC is IDEAL", got)

    def test_an_unreadable_source_record_is_reported_not_guessed(self):
        got = report.source_provenance(self.tb.experiment_dir, "20260729-000000-nosuch")
        self.assertIn("unknown", got)

    def test_a_source_record_with_no_provenance_field_is_reported(self):
        experiment = self.tb.experiment_dir
        records = experiment / report.RECORDS_DIR
        records.mkdir(parents=True, exist_ok=True)
        (records / "20260729-160000-1a7ef75.md").write_text("# Record\n\nnothing here\n")
        got = report.source_provenance(experiment, "20260729-160000-1a7ef75")
        self.assertIn("states no", got)

    def test_netlist_snapshot_is_frozen_and_append_only(self):
        experiment = self.tb.experiment_dir
        path = report.write_netlist_snapshot(self.tb, experiment, "20260729-153000-1a7ef75")
        self.assertEqual(path.parent.name, report.SNAPSHOT_DIR)
        self.assertIn("v1 out 0 dc {vdd_val}", path.read_text())
        self.assertIn(self.tb.netlist_sha256, path.read_text())
        with self.assertRaises(report.RecordExists):
            report.write_netlist_snapshot(self.tb, experiment, "20260729-153000-1a7ef75")


class ExtractedProvenanceRenderingTests(unittest.TestCase):
    """#86: a post-layout (extracted) record says so, carries its caveat, and
    points at its own (non-"testbench"-named) testbench subdirectory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        tb_dir = root / "por-output-chain-pulse" / "testbench-postlayout"
        tb_dir.mkdir(parents=True)
        (tb_dir / "y.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps(
                {
                    "name": "por-output-chain-pulse",
                    "netlist": "y.spice",
                    "measure": {"vout": "v(out)"},
                    "checks": {"vout": {"min": 0.0, "max": 10.0}},
                    "netlist_provenance": "extracted",
                    "netlist_provenance_note": "0 ideal devices, per layout/postlayout/AUDIT.md",
                }
            )
        )
        self.tb = testbench.load(tb_dir)
        self.pdk = fake_pdk(root / "gf180mcuD")
        points = corners.build_grid(
            corners.resolve_corners(["mos"]), (-40, 27, 125), corners.supply_points(3.3, 0.10)
        )
        results = [
            runner.PointResult(point=p, status="ok", measurements={"vout": 1.0})
            for p in points
        ]
        self.record = report.build_record(
            tb=self.tb,
            pdk=self.pdk,
            points=points,
            results=results,
            ngspice="ngspice-46",
            repo_root=SIM_DIR,
            record_id="20260811-000000-1a7ef75",
            started_utc="2026-08-11T00:00:00+00:00",
            wall_seconds=1.0,
            claim="spec/target-spec.md#por-reset-pulse",
            git={"commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": False},
        )

    def test_provenance_line_says_extracted_and_carries_the_caveat(self):
        text = report.render_record(self.record, "por-output-chain-pulse")
        self.assertIn(
            "**Netlist provenance**: extracted "
            "(`sim/por-output-chain-pulse/testbench-postlayout/y.spice`)",
            text,
        )
        self.assertIn("0 ideal devices, per layout/postlayout/AUDIT.md", text)

    def test_links_use_the_actual_testbench_subdirectory_not_the_schematic_default(self):
        text = report.render_record(self.record, "por-output-chain-pulse")
        self.assertIn("sim/por-output-chain-pulse/testbench-postlayout/y.spice", text)
        self.assertIn("sim/por-output-chain-pulse/testbench-postlayout/tb.json", text)
        self.assertNotIn("testbench/y.spice", text)


class CliTotalFailureRefusalTests(unittest.TestCase):
    """#193: ``cli.run()`` refuses to write evidence -- and cleans up the raw
    per-corner logs ``run_grid`` already wrote before the outcome was known
    -- when every point in the run died, instead of quietly banking a
    total-failure run as if it were simulation evidence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.experiment_dir = root / "total-failure-tb"
        tb_dir = self.experiment_dir / "testbench"
        tb_dir.mkdir(parents=True)
        (tb_dir / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tb_dir / "tb.json").write_text(
            json.dumps(
                {"name": "total-failure-tb", "netlist": "x.spice", "measure": {"vout": "v(out)"}}
            )
        )
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.parser = cli.build_parser()

        for obj, name, value in (
            (cli, "WORK_DIR", root / ".work"),
            (cli, "find_pdk", lambda: self.pdk),
            (cli.runner, "ngspice_version", lambda: "ngspice-test"),
        ):
            patcher = mock.patch.object(obj, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, corner_names, statuses, extra_args=()):
        """Run ``cli.run()`` with ``run_grid`` faked to return one
        ``PointResult`` per entry of ``statuses`` (grid-order), replaying
        ``run_point``'s real side effect of writing a log file into
        ``log_dir`` as each point completes -- *before* the caller knows
        whether the run, overall, is a total failure."""
        args = self.parser.parse_args(
            [
                str(self.experiment_dir),
                "--corners", *corner_names,
                "--temps", "27",
                "--supply-tol", "0",
                "--subset-reason", "cli guard test -- not evidence",
                *extra_args,
            ]
        )

        def fake_run_grid(tb, pdk, points, workdir, jobs=1, timeout_s=0, on_result=None,
                           log_dir=None):
            results = []
            for point, status in zip(points, statuses):
                if log_dir is not None:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    (log_dir / f"{point.corner_id}.log").write_text("TIMEOUT after 1s\n")
                result = runner.PointResult(
                    point=point,
                    status=status,
                    measurements={"vout": 1.0} if status == "ok" else {},
                    message="" if status == "ok" else "ngspice timed out after 1s",
                )
                results.append(result)
                if on_result is not None:
                    on_result(result)
            return results

        with mock.patch.object(cli.runner, "run_grid", side_effect=fake_run_grid):
            return cli.run(args)

    def test_total_failure_is_refused_and_exits_environment(self):
        exit_code = self._run(["tt"], ["error"])
        self.assertEqual(exit_code, cliutil.EXIT_ENVIRONMENT)

    def test_total_failure_writes_no_record_snapshot_or_corner_logs(self):
        self._run(["tt"], ["error"])
        self.assertFalse((self.experiment_dir / report.RECORDS_DIR).exists())
        self.assertFalse((self.experiment_dir / report.SNAPSHOT_DIR).exists())
        self.assertEqual(list(self.experiment_dir.rglob("*.log")), [])

    def test_supersedes_on_a_total_failure_run_is_also_refused(self):
        """A total-failure run must never be able to supersede a passing
        record -- the guard fires before the snapshot or the record (which
        is what would carry --supersedes) is written at all."""
        exit_code = self._run(
            ["tt"], ["error"], extra_args=["--supersedes", "20260101-000000-abc1234"]
        )
        self.assertEqual(exit_code, cliutil.EXIT_ENVIRONMENT)
        self.assertFalse((self.experiment_dir / report.RECORDS_DIR).exists())

    def test_partial_failure_still_writes_and_exits_sim_error(self):
        """0 < points_ok < len(points) is the ordinary, recordable mixed
        case -- this guard must not over-tighten and refuse that too."""
        exit_code = self._run(["tt", "ff"], ["ok", "error"])
        self.assertEqual(exit_code, cliutil.EXIT_SIM_ERROR)
        records = list((self.experiment_dir / report.RECORDS_DIR).glob("*.md"))
        self.assertEqual(len(records), 1)
        self.assertIn("ERROR", records[0].read_text())

    def test_no_write_still_runs_without_triggering_the_refusal_path(self):
        """--no-write is the existing debugging escape hatch: it must keep
        working unchanged -- run, report, write nothing -- rather than the
        new guard forcing EXIT_ENVIRONMENT on top of it."""
        exit_code = self._run(["tt"], ["error"], extra_args=["--no-write"])
        self.assertEqual(exit_code, cliutil.EXIT_SIM_ERROR)
        self.assertFalse((self.experiment_dir / report.RECORDS_DIR).exists())


class DefaultJobsTests(unittest.TestCase):
    """Issue #184: the -j/--jobs default must leave headroom, not claim every
    core -- and must never regress back to a fixed 8 or to unbounded
    parallelism on a high-core-count host."""

    def test_halves_the_host_core_count(self):
        self.assertEqual(cliutil.default_jobs(cpu_count=8), 4)
        self.assertEqual(cliutil.default_jobs(cpu_count=16), 8)
        self.assertEqual(cliutil.default_jobs(cpu_count=64), 32)

    def test_floors_odd_core_counts(self):
        self.assertEqual(cliutil.default_jobs(cpu_count=9), 4)

    def test_never_drops_below_one(self):
        self.assertEqual(cliutil.default_jobs(cpu_count=1), 1)
        self.assertEqual(cliutil.default_jobs(cpu_count=0), 1)

    def test_does_not_regress_to_the_old_fixed_eight_on_a_small_host(self):
        # The pre-#184 default was min(8, cpu_count) -- on a 2-core host that
        # resolved to 2, the same as the new default; the regression this
        # guards is a *larger* host still capping at a fixed value instead of
        # scaling with available cores.
        self.assertEqual(cliutil.default_jobs(cpu_count=2), 1)

    def test_scales_with_high_core_counts_instead_of_capping_at_eight(self):
        # The old `min(8, os.cpu_count() or 2)` default silently capped at 8
        # regardless of host size. The new default must not reintroduce that
        # cap -- it should keep scaling (with headroom) on a larger host.
        self.assertGreater(cliutil.default_jobs(cpu_count=32), 8)

    def test_falls_back_to_os_cpu_count_when_not_given(self):
        # cpu_count=None resolves via os.cpu_count() (with the pre-existing
        # `or 2` fallback for a host where that returns None) rather than
        # raising or silently defaulting to a fixed number.
        self.assertGreaterEqual(cliutil.default_jobs(), 1)


if __name__ == "__main__":
    unittest.main()
