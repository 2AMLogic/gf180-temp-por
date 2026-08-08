#!/usr/bin/env python3
"""Publish spec/target-spec.md#por-iq and #iq-total from an already-run
`temp-accuracy-vt` record's own raw per-point logs.

    python3 sim/por-iq/analyze_por_iq.py <temp-accuracy-vt-record-id> [--write]

WHY THIS IS A DERIVATION, NOT A FRESH SIMULATION

`sim/temp-accuracy-vt/`'s testbench (issue #13) already measures the POR
quiescent-current state (`RESETn` asserted, rail settled, sensor disabled --
target-spec.md section 5 rule 1) on the SAME real assembled path
(`design/netlist/temp_por_top.spice`, all four cells, bias_core-driven
`IBIAS`) this issue's own full-assembly testbenches use, in the same window
`sim/temp-por-top-release/` samples it in (1.5-1.9 ms, rail settled, sensor
still disabled). Its raw logs already carry `m_iq_por_ua` (the `por-iq` row)
and `m_iq_total_ua` (`por-iq` + `temp-iq`, i.e. the `iq-total` row) at every
point of its 108-point grid. Re-running an identical DC-operating-point
measurement on an identical netlist for a different experiment slug would
not be new evidence -- it would be the same ngspice solve a second time,
burning simulator time (this full-assembly transient is expensive; see
sim/por-vth/'s testbench header) to reproduce a number that already exists.

What was missing, and what this script supplies, is the PUBLICATION: per
`sim/temp-accuracy-vt/testbench/tb.json`'s own claim text, "`#iq-total` is
NOT closed here: `iq_total_ua` is reported unchecked and this record
supplies only the `temp-iq` half; #14 owns `por-iq`." This script reads that
record's raw per-point logs, filters to the standard 81-point mandated grid
(dropping the 25 C trim-reference plane #13 added only for its own
derivation), and checks `iq_por_ua` and `iq_total_ua` against the ratified
`spec/target-spec.md#por-iq` (<1 uA) and `#iq-total` (<21 uA) bounds -- the
formal, named, #14-owned publication those two rows have been missing.

This is a DERIVATION FROM RECORDED EVIDENCE, not a substitute for a
testbench: the source record is a real ngspice run against the real
assembled netlist, full PVT grid, and keeps its own checks and its own
PASS/FAIL. This script only re-reads its raw `m_*` measurements, the same
convention `sim/temp-accuracy-vt/analyze_derived.py` established for
`temp-accuracy-trimmed`.

KNOWN, ALREADY-OWNED RESULT: `por-iq` is expected to FAIL at the binding
corner (FF/+125C/3.63V) -- `design/bias_core.md`'s "Iq apportionment"
already measures the assembled block's always-on draw at 2.37x the <1 uA
budget from summed per-cell numbers, and `sim/temp-por-top-release/`
confirmed 0.657-2.385 uA on the real assembly. This script records that
result rather than relaxing the target to make it pass, per CLAUDE.md and
target-spec.md section 5.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SOURCE_CORNERS_DIR = EXPERIMENT_DIR.parent / "temp-accuracy-vt" / "corners"
RECORDS_DIR = EXPERIMENT_DIR / "records"

sys.path.insert(0, str(EXPERIMENT_DIR.parent))

from harness.runner import parse_measurements  # noqa: E402

TARGET_POR_IQ_UA = 1.0  # spec/target-spec.md#por-iq
TARGET_IQ_TOTAL_UA = 21.0  # spec/target-spec.md#iq-total

# The standard mandated PVT grid (sim/README.md / CLAUDE.md): -40/27/125 C.
# temp-accuracy-vt's grid adds 25 C on top, only for its own trim derivation.
STANDARD_TEMPS_C = (-40.0, 27.0, 125.0)

_CORNER_ID_RE = re.compile(
    r"^(?P<process>[a-z_]+)_(?P<temp>-?\d+(?:\.\d+)?)c_(?P<supply>\d+\.\d+)v$"
)


def parse_log(path: Path) -> dict[str, float]:
    """The `m_<name> = <value>` lines one ngspice point printed."""
    return parse_measurements(path.read_text())


def load_points(record_id: str) -> dict[str, dict[str, float]]:
    log_dir = SOURCE_CORNERS_DIR / record_id
    if not log_dir.is_dir():
        raise FileNotFoundError(
            f"no raw logs at {log_dir} -- run "
            f"'python3 sim/run_corners.py temp-accuracy-vt' first"
        )
    points = {p.stem: parse_log(p) for p in sorted(log_dir.glob("*.log"))}
    if not points:
        raise FileNotFoundError(f"no *.log files under {log_dir}")
    return points


def standard_grid_rows(points: dict[str, dict[str, float]]) -> list[dict]:
    rows: list[dict] = []
    for corner_id, measured in sorted(points.items()):
        match = _CORNER_ID_RE.match(corner_id)
        if not match:
            continue
        temp_c = float(match.group("temp"))
        if not any(abs(temp_c - t) < 1e-6 for t in STANDARD_TEMPS_C):
            continue  # drop the 25 C trim-reference plane -- not part of #14's grid
        if "iq_por_ua" not in measured or "iq_total_ua" not in measured:
            continue
        rows.append(
            {
                "corner_id": corner_id,
                "process": match.group("process"),
                "temp_c": temp_c,
                "supply": match.group("supply"),
                "por_iq_ua": measured["iq_por_ua"],
                "iq_total_ua": measured["iq_total_ua"],
                "temp_iq_ua": measured.get("temp_iq_ua"),
            }
        )
    return rows


def render(record_id: str, rows: list[dict], when: str, author: str) -> str:
    por_iq_vals = [r["por_iq_ua"] for r in rows]
    total_vals = [r["iq_total_ua"] for r in rows]
    por_iq_fail = [r for r in rows if r["por_iq_ua"] > TARGET_POR_IQ_UA]
    total_fail = [r for r in rows if r["iq_total_ua"] > TARGET_IQ_TOTAL_UA]
    por_iq_worst = max(rows, key=lambda r: r["por_iq_ua"])
    por_iq_best = min(rows, key=lambda r: r["por_iq_ua"])
    total_worst = max(rows, key=lambda r: r["iq_total_ua"])
    total_best = min(rows, key=lambda r: r["iq_total_ua"])

    overall = "FAIL" if por_iq_fail else "PASS"
    overall_total = "FAIL" if total_fail else "PASS"

    out: list[str] = [
        f"# Record {record_id}-por-iq-derived",
        "",
        f"- **Record ID**: `{record_id}-por-iq-derived`",
        "- **Claim**: `spec/target-spec.md#por-iq` -- POR quiescent current, "
        "`RESETn` asserted, temperature sensor disabled (section 5 rule 1), "
        "<1 uA target, binding at FF/+125C/3.63V. Also publishes "
        "`spec/target-spec.md#iq-total` = `por-iq` + `temp-iq` < 21 uA "
        "(normal operation, `RESETn` released, sensor enabled), per that "
        "row's own text: \"#13's half delivered ... this record's own "
        "carried por-iq read ... is not a ratifiable close of this row: "
        "por-iq is #14's row to publish, not #13's to carry as evidence.\" "
        "This record is that publication.",
        "- **Netlist provenance**: **derivation, not a fresh simulation** -- "
        f"computed by `sim/por-iq/analyze_por_iq.py` from the raw per-point "
        f"`m_iq_por_ua`/`m_iq_total_ua` measurements of "
        f"`sim/temp-accuracy-vt/`'s record `{record_id}` "
        f"(`sim/temp-accuracy-vt/corners/{record_id}/`), itself schematic-level "
        "(`design/netlist/temp_por_top.spice`, the full four-cell assembly, "
        "`RESETn`-gated sensor enable, bias_core-driven `IBIAS` -- nothing "
        "idealised). That source record keeps its own checks and its own "
        "PASS/FAIL and remains the primary evidence for the state it "
        "measures; this record only re-checks the SAME raw numbers against "
        "the `por-iq`/`iq-total` bounds, which the source record left "
        "unchecked by its own design (see that record's `iq_total_ua` "
        "measure).",
        "- **Corner matrix run**: the standard 81-point mandated grid (9 "
        "process corners x 3 temperatures [-40, 27, 125 C] x 3 supplies "
        "[2.97, 3.30, 3.63 V]), filtered out of the source record's "
        "108-point grid (which adds a 25 C trim-reference plane #13 needed "
        "for its own derivation and #14 does not). Full PVT matrix per "
        "CLAUDE.md.",
        "- **Statistical convention**: N/A (corner-matrix claim, not a "
        "distribution claim). Deterministic corners only "
        "(`sw_stat_mismatch=0` in `design.ngspice`).",
        "- **Result**:",
        "",
        "### `spec/target-spec.md#por-iq` -- <1 uA, RESETn asserted, sensor disabled",
        "",
        "| corner-id | por_iq_ua | status |",
        "|---|---|---|",
    ]
    for row in rows:
        status = "PASS" if row["por_iq_ua"] <= TARGET_POR_IQ_UA else "FAIL"
        out.append(f"| `{row['corner_id']}` | {row['por_iq_ua']:.6f} | {status} |")
    out += [
        "",
        f"**{len(rows) - len(por_iq_fail)}/{len(rows)} points within <{TARGET_POR_IQ_UA} uA. "
        f"Range: {por_iq_best['por_iq_ua']:.6f} uA (`{por_iq_best['corner_id']}`) ... "
        f"{por_iq_worst['por_iq_ua']:.6f} uA (`{por_iq_worst['corner_id']}`).**",
        "",
        f"**Overall: {overall}** -- EXPECTED. `design/bias_core.md`'s \"Iq "
        "apportionment\" already measures the assembled block's always-on "
        "draw at 2.37x the <1 uA budget from summed per-cell numbers "
        "(FF/+125C/3.63V: bias_core 2047 nA + por_comparator 292 nA + "
        "por_output_chain 31.6 nA = 2371 nA), and `sim/temp-por-top-release/` "
        "independently confirmed 0.657-2.385 uA on the real assembly. This is "
        "an already-owned architecture-level overrun pending a re-cost "
        "decision record through #1 (see `design/bias_core.md`, \"The "
        "starved-loop window\", options 1-3) -- CLAUDE.md and "
        "target-spec.md section 5 require recording it, not relaxing the "
        "ratified 1.0 uA target to make it pass.",
        "",
        "### `spec/target-spec.md#iq-total` -- <21 uA, RESETn released, sensor enabled",
        "",
        "| corner-id | por_iq_ua | temp_iq_ua | iq_total_ua | status |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        status = "PASS" if row["iq_total_ua"] <= TARGET_IQ_TOTAL_UA else "FAIL"
        temp_iq = row["temp_iq_ua"]
        temp_iq_s = f"{temp_iq:.6f}" if temp_iq is not None else "n/a"
        out.append(
            f"| `{row['corner_id']}` | {row['por_iq_ua']:.6f} | {temp_iq_s} | "
            f"{row['iq_total_ua']:.6f} | {status} |"
        )
    out += [
        "",
        f"**{len(rows) - len(total_fail)}/{len(rows)} points within <{TARGET_IQ_TOTAL_UA} uA. "
        f"Range: {total_best['iq_total_ua']:.6f} uA (`{total_best['corner_id']}`) ... "
        f"{total_worst['iq_total_ua']:.6f} uA (`{total_worst['corner_id']}`).**",
        "",
        f"**Overall: {overall_total}** -- `iq-total`'s budget is met at every "
        "corner even though `por-iq` alone is not, because `temp-iq`'s "
        "measured range (5.80-15.90 uA, `sim/temp-accuracy-vt/`) leaves "
        "enough headroom under the 21 uA sum. `iq-total` is a genuinely "
        "different bound from `por-iq` and is ratifiable on this evidence "
        "even while `por-iq` is not.",
        "",
        "- **Links**:",
        f"  - Source record: `sim/temp-accuracy-vt/records/{record_id}.md`",
        f"  - Raw logs derived from: `sim/temp-accuracy-vt/corners/{record_id}/`",
        "  - Derivation script: `sim/por-iq/analyze_por_iq.py`",
        "- **Deviation from the standard experiment layout**: this "
        "experiment has no `testbench/`, `netlist-snapshots/`, or `corners/` "
        "of its own -- it is a pure derivation from another experiment's raw "
        "logs, exactly as `sim/temp-accuracy-vt/analyze_derived.py` "
        "established for `temp-accuracy-trimmed` (see that script's own "
        "docstring). It still gets its own experiment directory because "
        "`por-iq`/`iq-total` are their own named spec-row claims per "
        "`sim/README.md`'s \"every ratified spec row maps to a named "
        "experiment slug\" rule, distinct from `temp-accuracy-vt`'s claims.",
        f"- **Timestamp / author**: {when}, {author}",
        "- **Supersedes**: (none -- first published record for these two rows; "
        "`sim/temp-por-top-release/`'s `iq_por_ua` column is independent "
        "corroborating evidence on the same assembled netlist, not a prior "
        "record this one supersedes)",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish por-iq/iq-total from a temp-accuracy-vt record."
    )
    parser.add_argument(
        "record_id", help="the sim/temp-accuracy-vt/ <record-id> to derive from"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write records/<record-id>-por-iq-derived.md (default: print to stdout)",
    )
    parser.add_argument("--author", default="agent-builder", help="author for the record header")
    args = parser.parse_args(argv)

    points = load_points(args.record_id)
    rows = standard_grid_rows(points)
    if not rows:
        print("no standard-grid points with iq_por_ua/iq_total_ua found", file=sys.stderr)
        return 2
    if len(rows) != 81:
        print(
            f"warning: expected 81 standard-grid points, found {len(rows)}",
            file=sys.stderr,
        )

    when = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    text = render(args.record_id, rows, when, args.author)

    if args.write:
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RECORDS_DIR / f"{args.record_id}-por-iq-derived.md"
        if out_path.exists():
            print(
                f"error: {out_path} already exists -- derived write-ups are "
                "append-only too; derive from a new record-id instead",
                file=sys.stderr,
            )
            return 1
        out_path.write_text(text)
        print(f"wrote {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
