#!/usr/bin/env python3
"""Tests for the fail-closed `klt sim` batch backend (#331).

No PDK, no ngspice, no klt, no network: a fake ``klt`` executable (and a fake
``ngspice`` that records any invocation) are placed first on PATH.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import cli, corners, klt_batch, runner, testbench  # noqa: E402
from harness.klt_batch import BatchConfig, BatchError  # noqa: E402
from testutil import fake_pdk  # noqa: E402

FAKE_KLT = r'''#!{python}
import json, os, sys, time
from pathlib import Path

mode = os.environ.get("FAKE_KLT_MODE", "ok")
state = Path(os.environ["FAKE_KLT_STATE"])
args = sys.argv[1:]
with open(state / "calls.jsonl", "a") as fh:
    fh.write(json.dumps(args) + "\n")
if args == ["--version"]:
    print("klt 0.0.0+fake"); sys.exit(0)
req_path = Path(args[1]); outdir = Path(args[args.index("-o") + 1])
req = json.loads(req_path.read_text())
n_prev = len(list(state.glob("req-*.json")))
(state / f"req-{n_prev}.json").write_text(json.dumps(req))
(state / f"body-{n_prev}.spice").write_text((req_path.parent / req["netlist"]).read_text())

if mode == "refuse":
    print(json.dumps({"error": {"message": "submission refused by the fleet"}})); sys.exit(1)
if mode == "invalid_json":
    print("this is not json"); sys.exit(0)
if mode == "empty":
    sys.exit(0)
if mode == "timeout":
    time.sleep(30); sys.exit(0)
if mode == "cap_then_ok" and not (state / "capped").exists():
    (state / "capped").write_text("1")
    print(json.dumps({"error": {"message": "exceeds BATCH_MAX_CONCURRENT_INSTANCES (4)"}})); sys.exit(1)

c = req["corners"]
procs = [p["name"] if isinstance(p, dict) else p for p in c.get("process", [None])]
sv = c.get("supply_v", {})
keys = list(sv)
rows = [dict(zip(keys, vals)) for vals in zip(*[sv[k] for k in keys])] if keys else [{}]
excl = req.get("exclude", [])
corners = []
for p in procs:
    for row in rows:
        for t in c["temperature_c"]:
            if any(e.get("process", p) == p and e.get("supply_v", row) == row for e in excl):
                continue
            cid = f"{p}/{row}/{t}"
            d = outdir / ("c%d" % len(corners)); d.mkdir(parents=True, exist_ok=True)
            lines = ["ngspice banner", "stdout of " + cid]
            meas = []
            for m in req["measurements"]:
                name = m["name"]
                absent = (mode == "absent_meas" and name == "t_trip") or mode in ("aborted", "all_absent")
                if mode == "missing_meas" and m is req["measurements"][-1]:
                    absent = True
                val = None if absent else 0.125
                if not absent:
                    lines.append(f"{name} = 1.2500000000e-01")
                meas.append({"name": name, "value": val, "status": "pass" if val is not None else "error"})
            if mode == "aborted":   # the shape the fleet returned for a TSTOP of zero
                lines += ["Error: TSTOP is invalid, must be greater than zero.",
                          "tran simulation(s) aborted"]
            log = d / "run.log"
            log.write_bytes(("\n".join(lines) + "\n\xb5 raw \r\n").encode("latin-1"))
            status, diags = "pass", []
            if mode == "failed_corner":
                status, diags = "error", [{"severity": "error", "code": "netlist", "message": "boom"}]
            if mode in ("missing_meas", "absent_meas", "aborted", "all_absent") and any(x["value"] is None for x in meas):
                status = "error"
                diags = [{"severity": "error", "code": "measurement", "message": "no value"}]
            if mode == "timeout_corner":
                status, diags = "error", [{"severity": "error", "code": "batch_poll_timeout", "message": "t"}]
            corner = {"corner_id": cid, "process": p, "supply_v": row, "temperature_c": t,
                       "status": status, "runtime_s": 1.5, "measurements": meas, "diagnostics": diags,
                       "artifacts": {"log": None if mode == "no_log" else str(log), "raw": None,
                                      "waveform": None, "deck": None}}
            if "FAKE_KLT_FIRST_VALUE" in os.environ:   # value of the first measurement
                meas[0]["value"] = json.loads(os.environ["FAKE_KLT_FIRST_VALUE"])
            corner.update(json.loads(os.environ.get("FAKE_KLT_CORNER_PATCH", "{}")))
            corners.append(corner)
if mode == "drop_corner":
    corners.pop(0)
if mode == "dup_corner":
    corners.append(dict(corners[0]))
if mode == "extra_corner":
    extra = dict(corners[0]); extra["temperature_c"] = 999; corners.append(extra)
env = {"engine": "ngspice"}
if mode != "no_remote":
    env["remote"] = {"provider": "aws-batch-fleet", "job_id": "klt-sim-fake",
                     "runner_compatibility": "match"}
    if mode == "mismatch":
        env["remote"].update(runner_compatibility="mismatch", runner_klt_version="0.0.1",
                             client_klt_version="0.0.0+fake")
    if mode == "legacy_remote":   # an older client that does not report the comparison
        del env["remote"]["runner_compatibility"]
print(json.dumps({"schema_version": 3, "status": "pass", "corner_count": len(corners),
                   "environment": env, "corners": corners}))
'''

FAKE_NGSPICE = '#!/bin/sh\necho "$@" >> "$FAKE_KLT_STATE/ngspice-called"\nexit 0\n'

CONTROL_DECK = textwrap.dedent(
    """\
    * control deck -- GENERATED
    .param vdd_nom=3.3
    .param vdd_val=3.3
    .param t_dip=0.02

    .include "{design}"
    .lib "{lib}" ss
    .lib "{lib}" res_ss

    .temp -40.0
    .options reltol=1e-4

    .include "../frag.spice"

    .control
    set numdgt=8
    set noaskquit
    tran 2e-05 0.03
    let praw_r = v(xdut.por_raw)/(v(vdd)+0.001)
    let vsg = v(vdd)-v(xdut.pg)

    meas tran vdd_pre find v(vdd) at=0.0199
    meas tran t_praw when praw_r=0.5 fall=1 td=0.02
    meas tran vsg_min min vsg from=0.02 to=0.03
    .endc
    .end
    """
)

FILE_SCOPE_DECK = textwrap.dedent(
    """\
    * dwell deck
    .param vdd_val=3.3
    .include "{design}"
    .lib "{lib}" tt
    .temp 27.0
    .param stop_s=0.0026200999999999998
    .tran 2e-06 {{stop_s}}
    .meas tran t_trip when v(xdut.pgdg)=1.1 fall=1 td=1e-05
    .meas tran pgdg_end find v(xdut.pgdg) at=2e-05
    .end
    """
)


class BatchTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self._write_exe("klt", FAKE_KLT.replace("{python}", sys.executable))
        self._write_exe("ngspice", FAKE_NGSPICE)
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_KLT_STATE": str(self.state),
            "HOME": str(self.root / "home"),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("FAKE_KLT_MODE", None)
        os.environ.pop(klt_batch.ENV_BACKEND, None)
        (self.root / "home").mkdir()
        self.pdk = fake_pdk(self.root / "gf180mcuD")
        (self.pdk.ngspice_dir / "design.ngspice").write_text(".param sw_stat_global=0\n")
        self.control = self.root / "control"
        (self.control / "decks").mkdir(parents=True)
        (self.control / "frag.spice").write_text("* fragment\nr1 a b 1k\n")

    def _write_exe(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def mode(self, value):
        os.environ["FAKE_KLT_MODE"] = value

    def cfg(self, **kw) -> BatchConfig:
        kw.setdefault("sleep", lambda s: None)
        kw.setdefault("log", lambda m: None)
        return BatchConfig(pdk=self.pdk, stage_root=self.root / "stage", **kw)

    def deck(self, template=CONTROL_DECK):
        return template.format(design=self.pdk.design_include, lib=self.pdk.model_lib)

    def unit(self, key="d1", template=CONTROL_DECK, **kw):
        return klt_batch.translate_deck(
            self.deck(template), key=key, log_path=self.control / "logs" / f"{key}.log",
            pdk=self.pdk, deck_dir=self.control / "decks", **kw,
        )

    def calls(self):
        p = self.state / "calls.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def assertNoLocalNgspice(self):
        self.assertFalse((self.state / "ngspice-called").exists(), "local ngspice was invoked")


class BackendSelectionTests(BatchTestCase):
    def test_default_is_local_and_needs_no_klt(self):
        self.assertEqual(klt_batch.resolve_backend(None, {}), "local")
        self.assertEqual(klt_batch.resolve_backend("auto", {}), "local")

    def test_env_selects_batch_only_through_the_resolver(self):
        self.assertEqual(klt_batch.resolve_backend(None, {"KLT_SIM_BACKEND": "batch"}), "batch")
        self.assertEqual(klt_batch.resolve_backend("local", {"KLT_SIM_BACKEND": "batch"}), "local")

    def test_unknown_backend_is_an_error_not_a_guess(self):
        for bad in ("remote", "local-parallel", "nope"):
            with self.assertRaises(BatchError):
                klt_batch.resolve_backend(bad, {})
            with self.assertRaises(BatchError):
                klt_batch.resolve_backend(None, {"KLT_SIM_BACKEND": bad})

    def test_library_default_ignores_the_environment(self):
        """KLT_SIM_BACKEND=batch on a dispatch worker must not flip library callers."""
        os.environ[klt_batch.ENV_BACKEND] = "batch"
        os.remove(self.bin / "klt")
        with mock.patch.object(runner.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout="m_x = 1\n", stderr="", returncode=0)
            runner.run_deck_raw("x", "* d\n.end\n", self.control)
        self.assertEqual(run.call_args[0][0][0], runner.NGSPICE)

    def test_batch_without_a_config_refuses_instead_of_running_locally(self):
        with mock.patch.object(runner.subprocess, "run") as run:
            with self.assertRaises(BatchError):
                runner.run_deck_raw("x", self.deck(), self.control, backend="batch")
            with self.assertRaises(BatchError):
                runner.run_deck_raw("x", self.deck(), self.control, backend="bogus")
        run.assert_not_called()


class TranslationTests(BatchTestCase):
    def test_control_deck_is_taken_apart(self):
        u = self.unit()
        self.assertEqual(u.process, ("ss", "res_ss"))
        self.assertEqual(u.temp_c, -40.0)
        self.assertEqual(u.analysis, ("tran", "2e-05 0.03"))
        names = [m[0] for m in u.measurements]
        self.assertEqual(names, ["vdd_pre", "t_praw", "vsg_min"])
        by = {m[0]: m[2] for m in u.measurements}
        # a control-block `let` vector is inlined where a file-scope .meas needs it
        self.assertIn("when par('v(xdut.por_raw)/(v(vdd)+0.001)')=0.5 fall=1 td=0.02", by["t_praw"])
        self.assertIn("min par('v(vdd)-v(xdut.pg)') from=0.02", by["vsg_min"])
        self.assertNotIn(".control", u.body)
        self.assertNotIn(".lib", u.body)
        self.assertNotIn(".temp", u.body)
        self.assertIn(".param vdd_val=3.3", u.body)       # not lifted unless asked
        self.assertIn("sw_stat_global=0", u.body)          # design.ngspice inlined
        self.assertIn("set numdgt=8", u.init)

    def test_file_scope_deck(self):
        u = self.unit(template=FILE_SCOPE_DECK)
        # klt runs the analysis as a control command, where .param braces are
        # not expanded (a live fleet run aborted on `tran 2e-06 {stop_s}`), so
        # the deck's own literal is substituted, unrounded
        self.assertEqual(u.analysis, ("tran", "2e-06 0.0026200999999999998"))
        self.assertIn(".param stop_s=0.0026200999999999998", u.body)
        self.assertEqual([m[0] for m in u.measurements], ["t_trip", "pgdg_end"])
        self.assertTrue(all(m[1] == "spice" for m in u.measurements))

    def test_compose_deck_result_translates_with_expr_measurements(self):
        (self.root / "tb").mkdir()
        (self.root / "tb" / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (self.root / "tb" / "tb.json").write_text(json.dumps({
            "name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)", "iq": "-i(v1)"},
            "params": {"cload": "1p"}, "options": ["reltol=1e-5"], "analyses": ["op"],
        }))
        tb = testbench.load(self.root / "tb")
        point = corners.build_grid(corners.resolve_corners(["ss"]), (125,), [3.63])[0]
        u = klt_batch.translate_deck(
            runner.compose_deck(tb, self.pdk, point), key=point.corner_id,
            log_path=self.root / "o.log", pdk=self.pdk, deck_dir=self.root,
            lift_params=("vdd_val",),
        )
        self.assertEqual(u.analysis, ("op", ""))
        self.assertEqual(u.measurements, (("m_vout", "expr", "v(out)"), ("m_iq", "expr", "-i(v1)")))
        self.assertEqual(u.supply, (("vdd_val", 3.63),))
        self.assertEqual(u.process, tuple(point.corner.sections))
        self.assertNotIn("vdd_val=3.63", u.body)
        self.assertIn(".param vdd_nom=3.3", u.body)
        self.assertIn(".param cload=1p", u.body)
        self.assertIn(".options reltol=1e-5", u.body)

    def test_unsupported_constructs_fail_before_submission(self):
        cases = {
            "write": CONTROL_DECK.replace(".endc", "write out.raw\n.endc"),
            "two analyses": CONTROL_DECK.replace("tran 2e-05 0.03", "tran 2e-05 0.03\nop"),
            "no analysis": CONTROL_DECK.replace("tran 2e-05 0.03\n", ""),
            "no temp": CONTROL_DECK.replace(".temp -40.0\n", ""),
            "foreign lib": CONTROL_DECK.replace('.lib "{lib}" ss', '.lib "/elsewhere/m.lib" ss'),
            "meas op": CONTROL_DECK.replace("meas tran vdd_pre", "meas op vdd_pre"),
            "no measurements": FILE_SCOPE_DECK.replace(".meas", "*meas"),
            "dup measurement": CONTROL_DECK.replace("t_praw", "vdd_pre"),
            "unclosed control": CONTROL_DECK.replace(".endc\n", ""),
            "print of non-let": CONTROL_DECK.replace(".endc", "print nothing\n.endc"),
            "unknown analysis param": FILE_SCOPE_DECK.replace("{{stop_s}}", "{{nope}}"),
            "analysis expression": FILE_SCOPE_DECK.replace("{{stop_s}}", "{{stop_s*2}}"),
            "non-numeric analysis param": FILE_SCOPE_DECK.replace(
                ".param stop_s=0.0026200999999999998", ".param stop_s={{t0+1m}}"),
        }
        for label, template in cases.items():
            with self.subTest(label):
                with self.assertRaises(klt_batch.BatchIncompatible):
                    self.unit(template=template)
        self.assertEqual(self.calls(), [])

    def test_lifted_param_in_analysis_is_rejected(self):
        with self.assertRaises(klt_batch.BatchIncompatible) as cm:
            self.unit(template=FILE_SCOPE_DECK.replace("{{stop_s}}", "{{vdd_val}}"),
                      lift_params=("vdd_val",))
        self.assertIn("lifted", str(cm.exception))

    def test_unresolved_include_is_rejected(self):
        with self.assertRaises(klt_batch.BatchIncompatible) as cm:
            self.unit(template=CONTROL_DECK.replace("../frag.spice", "../missing.spice"))
        self.assertIn("missing.spice", str(cm.exception))
        with self.assertRaises(klt_batch.BatchIncompatible):
            self.unit(template=CONTROL_DECK.replace("../frag.spice", "/nonexistent/abs.spice"))

    def test_env_var_include_and_pdk_tree_include_are_rejected(self):
        with self.assertRaises(klt_batch.BatchIncompatible):
            self.unit(template=CONTROL_DECK.replace("../frag.spice", "$PDK_ROOT/x.spice"))
        with self.assertRaises(klt_batch.BatchIncompatible):
            self.unit(template=CONTROL_DECK.replace("../frag.spice", str(self.pdk.model_lib)))


class RequestTests(BatchTestCase):
    def test_request_shape_staging_and_forced_backend(self):
        u = self.unit(extra_init=klt_batch.compat_init_lines())
        (out,) = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertEqual(req["backend"], "batch")
        self.assertEqual(req["engine"], "ngspice")
        self.assertEqual(req["analysis"], {"kind": "tran", "args": "2e-05 0.03"})
        self.assertEqual(req["corners"]["temperature_c"], [-40.0])
        self.assertEqual(req["corners"]["process"],
                         [{"name": "ss+res_ss", "sections": ["ss", "res_ss"]}])
        self.assertEqual(req["models"]["pdk"], "gf180mcuD")
        self.assertEqual(req["models"]["lib"], "libs.tech/ngspice/sm141064.ngspice")
        self.assertTrue(req["options"]["keep_artifacts"])
        init = req["options"]["ngspice_init"]
        self.assertIn("set num_threads=1", init)
        self.assertIn("set numdgt=8", init)
        self.assertTrue(all(not ln.startswith("*") for ln in init))
        self.assertEqual([m["name"] for m in req["measurements"]], ["vdd_pre", "t_praw", "vsg_min"])
        argv = self.calls()[0]
        self.assertEqual(argv[0], "sim")
        self.assertEqual(argv[argv.index("--backend") + 1], "batch")
        # relative include closure, resolvable from the staged body's directory
        body = (self.state / "body-0.spice").read_text()
        inc = [ln for ln in body.splitlines() if ln.startswith(".include")]
        self.assertEqual(len(inc), 1)
        rel = inc[0].split('"')[1]
        self.assertFalse(os.path.isabs(rel))
        self.assertTrue((self.root / "stage" / "d1" / rel).resolve().samefile(self.control / "frag.spice"))
        self.assertNoLocalNgspice()

    def test_points_sharing_a_body_become_one_matrix_request_with_sparse_excludes(self):
        units = []
        for sections, vdd in ((("ss",), 2.97), (("ss",), 3.63), (("ff",), 2.97)):
            u = klt_batch.translate_deck(
                self.deck(CONTROL_DECK).replace(".lib \"%s\" ss" % self.pdk.model_lib, "")
                .replace(".lib \"%s\" res_ss" % self.pdk.model_lib, "")
                .replace(".param vdd_val=3.3", f".param vdd_val={vdd}")
                + f'\n.lib "{self.pdk.model_lib}" {sections[0]}\n',
                key=f"{sections[0]}_{vdd}", log_path=self.control / "logs" / f"{sections[0]}_{vdd}.log",
                pdk=self.pdk, deck_dir=self.control / "decks", lift_params=("vdd_val",),
            )
            units.append(u)
        outs = klt_batch.run_units(units, self.cfg(), tolerate_absent=True)
        self.assertTrue(all(o.ok for o in outs), [o.message for o in outs])
        self.assertEqual(len(self.calls()), 1)
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertEqual(req["corners"]["supply_v"], {"vdd_val": [2.97, 3.63]})
        self.assertEqual(req["exclude"], [{"process": "ff", "supply_v": {"vdd_val": 3.63}}])
        self.assertEqual([o.unit.key for o in outs], ["ss_2.97", "ss_3.63", "ff_2.97"])

    def test_distinct_decks_are_distinct_requests(self):
        units = [self.unit("a"), self.unit("b", template=CONTROL_DECK.replace("0.02", "0.03", 1))]
        outs = klt_batch.run_units(units, self.cfg(), tolerate_absent=True, jobs=2)
        self.assertEqual([o.unit.key for o in outs], ["a", "b"])
        self.assertTrue(all(o.ok for o in outs))
        self.assertEqual(len(self.calls()), 2)

    def test_duplicate_keys_are_refused_before_any_submission(self):
        with self.assertRaises(klt_batch.BatchIncompatible):
            klt_batch.run_units([self.unit("a"), self.unit("a")], self.cfg(), tolerate_absent=True)
        self.assertEqual(self.calls(), [])


class ArtifactTests(BatchTestCase):
    def test_log_is_copied_byte_for_byte_to_the_expected_name(self):
        u = self.unit("na-x-1mvus-3.30v")
        (out,) = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        src = next((self.root / "stage").rglob("run.log"))
        dest = self.control / "logs" / "na-x-1mvus-3.30v.log"
        self.assertEqual(dest.read_bytes(), src.read_bytes())
        self.assertIn(b"\xb5", dest.read_bytes())
        self.assertEqual(out.log_path, dest)

    def test_run_deck_raw_returns_the_copied_log_and_parses_with_existing_parser(self):
        text = runner.run_deck_raw("na-a", self.deck(), self.control, backend="batch", batch=self.cfg())
        self.assertEqual(text, (self.control / "logs" / "na-a.log").read_text(errors="replace"))
        meas = runner.parse_bare_measurements(text)
        self.assertEqual(meas["vdd_pre"], 0.125)
        self.assertEqual(meas["vsg_min"], 0.125)
        self.assertTrue((self.control / "decks" / "na-a.spice").is_file())   # deck provenance kept
        self.assertNoLocalNgspice()

    def test_run_deck_batch_matches_local_parse_semantics(self):
        local_out = "banner\nvdd_pre = 1.2500000000e-01\nt_praw = 1.2500000000e-01\nvsg_min = 1.2500000000e-01\n"
        with mock.patch.object(runner.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout=local_out, stderr="", returncode=0)
            local = runner.run_deck("na-l", self.deck(), self.control)
        batch = runner.run_deck("na-b", self.deck(), self.control, backend="batch", batch=self.cfg())
        self.assertEqual(local, batch)


class TbFixture(BatchTestCase):
    def setUp(self):
        super().setUp()
        (self.root / "tb").mkdir()
        (self.root / "tb" / "x.spice").write_text("v1 out 0 dc {vdd_val}\n")
        (self.root / "tb" / "tb.json").write_text(json.dumps({
            "name": "x", "netlist": "x.spice", "measure": {"vout": "v(out)", "iq": "-i(v1)"},
        }))
        self.tb = testbench.load(self.root / "tb")
        self.points = corners.build_grid(corners.resolve_corners(["tt", "ss"]), (-40, 125), [2.97, 3.63])
        self.log_dir = self.root / "corners" / "rec"


class GridTests(TbFixture):
    def grid(self, **kw):
        seen = []
        res = runner.run_grid(
            self.tb, self.pdk, self.points, self.root / "work", jobs=2, log_dir=self.log_dir,
            on_result=seen.append, backend="batch", batch=self.cfg(**kw),
        )
        return res, seen

    def test_grid_order_statuses_logs_and_one_request_per_temperature(self):
        res, seen = self.grid()
        self.assertEqual([r.point.corner_id for r in res], [p.corner_id for p in self.points])
        self.assertEqual(len(seen), len(self.points))
        self.assertTrue(all(r.status == "ok" for r in res), [r.message for r in res])
        for r in res:
            self.assertEqual(r.log, f"{r.point.corner_id}.log")
            self.assertTrue((self.log_dir / r.log).is_file())
            self.assertEqual(set(r.measurements), {"vout", "iq"})
        self.assertEqual(len(self.calls()), 2)           # -40 C and 125 C
        self.assertTrue(list(self.log_dir.glob("klt-*.request.json")))
        self.assertTrue(list(self.log_dir.glob("klt-*.report.json")))
        self.assertNoLocalNgspice()

    def test_every_failure_mode_is_a_non_ok_point(self):
        for mode in ("refuse", "invalid_json", "empty", "failed_corner", "drop_corner",
                     "dup_corner", "extra_corner", "no_log", "missing_meas", "timeout_corner",
                     "no_remote", "absent_meas"):
            with self.subTest(mode):
                self.mode(mode)
                (self.state / "calls.jsonl").unlink(missing_ok=True)
                if mode == "absent_meas":
                    # t_trip is not one of this bench's measurements -> nothing absent
                    res, _ = self.grid()
                    self.assertTrue(all(r.status == "ok" for r in res))
                    continue
                res, _ = self.grid()
                self.assertEqual(len(res), len(self.points))
                if mode in ("drop_corner", "dup_corner"):
                    # each of the two requests (-40 C, 125 C) loses/duplicates one corner
                    bad = [r for r in res if r.status != "ok"]
                    self.assertEqual(len(bad), 2)
                    self.assertTrue(all(r.message for r in bad))
                else:
                    self.assertTrue(all(r.status != "ok" for r in res), mode)
                    self.assertTrue(all(r.message for r in res), mode)
                self.assertNoLocalNgspice()

    def test_klt_missing_raises_and_never_runs_local(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            with self.assertRaises(klt_batch.KltMissing):
                self.grid()
        self.assertNoLocalNgspice()

    def test_untranslatable_deck_becomes_an_error_point(self):
        with mock.patch.object(runner, "compose_deck", return_value="* d\n.control\nwrite x\n.endc\n"):
            res, _ = self.grid()
        self.assertTrue(all(r.status == "error" and "klt sim request" in r.message for r in res))
        self.assertEqual(self.calls(), [])


class CliTests(TbFixture):
    def _args(self, *extra):
        return cli.build_parser().parse_args(
            [str(self.root / "tb"), "--corners", "tt", "--temps", "27", "--supply-tol", "0",
             "--no-write", "--quiet", *extra]
        )

    def test_batch_cli_run_never_needs_local_ngspice(self):
        os.remove(self.bin / "ngspice")                       # not even installed
        with mock.patch.object(cli, "find_pdk", return_value=self.pdk), \
                mock.patch.object(cli, "WORK_DIR", self.root / "work"):
            code = cli.run(self._args("--backend", "batch"))
        self.assertEqual(code, cli.EXIT_OK)
        sims = [c for c in self.calls() if c[0] == "sim"]
        self.assertTrue(sims)
        self.assertEqual(sims[0][sims[0].index("--backend") + 1], "batch")

    def test_env_selected_batch_failure_is_a_nonzero_exit_not_a_local_run(self):
        self.mode("refuse")
        with mock.patch.dict(os.environ, {klt_batch.ENV_BACKEND: "batch"}), \
                mock.patch.object(cli, "find_pdk", return_value=self.pdk), \
                mock.patch.object(cli, "WORK_DIR", self.root / "work"):
            code = cli.run(self._args())
        self.assertNotEqual(code, cli.EXIT_OK)
        self.assertNoLocalNgspice()

    def test_missing_klt_is_an_environment_error(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), \
                mock.patch.object(cli, "find_pdk", return_value=self.pdk):
            code = cli.run(self._args("--backend", "batch"))
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        self.assertNoLocalNgspice()


class FailureMatrixTests(BatchTestCase):
    def assertFails(self, mode, needle, **cfg_kw):
        self.mode(mode)
        (out,) = klt_batch.run_units([self.unit()], self.cfg(**cfg_kw), tolerate_absent=True)
        self.assertEqual(out.status, "error", mode)
        self.assertIn(needle, out.message, mode)
        self.assertFalse((self.control / "logs" / "d1.log").exists(), "failed unit left a log")
        with self.assertRaises(BatchError):
            runner.run_deck_raw("r", self.deck(), self.control, backend="batch", batch=self.cfg(**cfg_kw))
        self.assertNoLocalNgspice()

    def test_refused_submission(self):
        self.assertFails("refuse", "refused")

    def test_invalid_json(self):
        self.assertFails("invalid_json", "not a JSON report")

    def test_no_output(self):
        self.assertFails("empty", "no JSON report")

    def test_timeout(self):
        self.assertFails("timeout", "did not finish", poll_timeout_s=1, client_slack_s=0.5)

    def test_failed_corner(self):
        self.assertFails("failed_corner", "netlist")

    def test_poll_timeout_diagnostic_is_never_tolerated(self):
        self.assertFails("timeout_corner", "batch_poll_timeout")

    def test_missing_corner(self):
        self.assertFails("drop_corner", "no result returned")

    def test_duplicate_corner(self):
        self.assertFails("dup_corner", "expected exactly one")

    def test_unrequested_corner(self):
        self.mode("extra_corner")
        (out,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("match no requested unit", out.message)

    def test_missing_log(self):
        self.assertFails("no_log", "no raw log")

    def test_not_executed_on_the_fleet(self):
        self.assertFails("no_remote", "not executed on the")

    def test_aborted_analysis_is_never_an_absent_measurement(self):
        # Observed live: the fleet returned status 'error' with only
        # `measurement` diagnostics for a run whose transient aborted. That
        # must not be read as "every event simply never happened".
        self.assertFails("aborted", "aborted")

    def test_no_measurement_value_at_all_is_an_error_even_when_absence_is_tolerated(self):
        self.assertFails("all_absent", "no requested measurement produced a value")

    def test_runner_client_mismatch_is_rejected_and_halts_the_run(self):
        self.mode("mismatch")
        units = [self.unit("a"), self.unit("b", template=CONTROL_DECK.replace("0.02", "0.03", 1))]
        cfg = self.cfg()
        outs = klt_batch.run_units(units, cfg, tolerate_absent=True)
        self.assertEqual([o.status for o in outs], ["error", "error"])
        self.assertIn("runner_compatibility='mismatch'", outs[0].message)
        self.assertIn("not submitted", outs[1].message)
        self.assertEqual(len(self.calls()), 1)              # the second request never left
        self.assertFalse((self.control / "logs" / "a.log").exists())
        with self.assertRaises(BatchError):                  # same config, later deck
            runner.run_deck_raw("r", self.deck(), self.control, backend="batch", batch=cfg)
        self.assertEqual(len(self.calls()), 1)
        self.assertNoLocalNgspice()

    def test_report_without_a_runner_comparison_is_still_accepted(self):
        self.mode("legacy_remote")
        (out,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)

    def test_klt_client_is_selectable(self):
        other = self.bin / "klt-runner-build"
        (self.bin / "klt").rename(other)
        (out,) = klt_batch.run_units([self.unit()], self.cfg(klt=str(other)), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        import argparse
        parser = argparse.ArgumentParser()
        klt_batch.add_backend_argument(parser)
        self.assertEqual(parser.parse_args([]).klt, "klt")
        self.assertEqual(parser.parse_args(["--klt", str(other)]).klt, str(other))

    def test_missing_measurement_is_an_error_unless_the_caller_tolerates_absence(self):
        self.mode("missing_meas")
        (strict,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=False)
        self.assertEqual(strict.status, "error")
        self.assertIn("vsg_min", strict.message)
        (lenient,) = klt_batch.run_units([self.unit("d2")], self.cfg(), tolerate_absent=True)
        self.assertTrue(lenient.ok)
        self.assertEqual(lenient.absent, ["vsg_min"])
        self.assertNotIn("vsg_min", runner.parse_bare_measurements(lenient.text()).keys() - {"vsg_min"})

    def test_klt_missing(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            with self.assertRaises(klt_batch.KltMissing):
                klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=True)
            with self.assertRaises(klt_batch.KltMissing):
                runner.run_deck_raw("r", self.deck(), self.control, backend="batch", batch=self.cfg())
        self.assertNoLocalNgspice()

    def test_capacity_refusal_is_retried_then_succeeds(self):
        self.mode("cap_then_ok")
        slept = []
        (out,) = klt_batch.run_units([self.unit()], self.cfg(sleep=slept.append), tolerate_absent=True)
        self.assertTrue(out.ok)
        self.assertEqual(len(slept), 1)
        self.assertEqual(len(self.calls()), 2)

    def test_minimal_valid_report_still_passes_strictly(self):
        (out,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=False)
        self.assertTrue(out.ok, out.message)
        self.assertEqual(out.values, {"vdd_pre": 0.125, "t_praw": 0.125, "vsg_min": 0.125})
        self.assertEqual(out.absent, [])

    def test_capacity_refusal_is_bounded(self):
        self.mode("cap_then_ok")
        (self.state / "capped").unlink(missing_ok=True)
        (out,) = klt_batch.run_units([self.unit()], self.cfg(max_cap_wait_s=0), tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("CONCURRENT", out.message)


class ResultValidationTests(BatchTestCase):
    """A report that disagrees with itself, or carries malformed values or
    containers, is an error outcome -- never ``ok``, never an unrelated
    exception, never a copied log, never a local run (#335)."""

    def patch(self, *, corner=None, first_value=None, mode="ok"):
        self.mode(mode)
        if corner is not None:
            os.environ["FAKE_KLT_CORNER_PATCH"] = json.dumps(corner)
        if first_value is not None:
            os.environ["FAKE_KLT_FIRST_VALUE"] = first_value

    def assertRejected(self, needle, unit_kw=None):
        unit_kw = unit_kw or {}
        for tolerate in (False, True):
            with self.subTest(tolerate_absent=tolerate):
                key = f"v{int(tolerate)}"
                (out,) = klt_batch.run_units([self.unit(key, **unit_kw)], self.cfg(),
                                             tolerate_absent=tolerate)
                self.assertEqual(out.status, "error", out.message)
                self.assertIn(needle, out.message)
                self.assertIsNone(out.log_path)
                self.assertFalse((self.control / "logs" / f"{key}.log").exists(),
                                 "a rejected unit's raw log was copied as an accepted result")
        with self.assertRaises(BatchError):
            runner.run_deck_raw("r", self.deck(), self.control, backend="batch", batch=self.cfg())
        self.assertFalse((self.control / "logs" / "r.log").exists())
        self.assertNoLocalNgspice()

    # -- contradictory success labels ------------------------------------

    def test_pass_label_with_netlist_error_diagnostic_fails(self):
        self.patch(corner={"diagnostics": [
            {"severity": "error", "code": "netlist", "message": "unknown subckt"}]})
        self.assertRejected("netlist")

    def test_pass_label_with_timeout_error_diagnostic_fails(self):
        self.patch(corner={"diagnostics": [
            {"severity": "error", "code": "timeout", "message": "wall clock"}]})
        self.assertRejected("timeout")

    def test_pass_label_with_only_absent_measurement_error_is_contradictory(self):
        # The absence exception is for corners klt itself labelled 'error'.
        self.patch(corner={"diagnostics": [
            {"severity": "error", "code": "measurement", "message": "no value"}]})
        self.assertRejected("contradict")

    def test_absence_error_without_an_absent_value_is_not_tolerated(self):
        self.patch(corner={"status": "error", "diagnostics": [
            {"severity": "error", "code": "measurement", "message": "no value"}]})
        self.assertRejected("no requested measurement is absent")

    def test_absence_error_mixed_with_another_error_is_not_tolerated(self):
        self.patch(mode="missing_meas", corner={"diagnostics": [
            {"severity": "error", "code": "measurement", "message": "no value"},
            {"severity": "error", "code": "netlist", "message": "boom"}]})
        self.assertRejected("netlist")

    def test_warning_diagnostics_do_not_fail_a_pass(self):
        self.patch(corner={"diagnostics": [
            {"severity": "warning", "code": "netlist", "message": "minor"}]})
        (out,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=False)
        self.assertTrue(out.ok, out.message)

    # -- measurement values ---------------------------------------------

    def test_string_value_fails(self):
        self.patch(first_value='"1.25e-01"')
        self.assertRejected("vdd_pre")

    def test_boolean_value_fails(self):
        self.patch(first_value="true")
        self.assertRejected("vdd_pre")

    def test_nan_value_fails(self):
        self.patch(first_value="NaN")
        self.assertRejected("not a finite number")

    def test_infinite_values_fail(self):
        for text in ("Infinity", "-Infinity"):
            with self.subTest(text):
                self.patch(first_value=text)
                self.assertRejected("not a finite number")

    def test_container_value_fails(self):
        self.patch(first_value="[0.125]")
        self.assertRejected("vdd_pre")

    def test_finite_zero_passes(self):
        for text in ("0", "0.0", "-0.0"):
            with self.subTest(text):
                self.patch(first_value=text)
                (out,) = klt_batch.run_units([self.unit(f"z{len(text)}")], self.cfg(),
                                             tolerate_absent=False)
                self.assertTrue(out.ok, out.message)
                self.assertEqual(out.values["vdd_pre"], 0.0)
                self.assertIsInstance(out.values["vdd_pre"], float)
                self.assertEqual(out.absent, [])

    def test_tolerated_absence_keeps_its_behaviour(self):
        self.patch(mode="missing_meas")
        (out,) = klt_batch.run_units([self.unit()], self.cfg(), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.assertEqual(out.absent, ["vsg_min"])
        self.assertIsNone(out.values["vsg_min"])

    def test_malformed_value_is_not_hidden_by_tolerated_absence(self):
        self.patch(mode="missing_meas", first_value='"oops"')
        self.assertRejected("vdd_pre")

    # -- malformed containers --------------------------------------------

    def test_measurements_not_a_list(self):
        self.patch(corner={"measurements": {"vdd_pre": 0.125}})
        self.assertRejected("measurements")

    def test_measurement_entry_not_an_object(self):
        self.patch(corner={"measurements": [["vdd_pre", 0.125]]})
        self.assertRejected("measurements")

    def test_measurement_name_not_a_string(self):
        self.patch(corner={"measurements": [{"name": 3, "value": 0.125}]})
        self.assertRejected("measurements")

    def test_duplicate_measurement_name(self):
        self.patch(corner={"measurements": [
            {"name": "vdd_pre", "value": 0.125}, {"name": "vdd_pre", "value": 0.5},
            {"name": "t_praw", "value": 0.125}, {"name": "vsg_min", "value": 0.125}]})
        self.assertRejected("more than once")

    def test_diagnostics_not_a_list(self):
        self.patch(corner={"diagnostics": "netlist: boom"})
        self.assertRejected("diagnostics")

    def test_diagnostic_entry_not_an_object(self):
        self.patch(corner={"diagnostics": ["error: boom"]})
        self.assertRejected("diagnostics")

    def test_artifacts_not_an_object(self):
        self.patch(corner={"artifacts": ["run.log"]})
        self.assertRejected("artifacts")

    def test_log_path_not_a_string(self):
        self.patch(corner={"artifacts": {"log": 7}})
        self.assertRejected("artifacts")

    def test_runtime_not_a_number(self):
        self.patch(corner={"runtime_s": "fast"})
        self.assertRejected("runtime_s")

    def test_status_missing(self):
        self.patch(corner={"status": None})
        self.assertRejected("status")

    def test_malformed_supply_value_is_a_batch_failure(self):
        lift = {"lift_params": ("vdd_val",)}
        for sv in ({"vdd_val": "abc"}, ["vdd_val"], "vdd_val"):
            with self.subTest(sv=sv):
                self.patch(corner={"supply_v": sv})
                for tolerate in (False, True):
                    (out,) = klt_batch.run_units([self.unit("s", **lift)], self.cfg(),
                                                 tolerate_absent=tolerate)
                    self.assertEqual(out.status, "error")
                    self.assertIn("match no requested unit", out.message)
                    self.assertFalse((self.control / "logs" / "s.log").exists())
        self.assertNoLocalNgspice()

    def test_boolean_temperature_does_not_match(self):
        self.patch(corner={"temperature_c": True})
        u = self.unit(template=CONTROL_DECK.replace(".temp -40.0", ".temp 1.0"))
        (out,) = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("match no requested unit", out.message)


class ControlScriptWiringTests(BatchTestCase):
    def test_dwell_sweep_run_all_routes_through_batch_and_keys_by_deck_name(self):
        import importlib.util

        path = SIM_DIR / "por-output-chain-deglitch" / "control" / "run_dwell_sweep.py"
        spec = importlib.util.spec_from_file_location("run_dwell_sweep_t", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.CONTROL_DIR = self.control
        jobs = [("d_a", self.deck(FILE_SCOPE_DECK)), ("d_b", self.deck(FILE_SCOPE_DECK).replace("1e-05", "2e-05"))]
        out = mod.run_all(jobs, 2, "batch", self.cfg())
        self.assertNoLocalNgspice()
        self.assertEqual(list(out), ["d_a", "d_b"])
        self.assertEqual(out["d_a"]["t_trip"], 0.125)
        self.assertTrue((self.control / "logs" / "d_a.log").is_file())

    def test_dwell_sweep_run_all_local_default_is_unchanged(self):
        import importlib.util

        path = SIM_DIR / "por-output-chain-deglitch" / "control" / "run_dwell_sweep.py"
        spec = importlib.util.spec_from_file_location("run_dwell_sweep_l", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.CONTROL_DIR = self.control
        with mock.patch.object(runner.subprocess, "run") as run:
            run.return_value = mock.Mock(stdout="t_trip = 1.0e-06\n", stderr="", returncode=0)
            out = mod.run_all([("d_a", "* x\n.end\n")], 1)
        self.assertEqual(out["d_a"]["t_trip"], 1e-06)
        self.assertEqual(run.call_args[0][0][:2], [runner.NGSPICE, "-b"])


if __name__ == "__main__":
    unittest.main()
