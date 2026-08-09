#!/usr/bin/env python3
"""Run a Monte Carlo mismatch testbench (issue #15).

    python3 sim/run_mc.py temp-accuracy-mc
    python3 sim/run_mc.py por-threshold-mc -j 8
    python3 sim/run_mc.py temp-accuracy-mc --n 500 --seed-base 20260802

Companion to ``sim/run_corners.py``: that script sweeps the deterministic
PVT grid (process x temperature x supply, mismatch off); this one samples
local mismatch (N independent draws per spec-ratified binding point, process
held at that row's own named deterministic corner). See
``sim/harness/montecarlo.py``'s module docstring for the full mechanism and
``sim/README.md`` for the evidence-record convention both scripts write.

A testbench opts in by carrying an ``"mc"`` block in its ``tb.json``
(``sim/harness/testbench.py``); ``sim/run_corners.py`` ignores that key
entirely, so the same manifest never needs to be edited to run under one
script and not the other -- though in practice each MC testbench in this
repo (``sim/temp-accuracy-mc/``, ``sim/por-threshold-mc/``) is MC-only: an
op/tran deck built for N=500-2500 fast invocations at a handful of named
points, not a 9x3x3 corner sweep.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = REPO_ROOT / "sim"
WORK_DIR = SIM_DIR / ".work"

sys.path.insert(0, str(SIM_DIR))

from harness import HARNESS_VERSION, cliutil, mc_report, montecarlo, report, testbench as tb_mod  # noqa: E402
from harness.montecarlo import ManifestError  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402
from harness.runner import NgspiceMissing, ngspice_version  # noqa: E402

EXIT_OK = cliutil.EXIT_OK
EXIT_CHECK_FAILED = cliutil.EXIT_CHECK_FAILED
EXIT_SIM_ERROR = cliutil.EXIT_SIM_ERROR
EXIT_ENVIRONMENT = cliutil.EXIT_ENVIRONMENT

_fmt = cliutil.fmt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_mc.py",
        description="Run a Monte Carlo mismatch testbench (issue #15).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 sim/run_mc.py temp-accuracy-mc\n"
            "  python3 sim/run_mc.py por-threshold-mc -j 8\n"
            "  python3 sim/run_mc.py --list\n"
        ),
    )
    parser.add_argument(
        "testbench", nargs="?", metavar="EXPERIMENT",
        help="MC experiment slug under sim/ (i.e. sim/<slug>/testbench/tb.json with an 'mc' block)",
    )
    parser.add_argument("--list", action="store_true", help="list MC testbenches and their binding points")
    parser.add_argument("--n", type=int, default=None, help="samples per binding point (overrides tb.json's mc.n)")
    parser.add_argument("--seed-base", type=int, default=None, help="overrides tb.json's mc.seed_base")
    parser.add_argument("-j", "--jobs", type=int, default=0, help="parallel ngspice runs")
    parser.add_argument("--timeout", type=int, default=300, help="per-sample ngspice timeout in seconds")
    parser.add_argument("--claim", default="", help="overrides the manifest's 'claim'")
    parser.add_argument("--supersedes", default="", metavar="RECORD_ID", help="prior record-id this run corrects")
    parser.add_argument("--no-write", action="store_true", help="run but do not record evidence (debugging only)")
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument("--version", action="version", version=f"gf180-temp-por harness {HARNESS_VERSION}")
    return parser


def cmd_list() -> int:
    print("Monte Carlo experiments (sim/<slug>/testbench/tb.json with an 'mc' block):")
    for directory in tb_mod.discover(SIM_DIR):
        try:
            tb = tb_mod.load(directory)
        except Exception:  # noqa: BLE001
            continue
        if not tb.mc:
            continue
        try:
            binding_points = montecarlo.load_binding_points(tb)
        except ManifestError as exc:
            print(f"  {directory.name:<20} !! {exc}")
            continue
        n = tb.mc.get("n", montecarlo.MIN_SAMPLES)
        print(f"  {directory.name:<20} {tb.description or tb.name}")
        print(f"  {'':<20} N={n} per binding point, {len(binding_points)} binding points:")
        for bp in binding_points:
            print(f"  {'':<20}   {bp.label}: {bp.corner.name} @ {bp.temp_c:g} C, {bp.vdd:.2f} V")
    return EXIT_OK


def run(args: argparse.Namespace) -> int:
    tb_path = cliutil.resolve_tb_path(args.testbench, SIM_DIR)
    tb = tb_mod.load(tb_path)
    if not tb.mc:
        print(
            f"error: {tb_path} has no 'mc' block in tb.json -- not a Monte Carlo "
            "testbench; use sim/run_corners.py for a deterministic PVT sweep",
            file=sys.stderr,
        )
        return EXIT_ENVIRONMENT

    try:
        pdk = find_pdk()
        ngspice = ngspice_version()
    except (PdkNotFound, NgspiceMissing) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    try:
        binding_points = montecarlo.load_binding_points(tb)
        n = args.n if args.n is not None else int(tb.mc.get("n", montecarlo.MIN_SAMPLES))
        seed_base = args.seed_base if args.seed_base is not None else int(tb.mc.get("seed_base", 1))
        points = montecarlo.build_mc_grid(binding_points, n, seed_base, enforce_min=not args.no_write)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    experiment_dir = tb.experiment_dir
    records_dir = experiment_dir / report.RECORDS_DIR

    jobs = args.jobs or min(8, (os.cpu_count() or 2))
    record_id, workdir, log_dir, git, started = cliutil.provision_record(
        REPO_ROOT, WORK_DIR, records_dir, experiment_dir, tb.experiment, args.no_write,
    )

    if not args.quiet:
        print(f"experiment: {tb.experiment}" + (f"  ({tb.description})" if tb.description else ""))
        print(f"pdk       : {pdk.variant} @ {pdk.version}  ({pdk.path})")
        print(f"ngspice   : {ngspice}")
        print(f"binding points: {len(binding_points)}")
        for bp in binding_points:
            print(f"  {bp.label:<40} {bp.corner.name:<8} {bp.temp_c:g} C  {bp.vdd:.2f} V")
        print(f"N per point: {n}   total samples: {len(points)}   seed_base: {seed_base}")
        print(f"record id : {record_id}")
        print()

    completed = 0

    def progress(result):
        nonlocal completed
        completed += 1
        if args.quiet:
            return
        if completed % 50 == 0 or completed == len(points):
            flag = {"ok": "ok", "failed": "FAIL", "error": "ERR"}[result.status]
            print(f"[{completed:>5}/{len(points)}] last={result.point.corner_id} {flag}")

    wall_start = _dt.datetime.now(_dt.timezone.utc)
    try:
        results = montecarlo.run_mc_grid(
            tb, pdk, points, workdir, jobs=jobs, timeout_s=args.timeout,
            on_result=progress, log_dir=log_dir,
        )
    except NgspiceMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    wall_seconds = (_dt.datetime.now(_dt.timezone.utc) - wall_start).total_seconds()

    derived = montecarlo.apply_derive_hook(tb, results)
    measure_names = list(tb.measure) + derived
    summary = montecarlo.summarize_mc(results, measure_names, tb.checks)

    record = mc_report.build_mc_record(
        tb=tb, pdk=pdk, binding_points=binding_points, points=points, results=results,
        summary=summary, ngspice=ngspice, repo_root=REPO_ROOT, record_id=record_id,
        started_utc=started.isoformat(timespec="seconds"), wall_seconds=wall_seconds,
        n_per_point=n, seed_base=seed_base, derived_measures=derived,
        claim=args.claim, supersedes=args.supersedes, git=git,
    )

    print()
    n_ok = sum(1 for r in results if r.status == "ok")
    print(f"summary ({n_ok}/{len(points)} samples ok, {wall_seconds:.1f}s):")
    for label, by_measure in summary.items():
        print(f"  {label}:")
        for name, stats in by_measure.items():
            if stats.get("n", 0) < 2:
                print(f"    {name:<20} no data")
                continue
            print(
                f"    {name:<20} n={stats['n']:<5} mean={_fmt(stats['mean']):>14} "
                f"sigma={_fmt(stats['stdev']):>14} "
                f"3sigma=[{_fmt(stats['sigma3_lo'])}, {_fmt(stats['sigma3_hi'])}] "
                f"yield={stats['empirical_yield']*100:.2f}%"
            )

    for f in record["checks"]["failures"]:
        print(
            f"  [3sigma] FAIL {f['label']}/{f['measurement']}: "
            f"mean+/-3sigma=[{_fmt(f['sigma3_lo'])}, {_fmt(f['sigma3_hi'])}] "
            f"vs spec [{_fmt(f['spec_min'])}, {_fmt(f['spec_max'])}]"
        )

    if not args.no_write:
        snapshot = report.write_netlist_snapshot(tb, experiment_dir, record_id)
        record_path = mc_report.write_mc_record(record, experiment_dir)
        print()
        print(f"record    : {record_path}")
        print(f"snapshot  : {snapshot}")
        print(f"raw logs  : {log_dir}")
    else:
        print()
        print("evidence  : not recorded (--no-write)")
    print(f"work dir  : {workdir}")
    print(f"status    : {record['status'].upper()}")

    return cliutil.exit_code_for_status(record["status"])


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return cmd_list()
    if not args.testbench:
        parser.print_help()
        return EXIT_ENVIRONMENT
    try:
        return run(args)
    except (FileNotFoundError, ValueError, KeyError, report.RecordExists) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    raise SystemExit(main())
