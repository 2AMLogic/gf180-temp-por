#!/usr/bin/env python3
"""Run the full characterization campaign behind this repo's spec table.

    python3 sim/characterize.py                 # every experiment, full PVT/MC grid
    python3 sim/characterize.py --list           # what would run, without running it
    python3 sim/characterize.py --only por-vth   # one experiment (repeatable)
    python3 sim/characterize.py --no-write       # dry run, no evidence recorded
    python3 sim/characterize.py -j 4             # override per-process job count

This is the single entry point `make characterize` wraps (issue #292 / the
Chipalooza design-review bar, 2AMLogic/2am#542). It is a thin driver over the
two entry points ``sim/README.md``/``sim/harness/README.md`` already document
-- it invents no new evidence format, no new corner grid, and no new PDK
resolution:

  - every schematic-level experiment discovered under ``sim/*/testbench/``
    (``sim/harness/testbench.discover()``, the same discovery
    ``run_corners.py --list`` and ``run_mc.py --list`` use) is run with its
    manifest's own defaults -- the full 81-point PVT grid
    (``sim/run_corners.py <slug>``) for a deterministic-grid testbench, or
    the full N>=500-per-binding-point Monte Carlo sweep
    (``sim/run_mc.py <slug>``) for one that carries an ``"mc"`` block;
  - every run mints and writes a new append-only record under
    ``sim/<slug>/records/`` (unless ``--no-write``), exactly as running
    each command by hand would.

**Scope: schematic-level only.** ``testbench-postlayout/`` re-runs
(``sim/harness/README.md`` "Netlist provenance") are deliberately not part of
this campaign. They are triggered by a layout change, not by routine
characterization -- ``discover()`` itself only walks ``testbench/``, so a
postlayout re-run already needs its own explicit invocation
(``sim/run_corners.py sim/<slug>/testbench-postlayout``) per that document.
Folding them in here would silently double this campaign's wall-clock time
every time this script's own defaults are asked for, for evidence this
project's post-layout effort (issue #18 and children) already produced and
that a schematic-only Chipalooza review does not need reproduced on demand.

Exit code is the worst (highest) exit code any sub-run returned -- 0 only if
every experiment passed. See ``sim/harness/cliutil.py``'s ``EXIT_*``
constants for what each non-zero code means.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = REPO_ROOT / "sim"

sys.path.insert(0, str(SIM_DIR))

from harness import cliutil, testbench as tb_mod  # noqa: E402

RUN_CORNERS = SIM_DIR / "run_corners.py"
RUN_MC = SIM_DIR / "run_mc.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="characterize.py",
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="SLUG",
        help="restrict the campaign to these experiment slugs (repeatable runs, debugging)",
    )
    parser.add_argument("--list", action="store_true", help="print what would run and exit")
    parser.add_argument(
        "--no-write", action="store_true", help="run but record no evidence (debugging only)"
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=0,
        help="parallel ngspice runs per experiment (default: sim/harness/cliutil.default_jobs())",
    )
    parser.add_argument("--timeout", type=int, default=0, help="per-point ngspice timeout in seconds (0: tool default)")
    parser.add_argument("--quiet", action="store_true", help="only print the per-experiment summary line")
    return parser


def experiments() -> list[tuple[Path, bool]]:
    """Every schematic-level experiment, paired with whether it is Monte Carlo."""
    out = []
    for directory in tb_mod.discover(SIM_DIR):
        tb = tb_mod.load(directory)
        out.append((directory, bool(tb.mc)))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    all_experiments = experiments()
    if args.only:
        wanted = set(args.only)
        all_experiments = [(d, mc) for d, mc in all_experiments if d.name in wanted]
        missing = wanted - {d.name for d, mc in all_experiments}
        if missing:
            print(f"error: unknown experiment slug(s): {', '.join(sorted(missing))}", file=sys.stderr)
            print("       run 'python3 sim/run_corners.py --list' for valid slugs", file=sys.stderr)
            return cliutil.EXIT_ENVIRONMENT

    if not all_experiments:
        print("error: no experiments discovered under sim/*/testbench/tb.json", file=sys.stderr)
        return cliutil.EXIT_ENVIRONMENT

    n_grid = sum(1 for _, mc in all_experiments if not mc)
    n_mc = sum(1 for _, mc in all_experiments if mc)
    print(
        f"characterize: {len(all_experiments)} experiment(s) "
        f"({n_grid} PVT-grid, {n_mc} Monte Carlo), schematic-level only"
    )
    if args.list:
        for directory, mc in all_experiments:
            kind = "mc" if mc else "grid"
            print(f"  [{kind:<4}] {directory.name}")
        return cliutil.EXIT_OK

    results: list[tuple[str, int, float]] = []
    worst = cliutil.EXIT_OK
    campaign_start = time.monotonic()

    for directory, mc in all_experiments:
        slug = directory.name
        tool = RUN_MC if mc else RUN_CORNERS
        cmd = [sys.executable, str(tool), slug]
        if args.no_write:
            cmd.append("--no-write")
        if args.jobs:
            cmd += ["-j", str(args.jobs)]
        if args.timeout:
            cmd += ["--timeout", str(args.timeout)]
        if args.quiet:
            cmd.append("--quiet")

        print(f"\n=== {slug} ({'mc' if mc else 'grid'}) ===")
        print(f"$ {' '.join(cmd)}")
        start = time.monotonic()
        proc = subprocess.run(cmd, cwd=REPO_ROOT)
        elapsed = time.monotonic() - start
        results.append((slug, proc.returncode, elapsed))
        worst = max(worst, proc.returncode)
        print(f"--- {slug}: exit {proc.returncode} ({elapsed:.1f}s) ---")

    campaign_elapsed = time.monotonic() - campaign_start

    print("\n" + "=" * 72)
    print(f"characterize summary ({campaign_elapsed:.1f}s total):")
    label = {0: "PASS", 1: "CHECK FAIL", 2: "SIM ERROR", 3: "ENV ERROR"}
    for slug, code, elapsed in results:
        print(f"  {label.get(code, f'exit {code}'):<12} {slug:<32} {elapsed:>7.1f}s")
    n_pass = sum(1 for _, code, _ in results if code == 0)
    print(f"\n{n_pass}/{len(results)} experiments passed.")
    if worst != cliutil.EXIT_OK:
        print(f"characterize: FAILED (worst exit code {worst})", file=sys.stderr)
    else:
        print("characterize: all experiments passed.")

    return worst


if __name__ == "__main__":
    raise SystemExit(main())
