#!/usr/bin/env python3
"""Batch backend for ``sim/run_mc.py`` (#420), against a fake ``klt``.

No PDK, no ngspice, no klt, no network (see ``test_klt_batch.py``).

    python3 -m unittest discover -s sim/tests -k batch
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR.parent / "sim"))

import run_mc  # noqa: E402
from harness import klt_batch, montecarlo, testbench  # noqa: E402
from test_klt_batch import BatchTestCase  # noqa: E402


class McBatchFixture(BatchTestCase):
    def setUp(self):
        super().setUp()
        exp = self.root / "mc-exp"
        tbd = exp / "testbench"
        tbd.mkdir(parents=True)
        (tbd / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (tbd / "tb.json").write_text(json.dumps({
            "name": "mc-exp", "netlist": "x.spice",
            "analyses": ["op"],
            "measure": {"vout": "v(out)", "iq": "-i(v1)"},
            "mc": {"n": 3, "seed_base": 7,
                   "binding_points": [
                       {"label": "a", "corner": "tt", "temp_c": 27, "vdd": 3.3},
                       {"label": "b", "corner": "ss", "temp_c": 125, "vdd": 2.97}]},
        }))
        self.tb = testbench.load(tbd)
        bps = montecarlo.load_binding_points(self.tb)
        self.points = montecarlo.build_mc_grid(bps, 3, 7, enforce_min=False)
        self.log_dir = self.root / "corners" / "rec"

    def grid(self, **kw):
        seen = []
        res = montecarlo.run_mc_grid(
            self.tb, self.pdk, self.points, self.root / "work", jobs=2,
            log_dir=self.log_dir, on_result=seen.append,
            backend="batch", batch=self.cfg(**kw),
        )
        return res, seen


class McBatchGridTests(McBatchFixture):
    def test_samples_run_on_klt_with_seeds_and_logs_in_place(self):
        res, seen = self.grid()
        self.assertEqual([r.point.corner_id for r in res], [p.corner_id for p in self.points])
        self.assertEqual(len(seen), 6)
        self.assertTrue(all(r.status == "ok" for r in res), [r.message for r in res])
        for r in res:
            self.assertEqual(r.log, f"{r.point.corner_id}.log")
            self.assertTrue(r.log.endswith(f"_s{r.point.sample:04d}.log"))
            self.assertTrue((self.log_dir / r.log).is_file())
            self.assertEqual(set(r.measurements), {"vout", "iq"})
        # seed formula unchanged: seed_base + binding_index*100000 + sample
        self.assertEqual([p.seed for p in self.points],
                         [7, 8, 9, 100007, 100008, 100009])
        # one request per sample (the seed makes every body distinct), each carrying its seed
        bodies = sorted(p.read_text() for p in self.state.glob("body-*.spice"))
        self.assertEqual(len(bodies), 6)
        for seed in (p.seed for p in self.points):
            self.assertEqual(sum(f".option seed={seed}\n" in b for b in bodies), 1, seed)
        self.assertTrue(all(".param sw_stat_mismatch=1" in b for b in bodies))
        self.assertNoLocalNgspice()

    def test_every_failure_mode_is_an_error_never_ok(self):
        for mode in ("refuse", "invalid_json", "empty", "failed_corner", "no_log",
                     "missing_meas", "timeout_corner", "no_remote", "mismatch",
                     "drop_corner"):
            with self.subTest(mode):
                self.mode(mode)
                res, _ = self.grid()
                self.assertEqual(len(res), 6)
                self.assertTrue(all(r.status != "ok" for r in res), mode)
                self.assertTrue(all(r.message for r in res), mode)
                self.assertNoLocalNgspice()

    def test_klt_missing_raises_and_never_runs_local(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            with self.assertRaises(klt_batch.KltMissing):
                self.grid()
        self.assertNoLocalNgspice()

    def test_batch_without_a_config_refuses_instead_of_running_locally(self):
        with self.assertRaises(klt_batch.BatchError):
            montecarlo.run_mc_grid(self.tb, self.pdk, self.points, self.root / "w",
                                   backend="batch")
        self.assertNoLocalNgspice()


class McBatchSetTests(McBatchFixture):
    def grid_set(self):
        seen = []
        res = montecarlo.run_mc_grid(
            self.tb, self.pdk, self.points, self.root / "work", jobs=2,
            log_dir=self.log_dir, on_result=seen.append, backend="batch",
            batch=self.cfg(batch_set=True, max_in_flight=3),
        )
        return res, seen

    def test_all_samples_go_through_one_batch_set_call(self):
        res, seen = self.grid_set()
        sims = [c for c in self.calls() if c[0] == "sim"]
        self.assertEqual(len(sims), 1)
        self.assertIn("--batch-set", sims[0])
        self.assertEqual(sims[0][sims[0].index("--max-in-flight") + 1], "3")
        self.assertEqual(len(res), 6)
        self.assertEqual(len(seen), 6)
        self.assertTrue(all(r.status == "ok" for r in res), [r.message for r in res])
        self.assertEqual([r.point.corner_id for r in res], [p.corner_id for p in self.points])
        for r in res:
            self.assertTrue((self.log_dir / r.log).is_file())
        self.assertNoLocalNgspice()

    def test_member_refused_is_a_per_sample_error_not_dropped(self):
        self.mode("set_member_refused")
        res, seen = self.grid_set()
        self.assertEqual(len(res), 6)             # every sample still counted
        self.assertEqual(len(seen), 6)
        bad = [r for r in res if r.status == "error"]
        self.assertEqual(len(bad), 1)
        self.assertIn("batch_no_capacity", bad[0].message)
        self.assertEqual(sum(r.status == "ok" for r in res), 5)
        self.assertNoLocalNgspice()

    def test_whole_set_refused_marks_every_sample_error(self):
        self.mode("set_refuse")
        res, _ = self.grid_set()
        self.assertEqual(len(res), 6)
        self.assertTrue(all(r.status == "error" and "set refused" in r.message for r in res))
        self.assertNoLocalNgspice()

    def test_set_mode_failure_modes_are_never_ok(self):
        for mode in ("failed_corner", "no_log", "missing_meas", "no_remote", "mismatch",
                     "drop_corner"):
            with self.subTest(mode):
                self.mode(mode)
                res, _ = self.grid_set()
                self.assertEqual(len(res), 6)
                self.assertTrue(all(r.status != "ok" for r in res), mode)
                self.assertNoLocalNgspice()


class McBatchCliTests(McBatchFixture):
    def _args(self, *extra):
        return run_mc.build_parser().parse_args(
            [str(self.root / "mc-exp"), "--n", "2", "--no-write", "--quiet", *extra])

    def _run(self, *extra):
        with mock.patch.object(run_mc, "find_pdk", return_value=self.pdk), \
                mock.patch.object(run_mc, "WORK_DIR", self.root / "workdir"):
            return run_mc.run(self._args(*extra))

    def test_backend_batch_never_needs_local_ngspice(self):
        os.remove(self.bin / "ngspice")
        self.assertEqual(self._run("--backend", "batch"), run_mc.EXIT_OK)
        sims = [c for c in self.calls() if c[0] == "sim"]
        # 2 binding points x n=2 samples = 4 requests, ONE --batch-set submission (#440)
        self.assertEqual(len(sims), 1)
        (call,) = sims
        self.assertEqual(call[call.index("--backend") + 1], "batch")
        first = call.index("--batch-set") + 1
        self.assertEqual(len([a for a in call[first:call.index("--max-in-flight")]]), 4)
        self.assertEqual(call[call.index("--max-in-flight") + 1], "4")
        self.assertEqual(call[call.index("--wait-for-capacity") + 1], "600")
        self.assertEqual(call[call.index("--capacity-retries") + 1], "3")

    def test_flags_are_forwarded(self):
        self.assertEqual(self._run("--backend", "batch", "--max-in-flight", "2",
                                   "--wait-for-capacity", "30", "--capacity-retries", "1"),
                         run_mc.EXIT_OK)
        (call,) = [c for c in self.calls() if c[0] == "sim"]
        self.assertEqual(call[call.index("--max-in-flight") + 1], "2")
        self.assertEqual(call[call.index("--wait-for-capacity") + 1], "30")
        self.assertEqual(call[call.index("--capacity-retries") + 1], "1")

    def test_env_selects_batch_and_failure_is_nonzero_not_local(self):
        self.mode("refuse")
        with mock.patch.dict(os.environ, {klt_batch.ENV_BACKEND: "batch"}):
            self.assertNotEqual(self._run(), run_mc.EXIT_OK)
        self.assertNoLocalNgspice()

    def test_missing_klt_is_an_environment_error(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            self.assertEqual(self._run("--backend", "batch"), run_mc.EXIT_ENVIRONMENT)
        self.assertNoLocalNgspice()

    def test_default_backend_is_local(self):
        self.assertEqual(klt_batch.resolve_backend(self._args().backend), klt_batch.BACKEND_LOCAL)


if __name__ == "__main__":
    unittest.main()
