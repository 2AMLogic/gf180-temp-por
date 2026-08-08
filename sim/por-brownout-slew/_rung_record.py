"""Shared rung-record parsing for the #60/#74 derived-record scripts.

Both ``analyze_boundary.py`` (issue #60's boundary bracket) and
``analyze_transition_band.py`` (issue #74's transition-band characterization)
read the same full-81-point-grid ``records/*.md`` "rung" records, produced by
``sim/run_corners.py`` per ``sim/README.md``. Each rung record's own
``Claim`` line is the only place the rung's falling-slew rate is recorded
(``testbench/`` is overwritten between rungs), so this module is the single
place that grammar is parsed, rather than two independently-maintained
copies.

Exports ``CLAIM_RE``, ``ROW_RE``, ``TIMESTAMP_RE``, ``DERIVED_SUFFIXES``,
``is_source_record()``, ``Rung``, and ``parse_record()`` -- nothing here runs
a simulation or makes a measurement of its own; it only reduces the
``pass/fail`` column and Claim text already written into each source record.

``DERIVED_SUFFIXES`` / ``is_source_record()`` are the one shared place that
knows which ``records/*.md`` filename stems are themselves derived records
(``analyze_boundary.py``'s ``-boundary`` and ``analyze_transition_band.py``'s
``-transition-band``) rather than a raw ladder "rung" record ``parse_record``
can actually parse. Both scripts glob the same ``records/`` directory and
must skip every derived-record kind, not just their own, or they crash trying
to parse a sibling script's output as an 81-point grid (#122).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DERIVED_SUFFIXES = ("-boundary", "-transition-band")


def is_source_record(path: Path) -> bool:
    """True if ``path`` is a raw ladder rung record, not a derived one.

    Only a true trailing-stem match excludes a record -- a rung record whose
    id merely *contains* "boundary" or "transition-band" mid-string (not as
    its own filename suffix) is still a source record and must be parsed.
    """
    return not any(path.stem.endswith(suffix) for suffix in DERIVED_SUFFIXES)


CLAIM_RE = re.compile(
    r"\*\*Claim\*\*:.*?rung '?([a-z]-slew-([0-9.]+)mvus)'?|"
    r"\*\*Claim\*\*:.*?rung ([0-9.]+) mV/us"
)
ROW_RE = re.compile(
    r"^\s*\|\s*`([a-z0-9_.\-]+)`\s*\|.*\|\s*(PASS|FAIL[^|]*)\s*\|\s*$"
)
TIMESTAMP_RE = re.compile(r"^# Record (\d{8}-\d{6}-[0-9a-f]+)\s*$")


@dataclass
class Rung:
    record_id: str
    label: str
    slew_mvus: float
    status: dict[str, bool]  # corner-id -> PASS(True)/FAIL(False)


def parse_record(path: Path) -> Rung:
    text = path.read_text()
    record_id = None
    for line in text.splitlines():
        m = TIMESTAMP_RE.match(line)
        if m:
            record_id = m.group(1)
            break
    if record_id is None:
        record_id = path.stem

    claim_line = next(
        (line for line in text.splitlines() if line.startswith("- **Claim**")),
        "",
    )
    m = CLAIM_RE.search(claim_line)
    if not m:
        raise ValueError(f"{path}: could not parse rung/slew from Claim line: {claim_line!r}")
    label = m.group(1) if m.group(1) else f"rung-{m.group(3)}mvus"
    slew_mvus = float(m.group(2) if m.group(2) else m.group(3))

    status: dict[str, bool] = {}
    for line in text.splitlines():
        rm = ROW_RE.match(line)
        if not rm:
            continue
        corner_id, verdict = rm.group(1), rm.group(2)
        status[corner_id] = verdict == "PASS"

    if len(status) != 81:
        raise ValueError(f"{path}: expected 81 corner rows, got {len(status)}")

    return Rung(record_id=record_id, label=label, slew_mvus=slew_mvus, status=status)
