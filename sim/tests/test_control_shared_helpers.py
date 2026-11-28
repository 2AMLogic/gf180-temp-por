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
    starts" column under ``sim/por-brownout-slew/control/``;
  * ``window_close_us`` / ``margin_to_close_us`` / ``resetn_verdict`` /
    ``fmt_us`` (#682) decide that directory's remaining shared vocabulary:
    the clock the dip window closes on, the margin every report races
    against it, the PASS/FAIL word for the manifest's
    ``resetn_ratio_min_in_dip`` bound, and the "**never**" spelling of an
    absent event time. All four existed as one hand-copied set per control
    before #682, and one copy (``run_postlayout_margin.py``'s verdict) had
    already drifted to a hardcoded bound.

``ReportRegenerationTests`` is #682's other half: those four helpers feed
all four ``write_results()`` implementations in that directory, so the
regression a consolidation could introduce is "same committed logs, same
manifest, a different report". Those tests re-run each ``write_results()``
headlessly (stub PDK, fixed date, no ngspice) and byte-compare against the
committed results files -- see that class's docstring for the two files
whose comparison is scoped to their log-derived content, and why.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import math
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

#: (control directory, helper name, the module that must be its one home).
SHARED_HELPERS = [
    ("por-output-chain-deglitch/control", "verdict", "_deglitch_criterion.py"),
    ("por-vth/control", "static_and_slope", "run_ramp_rate_probe.py"),
    ("por-brownout-slew/control", "us_after_dip", "run_band_mechanism.py"),
    ("por-brownout-slew/control", "window_close_us", "run_band_mechanism.py"),
    ("por-brownout-slew/control", "margin_to_close_us", "run_band_mechanism.py"),
    ("por-brownout-slew/control", "resetn_verdict", "run_band_mechanism.py"),
    ("por-brownout-slew/control", "fmt_us", "run_band_mechanism.py"),
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


class WindowCloseAndMarginTests(unittest.TestCase):
    """The dip window's close, and the margin left when `RESETn` makes it.

    Every report under ``sim/por-brownout-slew/control/`` races `RESETn`
    valid-low against ``window_close_us`` and prints the gap as *margin to
    close*; #682 gave both one definition in ``run_band_mechanism.py``.
    """

    def setUp(self):
        d = SIM_DIR / "por-brownout-slew" / "control"
        self.mod = _load(d / "run_band_mechanism.py", "run_band_mechanism")

    def test_close_is_the_edge_plus_the_dwell(self):
        vdd, slew = 3.3, 3.0
        self.assertAlmostEqual(
            self.mod.window_close_us(vdd, slew)
            - self.mod.edge_s(vdd, slew) * 1e6,
            self.mod.T_DWELL_S * 1e6,
        )
        # A slower slew needs a longer edge to fall the same delta_V, so its
        # window closes later -- the direction every margin column depends on.
        self.assertGreater(
            self.mod.window_close_us(vdd, slew / 2),
            self.mod.window_close_us(vdd, slew),
        )

    def test_margin_is_the_close_minus_the_valid_low_time(self):
        vdd, slew = 3.3, 3.0
        margin = self.mod.margin_to_close_us(vdd, slew, self.mod.T_DIP_S + 40e-6)
        self.assertAlmostEqual(
            margin, self.mod.window_close_us(vdd, slew) - 40.0
        )

    def test_margin_changes_sign_at_the_decks_exact_close(self):
        for vdd, slew in ((3.30, 2.45), (3.63, 3.40)):
            with self.subTest(vdd=vdd, slew=slew):
                close = self.mod.T_DIP_S + self.mod.edge_s(vdd, slew) + self.mod.T_DWELL_S
                before = math.nextafter(close, -math.inf)
                after = math.nextafter(close, math.inf)
                self.assertGreater(self.mod.margin_to_close_us(vdd, slew, before), 0.0)
                self.assertEqual(self.mod.margin_to_close_us(vdd, slew, close), 0.0)
                self.assertLess(self.mod.margin_to_close_us(vdd, slew, after), 0.0)

    def test_margin_is_negative_once_the_window_has_closed(self):
        vdd, slew = 3.3, 3.0
        t_after = (
            self.mod.T_DIP_S + self.mod.edge_s(vdd, slew)
            + self.mod.T_DWELL_S + 10e-6
        )
        self.assertLess(self.mod.margin_to_close_us(vdd, slew, t_after), 0.0)

    def test_an_absent_valid_low_measurement_gives_no_margin(self):
        """None in, None out: "`RESETn` never reached valid-low" is a
        different statement from "it reached it exactly at the close", and
        the reports spell the two differently ("—" vs "0.0")."""
        self.assertIsNone(self.mod.margin_to_close_us(3.3, 3.0, None))


class PostlayoutMarginReportTests(unittest.TestCase):
    def setUp(self):
        control = SIM_DIR / "por-brownout-slew" / "control"
        self.plm = _load(control / "run_postlayout_margin.py", "run_postlayout_margin")

    def report(self, row, bound):
        band = self.plm.band
        manifest = {"checks": {band.RESETN_RATIO_KEY: {"max": bound}}}
        pdk = SimpleNamespace(variant="test", version="test")
        results = {self.plm.variant_name("sch", 3.30, 2.45): row}
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(self.plm, "CONTROL_DIR", Path(tmp)):
                self.plm.write_results(pdk, manifest, results)
            return (Path(tmp) / "postlayout_margin_results.md").read_text()

    def test_schematic_margin_cell_flags_an_event_at_close(self):
        band = self.plm.band
        close = band.T_DIP_S + band.edge_s(3.30, 2.45) + band.T_DWELL_S
        report = self.report({"t_rst": close}, bound=0.1)
        self.assertIn("| +0.0 **FAIL** |", report)

    def test_report_prints_the_manifest_bound_used_for_the_verdict(self):
        report = self.report({"rst_r_min": 0.15}, bound=0.2)
        self.assertIn("bounded at 0.2.", report)
        self.assertIn("| 0.1500 | PASS |", report)


class ResetnVerdictTests(unittest.TestCase):
    """The one PASS/FAIL word for `resetn_ratio_min_in_dip` (#682)."""

    def setUp(self):
        d = SIM_DIR / "por-brownout-slew" / "control"
        self.mod = _load(d / "run_band_mechanism.py", "run_band_mechanism")

    def test_a_ratio_exactly_on_the_bound_is_the_pass_word(self):
        """``<=``, the grid's own comparison: a rung landing exactly on the
        manifest bound gets the milder word, not a coin-flip between four
        hand-copied spellings of the comparison."""
        self.assertEqual(self.mod.resetn_verdict(0.1, 0.1), "PASS")

    def test_a_ratio_under_the_bound_passes(self):
        self.assertEqual(self.mod.resetn_verdict(0.0, 0.1), "PASS")
        self.assertEqual(self.mod.resetn_verdict(0.0999, 0.1), "PASS")

    def test_a_ratio_over_the_bound_fails(self):
        self.assertEqual(self.mod.resetn_verdict(0.1000001, 0.1), "**FAIL**")
        self.assertEqual(self.mod.resetn_verdict(1.0, 0.1), "**FAIL**")

    def test_an_absent_measurement_is_an_em_dash_not_a_verdict(self):
        self.assertEqual(self.mod.resetn_verdict(None, 0.1), "—")


class FmtUsTests(unittest.TestCase):
    """The one spelling of an event-time cell (#682)."""

    def setUp(self):
        d = SIM_DIR / "por-brownout-slew" / "control"
        self.mod = _load(d / "run_band_mechanism.py", "run_band_mechanism")

    def test_an_absent_event_is_never_not_zero(self):
        """The two statements answer different questions: the event did not
        happen vs it happened at 0.0 µs."""
        self.assertEqual(self.mod.fmt_us(None), "**never**")

    def test_one_digit_by_default(self):
        self.assertEqual(self.mod.fmt_us(303.36), "303.4")
        self.assertEqual(self.mod.fmt_us(-45.04), "-45.0")

    def test_digits_selects_the_precision(self):
        """``run_band_mechanism.py``'s part B renders its Δ column with 2 --
        the parameter exists for that caller and must keep working."""
        self.assertEqual(self.mod.fmt_us(2.346, 2), "2.35")


# --------------------------------------------------------------------------
# #682's regression half: same committed logs in, same report out.
# --------------------------------------------------------------------------

_NETLIST_SHA_RE = re.compile(r"sha256 `[0-9a-f]+…`")


def _mask_netlist_shas(text: str) -> str:
    """``text`` with every ``sha256 `…``` provenance fragment blanked.

    ``results.md``'s DUT-netlist sha line records the netlist its committed
    decks were generated against; ``design/netlist/temp_por_top.spice`` has
    changed since, so that one line cannot regenerate from the committed
    logs (the tables do -- only the hash of the file the decks named has
    moved). Masked on both sides, the comparison covers exactly the cells
    the consolidated helpers feed.
    """
    return _NETLIST_SHA_RE.sub("sha256 `<masked>`", text)


def _from_section_2(text: str) -> str:
    """``text`` from its "## 2 —" heading on, trailing blank line stripped.

    ``net_attribution_results.md``'s hand-added #316 note and its section 1
    (anchor-netlist shas, parasitic-model prose, the ΣC/ΣR table) describe
    the CURRENT ``layout/postlayout/`` extraction, while the committed rows
    were measured against the pre-#314 one -- the note block in the file
    says exactly that, and section 1's per-arm numbers are recomputed from
    the current netlist by design. Everything from section 2 on is read out
    of the committed logs, the manifest and arithmetic, and must regenerate
    byte-for-byte. The trailing blank line is stripped because the committed
    file has carried one since its first commit that
    ``write_text(... + "\n")`` never writes.
    """
    return text[text.index("## 2 —"):].rstrip("\n")


def _fixed_datetime(committed: str) -> SimpleNamespace:
    """A ``datetime`` stand-in whose ``today()`` is the report's own date.

    ``run_por_edge_check.write_results()`` stamps the day it ran; the
    committed report's own stamp is the date to regenerate with, so the
    test does not fail merely because days pass. Patched over the module's
    ``datetime`` name, never the real stdlib.
    """
    import datetime

    m = re.search(r"on (\d{4}-\d{2}-\d{2})", committed)
    fixed = datetime.date.fromisoformat(m.group(1))

    class _Date(datetime.date):
        @classmethod
        def today(cls):
            return fixed

    return SimpleNamespace(date=_Date)


class ReportRegenerationTests(unittest.TestCase):
    """The four consolidated helpers must not move a byte of the reports.

    #682 replaced the four hand-copied window-close / margin / verdict /
    fmt helpers inside this directory's four ``write_results()``
    implementations with one shared set in ``run_band_mechanism.py``. The
    failure mode consolidation can introduce is precise: the committed
    ``logs/`` parse the same, the manifest reads the same, but a report now
    prints a different digit or word. So each test below re-runs one
    ``write_results()`` headlessly -- stub PDK, no ngspice, no PDK install
    -- against the committed logs and byte-compares with the committed
    results file, which is the "generated, never transcribed twice" rule
    (sim/README.md) turned into a check that survives the code motion.

    The stub inputs are read back out of the committed file itself (its
    PDK line, and for ``run_por_edge_check.py`` its generation date), so
    the comparison pins the tables, not which PDK install or day produced
    them: a control legitimately re-run updates both sides together, and
    the test fails only when logs and report actually disagree.

    Two comparisons are scoped rather than whole-file, for input drift the
    committed files themselves document -- ``_mask_netlist_shas`` (the
    design netlist has changed since ``results.md`` was generated) and
    ``_from_section_2`` (``net_attribution_results.md``'s note and
    section 1 belong to a different extraction than its rows were measured
    against).
    """

    CONTROL = SIM_DIR / "por-brownout-slew" / "control"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)

    def _stub_pdk(self, committed: str):
        """A Pdk whose variant/version are the ones the report records."""
        from harness.pdk import Pdk

        m = re.search(r"`(gf180mcu\w+)` @ `([^`]+)`", committed)
        self.assertIsNotNone(m, "committed report has no PDK line to stub")
        root = self.out / "pdk" / m.group(1)
        root.mkdir(parents=True)
        if m.group(2) != "unknown":
            (root / "SOURCES").write_text(f"open_pdks {m.group(2)}\n")
        return Pdk(path=root, variant=m.group(1), source="unit test")

    def test_band_mechanism_report_reproduces_from_the_committed_logs(self):
        band = _load(self.CONTROL / "run_band_mechanism.py", "run_band_mechanism")
        from harness import cliutil, runner

        manifest = cliutil.load_manifest(band.MANIFEST)
        results = runner.read_bare_logs(self.CONTROL)
        committed_md = (self.CONTROL / "results.md").read_text()
        committed_json = (self.CONTROL / "results.json").read_text()
        with unittest.mock.patch.object(band, "CONTROL_DIR", self.out):
            band.write_results(self._stub_pdk(committed_md), manifest, results)

        self.assertEqual(
            (self.out / "results.json").read_text(), committed_json,
            "results.json no longer regenerates byte-identically from the "
            "committed logs -- the #682 consolidation changed a recorded "
            "number, not just where a helper lives",
        )
        self.assertEqual(
            _mask_netlist_shas((self.out / "results.md").read_text()),
            _mask_netlist_shas(committed_md),
            "results.md no longer regenerates identically from the committed "
            "logs (the netlist sha line is masked -- see "
            "_mask_netlist_shas); the tables the consolidated helpers feed "
            "must not have moved",
        )

    def test_net_attribution_report_tables_reproduce_from_the_logs(self):
        rna = _load(self.CONTROL / "run_net_attribution.py", "run_net_attribution")
        from harness import cliutil, runner

        manifest = cliutil.load_manifest(rna.band.MANIFEST)
        parasitics = rna.parasitics_by_net(rna.EXTRACTED)
        variants = rna.build_variants(parasitics)
        results = runner.read_bare_logs(self.CONTROL, "na-*.log")
        committed = (self.CONTROL / "net_attribution_results.md").read_text()
        with unittest.mock.patch.object(rna, "CONTROL_DIR", self.out):
            rna.write_results(
                self._stub_pdk(committed), manifest, variants, parasitics,
                results,
            )

        self.assertEqual(
            _from_section_2(
                (self.out / "net_attribution_results.md").read_text()
            ),
            _from_section_2(committed),
            "net_attribution_results.md's log-derived sections (2 onward) no "
            "longer regenerate from the committed logs -- the consolidated "
            "helpers changed a margin, verdict or event-time cell",
        )

    def test_por_edge_check_report_reproduces_from_the_committed_logs(self):
        edge = _load(self.CONTROL / "run_por_edge_check.py", "run_por_edge_check")
        from harness import cliutil, runner

        results = runner.read_bare_logs(self.CONTROL, "edge-*.log")
        committed = (self.CONTROL / "por_edge_check_results.md").read_text()
        out_md = self.out / "por_edge_check_results.md"
        with unittest.mock.patch.object(edge, "RESULTS_MD", out_md), \
                unittest.mock.patch.object(
                    edge, "datetime", _fixed_datetime(committed)
                ):
            edge.write_results(
                self._stub_pdk(committed),
                cliutil.load_manifest(edge.band.MANIFEST)["options"],
                results,
            )

        self.assertEqual(
            out_md.read_text(), committed,
            "por_edge_check_results.md no longer regenerates byte-identically "
            "from the committed logs (stub PDK, the file's own date) -- the "
            "consolidated helpers changed a margin, verdict or event-time "
            "cell",
        )

    def test_postlayout_margin_report_reproduces_from_the_committed_logs(self):
        plm = _load(
            self.CONTROL / "run_postlayout_margin.py", "run_postlayout_margin"
        )
        from harness import cliutil, runner

        manifest = cliutil.load_manifest(plm.band.MANIFEST)
        results = runner.read_bare_logs(self.CONTROL, "pl-*.log")
        committed = (self.CONTROL / "postlayout_margin_results.md").read_text()
        with unittest.mock.patch.object(plm, "CONTROL_DIR", self.out):
            plm.write_results(self._stub_pdk(committed), manifest, results)

        self.assertEqual(
            (self.out / "postlayout_margin_results.md").read_text(), committed,
            "postlayout_margin_results.md no longer regenerates "
            "byte-identically from the committed logs. Its grid-verdict "
            "column now reads the manifest bound via band.bound_for rather "
            "than a hardcoded 0.1 (#682), so a mismatch here means either a "
            "helper changed a cell or the manifest bound itself moved -- "
            "both are worth failing on",
        )


# --------------------------------------------------------------------------
# Deck-tail consolidation guard (#587; harness modules added by #597).
#
# Every ``sim/*/control/run_*.py`` that builds its own ngspice deck used to
# spell out the ``.control`` header by hand -- ``set numdgt=`` and
# ``set noaskquit`` -- as 15 hand-maintained copies across 14 control
# scripts of the two settings the harness's own decks carry, each
# one a place ``numdgt`` or the quit setting could drift without anything
# noticing. They now all call ``runner.deck_control_block()``. The guard
# below fails the moment a second inline copy reappears -- in a control
# script or, since #597, in any ``sim/harness/`` module other than
# ``runner.py`` itself (``montecarlo.py`` carried the same hand-written
# tail for its MC decks) -- the same way
# ``test_each_shared_helper_has_exactly_one_definition_
# in_its_directory`` above guards the #493 helpers.
# --------------------------------------------------------------------------

#: The settings ``deck_control_block()`` owns; spelled inline anywhere else
#: they are drift waiting to happen. ``set numdgt`` is matched with the
#: ``=`` so prose that merely mentions the setting is not flagged.
CONTROL_SETTING_SNIPPETS = ("set noaskquit", "set numdgt=")


def _inline_control_setting_sites(script: Path) -> list[str]:
    """``file:line`` of every string constant in ``script`` that spells one
    of the control-block settings."""
    tree = ast.parse(script.read_text(), filename=str(script))
    return [
        f"{script.relative_to(SIM_DIR)}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(snippet in node.value for snippet in CONTROL_SETTING_SNIPPETS)
    ]


def _harness_modules() -> list[Path]:
    """Every ``sim/harness/*.py`` except ``runner.py``, the one allowed home."""
    modules = sorted(
        p for p in (SIM_DIR / "harness").glob("*.py") if p.name != "runner.py"
    )
    if not modules:
        raise AssertionError(
            "glob 'harness/*.py' matched nothing under sim/ -- "
            "the harness guard is covering nothing"
        )
    return modules


class ControlSettingsGuardTests(unittest.TestCase):
    """The control-block settings have exactly one home: harness.runner."""

    def test_no_control_script_spells_the_control_settings_itself(self):
        for script in _control_scripts():
            with self.subTest(script=script.relative_to(SIM_DIR)):
                self.assertEqual(
                    _inline_control_setting_sites(script), [],
                    f"{script.relative_to(SIM_DIR)} spells a control-block "
                    "setting itself -- the control-block settings belong to "
                    "sim/harness/runner.py's deck_control_block() (#587), so "
                    "an inline copy is drift waiting to happen",
                )

    def test_no_harness_module_other_than_runner_spells_the_control_settings(self):
        """#597: the harness's own MC decks compose through
        ``deck_control_block()`` too -- ``montecarlo.py`` used to carry its
        own hand-written tail, one ``numdgt`` edit away from drifting off
        the PVT decks ``compose_deck`` emits."""
        for script in _harness_modules():
            with self.subTest(script=script.relative_to(SIM_DIR)):
                self.assertEqual(
                    _inline_control_setting_sites(script), [],
                    f"{script.relative_to(SIM_DIR)} spells a control-block "
                    "setting itself -- the control-block settings belong to "
                    "sim/harness/runner.py's deck_control_block() (#597), so "
                    "an inline copy is drift waiting to happen",
                )


# --------------------------------------------------------------------------
# Manifest loading and the worker default (#704).
#
# ``cliutil.load_manifest()`` (#158) and ``cliutil.default_jobs()`` (#184)
# are the one home for two expressions the control scripts used to copy: before
# #704 twelve sites in eleven scripts spelled ``json.loads(MANIFEST.read_text())``
# inline (ten of them importing ``json`` for that line alone) and
# ``run_depth_sweep.py`` hand-rolled ``(os.cpu_count() or 4) // 2``. Nothing
# held the migrated scripts to the shared helpers, so a script copied from an
# un-migrated one brought the inline form back. The guard below closes that
# gap the way ``ControlSettingsGuardTests`` does for the control-block
# settings. It matches call nodes, not source text, so a comment that merely
# mentions either form is not an inline copy.
# --------------------------------------------------------------------------

#: Inline form -> (what a control script spelling it is doing itself, the one
#: shared home for it). The keys are how the failure message spells the form.
SHARED_CLIUTIL_FORMS = {
    "MANIFEST.read_text()": (
        "reads the manifest itself",
        "sim/harness/cliutil.py's load_manifest() (#158)",
    ),
    "cpu_count()": (
        "counts cores itself",
        "sim/harness/cliutil.py's default_jobs() (#184)",
    ),
}

#: Control scripts that still spell an inline form because a separate open PR
#: is removing it: #699 / PR #700 migrates ``run_dwell_sweep.py``. Entries
#: only ever come out as those PRs land, never go in. The stale-entry test
#: below fails only when a listed script has left the tree; a script that has
#: *already migrated* is tolerated, because the migrating PR and this one can
#: land in either order and neither's CI re-runs when the other merges.
#: Delete an entry once its script is migrated (a harmless, no-longer-needed
#: exemption).
PENDING_MIGRATION = {"run_dwell_sweep.py"}


def _last_name(node: ast.expr) -> str | None:
    """``MANIFEST`` for ``MANIFEST`` / ``band.MANIFEST``, ``cpu_count`` for
    ``os.cpu_count`` / ``cpu_count``; ``None`` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _inline_shared_cliutil_sites(source: str) -> dict[str, list[int]]:
    """``form -> line numbers`` of every inline copy in ``source``.

    A ``read_text()`` call on anything named ``MANIFEST`` and any
    ``cpu_count()`` call, wherever they sit (inside ``json.loads(...)`` or not).
    """
    sites: dict[str, list[int]] = {form: [] for form in SHARED_CLIUTIL_FORMS}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if _last_name(node.func) == "cpu_count":
            sites["cpu_count()"].append(node.lineno)
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_text"
            and _last_name(node.func.value) == "MANIFEST"
        ):
            sites["MANIFEST.read_text()"].append(node.lineno)
    return sites


class ControlCliutilGuardTests(unittest.TestCase):
    """``load_manifest`` and ``default_jobs`` have exactly one home: harness.cliutil."""

    def test_no_control_script_loads_the_manifest_or_counts_cores_itself(self):
        for script in _control_scripts():
            if script.name in PENDING_MIGRATION:
                continue
            with self.subTest(script=script.relative_to(SIM_DIR)):
                sites = _inline_shared_cliutil_sites(script.read_text())
                for form, (doing, home) in SHARED_CLIUTIL_FORMS.items():
                    self.assertEqual(
                        sites[form], [],
                        f"{script.relative_to(SIM_DIR)} {doing} on line(s) "
                        f"{sites[form]} -- {home} is its one home, so an "
                        "inline copy is drift waiting to happen",
                    )

    def test_the_pending_migration_list_has_no_stale_entries(self):
        """A listed script must still exist. Having already migrated is fine:
        the migrating PR may land before this guard, and that merge order must
        not turn ``main`` red. The detector's positive control is the boundary
        test below."""
        names = {script.name for script in _control_scripts()}
        stale = sorted(PENDING_MIGRATION - names)
        self.assertEqual(
            stale, [],
            "PENDING_MIGRATION lists script(s) that are not in the tree: "
            f"{stale}. Remove them -- the ratchet only tightens.",
        )

    def test_the_detector_matches_the_inline_forms_and_nothing_else(self):
        """Pins the boundary, so a refactor cannot silently neuter the guard."""
        inline = {
            "options = json.loads(MANIFEST.read_text())['options']": "MANIFEST.read_text()",
            "manifest = json.loads(band.MANIFEST.read_text())": "MANIFEST.read_text()",
            "workers = min(6, max(1, (os.cpu_count() or 4) // 2))": "cpu_count()",
            "jobs = cpu_count()": "cpu_count()",
        }
        for source in (
            *inline,
            "manifest = cliutil.load_manifest(band.MANIFEST)",
            "jobs = cliutil.default_jobs()",
            "rows = json.loads(path.read_text())",
            "# the default used to be os.cpu_count() // 2",
            '"""Every deck is composed from MANIFEST.read_text() ..."""',
        ):
            with self.subTest(source=source):
                sites = _inline_shared_cliutil_sites(source)
                self.assertEqual(
                    {form for form, lines in sites.items() if lines},
                    {inline[source]} if source in inline else set(),
                )


# --------------------------------------------------------------------------
# Control-script argv contract (#512).
#
# Every ``sim/*/control/run_*.py`` entry point used to fall into one of two
# silent-argv traps: the twelve that read no argv at all ignored any argument
# (``--help`` included) and ran their full local ngspice grid, and the three
# that tested ``"--report-only" in argv`` silently *simulated* on any other
# unrecognized flag. The contract now: ``--help`` prints usage and exits 0,
# an unrecognized flag prints usage and exits non-zero, and neither ever
# reaches the sweep.
#
# Since #546 the covered set is discovered by globbing, not maintained: the
# lists this section once carried had fallen five scripts behind reality.
# --------------------------------------------------------------------------

#: Every control entry point, discovered rather than maintained (#546): a new
#: ``sim/*/control/run_*.py`` is covered the moment it is committed, with no
#: edit to this file. ``--help`` exits 0 and an unrecognized flag exits
#: non-zero are argparse behaviour, so one pair of assertions holds for every
#: script regardless of which real options it declares.
def _control_scripts() -> list[Path]:
    scripts = sorted(SIM_DIR.glob("*/control/run_*.py"))
    if not scripts:
        raise AssertionError(
            "glob '*/control/run_*.py' matched nothing under sim/ -- "
            "the argv contract is covering nothing"
        )
    return scripts


def _tree_state(dirs: list[Path]) -> dict[str, tuple[int, int]]:
    """``path -> (size, mtime_ns)`` for every file under ``dirs``.

    A control script writes into directories resolved from its own ``__file__``,
    not the CWD, so the "nothing was written" assertion has to snapshot the
    script's own ``control/decks/`` and ``control/logs/`` before and after.
    """
    state: dict[str, tuple[int, int]] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for path in d.rglob("*"):
            if path.is_file():
                st = path.stat()
                state[str(path)] = (st.st_size, st.st_mtime_ns)
    return state


class ParseNoOptionsUnitTests(unittest.TestCase):
    """``cliutil.parse_no_options`` itself -- the guard every script calls."""

    def test_empty_argv_is_accepted(self):
        """A bare invocation returns normally; the caller runs its sweep."""
        from harness import cliutil

        self.assertIsNone(cliutil.parse_no_options([], "doc"))

    def test_none_argv_reads_sys_argv(self):
        """``argv=None`` means "parse the process argv", so it must reject a
        bad one -- that is the path the real ``__main__`` invocation takes."""
        from harness import cliutil

        with unittest.mock.patch("sys.argv", ["prog"]):
            cliutil.parse_no_options(None, "doc")
        with unittest.mock.patch("sys.argv", ["prog", "--nope"]):
            with self.assertRaises(SystemExit) as cm:
                cliutil.parse_no_options(None, "doc")
        self.assertEqual(cm.exception.code, 2)

    def test_help_prints_the_description_and_exits_zero(self):
        from harness import cliutil

        out = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stdout(out):
                cliutil.parse_no_options(["--help"], "the docstring")
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("usage:", out.getvalue())
        self.assertIn("the docstring", out.getvalue())

    def test_unknown_flag_exits_two_with_usage_on_stderr(self):
        from harness import cliutil

        err = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stderr(err):
                cliutil.parse_no_options(["--nope"], "the docstring")
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("unrecognized arguments", err.getvalue())

    def test_a_bare_dash_dash_is_rejected(self):
        """``--`` is rejected too, not silently accepted.

        With no option definitions there is no positional to consume the
        end-of-options marker, so argparse reports ``--`` unrecognized.
        That is the right contract for a script that takes no options:
        ``script --`` never silently reads as "run the sweep".
        """
        from harness import cliutil

        with self.assertRaises(SystemExit) as cm:
            cliutil.parse_no_options(["--"], "doc")
        self.assertEqual(cm.exception.code, 2)


class ControlArgvContractTests(unittest.TestCase):
    """The real ``__main__`` path of every control script the glob finds.

    Each invocation is a ``subprocess`` from a temp CWD, so the committed
    script is exercised, not an in-process import of it. No test here ever
    runs a grid: the guard exits before the sweep, and the tree-state
    comparison proves no file under the script's own ``control/decks/`` or
    ``control/logs/`` was created or modified. A bare (no-argument)
    invocation is deliberately not exercised -- on a PDK-equipped host that
    *is* the sweep; its unchanged acceptance is pinned by
    ``ParseNoOptionsUnitTests.test_empty_argv_is_accepted`` instead.
    """

    def _run(self, script: Path, *argv: str) -> subprocess.CompletedProcess:
        control = script.parent
        watch = [control / "decks", control / "logs"]
        before = _tree_state(watch)
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(
                [sys.executable, str(script), *argv],
                capture_output=True, text=True, cwd=cwd, timeout=120,
            )
        self.assertEqual(
            _tree_state(watch), before,
            f"{script.name} {' '.join(argv)} wrote under control/decks|logs",
        )
        return proc

    def test_help_prints_usage_and_exits_zero_without_simulating(self):
        for script in _control_scripts():
            with self.subTest(script=script.relative_to(SIM_DIR)):
                proc = self._run(script, "--help")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("usage:", proc.stdout)

    def test_an_unrecognized_flag_exits_nonzero_without_simulating(self):
        """The #512 hazard: this used to be the path that started the sweep."""
        for script in _control_scripts():
            with self.subTest(script=script.relative_to(SIM_DIR)):
                proc = self._run(script, "--nope")
                self.assertNotEqual(
                    proc.returncode, 0,
                    f"{script.relative_to(SIM_DIR)} ignored --nope and "
                    "would have run the sweep",
                )
                self.assertIn("unrecognized arguments", proc.stderr)


if __name__ == "__main__":
    unittest.main()
