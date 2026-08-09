#!/usr/bin/env python3
"""Derive spec/target-spec.md#temp-accuracy-trimmed (and the published V(T)
summary) from a `temp-accuracy-vt` record's own raw per-point logs.

    python3 sim/temp-accuracy-vt/analyze_derived.py <record-id> [--write]

WHY THIS EXISTS (read before touching the numbers)

`temp-accuracy-trimmed` is the one row of issue #13's set that cannot be a
direct measurement, for two independent reasons:

1. **`.temp` is a single global value per ngspice run.** "Error after a
   one-point 25 C gain trim" is by definition a statement relating a point's
   own reading to that same corner's reading at 25 C. No single point of the
   PVT grid can see both, so the quantity only exists across two points of
   the same record.
2. **The wave-1 trim is not a runtime knob.** `design/temp_core.md`
   ("Trim: single 25 C gain trim") specifies a 6-bit binary-weighted
   short-out ladder on `R2` whose switch gates are **strapped by metal-1
   mask option**, code `100000b` — already baked into
   `design/netlist/temp_core.spice` (XSW5's gate to VDD, XSW4..XSW0's to
   VSS). There is no second, "trimmed", netlist state to re-simulate: the
   committed netlist already *is* the wave-1-trimmed circuit, and issue #13
   is measurement-only (no schematic edits).

So what the `[3 sigma]` stretch row actually asks — *what does a one-point
25 C gain trim leave behind?* — is answered the way `design/temp_core.md`'s
own error budget answers it: renormalise each (corner, supply) group's gain
on its own 25 C point and ask how far off the renormalised read is at the
other temperatures. A single shared metal code cannot do better than a
per-corner-optimal calibration, so this is the mechanism's best case, which
is the right thing to compare a stretch goal against.

This is a DERIVATION FROM RECORDED EVIDENCE, not a substitute for it. The
source record keeps its own checks and its own PASS/FAIL and remains the
primary evidence; this script only re-reads its raw `m_*` measurements. It
is committed and re-runnable so the numbers are reproducible per CLAUDE.md's
"no claim without a testbench" rule: re-running it against the same
record-id reproduces the identical table, and running it against a
superseding record-id re-derives it from fresh data.

WHAT IT COMPUTES

1. **`#temp-accuracy-trimmed`** (the reason this script exists). For each
   (process corner, supply) group, let `V25` be that group's 25 C PTAT
   reading. The trim-referenced gain is `K25 = V25 / 298.15 K`. A perfectly
   executed 25 C gain trim on that corner reports `T_hat(T) =
   V(PTAT,T) / K25`, so the residual curvature is `T_hat(T) - T`, evaluated
   at every other temperature of the group. On top of that sits the trim
   mechanism's own **quantisation**: the ladder is discrete
   (1 LSB = 0.2287-0.2423 % of `R2`, `design/temp_core.md`), so a real trim
   lands within half an LSB of the ideal gain. Half an LSB of *gain* error
   costs `(LSB/2) * T` in reported temperature — 0.36 C at the 25 C trim
   point, which is the +/-0.35 C `design/temp_core.md` quotes, and more at
   125 C. The two are summed in the worse direction, exactly as that
   document's budget does (curvature +/-0.256 C + quantisation +/-0.35 C =
   +/-0.61 C).

2. **`#temp-vt-transfer` published summary.** The per-point `ptat_k_mvk` and
   `vptat_v`/`vctat_v` columns are already in the source record; what a
   *published characteristic* additionally needs is the cross-point form of
   them — `K0` at the 25 C reference and its spread over corners, the CTAT
   slope in mV/C from each corner's -40/+125 C endpoints, and the output
   range of both pads over the grid. All are pure cross-point reductions of
   the same data.

3. **`#temp-supply-sensitivity` strict cross-check.** The source record
   measures this per point against an identical DUT held at `vdd_nom` in the
   same run, and checks it at +/-0.33 C. That is the bound as target-spec.md
   parenthesises it ("<=0.33 C across the +/-10 % window") applied to each
   rail extreme separately. The stricter reading of the same row — total
   peak-to-peak across the whole 2.97-3.63 V window at one (corner,
   temperature) — is reported here so the row is judged on both readings and
   neither is quietly the convenient one.

None of the three needs a fresh circuit simulation; all three are reductions
of data the source record already collected. That is why the grid carries
25 C on top of the three ratified temperature anchors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
CORNERS_DIR = EXPERIMENT_DIR / "corners"
RECORDS_DIR = EXPERIMENT_DIR / "records"

sys.path.insert(0, str(EXPERIMENT_DIR.parent))

from harness.cliutil import add_author_arg, now_iso  # noqa: E402
from harness.corners import parse_corner_id  # noqa: E402
from harness.runner import load_points  # noqa: E402

# design/temp_core.md "V(T) transfer and output range": the declared nominal
# transfer constant, K0 = 4.308842 mV/K (tt, 25 C). Used for the supply
# cross-check; the trim derivation deliberately uses each corner's OWN K25.
K0 = 4.308842e-3

# design/temp_core.md "Trim: single 25 C gain trim": 1 LSB = 0.2287-0.2423 %
# of R2 as measured over the 216-point grid. Quoted at the wider end so the
# quantisation allowance is conservative rather than flattering.
TRIM_LSB_FRAC = 0.002423

TRIM_REFERENCE_K = 298.15  # 25 C, the trim point DR-005 ratified

TARGET_TRIMMED_C = 1.5  # spec/target-spec.md#temp-accuracy-trimmed (stretch)
TARGET_SUPPLY_C = 0.33  # spec/target-spec.md#temp-supply-sensitivity
NOMINAL_SUPPLY_V = "3.30"

def parse_corner_ids(points: dict[str, dict[str, float]]) -> dict[str, tuple[str, float, str]]:
    """Map each parseable corner id to its ``(process, temp_c, supply)``.

    Ids that are not in the harness's ratified naming are dropped, so the
    derivations below only ever group points they can place on the grid.
    """
    parsed: dict[str, tuple[str, float, str]] = {}
    for corner_id in points:
        fields = parse_corner_id(corner_id)
        if fields is not None:
            parsed[corner_id] = fields
    return parsed


# --------------------------------------------------------------------------
# 1. temp-accuracy-trimmed
# --------------------------------------------------------------------------


def derive_trimmed(points, parsed) -> list[dict]:
    """One row per non-25 C point: the residual a perfect 25 C gain trim leaves."""
    groups: dict[tuple[str, str], list[str]] = {}
    for corner_id, (process, _temp_c, supply) in parsed.items():
        groups.setdefault((process, supply), []).append(corner_id)

    rows: list[dict] = []
    for (process, supply), corner_ids in sorted(groups.items()):
        anchor = next(
            (cid for cid in corner_ids if abs(parsed[cid][1] - 25.0) < 1e-6), None
        )
        if anchor is None or "vptat_v" not in points[anchor]:
            rows.append(
                {
                    "process": process,
                    "supply": supply,
                    "status": "no 25 C anchor in this record -- cannot derive",
                }
            )
            continue
        k25 = points[anchor]["vptat_v"] / TRIM_REFERENCE_K

        for corner_id in sorted(corner_ids, key=lambda cid: parsed[cid][1]):
            temp_c = parsed[corner_id][1]
            if abs(temp_c - 25.0) < 1e-6:
                continue  # the calibration point itself: residual is 0 by construction
            if "vptat_v" not in points[corner_id]:
                rows.append(
                    {
                        "process": process,
                        "supply": supply,
                        "temp_c": temp_c,
                        "status": f"{corner_id}: no vptat_v measurement",
                    }
                )
                continue
            t_k = temp_c + 273.15
            curvature_c = points[corner_id]["vptat_v"] / k25 - t_k
            quant_c = (TRIM_LSB_FRAC / 2.0) * t_k
            # Sum in the worse direction: the two terms are independent, and
            # design/temp_core.md's budget adds their magnitudes.
            total_c = curvature_c + (quant_c if curvature_c >= 0 else -quant_c)
            rows.append(
                {
                    "process": process,
                    "supply": supply,
                    "temp_c": temp_c,
                    "corner_id": corner_id,
                    "k25_mvk": k25 * 1e3,
                    "curvature_c": curvature_c,
                    "quant_c": quant_c,
                    "trimmed_error_c": total_c,
                    "status": "PASS"
                    if abs(total_c) <= TARGET_TRIMMED_C
                    else f"FAIL (|{total_c:.4f}| > {TARGET_TRIMMED_C})",
                }
            )
    return rows


# --------------------------------------------------------------------------
# 2. temp-vt-transfer published summary
# --------------------------------------------------------------------------


def derive_vt(points, parsed) -> dict:
    """Cross-point reductions of the published V(T) characteristic."""
    k25: list[tuple[float, str]] = []
    ctat_slope: list[tuple[float, str]] = []
    ptat_all: list[tuple[float, str]] = []
    ctat_all: list[tuple[float, str]] = []
    ctat_27: list[tuple[float, str]] = []

    for corner_id, (_process, temp_c, _supply) in parsed.items():
        measured = points[corner_id]
        if "vptat_v" in measured:
            ptat_all.append((measured["vptat_v"], corner_id))
        if "vctat_v" in measured:
            ctat_all.append((measured["vctat_v"], corner_id))
        if abs(temp_c - 25.0) < 1e-6 and "vptat_v" in measured:
            k25.append((measured["vptat_v"] / TRIM_REFERENCE_K * 1e3, corner_id))
        if abs(temp_c - 27.0) < 1e-6 and "vctat_v" in measured:
            ctat_27.append((measured["vctat_v"], corner_id))

    groups: dict[tuple[str, str], dict[float, str]] = {}
    for corner_id, (process, temp_c, supply) in parsed.items():
        groups.setdefault((process, supply), {})[temp_c] = corner_id
    for (process, supply), by_temp in sorted(groups.items()):
        cold, hot = by_temp.get(-40.0), by_temp.get(125.0)
        if cold and hot and "vctat_v" in points[cold] and "vctat_v" in points[hot]:
            slope = (points[hot]["vctat_v"] - points[cold]["vctat_v"]) / 165.0 * 1e3
            ctat_slope.append((slope, f"{process}@{supply}V"))

    def span(samples):
        if not samples:
            return None
        lo, hi = min(samples), max(samples)
        return {"min": lo[0], "min_at": lo[1], "max": hi[0], "max_at": hi[1]}

    return {
        "k25_mvk": span(k25),
        "ctat_slope_mvc": span(ctat_slope),
        "ptat_range_v": span(ptat_all),
        "ctat_range_v": span(ctat_all),
        "ctat_27_v": span(ctat_27),
    }


# --------------------------------------------------------------------------
# 3. temp-supply-sensitivity, strict full-window reading
# --------------------------------------------------------------------------


def derive_supply_window(points, parsed) -> list[dict]:
    """Peak-to-peak reported-temperature shift across the whole +/-10 % window."""
    groups: dict[tuple[str, float], list[str]] = {}
    for corner_id, (process, temp_c, _supply) in parsed.items():
        groups.setdefault((process, temp_c), []).append(corner_id)

    rows: list[dict] = []
    for (process, temp_c), corner_ids in sorted(groups.items()):
        values = [
            (points[cid]["vptat_v"], parsed[cid][2])
            for cid in corner_ids
            if "vptat_v" in points[cid]
        ]
        if len(values) < 2:
            continue
        lo, hi = min(values), max(values)
        pp_c = (hi[0] - lo[0]) / K0
        rows.append(
            {
                "process": process,
                "temp_c": temp_c,
                "n_supplies": len(values),
                "pp_c": pp_c,
                "lo_at": lo[1],
                "hi_at": hi[1],
                "status": "PASS"
                if pp_c <= TARGET_SUPPLY_C
                else f"FAIL ({pp_c:.4f} > {TARGET_SUPPLY_C})",
            }
        )
    return rows


# --------------------------------------------------------------------------
# write-up
# --------------------------------------------------------------------------


def _tally(rows: list[dict]) -> tuple[int, int]:
    scored = [r for r in rows if "corner_id" in r or "pp_c" in r]
    failed = [r for r in scored if str(r.get("status", "")).startswith("FAIL")]
    return len(scored), len(failed)


def _extreme(rows: list[dict], key: str):
    scored = [r for r in rows if key in r]
    if not scored:
        return None, None
    return (
        min(scored, key=lambda r: r[key]),
        max(scored, key=lambda r: r[key]),
    )


def render(record_id: str, trimmed, vt, supply, when: str, author: str) -> str:
    n_trim, n_trim_fail = _tally(trimmed)
    n_sup, n_sup_fail = _tally(supply)
    lo, hi = _extreme(trimmed, "trimmed_error_c")
    overall = "PASS" if (n_trim_fail == 0 and n_sup_fail == 0) else "FAIL"

    out: list[str] = [
        f"# Record {record_id}-derived",
        "",
        f"- **Record ID**: `{record_id}-derived`",
        "- **Claim**: `spec/target-spec.md#temp-accuracy-trimmed` — temperature "
        "error after the ratified 1-point 25 °C gain trim "
        "([`temp-trim-strategy`](../../../spec/target-spec.md#temp-trim-strategy), "
        "wave-1 code `100000b`), ±1.5 °C stretch, `[3σ]` · `conditional #15`. "
        "Also carries the published cross-point reductions of "
        "`spec/target-spec.md#temp-vt-transfer` (K₀ at the 25 °C reference, "
        "CTAT slope, output range) and a stricter full-window reading of "
        "`spec/target-spec.md#temp-supply-sensitivity` than the per-point "
        "check in the source record.",
        f"- **Netlist provenance**: **derivation, not a fresh simulation** — "
        f"computed by `sim/temp-accuracy-vt/analyze_derived.py` from the raw "
        f"per-point `m_*` measurements of record `{record_id}` "
        f"(`sim/temp-accuracy-vt/corners/{record_id}/`), which is itself "
        f"schematic-level (`design/netlist/temp_por_top.spice`, the full "
        f"four-cell assembly). The source record keeps its own checks and its "
        f"own PASS/FAIL and remains the primary evidence.",
        "- **Corner matrix run**: inherited verbatim from the source record — "
        "9 process corners × 4 temperatures (−40, **25**, 27, 125 °C) × 3 "
        "supplies (2.97/3.30/3.63 V) = 108 points, i.e. the full 81-point "
        "mandated grid plus the 25 °C trim-reference plane this derivation "
        "renormalises against.",
        "- **Statistical convention**: N/A — deterministic corners only "
        "(`sw_stat_mismatch=0`). `temp-accuracy-trimmed` is a `[3σ]` row, so "
        "this bounds its **systematic/corner share only**; the mismatch share "
        "is #15's Monte Carlo job and target-spec.md marks the row "
        "`conditional #15` for that reason.",
        "- **Result**:",
        "",
        "### `spec/target-spec.md#temp-accuracy-trimmed` — ±1.5 °C (stretch)",
        "",
        "Residual left by a *perfect* one-point 25 °C gain trim on each "
        "(corner, supply) group's own data — `T̂(T) = V(PTAT,T) / K₂₅` with "
        "`K₂₅ = V(PTAT,25 °C)/298.15 K` — plus the trim ladder's own half-LSB "
        "quantisation (`½ × 0.2423 % × T`, i.e. the ±0.35 °C "
        "`design/temp_core.md` quotes at the trim point, scaled per point). "
        "The two are summed in the worse direction. The 25 °C points "
        "themselves are omitted: their residual is 0 by construction.",
        "",
        "| process | supply (V) | T (°C) | K₂₅ (mV/K) | curvature (°C) | ½-LSB quant (°C) | trimmed error (°C) | status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in trimmed:
        if "corner_id" not in row:
            out.append(
                f"| `{row['process']}` | {row.get('supply', '—')} | — | — | — | — | — | {row['status']} |"
            )
            continue
        out.append(
            f"| `{row['process']}` | {row['supply']} | {row['temp_c']:g} | "
            f"{row['k25_mvk']:.6f} | {row['curvature_c']:+.4f} | "
            f"{row['quant_c']:.4f} | {row['trimmed_error_c']:+.4f} | {row['status']} |"
        )
    out.append("")
    if lo and hi:
        out.append(
            f"**Worst case: {lo['trimmed_error_c']:+.4f} °C (`{lo['corner_id']}`) … "
            f"{hi['trimmed_error_c']:+.4f} °C (`{hi['corner_id']}`)** against the "
            f"±{TARGET_TRIMMED_C} °C stretch — "
            f"{max(abs(lo['trimmed_error_c']), abs(hi['trimmed_error_c'])) / TARGET_TRIMMED_C * 100:.0f} % "
            f"of the budget consumed by the systematic + quantisation terms, "
            f"leaving the remainder for the mismatch share #15 owns."
        )
        out.append("")
    out.append(f"**{n_trim - n_trim_fail}/{n_trim} points within ±{TARGET_TRIMMED_C} °C.**")

    out += [
        "",
        "### `spec/target-spec.md#temp-vt-transfer` — published cross-point reductions",
        "",
        "| Quantity | Min | Max |",
        "|---|---|---|",
    ]
    labels = {
        "k25_mvk": "K₂₅ = V(PTAT)/298.15 K at 25 °C (mV/K)",
        "ctat_slope_mvc": "CTAT slope over −40…125 °C (mV/°C)",
        "ptat_range_v": "PTAT output range over the grid (V)",
        "ctat_range_v": "CTAT output range over the grid (V)",
        "ctat_27_v": "CTAT at 27 °C (V)",
    }
    for key, label in labels.items():
        span = vt.get(key)
        if not span:
            out.append(f"| {label} | — | — |")
            continue
        out.append(
            f"| {label} | {span['min']:.6g} (`{span['min_at']}`) | "
            f"{span['max']:.6g} (`{span['max_at']}`) |"
        )

    out += [
        "",
        "### `spec/target-spec.md#temp-supply-sensitivity` — strict full-window reading",
        "",
        "The source record checks each rail extreme against its own nominal-rail "
        "reference DUT at ±0.33 °C. This is the stricter reading of the same row: "
        "total peak-to-peak across the whole 2.97–3.63 V window at one (corner, "
        "temperature), against the same 0.33 °C figure (= 0.5 °C/V × 0.66 V).",
        "",
        "| process | T (°C) | supplies | peak-to-peak (°C) | min at | max at | status |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in supply:
        out.append(
            f"| `{row['process']}` | {row['temp_c']:g} | {row['n_supplies']} | "
            f"{row['pp_c']:.4f} | {row['lo_at']} V | {row['hi_at']} V | {row['status']} |"
        )
    out += [
        "",
        f"**{n_sup - n_sup_fail}/{n_sup} (corner, temperature) groups within "
        f"±{TARGET_SUPPLY_C} °C peak-to-peak.**",
        "",
        f"  - **Overall: {overall}**",
        "",
        "A miss in either table is recorded and owned, not relaxed to pass — "
        "CLAUDE.md and `spec/target-spec.md` §5, the same convention the "
        "already-owned `por-iq` overrun follows.",
        "",
        "- **Links**:",
        f"  - Source record: `sim/temp-accuracy-vt/records/{record_id}.md`",
        f"  - Raw logs derived from: `sim/temp-accuracy-vt/corners/{record_id}/`",
        "  - Derivation script: `sim/temp-accuracy-vt/analyze_derived.py`",
        "  - Testbench: `sim/temp-accuracy-vt/testbench/tb.json`, "
        "`sim/temp-accuracy-vt/testbench/tb_temp_accuracy_vt.spice`",
        f"- **Timestamp / author**: {when}, {author}",
        "- **Supersedes**: (none — first derived record for this claim; the "
        "design-intent curvature figure in `design/temp_core.md` came from "
        "`sim/temp-core-designer-check/`'s idealised-500 nA-source grid and is "
        "not a record this one replaces)",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive temp-accuracy-trimmed from a temp-accuracy-vt record."
    )
    parser.add_argument("record_id", help="the temp-accuracy-vt <record-id> to derive from")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write records/<record-id>-derived.md (default: print to stdout)",
    )
    add_author_arg(parser)
    args = parser.parse_args(argv)

    points = load_points(CORNERS_DIR, args.record_id)
    parsed = parse_corner_ids(points)
    if not parsed:
        print("no parseable corner-ids in that record", file=sys.stderr)
        return 2

    trimmed = derive_trimmed(points, parsed)
    vt = derive_vt(points, parsed)
    supply = derive_supply_window(points, parsed)

    when = now_iso()
    text = render(args.record_id, trimmed, vt, supply, when, args.author)

    if args.write:
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RECORDS_DIR / f"{args.record_id}-derived.md"
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
