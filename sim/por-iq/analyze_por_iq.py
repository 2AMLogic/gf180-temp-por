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
`spec/target-spec.md#por-iq` (<3.0 uA, re-costed from <1 uA by DR-018 --
see spec/decision-records/DR-018-por-iq-recost.md) and `#iq-total`
(<21 uA) bounds -- the formal, named, #14-owned publication those two rows
have been missing.

This is a DERIVATION FROM RECORDED EVIDENCE, not a substitute for a
testbench: the source record is a real ngspice run against the real
assembled netlist, full PVT grid, and keeps its own checks and its own
PASS/FAIL. This script only re-reads its raw `m_*` measurements, the same
convention `sim/temp-accuracy-vt/analyze_derived.py` established for
`temp-accuracy-trimmed`.

KNOWN, ALREADY-OWNED RESULT: `por-iq` is expected to PASS at every corner
against the DR-018-recosted <3.0 uA ceiling, including the binding corner
(FF/+125C/3.63V) -- `design/bias_core.md`'s "Iq apportionment" measures the
assembled block's always-on draw at 2.37x the WITHDRAWN <1 uA budget from
summed per-cell numbers, and `sim/temp-por-top-release/` confirmed
0.657-2.385 uA on the real assembly. DR-018 re-costed `por-iq` to <3.0 uA
against exactly that measured overrun (20.5% margin at the binding corner),
so this script records the now-passing result against the currently
ratified ceiling rather than the withdrawn one, per CLAUDE.md and
target-spec.md section 5.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SOURCE_CORNERS_DIR = EXPERIMENT_DIR.parent / "temp-accuracy-vt" / "corners"
RECORDS_DIR = EXPERIMENT_DIR / "records"

sys.path.insert(0, str(EXPERIMENT_DIR.parent))

from harness.cliutil import add_author_arg, now_iso, write_derived_record  # noqa: E402
from harness.corners import parse_corner_id  # noqa: E402
from harness.report import RecordExists, source_provenance  # noqa: E402
from harness.runner import load_points  # noqa: E402

SOURCE_EXPERIMENT_DIR = SOURCE_CORNERS_DIR.parent

# spec/target-spec.md#por-iq: re-costed <1 uA -> <3.0 uA by DR-018
# (spec/decision-records/DR-018-por-iq-recost.md), against the measured
# 2.37-2.38x apportionment overrun. sim/tests/test_por_iq_spec_sync.py
# fails if this drifts from the ratified spec table again.
TARGET_POR_IQ_UA = 3.0  # spec/target-spec.md#por-iq [DR-018]
TARGET_IQ_TOTAL_UA = 21.0  # spec/target-spec.md#iq-total (unchanged by DR-018)

# The standard mandated PVT grid (sim/README.md / CLAUDE.md): -40/27/125 C.
# temp-accuracy-vt's grid adds 25 C on top, only for its own trim derivation.
STANDARD_TEMPS_C = (-40.0, 27.0, 125.0)

def standard_grid_rows(points: dict[str, dict[str, float]]) -> list[dict]:
    rows: list[dict] = []
    for corner_id, measured in sorted(points.items()):
        fields = parse_corner_id(corner_id)
        if fields is None:
            continue
        process, temp_c, supply = fields
        if not any(abs(temp_c - t) < 1e-6 for t in STANDARD_TEMPS_C):
            continue  # drop the 25 C trim-reference plane -- not part of #14's grid
        if "iq_por_ua" not in measured or "iq_total_ua" not in measured:
            continue
        rows.append(
            {
                "corner_id": corner_id,
                "process": process,
                "temp_c": temp_c,
                "supply": supply,
                "por_iq_ua": measured["iq_por_ua"],
                "iq_total_ua": measured["iq_total_ua"],
                "temp_iq_ua": measured.get("temp_iq_ua"),
            }
        )
    return rows


def render(
    record_id: str,
    rows: list[dict],
    when: str,
    author: str,
    prior_records: list[str],
) -> str:
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
        "<3.0 uA target (re-costed from <1 uA by "
        "`spec/decision-records/DR-018-por-iq-recost.md`), binding at "
        "FF/+125C/3.63V. Also publishes "
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
        f"(`sim/temp-accuracy-vt/corners/{record_id}/`), whose own **Netlist "
        f"provenance** field reads: "
        f"{source_provenance(SOURCE_EXPERIMENT_DIR, record_id)} "
        "That source record keeps its own checks and its own "
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
        f"### `spec/target-spec.md#por-iq` -- <{TARGET_POR_IQ_UA} uA [DR-018], "
        "RESETn asserted, sensor disabled",
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
        (
            f"**Overall: {overall}** -- EXPECTED, against the DR-018-recosted "
            f"<{TARGET_POR_IQ_UA} uA ceiling. `design/bias_core.md`'s \"Iq "
            "apportionment\" measures the assembled block's always-on draw "
            "at 2.37x the WITHDRAWN <1 uA budget from summed per-cell "
            "numbers (FF/+125C/3.63V: bias_core 2047 nA + por_comparator "
            "292 nA + por_output_chain 31.6 nA = 2371 nA), and "
            "`sim/temp-por-top-release/` independently confirmed "
            "0.657-2.385 uA on the real assembly. "
            "`spec/decision-records/DR-018-por-iq-recost.md` re-costed "
            f"`por-iq` to <{TARGET_POR_IQ_UA} uA against exactly that "
            "measured overrun (20.5% margin at the binding corner), so "
            "this already-owned architecture-level result now PASSES the "
            "currently ratified ceiling. This does not touch the "
            "separate, still-open starved-loop window (see "
            "`design/bias_core.md`, \"The starved-loop window\") -- CLAUDE.md "
            "and target-spec.md section 5 still require recording the "
            "measured number rather than asserting a target unbacked by "
            "measurement."
            if overall == "PASS"
            else f"**Overall: {overall}** -- REGRESSION against the "
            f"DR-018-recosted <{TARGET_POR_IQ_UA} uA ceiling, which prior "
            "measurement (schematic and post-layout, both cited by "
            "`spec/decision-records/DR-018-por-iq-recost.md`) found met "
            "with 20.5% margin at the binding corner. This is NOT the "
            "already-known withdrawn-<1 uA overrun `design/bias_core.md`'s "
            "\"Iq apportionment\" documents -- it needs its own "
            "investigation and, if confirmed, a new decision record rather "
            "than being folded into DR-018's disposition."
        ),
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
        (
            f"**Overall: {overall_total}** -- `iq-total`'s budget is met at "
            "every corner, and (per the table above) so is `por-iq`'s own "
            f"DR-018-recosted <{TARGET_POR_IQ_UA} uA ceiling: `temp-iq`'s "
            "measured range (5.80-15.90 uA, `sim/temp-accuracy-vt/`) leaves "
            "real headroom under the 21 uA sum on top of that. `iq-total` "
            "is a genuinely different, independently-ratified bound from "
            "`por-iq` (DR-018) and is ratifiable on this evidence "
            "regardless of `por-iq`'s own disposition."
            if overall_total == "PASS" and overall == "PASS"
            else f"**Overall: {overall_total}** -- `iq-total`'s budget is "
            f"met at every corner even though `por-iq` alone is not (against "
            f"the DR-018-recosted <{TARGET_POR_IQ_UA} uA ceiling), because "
            "`temp-iq`'s measured range (5.80-15.90 uA, "
            "`sim/temp-accuracy-vt/`) leaves enough headroom under the "
            "21 uA sum. `iq-total` is a genuinely different bound from "
            "`por-iq` and is ratifiable on this evidence even while "
            "`por-iq` is not."
            if overall_total == "PASS"
            else f"**Overall: {overall_total}** -- `iq-total`'s own <21 uA "
            "ceiling is MISSED at one or more corners -- this is a genuine "
            "regression against every prior measurement cited by "
            "`spec/decision-records/DR-018-por-iq-recost.md` and needs its "
            "own investigation, not a relaxed target."
        ),
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
        (
            "- **Supersedes**: (none -- first published record for these "
            "two rows; `sim/temp-por-top-release/`'s `iq_por_ua` column is "
            "independent corroborating evidence on the same assembled "
            "netlist, not a prior record this one supersedes)"
            if not prior_records
            else "- **Supersedes**: (none -- does not chain-supersede "
            + ", ".join(f"`{r}`" for r in prior_records)
            + ", the prior derived record(s) for this same claim from a "
            "different source record-id. Per the convention "
            "`sim/temp-accuracy-vt/analyze_derived.py`'s own post-layout "
            "derived record established, a re-derivation against a new "
            "source record is independent evidence tied to that source's "
            "own record-id rather than a correction superseding the prior "
            "derivation; both stand as evidence for this claim.)"
        ),
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
    add_author_arg(parser)
    args = parser.parse_args(argv)

    points = load_points(SOURCE_CORNERS_DIR, args.record_id)
    rows = standard_grid_rows(points)
    if not rows:
        print("no standard-grid points with iq_por_ua/iq_total_ua found", file=sys.stderr)
        return 2
    if len(rows) != 81:
        print(
            f"warning: expected 81 standard-grid points, found {len(rows)}",
            file=sys.stderr,
        )

    exclude_name = f"{args.record_id}-por-iq-derived.md"
    prior_records = sorted(
        p.stem for p in RECORDS_DIR.glob("*-por-iq-derived.md") if p.name != exclude_name
    )

    when = now_iso()
    text = render(args.record_id, rows, when, args.author, prior_records)

    if args.write:
        try:
            out_path = write_derived_record(
                text, RECORDS_DIR, f"{args.record_id}-por-iq-derived.md"
            )
        except RecordExists as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
