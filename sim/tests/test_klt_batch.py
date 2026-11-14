#!/usr/bin/env python3
"""Tests for the fail-closed `klt sim` batch backend (#331).

No PDK, no ngspice, no klt, no network: a fake ``klt`` executable (and a fake
``ngspice`` that records any invocation) are placed first on PATH.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import contextlib
import hashlib
import io
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
if not os.environ.get("FAKE_KLT_INNER"):
    with open(state / "calls.jsonl", "a") as fh:
        fh.write(json.dumps(args) + "\n")
if args == ["--version"]:
    print("klt 0.0.0+fake"); sys.exit(0)
if "--batch-set" in args:
    import subprocess
    i = args.index("--batch-set") + 1
    reqs = []
    while i < len(args) and not args[i].startswith("--"):
        reqs.append(args[i]); i += 1
    outdir = Path(args[args.index("-o") + 1])
    if mode == "set_refuse":
        print(json.dumps({"error": {"message": "set refused"}})); sys.exit(1)
    entries, worst = [], 0
    for k, r in enumerate(reqs):
        stem = Path(r).stem
        d = outdir / stem; d.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, FAKE_KLT_INNER="1")
        p = subprocess.run([sys.argv[0], "sim", r, "-o", str(d), "--format", "json"],
                           capture_output=True, text=True, env=env)
        try:
            rep = json.loads(p.stdout)
        except ValueError:
            rep = None
        if mode == "set_member_refused" and k == 0:
            rep = None
        if isinstance(rep, dict) and "corners" in rep:
            (d / "report.json").write_text(json.dumps(rep))
            entries.append({"index": k, "request": r, "status": "pass", "exit_code": 0,
                            "report": str(d / "report.json"), "error": None})
        else:
            worst = 4
            entries.append({"index": k, "request": r, "status": "error", "exit_code": 1,
                            "report": None,
                            "error": {"message": "refused", "code": "batch_no_capacity"}})
    print(json.dumps({"schema_version": 1, "status": "pass" if not worst else "error",
                      "request_count": len(reqs), "requests": entries}))
    sys.exit(worst)
req_path = Path(args[1]); outdir = Path(args[args.index("-o") + 1])
req = json.loads(req_path.read_text())
# Claim the next free index atomically ("x" = O_EXCL): concurrent fake-klt
# processes (the MC grid runs jobs>1) must never share an index.
n_prev = 0
while True:
    try:
        fh = open(state / f"req-{n_prev}.json", "x")
        break
    except FileExistsError:
        n_prev += 1
with fh:
    fh.write(json.dumps(req))
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
sv = c.get("params", {})
keys = list(sv)
rows = [dict(zip(keys, vals)) for vals in zip(*[sv[k] for k in keys])] if keys else [{}]
excl = req.get("exclude", [])
corners = []
for p in procs:
    for row in rows:
        for t in c["temperature_c"]:
            if any(e.get("process", p) == p and e.get("params", row) == row for e in excl):
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
            corner = {"corner_id": cid, "process": p, "supply_v": {}, "temperature_c": t,
                       **({"params": row} if row else {}),
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
    # The model card the runner executed, in klt 0.9.2's shape: a lowercase
    # 64-hex string or null, plus klt's own client-vs-runner comparison
    # (`match` / `mismatch` / `not_comparable` + reason).
    sha = os.environ.get("FAKE_KLT_RUNNER_MODELS_SHA", "")
    env["remote"]["runner_models_lib_sha256"] = sha or None
    env["remote"]["models_lib_comparison"] = json.loads(
        os.environ.get("FAKE_KLT_MODELS_COMPARISON", json.dumps(
            {"status": "match"} if sha
            else {"status": "not_comparable", "reason": "runner_hash_unavailable"})))
    if mode == "mismatch":
        env["remote"].update(runner_compatibility="mismatch", runner_klt_version="0.0.1",
                             client_klt_version="0.0.0+fake")
    if mode == "legacy_remote":   # an older client that does not report the comparison
        del env["remote"]["runner_compatibility"]
        del env["remote"]["runner_models_lib_sha256"]
        del env["remote"]["models_lib_comparison"]
    if mode == "fleet_members":
        # A multi-job submission: klt attaches the comparison per fleet
        # member rather than on `environment.remote` itself.
        env["remote"]["fleet"] = [
            {"job_id": "klt-sim-fake-a", "runner_models_lib_sha256": sha or None,
             "models_lib_comparison": env["remote"]["models_lib_comparison"]},
            {"job_id": "klt-sim-fake-b", "runner_models_lib_sha256": sha or None,
             "models_lib_comparison": env["remote"]["models_lib_comparison"]},
        ]
        del env["remote"]["runner_models_lib_sha256"]
        del env["remote"]["models_lib_comparison"]
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
        # By default the fake runner reports the model library THIS fixture
        # resolved, the way a correctly-matched fleet image does (#468).
        self.local_models_sha = hashlib.sha256(self.pdk.model_lib.read_bytes()).hexdigest()
        os.environ["FAKE_KLT_RUNNER_MODELS_SHA"] = self.local_models_sha
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

    STEPPED_DECK = textwrap.dedent(
        """\
        * two-solve deck
        .param vdd_val=3.3
        .include "{design}"
        .lib "{lib}" tt
        .temp 125.0
        .control
        set numdgt=10
        dc temp 25 25 1
        let m_a25 = v(ptat)
        print m_a25
        dc temp 125 125 1
        let m_atgt = v(ptat)
        let m_tk = v(tk)
        print m_atgt
        print m_tk
        .endc
        .end
        """
    )

    def test_two_solve_deck_becomes_analysis_steps(self):
        u = self.unit(template=self.STEPPED_DECK)
        self.assertEqual([s[0] for s in u.steps], ["s1", "s2"])
        self.assertEqual(u.steps[0][1], ("dc", "temp 25 25 1"))
        self.assertEqual(u.steps[1][1], ("dc", "temp 125 125 1"))
        self.assertEqual(u.steps[0][2], (("raw_m_a25", "expr", "v(ptat)"),))
        self.assertEqual([m[0] for m in u.steps[1][2]], ["raw_m_atgt", "raw_m_tk"])
        # derived measurements keep the deck's own print names
        self.assertEqual(u.measurements, (("m_a25", "expr", "s1.raw_m_a25"),
                                          ("m_atgt", "expr", "s2.raw_m_atgt"),
                                          ("m_tk", "expr", "s2.raw_m_tk")))
        req = klt_batch._build_request([u], self.pdk, self.cfg())
        self.assertNotIn("analysis", req)
        self.assertEqual([s["name"] for s in req["analysis_steps"]], ["s1", "s2"])
        self.assertEqual(req["analysis_steps"][1]["analysis"], {"kind": "dc", "args": "temp 125 125 1"})
        self.assertEqual([m["name"] for m in req["measurements"]], ["m_a25", "m_atgt", "m_tk"])

    def test_two_solve_deck_runs_through_the_fake_klt(self):
        u = self.unit(template=self.STEPPED_DECK)
        (out,) = klt_batch.run_units([u], self.cfg())
        self.assertTrue(out.ok, out.message)
        self.assertIn("analysis_steps", self.calls() and json.loads((self.state / "req-0.json").read_text()))
        self.assertNoLocalNgspice()

    def test_single_analysis_request_is_unchanged(self):
        u = self.unit()
        self.assertEqual(u.steps, ())
        req = klt_batch._build_request([u], self.pdk, self.cfg())
        self.assertEqual(req["analysis"], {"kind": "tran", "args": "2e-05 0.03"})
        self.assertNotIn("analysis_steps", req)

    def test_second_file_scope_analysis_is_still_refused(self):
        deck = self.deck(FILE_SCOPE_DECK).replace(".end\n", ".op\n.end\n")
        with self.assertRaises(klt_batch.BatchIncompatible):
            klt_batch.translate_deck(deck, key="x", log_path=self.root / "x.log",
                                     pdk=self.pdk, deck_dir=self.control / "decks")

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
        self.assertEqual(u.lifted, (("vdd_val", 3.63),))
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
        self.assertEqual(req["corners"]["params"], {"vdd_val": [2.97, 3.63]})
        self.assertNotIn("supply_v", req["corners"])
        self.assertEqual(req["exclude"], [{"process": "ff", "params": {"vdd_val": 3.63}}])
        self.assertEqual([o.unit.key for o in outs], ["ss_2.97", "ss_3.63", "ff_2.97"])

    def test_lifted_param_rides_the_params_axis_with_a_declaration_kept(self):
        """#464: klt's `supply_v` axis is an `alter` of a voltage *source*, so a
        `.param` name on it addresses nothing and the request is refused. The
        value must ride `corners.params` instead, and the body must keep a
        top-level declaration for `alterparam` to rewrite."""
        u = self.unit("s", lift_params=("vdd_val",))
        self.assertEqual(u.lifted, (("vdd_val", 3.3),))
        decls = [ln for ln in u.body.splitlines() if ln.startswith(".param vdd_val")]
        self.assertEqual(decls, [f".param vdd_val={klt_batch._LIFTED_DEFAULT}"])
        self.assertNotIn(".param vdd_val=3.3", u.body)
        outs = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertTrue(all(o.ok for o in outs), [o.message for o in outs])
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertEqual(req["corners"]["params"], {"vdd_val": [3.3]})
        self.assertNotIn("supply_v", req["corners"])

    def test_lifted_declaration_is_constant_so_points_still_share_one_request(self):
        """The kept declaration must not carry the unit's own value: bodies
        would then differ and every supply point would cost its own request."""
        units = [self.unit(f"s{v}", lift_params=("vdd_val",),
                           template=CONTROL_DECK.replace(".param vdd_val=3.3", f".param vdd_val={v}"))
                 for v in (2.97, 3.3, 3.63)]
        self.assertEqual(len({u.body for u in units}), 1)
        outs = klt_batch.run_units(units, self.cfg(), tolerate_absent=True)
        self.assertTrue(all(o.ok for o in outs), [o.message for o in outs])
        self.assertEqual(len(self.calls()), 1)
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertEqual(req["corners"]["params"], {"vdd_val": [2.97, 3.3, 3.63]})
        self.assertEqual([o.unit.key for o in outs], ["s2.97", "s3.3", "s3.63"])

    def test_no_lifted_params_builds_an_unchanged_axis_set(self):
        """`lift_params=()` (sim/pex/build_requests.py) keeps the old shape:
        no parameter axis, no declaration rewritten."""
        u = self.unit("s")
        self.assertEqual(u.lifted, ())
        self.assertIn(".param vdd_val=3.3", u.body)
        outs = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertTrue(all(o.ok for o in outs), [o.message for o in outs])
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertNotIn("params", req["corners"])
        self.assertNotIn("supply_v", req["corners"])

    def test_request_does_not_pin_models_pdk_root(self):
        """#464: klt refuses a `models.pdk_root` that is a directory on the
        submitting host (`models_pdk_root_host_path`), because the field is
        forwarded to the fleet runner verbatim. It is refused at submit time,
        which `--dry-run` never reaches, so the guard has to live here."""
        klt_batch.run_units([self.unit("s", lift_params=("vdd_val",))], self.cfg(),
                            tolerate_absent=True)
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertEqual(req["models"]["pdk"], self.pdk.variant)
        self.assertNotIn("pdk_root", req["models"])

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
        # wait_for_capacity_s=0 because the client-side bound now includes it
        # (#467); the default 600 would make this test wait out that window.
        self.assertFails("timeout", "did not finish",
                         poll_timeout_s=1, client_slack_s=0.5, wait_for_capacity_s=0)

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

    # ---- the PDK the fleet runner actually read (#468) -------------------
    #
    # On batch the models come from the runner's own image, so a report is
    # only accepted when the model library it executed is the one this host
    # resolved -- otherwise the record would name a build the simulation
    # never read.

    def test_runner_pdk_matching_this_host_is_accepted_and_recorded(self):
        cfg = self.cfg()
        (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.assertEqual(cfg.provenance, [{
            "job_id": "klt-sim-fake",
            "runner_models_lib_sha256": self.local_models_sha,
            "models_lib_sha256": self.local_models_sha,
            "comparison": {"status": "match"},
            "klt_models_lib_comparison": "match",
        }])
        self.assertEqual(klt_batch.batch_provenance(cfg), {
            "backend": "batch",
            "models_lib_sha256": self.local_models_sha,
            "models_lib_comparison": "match",
            "jobs": cfg.provenance,
        })

    def test_runner_pdk_differing_from_this_host_is_rejected_and_halts_the_run(self):
        other = "a" * 64
        os.environ["FAKE_KLT_RUNNER_MODELS_SHA"] = other
        units = [self.unit("a"), self.unit("b", template=CONTROL_DECK.replace("0.02", "0.03", 1))]
        cfg = self.cfg()
        outs = klt_batch.run_units(units, cfg, tolerate_absent=True)
        self.assertEqual([o.status for o in outs], ["error", "error"])
        self.assertIn(other, outs[0].message)                  # both hashes named
        self.assertIn(self.local_models_sha, outs[0].message)
        self.assertIn(str(self.pdk.model_lib), outs[0].message)  # the local path
        self.assertIn("PDK_ROOT", outs[0].message)               # and the fix
        self.assertIn("not submitted", outs[1].message)
        self.assertEqual(len(self.calls()), 1)                 # the second request never left
        self.assertTrue(cfg.halted)
        self.assertEqual(cfg.provenance, [])                   # nothing recorded
        self.assertFalse((self.control / "logs" / "a.log").exists())
        with self.assertRaises(BatchError):                    # same config, later deck
            runner.run_deck_raw("r", self.deck(), self.control, backend="batch", batch=cfg)
        self.assertEqual(len(self.calls()), 1)
        self.assertNoLocalNgspice()

    def test_klt_own_models_lib_mismatch_verdict_is_rejected_the_same_way(self):
        # klt compares the runner against the install *klt* resolved, which
        # need not be the one find_pdk() resolved: its verdict is fatal even
        # when the hash it reports equals ours.
        os.environ["FAKE_KLT_MODELS_COMPARISON"] = json.dumps(
            {"status": "mismatch", "warning": "runner models differ from client"})
        cfg = self.cfg()
        (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("models_lib_comparison='mismatch'", out.message)
        self.assertIn("runner models differ from client", out.message)
        self.assertTrue(cfg.halted)
        self.assertEqual(cfg.provenance, [])
        self.assertNoLocalNgspice()

    def test_no_usable_runner_hash_is_accepted_as_not_comparable_never_a_match(self):
        for label, sha in (("null", ""), ("not 64-hex", "deadbeef"), ("uppercase junk", "ZZ")):
            with self.subTest(label):
                os.environ["FAKE_KLT_RUNNER_MODELS_SHA"] = sha
                os.environ["FAKE_KLT_MODELS_COMPARISON"] = json.dumps(
                    {"status": "not_comparable", "reason": "runner_hash_unavailable"})
                cfg = self.cfg()
                (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
                self.assertTrue(out.ok, out.message)
                self.assertFalse(cfg.halted)
                (row,) = cfg.provenance
                self.assertIsNone(row["runner_models_lib_sha256"])
                self.assertEqual(row["comparison"],
                                 {"status": "not_comparable", "reason": "runner_hash_unavailable"})
                self.assertEqual(klt_batch.batch_provenance(cfg)["models_lib_comparison"],
                                 "not_comparable")

    def test_an_older_runner_reporting_no_models_fields_at_all_is_accepted(self):
        self.mode("legacy_remote")
        cfg = self.cfg()
        (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        (row,) = cfg.provenance
        self.assertIsNone(row["runner_models_lib_sha256"])
        self.assertIsNone(row["klt_models_lib_comparison"])
        self.assertEqual(row["comparison"]["status"], "not_comparable")

    def test_a_model_library_this_host_cannot_read_is_not_comparable_not_a_match(self):
        unit = self.unit()
        self.pdk.model_lib.unlink()
        cfg = self.cfg()
        (out,) = klt_batch.run_units([unit], cfg, tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        (row,) = cfg.provenance
        self.assertIsNone(row["models_lib_sha256"])
        self.assertEqual(row["comparison"],
                         {"status": "not_comparable", "reason": "client_hash_unavailable"})

    def test_a_multi_job_report_is_gated_and_recorded_per_fleet_member(self):
        self.mode("fleet_members")
        cfg = self.cfg()
        (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.assertEqual([r["job_id"] for r in cfg.provenance],
                         ["klt-sim-fake-a", "klt-sim-fake-b"])
        self.assertEqual({r["comparison"]["status"] for r in cfg.provenance}, {"match"})
        self.assertEqual(klt_batch.batch_provenance(cfg)["models_lib_comparison"], "match")
        # ... and one differing member condemns the report
        os.environ["FAKE_KLT_RUNNER_MODELS_SHA"] = "b" * 64
        bad = self.cfg()
        (out,) = klt_batch.run_units([self.unit("b")], bad, tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("klt-sim-fake-a", out.message)
        self.assertTrue(bad.halted)
        self.assertEqual(bad.provenance, [])

    def test_batch_provenance_of_a_run_that_accepted_nothing_says_so(self):
        self.mode("refuse")
        cfg = self.cfg()
        (out,) = klt_batch.run_units([self.unit()], cfg, tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertEqual(klt_batch.batch_provenance(cfg)["models_lib_comparison"],
                         "no_accepted_report")

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

    def test_klt_pin_builds_a_uvx_wrapper_without_touching_host_klt(self):
        import argparse
        import subprocess
        parser = argparse.ArgumentParser()
        klt_batch.add_backend_argument(parser)
        args = parser.parse_args(["--klt-pin", "0.5.0"])
        self.assertEqual(args.klt_pin, "0.5.0")
        self.assertNotEqual(args.klt, "klt")
        self.assertIsNone(parser.parse_args([]).klt_pin)
        # the wrapper runs `uvx --from klayout-tools==0.5.0 klt <args>`
        uvx = self.bin / "uvx"
        uvx.write_text("#!/bin/sh\necho \"$*\" > \"$FAKE_KLT_STATE/uvx.txt\"\n")
        uvx.chmod(0o755)
        subprocess.run([args.klt, "sim", "x"], check=True)
        self.assertEqual((self.state / "uvx.txt").read_text().strip(),
                         "--from klayout-tools==0.5.0 klt sim x")
        self.assertEqual(self.calls(), [])                  # host klt never ran
        for bad in ("0.5.0; true", "", "$(x)", "0.5 0"):
            with self.assertRaises(BatchError):
                klt_batch.pinned_klt(bad)

    def test_klt_pin_and_klt_are_mutually_exclusive(self):
        import argparse
        parser = argparse.ArgumentParser()
        klt_batch.add_backend_argument(parser)
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parser.parse_args(["--klt", "/x/klt", "--klt-pin", "0.5.0"])
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parser.parse_args(["--klt-pin", "0.5.0", "--klt", "/x/klt"])

    def test_pinned_client_matching_the_runner_is_accepted_and_mismatch_still_refused(self):
        pin = self.bin / "klt-pinned"
        (self.bin / "klt").rename(pin)
        (out,) = klt_batch.run_units([self.unit()], self.cfg(klt=str(pin)), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.mode("mismatch")                              # a pin that still disagrees
        (bad,) = klt_batch.run_units([self.unit("b")], self.cfg(klt=str(pin)), tolerate_absent=True)
        self.assertEqual(bad.status, "error")
        self.assertIn("runner_compatibility='mismatch'", bad.message)

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


class CapacityWaitTests(BatchTestCase):
    """The single-request submit path passes ``--wait-for-capacity`` and
    bounds its own subprocess with room for that wait (#467). Before this,
    only the ``--batch-set`` path passed the flag, so a ``run_corners.py``
    batch run got one launch attempt and failed outright on a full fleet."""

    def sim_calls(self):
        return [c for c in self.calls() if c[:1] == ["sim"]]

    def flag(self, args, name):
        self.assertIn(name, args, f"{name} missing from {args}")
        return args[args.index(name) + 1]

    def submit(self, **cfg_kw):
        (out,) = klt_batch.run_units([self.unit()], self.cfg(**cfg_kw), tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        (call,) = self.sim_calls()
        return call

    def test_default_capacity_wait_is_passed(self):
        self.assertEqual(BatchConfig.wait_for_capacity_s, 600)
        self.assertEqual(self.flag(self.submit(), "--wait-for-capacity"), "600")

    def test_non_default_capacity_wait_is_forwarded(self):
        self.assertEqual(
            self.flag(self.submit(wait_for_capacity_s=120), "--wait-for-capacity"), "120")

    def test_zero_capacity_wait_is_forwarded_not_dropped(self):
        # klt documents 0 as "one attempt" -- an explicit opt-out, which only
        # reaches klt if the flag is still passed.
        self.assertEqual(
            self.flag(self.submit(wait_for_capacity_s=0), "--wait-for-capacity"), "0")

    def test_capacity_retries_is_not_passed_on_this_path(self):
        # klt documents --capacity-retries as applying "with --batch-set" only.
        self.assertNotIn("--capacity-retries", self.submit())

    def test_backend_is_still_forced_to_batch(self):
        self.assertEqual(self.flag(self.submit(), "--backend"), klt_batch.BACKEND_BATCH)

    def test_subprocess_timeout_includes_the_capacity_wait(self):
        # klt measures the capacity wait on its own clock and does not charge
        # it to poll_timeout_s, so our bound must carry it on top: a submit
        # that waits out the window and then runs must not be killed here.
        seen = []
        real = klt_batch.subprocess.run

        def spy(cmd, **kw):
            if "sim" in cmd:
                seen.append(kw.get("timeout"))
            return real(cmd, **kw)

        with mock.patch.object(klt_batch.subprocess, "run", spy):
            (out,) = klt_batch.run_units(
                [self.unit()],
                self.cfg(poll_timeout_s=100, wait_for_capacity_s=42, client_slack_s=7),
                tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.assertEqual(seen, [100 + 42 + 7])

    def test_capacity_wait_does_not_shorten_the_bound_when_it_is_zero(self):
        seen = []
        real = klt_batch.subprocess.run

        def spy(cmd, **kw):
            if "sim" in cmd:
                seen.append(kw.get("timeout"))
            return real(cmd, **kw)

        with mock.patch.object(klt_batch.subprocess, "run", spy):
            (out,) = klt_batch.run_units(
                [self.unit()],
                self.cfg(poll_timeout_s=100, wait_for_capacity_s=0, client_slack_s=7),
                tolerate_absent=True)
        self.assertTrue(out.ok, out.message)
        self.assertEqual(seen, [107])

    def test_request_content_is_unchanged_by_the_flag(self):
        # Rejected alternative: writing batch.capacity_wait_s into the request.
        # The staged request.json is copied into the evidence directory, so it
        # stays byte-stable; the wait is a command-line concern only.
        self.submit(wait_for_capacity_s=120)
        req = json.loads((self.state / "req-0.json").read_text())
        self.assertNotIn("batch", req)


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

    def test_corner_matched_by_param_value_not_by_supply_v(self):
        """A report corner is matched back to its unit on `params`. A corner
        carrying the right value under the old `supply_v` key matches nothing,
        so a klt that ignored the axis can never be read as `ok`."""
        u = self.unit("s", lift_params=("vdd_val",))
        self.patch(corner={"params": {"vdd_val": 9.99}})
        (out,) = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertIn("match no requested unit", out.message)
        self.patch(corner={"params": None, "supply_v": {"vdd_val": 3.3}})
        (out,) = klt_batch.run_units([u], self.cfg(), tolerate_absent=True)
        self.assertEqual(out.status, "error")
        self.assertNoLocalNgspice()

    def test_malformed_param_value_is_a_batch_failure(self):
        lift = {"lift_params": ("vdd_val",)}
        for sv in ({"vdd_val": "abc"}, ["vdd_val"], "vdd_val"):
            with self.subTest(sv=sv):
                self.patch(corner={"params": sv})
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


# ---------------------------------------------------------------------------
# request building with ratified spec limits (#496)
# ---------------------------------------------------------------------------

#: A `tb.json`-shaped `checks` block with every bound shape that matters:
#: min+max, min-only, max-only, neither, and a check on a quantity no deck
#: measures. Row ids are real `spec/target-spec.md` anchors, because
#: `runner.batch_measurement_specs` cross-checks them against the file.
CHECKS = {
    "vout": {
        "min": 1.0, "max": 2.0,
        "description": "spec/target-spec.md#por-vth-rise -- the release threshold.",
    },
    "iq": {
        "max": 5.0,
        "description": "informative droop guard; mentions spec/target-spec.md#por-iq "
                       "only in passing, so it is not evidence for that row.",
    },
    "ratio": {
        "min": 0.4,
        "description": "`spec/target-spec.md#por-reset-valid-floor` valid-low ratio.",
    },
    "spread_only": {
        "max_spread_pct": 5.0,
        "description": "a grid-level stability check, no per-corner bound at all.",
    },
    "derived_in_python": {
        "min": 0.0, "max": 1.0,
        "description": "computed after the run from the rows above; no deck vector.",
    },
}

REQUEST_NAMES = {"vout": "m_vout", "iq": "m_iq", "ratio": "m_ratio",
                 "spread_only": "m_spread_only"}


def specs_of(request: dict) -> dict[str, tuple[dict | None, str | None]]:
    """``name -> (limits, spec_row)`` for every measurement of ``request``."""
    return {m["name"]: (m.get("limits"), m.get("spec_row"))
            for m in request["measurements"]}


class MeasurementSpecTests(unittest.TestCase):
    """``tb.json`` ``checks`` -> the ``limits``/``spec_row`` klt grades (#496).

    Pure dict-in/dataclass-out: no PDK, no deck, no klt.
    """

    def specs(self, **kw):
        return klt_batch.measurement_specs(CHECKS, request_names=REQUEST_NAMES, **kw)

    def test_only_declared_bounds_become_limits(self):
        by_name = {s.name: s for s in self.specs()}
        self.assertEqual(by_name["m_vout"].limits(), {"min": 1.0, "max": 2.0})
        self.assertEqual(by_name["m_iq"].limits(), {"max": 5.0})
        self.assertEqual(by_name["m_ratio"].limits(), {"min": 0.4})

    def test_a_check_with_no_bound_contributes_no_spec(self):
        """A grid-level `max_spread_pct` check has nothing klt can grade one
        corner against; an empty `limits` would read as "never fails"."""
        self.assertNotIn("m_spread_only", {s.name for s in self.specs()})

    def test_a_check_with_no_request_measurement_is_skipped(self):
        """`derived_in_python` is bounded, but no deck vector carries it (the
        MC benches' `terr_trim_c` is the real case)."""
        self.assertNotIn("derived_in_python", {s.name for s in self.specs()})
        self.assertEqual(len(self.specs()), 3)

    def test_only_a_leading_reference_is_a_spec_row(self):
        """A row cited in prose is not a row this measurement substantiates."""
        rows = {s.name: s.spec_row for s in self.specs()}
        self.assertEqual(rows["m_vout"], "por-vth-rise")
        self.assertEqual(rows["m_ratio"], "por-reset-valid-floor")   # backticked
        self.assertEqual(rows["m_iq"], "")                           # prose mention
        self.assertEqual(klt_batch.spec_row_of("see spec/target-spec.md#por-iq"), "")

    def test_an_unratified_row_is_refused_not_emitted(self):
        checks = {"vout": {"min": 1.0, "description": "spec/target-spec.md#no-such-row"}}
        known = klt_batch.spec_row_ids('| <a id="por-vth-rise"></a>`por-vth-rise` |')
        with self.assertRaises(klt_batch.BatchIncompatible) as cm:
            klt_batch.measurement_specs(checks, request_names=REQUEST_NAMES,
                                        known_rows=known)
        self.assertIn("no-such-row", str(cm.exception))
        # Without the cross-check it is emitted as written, not invented.
        (spec,) = klt_batch.measurement_specs(checks, request_names=REQUEST_NAMES)
        self.assertEqual(spec.spec_row, "no-such-row")

    def test_spec_row_ids_reads_the_real_spec(self):
        rows = runner.ratified_spec_rows()
        self.assertIsNotNone(rows, "spec/target-spec.md unreadable from the repo")
        for row in ("por-vth-rise", "por-vth-fall", "por-hysteresis"):
            self.assertIn(row, rows)

    def test_an_unreadable_spec_is_not_comparable_not_empty(self):
        """`None` must mean "cannot cross-check", never "nothing is ratified"
        -- an empty set would refuse every row."""
        self.assertIsNone(runner.ratified_spec_rows(Path("/nonexistent/spec.md")))


class SpecLimitRequestTests(BatchTestCase):
    """The limits reach the staged request, and bound the request grouping."""

    SPECS = (
        klt_batch.MeasurementSpec("vdd_pre", 1.0, 2.0, "por-vth-rise"),
        klt_batch.MeasurementSpec("t_praw", None, 0.5),
        klt_batch.MeasurementSpec("vsg_min", -1.0, None),
    )

    def test_limits_and_spec_rows_land_on_the_right_measurements(self):
        (staged,) = klt_batch.stage_requests([self.unit(specs=self.SPECS)], self.cfg())
        seen = specs_of(staged.request)
        self.assertEqual(seen["vdd_pre"], ({"min": 1.0, "max": 2.0}, "por-vth-rise"))
        self.assertEqual(seen["t_praw"], ({"max": 0.5}, None))
        self.assertEqual(seen["vsg_min"], ({"min": -1.0}, None))
        # No null bound for an undeclared side, anywhere.
        for limits, _ in seen.values():
            self.assertNotIn(None, (limits or {}).values())

    def test_a_unit_without_specs_builds_the_pre_496_request(self):
        (plain,) = klt_batch.stage_requests([self.unit()], self.cfg())
        for m in plain.request["measurements"]:
            self.assertNotIn("limits", m)
            self.assertNotIn("spec_row", m)

    def test_units_differing_only_in_limits_do_not_share_a_request(self):
        """`_build_request` reads `measurements[]` from the group's FIRST
        member, so grouping two differently-bounded units would silently
        grade one of them against the other's limits."""
        loose = (klt_batch.MeasurementSpec("vdd_pre", 1.0, 9.0),)
        tight = (klt_batch.MeasurementSpec("vdd_pre", 1.0, 2.0),)
        a, b = self.unit("d1", specs=tight), self.unit("d2", specs=loose)
        self.assertEqual(len(klt_batch.group_units([a, b])), 2)
        # Same limits still share one request: only the bounds split them.
        self.assertEqual(len(klt_batch.group_units([a, self.unit("d3", specs=tight)])), 1)
        got = [specs_of(s.request)["vdd_pre"][0]
               for s in klt_batch.stage_requests([a, b], self.cfg())]
        self.assertEqual(got, [{"min": 1.0, "max": 2.0}, {"min": 1.0, "max": 9.0}])

    def test_a_bound_on_an_unmeasured_vector_is_refused(self):
        with self.assertRaises(klt_batch.BatchIncompatible) as cm:
            self.unit(specs=(klt_batch.MeasurementSpec("not_measured", 1.0),))
        self.assertIn("not_measured", str(cm.exception))

    def test_staging_submits_nothing(self):
        klt_batch.stage_requests([self.unit(specs=self.SPECS)], self.cfg())
        self.assertEqual(self.calls(), [], "staging invoked klt")
        self.assertNoLocalNgspice()

    def test_staging_needs_no_klt_on_path(self):
        (self.bin / "klt").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            (staged,) = klt_batch.stage_requests([self.unit()], self.cfg())
        self.assertTrue(staged.path.is_file())
        self.assertNoLocalNgspice()


class EmitRequestCliTests(BatchTestCase):
    """``run_corners.py <exp> --emit-request DIR`` (#496)."""

    def setUp(self):
        super().setUp()
        self.out = self.root / "emit"
        (self.root / "tb").mkdir()
        (self.root / "tb" / "x.spice").write_text(
            "v1 out 0 dc {vdd_val}\nr1 out 0 1k\n")
        self.write_tb(CHECKS)

    def write_tb(self, checks):
        (self.root / "tb" / "tb.json").write_text(json.dumps({
            "name": "x", "netlist": "x.spice", "corners": ["tt"],
            "temperatures_c": [-40, 125], "analyses": ["tran 1e-6 1e-3"],
            "measure": {"vout": "v(out)", "iq": "-i(v1)", "ratio": "v(out)/3.3"},
            "checks": checks,
        }))

    def emit(self, *extra, testbench=None, out=None):
        args = cli.build_parser().parse_args(
            [testbench or str(self.root / "tb"),
             "--emit-request", str(out or self.out), *extra])
        with mock.patch.object(cli, "find_pdk", return_value=self.pdk):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code = cli.cmd_emit_request(args)
        return code, buf.getvalue()

    def requests(self, out=None):
        return sorted((out or self.out).glob("requests/*/*.json"))

    def test_it_writes_requests_and_submits_nothing(self):
        code, text = self.emit()
        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(self.requests())
        self.assertEqual(self.calls(), [], "--emit-request invoked klt")
        self.assertNoLocalNgspice()
        self.assertIn("Nothing was submitted", text)

    def test_it_records_no_evidence(self):
        self.emit()
        self.assertEqual(list((self.root / "tb").glob("records/*")), [])
        self.assertEqual(list(self.out.rglob("*.md")), [])

    def test_one_request_per_temperature_carrying_the_ratified_limits(self):
        self.emit()
        paths = self.requests()
        self.assertEqual(len(paths), 2)                     # -40 C and 125 C
        for path in paths:
            request = json.loads(path.read_text())
            self.assertEqual(len(request["corners"]["temperature_c"]), 1)
            seen = specs_of(request)
            self.assertEqual(seen["m_vout"], ({"min": 1.0, "max": 2.0}, "por-vth-rise"))
            self.assertEqual(seen["m_iq"], ({"max": 5.0}, None))
            self.assertEqual(seen["m_ratio"], ({"min": 0.4}, "por-reset-valid-floor"))

    def test_a_manifest_with_no_checks_still_builds(self):
        self.write_tb({})
        code, _ = self.emit()
        self.assertEqual(code, cli.EXIT_OK)
        for path in self.requests():
            for m in json.loads(path.read_text())["measurements"]:
                self.assertNotIn("limits", m)

    def test_an_unratified_spec_row_is_an_environment_error(self):
        self.write_tb({"vout": {"min": 1.0,
                                "description": "spec/target-spec.md#not-a-real-row"}})
        code, _ = self.emit()
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        self.assertEqual(self.requests(), [])

    def test_an_untranslatable_deck_is_refused_never_dropped(self):
        """A request set with a hole in it is worse than no request set: it
        looks like a complete grid. Mirrors the submit path's
        `test_untranslatable_deck_becomes_an_error_point`, which instead
        returns an error *result* per point."""
        with mock.patch.object(runner, "compose_deck",
                               return_value="* d\n.control\nwrite x\n.endc\n"):
            code, _ = self.emit()
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        self.assertEqual(self.requests(), [])
        self.assertEqual(self.calls(), [])

    def test_it_refuses_to_mix_with_an_existing_request_set(self):
        self.assertEqual(self.emit()[0], cli.EXIT_OK)
        before = {p: p.read_text() for p in self.requests()}
        code, _ = self.emit("--temps", "27")
        self.assertEqual(code, cli.EXIT_ENVIRONMENT)
        self.assertEqual({p: p.read_text() for p in self.requests()}, before)

    def test_the_grid_honours_the_cli_overrides(self):
        self.emit("--temps", "27", "--supply-tol", "0")
        (path,) = self.requests()
        request = json.loads(path.read_text())
        self.assertEqual(request["corners"]["temperature_c"], [27.0])
        self.assertEqual(request["corners"]["params"], {"vdd_val": [3.3]})

    def test_por_vth_is_81_units_in_3_requests(self):
        """The acceptance criterion, on the committed manifest: 9 process x 3
        supply x 3 temperature = 81 units, packaged one request per
        temperature (`_unit_group_key` includes `temp_c`)."""
        out = self.root / "por-vth"
        code, text = self.emit(testbench="por-vth", out=out)
        self.assertEqual(code, cli.EXIT_OK, text)
        paths = self.requests(out)
        self.assertEqual(len(paths), 3)
        total = 0
        for path in paths:
            request = json.loads(path.read_text())
            self.assertEqual(len(request["corners"]["temperature_c"]), 1)
            self.assertEqual(len(request["corners"]["process"]), 9)
            self.assertEqual(len(request["corners"]["params"]["vdd_val"]), 3)
            self.assertEqual(request.get("exclude", []), [])
            total += 9 * 3
        self.assertEqual(total, 81)
        self.assertIn("81 unit(s) total", text)
        self.assertEqual(self.calls(), [])
        self.assertNoLocalNgspice()

    def test_por_vth_tags_exactly_the_three_ratified_rows(self):
        out = self.root / "por-vth"
        self.emit(testbench="por-vth", out=out)
        request = json.loads(self.requests(out)[0].read_text())
        seen = specs_of(request)
        self.assertEqual(
            {name: row for name, (_, row) in seen.items() if row},
            {"m_vpor_rise_v": "por-vth-rise", "m_vpor_fall_v": "por-vth-fall",
             "m_v_hys_mv": "por-hysteresis"},
        )
        # Every bounded check is graded; the one unbounded measure is not.
        self.assertEqual(sum(1 for limits, _ in seen.values() if limits), 12)
        self.assertIsNone(seen["m_v_hys_guard_mv"][0])
        self.assertEqual(seen["m_rise_chatter_guard_ms"][0], {"min": 16.0})
        self.assertEqual(seen["m_por_raw_hi_droop_mv"][0], {"max": 50.0})


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
