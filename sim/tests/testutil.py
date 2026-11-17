#!/usr/bin/env python3
"""Shared test fixtures for sim/tests.

No PDK and no ngspice required -- fake_pdk() builds a minimal on-disk PDK
stand-in so unit tests can run without either, and published() stamps a
record the way a real run does before it is rendered.
"""

from __future__ import annotations

import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import evidence_store  # noqa: E402
from harness.pdk import Pdk  # noqa: E402


def fake_pdk(root: Path) -> Pdk:
    (root / "libs.tech" / "ngspice").mkdir(parents=True, exist_ok=True)
    (root / "libs.tech" / "ngspice" / "sm141064.ngspice").write_text("* fake\n")
    (root / "libs.tech" / "ngspice" / "design.ngspice").write_text("* fake\n")
    (root / "SOURCES").write_text("open_pdks deadbeef\n")
    return Pdk(path=root, variant=root.name, source="test")


def published(record: dict, experiment: str) -> dict:
    """Stamp ``record`` with the ``evidence_manifest`` a real run carries.

    DR-030: ``cliutil.finish_run`` publishes the run's staged raw bytes to
    the artifact store and records the resulting manifest path *before*
    rendering the record, so a record is never rendered without this field.
    Rendering fixtures must do the same.
    """
    record["evidence_manifest"] = evidence_store.manifest_relpath(
        experiment, record["record_id"]
    ).as_posix()
    return record
