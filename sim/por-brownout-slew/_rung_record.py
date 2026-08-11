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

``Rung.provenance`` / ``rungs_of()`` are the same idea applied to the OTHER
way this ladder can be silently mixed (#188). Since #86/#87 a rung can be run
against either the schematic export or the extracted post-layout netlist, and
both mint an ordinary rung record in this same ``records/`` directory. A
ladder is only a ladder if every rung sits on the same DUT: mixing them puts
two different circuits on one slew axis, and once a rung has been run at the
same slew at both levels it also puts two contradictory verdicts at one x
value. So every caller selects ONE provenance rather than globbing blindly,
and the derived records say which one they are.
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
#: ``- **Netlist provenance**: schematic (`...`)`` / ``... extracted (`...`)``
#: -- the field sim/README.md requires every record to carry.
PROVENANCE_RE = re.compile(r"^- \*\*Netlist provenance\*\*:\s*(\w+)")

#: the two values sim/README.md defines for that field.
PROVENANCES = ("schematic", "extracted")


@dataclass
class Rung:
    record_id: str
    label: str
    slew_mvus: float
    status: dict[str, bool]  # corner-id -> PASS(True)/FAIL(False)
    provenance: str = "schematic"


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

    pm = next(
        (m for m in (PROVENANCE_RE.match(line) for line in text.splitlines()) if m),
        None,
    )
    if pm is None or pm.group(1) not in PROVENANCES:
        raise ValueError(
            f"{path}: no parsable **Netlist provenance** field "
            f"({'/'.join(PROVENANCES)} expected)"
        )

    return Rung(
        record_id=record_id,
        label=label,
        slew_mvus=slew_mvus,
        status=status,
        provenance=pm.group(1),
    )


def rungs_of(records_dir: Path, provenance: str) -> list[Rung]:
    """Every rung record under ``records_dir`` run at ``provenance``.

    The one place the ladder is assembled, so neither derived-record script
    can accidentally mix a schematic rung with an extracted one (#188) -- see
    this module's docstring for why that would not be a ladder.
    """
    if provenance not in PROVENANCES:
        raise ValueError(f"unknown provenance {provenance!r}; expected one of {PROVENANCES}")
    rungs = [
        parse_record(p) for p in sorted(records_dir.glob("*.md")) if is_source_record(p)
    ]
    selected = [r for r in rungs if r.provenance == provenance]
    if not selected:
        raise SystemExit(
            f"no {provenance} rung records found under {records_dir} "
            f"(saw {len(rungs)} rung record(s) at "
            f"{sorted({r.provenance for r in rungs})})"
        )
    by_slew: dict[float, list[str]] = {}
    for r in selected:
        by_slew.setdefault(r.slew_mvus, []).append(r.record_id)
    duplicates = {slew: ids for slew, ids in by_slew.items() if len(ids) > 1}
    if duplicates:
        raise SystemExit(
            f"{provenance} ladder has more than one rung at the same slew: "
            f"{duplicates} -- a re-run of an existing rung supersedes it, so "
            "decide which record the ladder should carry before deriving from it"
        )
    return selected
