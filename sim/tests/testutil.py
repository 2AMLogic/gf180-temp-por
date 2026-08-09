#!/usr/bin/env python3
"""Shared test fixtures for sim/tests.

No PDK and no ngspice required -- fake_pdk() builds a minimal on-disk PDK
stand-in so unit tests can run without either.
"""

from __future__ import annotations

import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness.pdk import Pdk  # noqa: E402


def fake_pdk(root: Path) -> Pdk:
    (root / "libs.tech" / "ngspice").mkdir(parents=True, exist_ok=True)
    (root / "libs.tech" / "ngspice" / "sm141064.ngspice").write_text("* fake\n")
    (root / "libs.tech" / "ngspice" / "design.ngspice").write_text("* fake\n")
    (root / "SOURCES").write_text("open_pdks deadbeef\n")
    return Pdk(path=root, variant=root.name, source="test")
