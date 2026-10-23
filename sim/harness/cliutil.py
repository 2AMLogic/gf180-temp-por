"""Shared CLI/report helpers for the harness entry points.

``fmt()`` and the testbench-path resolution helpers below used to be
copy-pasted across ``sim/run_mc.py``, ``sim/harness/cli.py``,
``sim/harness/report.py`` and ``sim/harness/mc_report.py`` (issue #135) --
this is their one shared home, alongside the sha256/git_describe/
measurement-parsing helpers already consolidated into
``sim/harness/runner.py`` (#130). The exit-code constants and the
record-provisioning / status-to-exit-code helpers below closed the same gap
for ``sim/run_mc.py`` vs. ``sim/harness/cli.py`` (#168).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import evidence_store
from .pdk import Pdk, PdkNotFound, find_pdk
from .testbench import MANIFEST_NAME, TESTBENCH_DIRNAME, discover

# Exit codes shared by the record-derivation CLIs (sim/run_corners.py via
# sim/harness/cli.py, and sim/run_mc.py).
EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_SIM_ERROR = 2
EXIT_ENVIRONMENT = 3


def locate_toolchain(*, need_ngspice: bool = True) -> tuple[Pdk, str | None] | None:
    """Locate the PDK (and, if ``need_ngspice``, the ngspice version string).

    Shared preamble of the ``sim/*/control/run_*.py`` entry points. On a
    missing PDK or ngspice, prints the error to stderr and returns ``None``;
    the caller then returns ``EXIT_ENVIRONMENT``. The version is ``None`` when
    ``need_ngspice`` is false.
    """
    # Local import: runner pulls in the simulation stack, which the pure
    # formatting/path helpers in this module do not need.
    from . import runner

    try:
        pdk = find_pdk()
        version = runner.ngspice_version() if need_ngspice else None
    except (PdkNotFound, runner.NgspiceMissing) as exc:
        print(exc, file=sys.stderr)
        return None
    return pdk, version


def load_manifest(path: Path) -> dict:
    """Load and parse a testbench manifest (``tb.json``) from ``path``."""
    return json.loads(path.read_text())


def now_iso() -> str:
    """UTC timestamp, second precision, for record ``when`` fields."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def add_author_arg(
    parser: argparse.ArgumentParser, default: str = "agent-builder"
) -> None:
    """Add the ``--author`` option shared by the record-derivation CLIs."""
    parser.add_argument(
        "--author", default=default, help="author for the record header"
    )


def default_jobs(cpu_count: int | None = None) -> int:
    """Default ``-j``/``--jobs`` when the caller didn't pass one explicitly.

    Half the host's logical cores (floor), minimum 1 -- headroom, not a
    claim on every core. ``cpu_count`` defaults to ``os.cpu_count()``, with
    the existing ``or 2`` fallback preserved for the rare host where that
    returns ``None``.

    This is a **per-process** default: it has no visibility into other
    ``run_corners.py``/``run_mc.py`` invocations running concurrently on the
    same host (a second worktree's designer-check sweep, a third agent's
    Monte Carlo run, ...). N concurrent invocations each pick this same
    per-process number independently, so the host-wide total still scales
    with N -- halving the per-process default only buys headroom for a
    small, not unbounded, number of concurrent agents. A host-wide budget
    shared *across* concurrently running agents is a fleet-orchestration
    concern this repo cannot see or enforce; see rjwalters/loom#5979.
    """
    cores = cpu_count if cpu_count is not None else (os.cpu_count() or 2)
    return max(1, cores // 2)


def fmt(value) -> str:
    """Render a measurement/limit value for CLI and record output.

    ``None`` -> ``"n/a"``; ``bool`` -> ``"yes"``/``"no"``; ``float`` picks
    scientific vs. fixed notation by magnitude; everything else falls back
    to ``str(value)``.
    """
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != 0 and (abs(value) < 1e-3 or abs(value) >= 1e5):
            return f"{value:.6e}"
        return f"{value:.6g}"
    return str(value)


def has_manifest(candidate: Path) -> bool:
    """True if ``candidate`` is, or directly contains, a ``tb.json`` manifest."""
    if candidate.is_file() and candidate.name == MANIFEST_NAME:
        return True
    if (candidate / MANIFEST_NAME).is_file():
        return True
    return (candidate / TESTBENCH_DIRNAME / MANIFEST_NAME).is_file()


def resolve_tb_path(argument: str, sim_dir: Path) -> Path:
    """Accept an experiment slug, an experiment dir, or a testbench dir.

    Tries ``argument`` as given, then relative to ``sim_dir``. On failure,
    the ``FileNotFoundError`` lists both tried paths and the experiments
    ``sim_dir`` actually contains.
    """
    candidates = [Path(argument), sim_dir / argument]
    for candidate in candidates:
        if has_manifest(candidate):
            return candidate
    raise FileNotFoundError(
        f"no experiment {argument!r}; tried: "
        + ", ".join(str(c) for c in candidates)
        + ".\nAvailable: "
        + ", ".join(p.name for p in discover(sim_dir))
    )


def provision_record(
    repo_root: Path,
    work_dir: Path,
    records_dir: Path,
    experiment_dir: Path,
    experiment_name: str,
    no_write: bool,
    stage: bool = False,
) -> tuple[str, Path, Path | None, dict, datetime]:
    """Allocate a record id and derive its workdir/log_dir, as both
    ``sim/run_corners.py`` (via ``sim/harness/cli.py``) and ``sim/run_mc.py``
    do at the top of their ``run()``.

    Returns ``(record_id, workdir, log_dir, git, started)``. ``log_dir`` is
    ``None`` when ``no_write`` is set (debugging runs write no evidence).

    With ``stage=True`` (what the entry points pass, DR-030) the run's raw
    outputs are staged in the git-ignored ``<work_dir>/evidence-stage/`` tree
    instead of ``<experiment>/corners/<record-id>/``: ``log_dir`` is then
    ``<stage>/corners`` and ``finish_run(..., stage=True)`` ships the stage to
    the artifact store. Nothing is reserved in the tracked tree, and the store
    is checked up front so a worker that cannot publish fails before it
    simulates anything.
    """
    # Local import: sim/harness/report.py imports this module (for `fmt()`),
    # so importing it at module scope here would be circular.
    from . import report as report_mod

    if stage and not no_write:
        evidence_store.preflight()
    started = datetime.now(timezone.utc)
    git = report_mod.git_provenance(repo_root)
    when = started
    staging = stage and not no_write
    stage_dir = None
    while True:
        # Writing runs atomically reserve the record id (its raw-log
        # directory) before any simulation starts; --no-write runs reserve
        # nothing in the evidence tree.
        record_id = report_mod.allocate_record_id(
            repo_root, records_dir, when, git=git, reserve=not no_write and not staging
        )
        workdir = work_dir / experiment_name / record_id
        # The scratch directory is claimed exclusively too, so two runs
        # (including --no-write ones) never share decks.
        workdir.parent.mkdir(parents=True, exist_ok=True)
        try:
            workdir.mkdir()
            if staging:
                stage_dir = evidence_store.stage_dir_for(work_dir, experiment_name, record_id)
                stage_dir.parent.mkdir(parents=True, exist_ok=True)
                stage_dir.mkdir()
            break
        except FileExistsError:
            # The id's leading YYYYMMDD-HHMMSS is the (possibly advanced) time.
            when = datetime.strptime(record_id[:15], "%Y%m%d-%H%M%S").replace(
                tzinfo=timezone.utc
            ) + timedelta(seconds=1)
    if no_write:
        log_dir = None
    elif staging:
        log_dir = stage_dir / evidence_store.STAGE_CORNERS
        log_dir.mkdir()
    else:
        log_dir = experiment_dir / report_mod.CORNERS_DIR / record_id
    return record_id, workdir, log_dir, git, started


def exit_code_for_status(status: str) -> int:
    """Translate a record's ``status`` field into the CLI's exit code."""
    if status == "error":
        return EXIT_SIM_ERROR
    if status == "fail":
        return EXIT_CHECK_FAILED
    return EXIT_OK


def finish_run(
    tb,
    record: dict,
    experiment_dir: Path,
    record_id: str,
    workdir: Path,
    log_dir: Path | None,
    no_write: bool,
    write_record: Callable[[dict, Path], Path],
    stage: bool = False,
    repo_root: Path | None = None,
) -> int:
    """Write evidence to disk (or note that it wasn't written) and print the
    footer shared by ``sim/run_corners.py`` (via ``sim/harness/cli.py``) and
    ``sim/run_mc.py``'s ``run()`` implementations, then return the exit code
    for ``record["status"]``.

    ``write_record`` is the record-writer the caller wants invoked as
    ``write_record(record, experiment_dir)`` -- ``report.write_record`` for
    the PVT-grid harness, ``mc_report.write_mc_record`` for Monte Carlo runs
    -- the one line the two callers' footers otherwise differ on.
    """
    # Local import: sim/harness/report.py imports this module (for `fmt()`),
    # so importing it at module scope here would be circular.
    from . import report as report_mod

    if not no_write and stage:
        # DR-030: the raw logs and the netlist snapshot go to the artifact
        # store; git gets the manifest and the summary record. Publish first
        # so a failed put leaves no record behind (fail closed, no fallback).
        stage_dir = log_dir.parent
        report_mod.write_netlist_snapshot(
            tb, experiment_dir, record_id, out_dir=stage_dir / evidence_store.STAGE_SNAPSHOTS
        )
        try:
            manifest = evidence_store.publish(
                stage_dir, repo_root, experiment_dir.name, record_id
            )
        except evidence_store.EvidenceStoreError as exc:
            print(f"error: {exc}\nstaged bytes kept at {stage_dir}", file=sys.stderr)
            return EXIT_ENVIRONMENT
        record["evidence_manifest"] = manifest.relative_to(repo_root).as_posix()
        record_path = write_record(record, experiment_dir)
        print()
        print(f"record    : {record_path}")
        print(f"manifest  : {manifest}")
    elif not no_write:
        snapshot = report_mod.write_netlist_snapshot(tb, experiment_dir, record_id)
        record_path = write_record(record, experiment_dir)
        print()
        print(f"record    : {record_path}")
        print(f"snapshot  : {snapshot}")
        print(f"raw logs  : {log_dir}")
    else:
        print()
        print("evidence  : not recorded (--no-write)")
    print(f"work dir  : {workdir}")
    print(f"status    : {record['status'].upper()}")

    return exit_code_for_status(record["status"])


def write_derived_record(text: str, records_dir: Path, filename: str) -> Path:
    """Write a derived-record write-up, refusing to overwrite an existing one.

    The derived-record counterpart to ``report.write_record``'s append-only
    guard for primary records: ``sim/por-iq/analyze_por_iq.py``,
    ``sim/postlayout_delta.py``, ``sim/temp-accuracy-mc/analyze_breakdown.py``
    and ``sim/temp-accuracy-vt/analyze_derived.py`` each derive a write-up
    from an already-recorded primary record and share this same
    exists-check/write footer (issue #276). Raises ``report.RecordExists``
    (the same exception the primary-record path already raises) instead of
    each call site hand-rolling its own check.
    """
    # Local import: sim/harness/report.py imports this module (for `fmt()`),
    # so importing it at module scope here would be circular.
    from . import report as report_mod

    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / filename
    report_mod.write_exclusive(path, text)
    return path


def run_and_report(
    run_fn: Callable[[argparse.Namespace], int], args: argparse.Namespace
) -> int:
    """Shared error-handling tail for the record-derivation CLIs' ``main()``:
    call ``run_fn(args)`` and translate the exceptions it lets escape into
    ``EXIT_ENVIRONMENT``, as both ``sim/harness/cli.py`` and ``sim/run_mc.py``
    do around their own ``run(args)`` call.
    """
    # Local import: sim/harness/report.py imports this module (for `fmt()`),
    # so importing it at module scope here would be circular.
    from . import report as report_mod

    try:
        return run_fn(args)
    except (
        FileNotFoundError, ValueError, KeyError, report_mod.RecordExists,
        evidence_store.EvidenceStoreError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
