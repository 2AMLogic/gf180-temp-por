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
from datetime import datetime, timezone
from pathlib import Path

from .testbench import MANIFEST_NAME, TESTBENCH_DIRNAME, discover

# Exit codes shared by the record-derivation CLIs (sim/run_corners.py via
# sim/harness/cli.py, and sim/run_mc.py).
EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_SIM_ERROR = 2
EXIT_ENVIRONMENT = 3


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
) -> tuple[str, Path, Path | None, dict, datetime]:
    """Allocate a record id and derive its workdir/log_dir, as both
    ``sim/run_corners.py`` (via ``sim/harness/cli.py``) and ``sim/run_mc.py``
    do at the top of their ``run()``.

    Returns ``(record_id, workdir, log_dir, git, started)``. ``log_dir`` is
    ``None`` when ``no_write`` is set (debugging runs write no evidence).
    """
    # Local import: sim/harness/report.py imports this module (for `fmt()`),
    # so importing it at module scope here would be circular.
    from . import report as report_mod

    started = datetime.now(timezone.utc)
    git = report_mod.git_provenance(repo_root)
    record_id = report_mod.allocate_record_id(repo_root, records_dir, started, git=git)
    workdir = work_dir / experiment_name / record_id
    log_dir = None if no_write else experiment_dir / report_mod.CORNERS_DIR / record_id
    return record_id, workdir, log_dir, git, started


def exit_code_for_status(status: str) -> int:
    """Translate a record's ``status`` field into the CLI's exit code."""
    if status == "error":
        return EXIT_SIM_ERROR
    if status == "fail":
        return EXIT_CHECK_FAILED
    return EXIT_OK
