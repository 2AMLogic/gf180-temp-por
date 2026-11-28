"""#555: the smoke's `got n/a` spread checks must fail loudly, and the batch
report -> ``PointResult.measurements`` mapping must hold for the fleet's real
report/log shape.

Two things are pinned here:

- **The mapping is not the defect.** A klt batch report in the fleet's real
  shape (corner ``status: "pass"``, ``expr`` measurements named ``m_<x>``,
  raw ngspice log carrying ``m_<x> = <value>`` lines) fed through the real
  staging, collection (``_collect_group``/``_judge``) and ``run_batch_grid``'s
  outcome mapping yields ``ok`` points whose ``summarize()`` spread values
  are real numbers -- refuting the issue's (a)/(b)/(c) hypotheses by
  construction. The measurement values are the ones captured from a live
  fleet run of this grid (2026-11-17, 27 C / nominal, klt 0.9.3.dev242
  client and runner); only host-specific fields are normalized to the
  fixture: the ``artifacts.log`` path points at the fixture's own log copy
  and the runner PDK digest at the fake PDK's (a matched fleet image).
- **A run whose points all die before judgement fails loudly.** When the
  fleet provenance gates (runner PDK digest, runner klt version) reject
  every corner, no point is ``ok``, every spread check reads ``n/a``, and
  the footer must say so with the per-point statuses and the distinct
  causes -- not leave three opaque ``got n/a`` lines as the whole story.
"""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import cli, cliutil, corners as corners_mod, klt_batch, report, runner
from harness import pdk as runner_pdk
from harness import testbench as tb_mod
from tests.testutil import fake_pdk


# The fleet's raw ngspice log format for an expr measurement, captured
# verbatim from a smoke-grid corner log (2026-11-17 fleet run): ngspice
# `print` of the lifted `let` vector at `set numdgt=10` precision.
def corner_log(measurements: dict[str, float]) -> str:
    lines = [
        "Circuit: * klt sim -- generated corner deck, do not edit",
        "",
        "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000",
        "",
        "Using SPARSE 1.3 as Direct Linear Solver",
        "",
        "No. of Data Rows : 1",
    ]
    lines += [f"m_{name} = {value:.10e}" for name, value in sorted(measurements.items())]
    lines += ["ngspice-47 done", ""]
    return "\n".join(lines)


SMOKE_MEASURE = {
    "vdiv_ratio": "v(ndiv)/v(vdd)",
    "vbias": "v(nbias)",
    "vbe": "v(nbe)",
    "isup_ua": "-i(vsup)*1e6",
}
SMOKE_CHECKS = {
    "vdiv_ratio": {"min": 0.4999, "max": 0.5001, "max_spread_pct": 0.001},
    "vbias": {"min": 0.6, "max": 1.4, "min_spread_pct": 5.0},
    "vbe": {"min": 0.35, "max": 0.95},
    "isup_ua": {"min": 20.0, "max": 250.0},
}
# The real smoke-bias manifest also floors vbe's spread at 20 %, but that
# envelope needs the full -40..125 C temperature axis; these fixtures run a
# 27 C process grid (captured values, ~2.2 % vbe spread), so the vbe spread
# floor is scoped out here. vdiv/vbias spread floors stay: they are what the
# n/a symptom hides.

# Captured 2026-11-17, fleet run of the smoke grid at 27 C / 3.3 V: the
# report's measurements[] values, keyed per process corner.
CAPTURED_27C = {
    "tt": {"vdiv_ratio": 0.5, "vbias": 0.965796, "vbe": 0.689307, "isup_ua": 79.585825},
    "ff": {"vdiv_ratio": 0.5, "vbias": 0.864477, "vbe": 0.683181, "isup_ua": 97.931528},
    "ss": {"vdiv_ratio": 0.5, "vbias": 1.030326, "vbe": 0.698160, "isup_ua": 67.163293},
}


def write_smoke_tb(root: Path) -> Path:
    """Lay out a smoke-bias-shaped experiment the way sim/README.md specifies."""
    tb_dir = root / "smoke-tb" / "testbench"
    tb_dir.mkdir(parents=True)
    (tb_dir / "x.spice").write_text(
        "vsup vdd 0 dc {vdd_val}\n"
        "Rtop vdd ndiv 100k\n"
        "Rbot ndiv 0 100k\n"
        "Iq 0 nbe dc 10u\n"
    )
    (tb_dir / "tb.json").write_text(json.dumps({
        "name": "smoke-tb",
        "netlist": "x.spice",
        "nominal_supply_v": 3.3,
        "measure": SMOKE_MEASURE,
        "checks": SMOKE_CHECKS,
        "corners": ["tt", "ff", "ss"],
    }))
    return root / "smoke-tb"


class PdkResolutionMatchesKltClientTests(unittest.TestCase):
    """The harness and the klt client must resolve the same PDK install
    where several exist: klt reads ``~/.ciel`` before ``~/.volare``
    (first-match-wins, and its own resolution warning says so), so a host
    provisioned with both gets a harness-vs-fleet provenance mismatch --
    every batch corner rejected, the smoke's spread checks all ``n/a``
    (#555, measured 2026-11-17: fleet reads open_pdks f6eeac7d via
    ``~/.ciel``, ``~/.volare`` holds an older c6d73a35 build)."""

    def test_builtin_roots_prefer_ciel_over_volare(self):
        roots = [r.split("/")[-1] for r in runner_pdk.BUILTIN_SEARCH_ROOTS]
        self.assertIn(".ciel", roots)
        self.assertIn(".volare", roots)
        self.assertLess(roots.index(".ciel"), roots.index(".volare"))

    def test_with_both_installs_present_the_ciel_one_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ciel = root / ".ciel"
            volare = root / ".volare"
            for base in (ciel, volare):
                variant = base / "gf180mcuD"
                (variant / "libs.tech" / "ngspice").mkdir(parents=True)
                (variant / "libs.tech" / "ngspice" / "sm141064.ngspice").write_text("x")
            clean = {k: v for k, v in os.environ.items()
                     if k not in ("GF180_PDK_PATH", "PDK_ROOT", "PDK")}
            clean["HOME"] = str(root)
            with mock.patch.dict(os.environ, clean, clear=True):
                pdk = runner_pdk.find_pdk()
            self.assertEqual(pdk.path.parent.name, ".ciel")
            self.assertIn(".ciel", pdk.source)


class BatchMappingYieldsSpreadTests(unittest.TestCase):
    """A real-shaped fleet report + raw logs through the real mapping."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pdk = fake_pdk(self.root / "gf180mcuD")
        self.tb = tb_mod.load(write_smoke_tb(self.root))

    def _points(self):
        corner_list = corners_mod.resolve_corners(["tt", "ff", "ss"])
        return corners_mod.build_grid(corner_list, [27.0],
                                      corners_mod.supply_points(3.3, 0.0))

    def _fleet_shape(self, units, log_dir: Path) -> dict:
        """A batch report in the shape the fleet actually returns for this
        grid: one pass corner per unit, expr measurements named ``m_<x>``
        whose values match the raw log's ``m_<x> = <value>`` lines."""
        # unit process section -> the captured corner values (first section
        # names the base corner: typical=tt, ff=ff, ss=ss).
        captured = {"typical": CAPTURED_27C["tt"], "ff": CAPTURED_27C["ff"],
                    "ss": CAPTURED_27C["ss"]}
        corners = []
        for u in units:
            key = u.process_name.split("+")[0]
            meas = captured[key]
            # The fleet's log lives where klt collected it (a different path
            # than the unit's own evidence log_path, which _judge copies it
            # onto byte-for-byte).
            log_path = log_dir / "fleet" / f"{u.key}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(corner_log(meas))
            corners.append({
                "corner_id": f"{u.process_name}/novdd/27C/params:vdd_val=3.3",
                "process": u.process_name,
                "supply_v": {},
                "temperature_c": 27.0,
                "params": {"vdd_val": 3.3},
                "status": "pass",
                "runtime_s": 0.1,
                "peak_rss_bytes": 1,
                "engine_exit_code": 0,
                "engine_killed_by_signal": None,
                "measurements": [
                    {"name": f"m_{name}", "value": value, "unit": None,
                     "status": "pass", "margin": None}
                    for name, value in meas.items()
                ],
                "diagnostics": [],
                "artifacts": {"log": str(log_path), "raw": None, "waveform": None,
                              "deck": str(log_path.parent / "corner.cir")},
                "monte_carlo": None,
            })
        runner_sha = None
        if self.pdk.model_lib.is_file():
            runner_sha = hashlib.sha256(self.pdk.model_lib.read_bytes()).hexdigest()
        return {
            "schema_version": 1,
            "environment": {"remote": {
                "job_id": "klt-sim-fixture",
                "runner_compatibility": "match",
                "runner_klt_version": "0.9.3.dev242",
                "client_klt_version": "0.9.3.dev242",
                "runner_models_lib_sha256": runner_sha,
                "models_lib_comparison": {"status": "match"},
            }},
            "corners": corners,
        }

    def _run_batch_grid(self):
        points = self._points()
        workdir = self.root / "work"
        workdir.mkdir(parents=True)
        cfg = klt_batch.BatchConfig(pdk=self.pdk, stage_root=self.root / "stage",
                                    sleep=lambda s: None, log=lambda m: None)
        # The same staging run_grid's batch path does (compose + lift).
        units, _, _ = runner._batch_units(
            self.tb, self.pdk, points, workdir, runner.compose_deck,
            ("vdd_val",), runner.DEFAULT_TIMEOUT_S, workdir / "logs", (), strict=True,
        )
        report_dict = self._fleet_shape(units, workdir / "logs")
        collected = klt_batch._collect_group(units, report_dict, False, cfg)
        self.assertTrue(all(o.ok for o in collected),
                        msg=[o.message for o in collected if not o.ok])

        def fake_run_units(units_, cfg_, **kw):
            on_outcome = kw["on_outcome"]
            for out in collected:
                on_outcome(out)
            return collected

        with mock.patch.object(klt_batch, "run_units", side_effect=fake_run_units):
            return runner.run_batch_grid(
                self.tb, self.pdk, points, workdir, cfg, runner.compose_deck,
                lift_params=("vdd_val",),
            )

    def test_real_shape_report_maps_to_ok_points_and_real_spread(self):
        results = self._run_batch_grid()
        self.assertTrue(all(r.status == "ok" for r in results),
                        msg=[(r.point.corner_id, r.status, r.message) for r in results])
        for r in results:
            self.assertEqual(set(r.measurements), set(self.tb.measure))
        summary = report.summarize(results, list(self.tb.measure))
        for name in ("vdiv_ratio", "vbias", "vbe"):
            self.assertIsNotNone(summary[name].get("spread_pct"),
                                 msg=f"{name} spread still n/a: {summary[name]}")
        self.assertEqual(summary["vdiv_ratio"]["spread_pct"], 0.0)
        # 27 C process corners only: the captured vbe spread is small but
        # real (2.17 %) -- a number, never n/a. (The smoke's 20 % vbe floor
        # needs the -40..125 C temperature axis, which this fixture scopes
        # out; the point here is the mapping, not the spec envelope.)
        self.assertGreater(summary["vbe"]["spread_pct"], 2.0)
        failures = report.evaluate_checks(self.tb.checks, results, summary)
        self.assertEqual([f for f in failures if "spread" in f["kind"]], [])

    def test_captured_log_lines_parse_with_the_existing_regex(self):
        # Hypothesis (a) of the issue, refuted against the captured shape:
        # the fleet log's m_ lines match the harness's existing regex.
        text = corner_log(CAPTURED_27C["tt"])
        parsed = runner.parse_measurements(text)
        self.assertAlmostEqual(parsed["vbe"], 0.689307, places=5)


class FooterLoudFailureTests(unittest.TestCase):
    """A run whose every point was rejected (e.g. the fleet PDK gate) prints
    the per-point statuses and causes in the footer, not just n/a."""

    # The message the fleet provenance gate actually emits (2026-11-17,
    # smoke grid, 81/81 points rejected), host paths shortened.
    GATE_MESSAGE = (
        "fleet job klt-sim-fixture: the runner read model library sha256 "
        "f6f4a96e18fc5ad11270ad3451aaecc7ac37fc81eb61e15b0d7d94c7bc594a24, "
        "but this host resolved 6edba54d23b38a2c60f8ffdbaa3eb75a7568c615e482"
        "0808969bd1121b77b1aa (/pdk/gf180mcuD/libs.tech/ngspice/sm141064.ngs"
        "pice); its result is not accepted, because a record of it would na"
        "me a PDK build the simulation never read -- point PDK_ROOT (or sim"
        "/pdk.local.json) at the install the fleet runner uses"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.experiment_dir = write_smoke_tb(root)
        self.pdk = fake_pdk(root / "gf180mcuD")
        self.parser = cli.build_parser()
        for obj, name, value in (
            (cli, "WORK_DIR", root / ".work"),
            (cliutil, "find_pdk", lambda: self.pdk),
            (cli.runner, "ngspice_version", lambda: "ngspice-test"),
            (cliutil.evidence_store, "preflight", lambda *a, **k: None),
            (cliutil.evidence_store, "publish", lambda *a, **k: root / "manifest"),
        ):
            patcher = mock.patch.object(obj, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, statuses):
        args = self.parser.parse_args([
            str(self.experiment_dir),
            "--corners", "tt", "ff", "ss",
            "--temps", "27",
            "--supply-tol", "0",
            "--subset-reason", "footer guard test -- not evidence",
            "--backend", "local",
            "--no-write",
        ])

        def fake_run_grid(tb, pdk, points, workdir, jobs=1, timeout_s=0,
                          on_result=None, log_dir=None, backend="local", batch=None):
            # ok points carry the captured per-corner values, so the grid's
            # spread floors are genuinely met (flat values are not).
            captured = {"tt": CAPTURED_27C["tt"], "ff": CAPTURED_27C["ff"],
                        "ss": CAPTURED_27C["ss"]}
            results = []
            for point, status in zip(points, statuses):
                result = runner.PointResult(
                    point=point, status=status,
                    measurements=dict(captured[point.corner.name])
                    if status == "ok" else {},
                    message="" if status == "ok" else self.GATE_MESSAGE)
                results.append(result)
                if on_result is not None:
                    on_result(result)
            return results

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with mock.patch.object(cli.runner, "run_grid", side_effect=fake_run_grid):
                exit_code = cli.run(args)
        return exit_code, out.getvalue()

    def test_all_points_rejected_prints_the_per_point_causes(self):
        exit_code, text = self._run(["error", "error", "error"])
        self.assertEqual(exit_code, cliutil.EXIT_SIM_ERROR)
        # The old, opaque lines are still there...
        self.assertIn("got n/a at grid", text)
        # ...but the footer now names how many points died and why.
        self.assertIn("did not produce a result", text)
        self.assertIn("3 x [error]", text)
        self.assertIn("the runner read model library sha256", text)
        self.assertIn("point PDK_ROOT (or sim/pdk.local.json)", text)

    def test_mixed_causes_are_grouped_by_distinct_message(self):
        exit_code, text = self._run(["error", "failed", "error"])
        self.assertEqual(exit_code, cliutil.EXIT_SIM_ERROR)
        self.assertIn("did not produce a result", text)
        self.assertIn("2 x [error]", text)
        self.assertIn("1 x [failed]", text)

    def test_partial_loss_is_reported_even_though_every_measurement_has_samples(self):
        # The review's failure shape: some points die, the survivors still
        # give every measurement n > 0, so no "no data" row appears -- the
        # footer must still name the dead points and the truncated coverage.
        _, text = self._run(["ok", "error", "error"])
        self.assertNotIn("no measurement for", text)
        self.assertIn("2/3 point(s) did not produce a result", text)
        self.assertIn("surviving points only", text)
        self.assertIn("2 x [error]", text)

    def test_healthy_run_prints_no_failure_block(self):
        exit_code, text = self._run(["ok", "ok", "ok"])
        self.assertEqual(exit_code, cliutil.EXIT_OK)
        self.assertNotIn("did not produce a result", text)


class KltFailureTextTests(unittest.TestCase):
    """A refused submit must surface klt's refusal reason, not the advisory
    warnings that precede it on stderr (#555)."""

    WARNING = ("klt: warning: 2 installs provide PDK variant 'gf180mcuD'; "
               "read /home/u/.ciel ..., skipped /home/u/.volare ...\n") * 3

    def test_real_refusal_survives_long_leading_warnings(self):
        stderr = self.WARNING + ("batch job bound 8220s exceeds ceiling " * 20
                                 + "\nklt: error: REAL-REFUSAL-REASON")
        text = klt_batch._failure_text(None, stderr)
        self.assertIn("REAL-REFUSAL-REASON", text)
        self.assertLessEqual(len(text), 900)

    def test_json_error_message_comes_first(self):
        text = klt_batch._failure_text({"error": {"message": "JSON-ERR"}}, self.WARNING)
        self.assertTrue(text.startswith("JSON-ERR"))

    def test_short_stderr_is_kept_whole(self):
        self.assertEqual(klt_batch._failure_text(None, "boom\n"), "boom")

    def _batch_set_error(self, stderr):
        proc = mock.Mock(returncode=2, stdout="", stderr=stderr)
        with mock.patch.object(klt_batch.shutil, "which", return_value="/bin/klt"), \
                mock.patch.object(klt_batch.subprocess, "run", return_value=proc):
            with self.assertRaises(klt_batch.BatchSubmitError) as ctx:
                klt_batch.invoke_klt_set([Path("a.json")], Path("out"),
                                         klt_batch.BatchConfig(pdk=None, stage_root=Path(".")), 10.0)
        return str(ctx.exception)

    def test_batch_set_refusal_survives_long_leading_warnings(self):
        stderr = self.WARNING + ("batch job bound 8220s exceeds ceiling " * 20
                                 + "\nklt: error: REAL-REFUSAL-REASON")
        self.assertIn("REAL-REFUSAL-REASON", self._batch_set_error(stderr))

    def test_batch_set_empty_stderr_reports_no_output(self):
        self.assertIn("no output", self._batch_set_error(""))


if __name__ == "__main__":
    unittest.main()

