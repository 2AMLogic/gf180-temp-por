"""Shared CLI/report helpers for the harness entry points.

``fmt()`` and the testbench-path resolution helpers below used to be
copy-pasted across ``sim/run_mc.py``, ``sim/harness/cli.py``,
``sim/harness/report.py`` and ``sim/harness/mc_report.py`` (issue #135) --
this is their one shared home, alongside the sha256/git_describe/
measurement-parsing helpers already consolidated into
``sim/harness/runner.py`` (#130).
"""

from __future__ import annotations

import json
from pathlib import Path

from .testbench import MANIFEST_NAME, TESTBENCH_DIRNAME, discover


def load_manifest(path: Path) -> dict:
    """Load and parse a testbench manifest (``tb.json``) from ``path``."""
    return json.loads(path.read_text())


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
