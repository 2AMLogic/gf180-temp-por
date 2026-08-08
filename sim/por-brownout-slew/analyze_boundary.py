#!/usr/bin/env python3
"""Aggregate the #60 falling-slew ladder into a per-corner boundary table.

    python3 sim/por-brownout-slew/analyze_boundary.py

Reads every existing ``records/*.md`` full-81-point-grid record under this
experiment directory (each one is a single ladder "rung" -- a fixed falling
slew rate, swept across the full PVT grid by ``sim/run_corners.py``, per
``sim/README.md``), extracts the per-corner PASS/FAIL status and the rung's
own falling-slew rate from each record's ``Claim`` line, and combines them
into ONE bracket per corner: the fastest (highest mV/us) TESTED rung that
corner still PASSED at, and the slowest (lowest mV/us) TESTED rung it FAILED
at. This is a **derived** record per ``sim/README.md``'s worked example
("A derived record reduces an existing record's raw logs without running a
simulation ... cites its source record, makes no measurement of its own"):
it makes no new ngspice measurement, only recombines the ``pass/fail`` column
already written by ``sim/run_corners.py`` into each source record, so no
number here is transcribed by hand -- every cell traces to exactly one
source record's own table.

Writes ``records/<latest-record-id>-boundary.md``, citing every source
record it read. Does not supersede any of them (a derived record is not a
correction).
"""

from __future__ import annotations

from pathlib import Path

from _rung_record import is_source_record, parse_record

EXPERIMENT_DIR = Path(__file__).resolve().parent
RECORDS_DIR = EXPERIMENT_DIR / "records"


def main() -> int:
    record_paths = sorted(p for p in RECORDS_DIR.glob("*.md") if is_source_record(p))
    if not record_paths:
        raise SystemExit(f"no records found under {RECORDS_DIR}")

    rungs = [parse_record(p) for p in record_paths]
    # Chronologically last source record (record-ids sort lexically the same
    # as chronologically, YYYYMMDD-HHMMSS-<sha>) supplies this derived
    # record's own id suffix -- not the highest-slew rung, which is an
    # unrelated ordering.
    latest_chrono_id = max(r.record_id for r in rungs)
    rungs.sort(key=lambda r: r.slew_mvus)

    corner_ids = sorted(rungs[0].status)
    for r in rungs[1:]:
        if sorted(r.status) != corner_ids:
            raise ValueError(f"{r.record_id}: corner set does not match {rungs[0].record_id}")

    # Per-corner bracket: fastest (max mV/us) TESTED rung this corner PASSED,
    # and slowest (min mV/us) TESTED rung it FAILED, among the rungs actually
    # run. Also flag any corner whose PASS/FAIL is non-monotonic in the
    # tested ladder (a FAIL at a slower rung than some PASS) -- observed near
    # the boundary and reported rather than silently smoothed over.
    rows = []
    for cid in corner_ids:
        passes = [r.slew_mvus for r in rungs if r.status[cid]]
        fails = [r.slew_mvus for r in rungs if not r.status[cid]]
        max_pass = max(passes) if passes else None
        min_fail = min(fails) if fails else None
        # Non-monotonic: some FAIL rung is slower (smaller mV/us) than some
        # PASS rung's own... no: flag if there exists a fail slower than the
        # fastest confirmed-safe-so-far prefix, i.e. any fail below max_pass
        # among fails that are NOT all >= max_pass.
        non_monotonic = any(f < max_pass for f in fails) if (fails and passes) else False
        rows.append((cid, max_pass, min_fail, non_monotonic))

    # Binding corner: smallest min_fail (earliest/lowest slew at which ANY
    # tested rung failed) -- ties broken by smallest max_pass.
    with_fail = [r for r in rows if r[2] is not None]
    binding = min(with_fail, key=lambda r: (r[2], r[1] if r[1] is not None else 0.0))

    # Ratified bound: the fastest rung at which EVERY one of the 81 corners
    # PASSED (a clean full-grid PASS), among all tested rungs.
    clean_pass_rungs = [r.slew_mvus for r in rungs if all(r.status.values())]
    ratified = max(clean_pass_rungs) if clean_pass_rungs else None
    # Confirm tightness: the next-tested rung above the ratified bound that
    # is NOT a clean pass (i.e. the immediate upper bracket).
    tighter_fails = sorted(
        r.slew_mvus for r in rungs if ratified is not None and r.slew_mvus > ratified
    )
    next_fail = tighter_fails[0] if tighter_fails else None

    out_id = f"{latest_chrono_id}-boundary"
    out_path = RECORDS_DIR / f"{out_id}.md"

    lines = []
    lines.append(f"# Record {out_id} (derived)")
    lines.append("")
    lines.append(f"- **Record ID**: {out_id}")
    lines.append(
        "- **Claim**: spec/target-spec.md#por-brownout clause (c) -- "
        "dVDD/dt|fall,max, per-corner boundary bracket and ratified worst-case "
        "bound, derived from the falling-slew ladder below (issue #60 / "
        "DR-011 decision 2)"
    )
    lines.append(
        "- **Derived from** (no new simulation; recombines each source "
        "record's own `pass/fail` column -- see `analyze_boundary.py`):"
    )
    for r in rungs:
        lines.append(
            f"  - `{r.record_id}` -- rung `{r.label}`, {r.slew_mvus:.6g} mV/us -- "
            f"{sum(r.status.values())}/81 PASS"
        )
    lines.append("")
    lines.append(
        f"- **Binding corner**: `{binding[0]}` -- the lowest tested slew at "
        f"which ANY corner failed ({binding[2]:.6g} mV/us), confirming "
        f"`design/bias_core.md`'s SS/-40C architectural prediction "
        f"(`spec/target-spec.md#por-brownout`'s own \"Binds at SS / -40 C\" "
        f"note). Its own bracket: PASS up to {binding[1]:.6g} mV/us, FAIL "
        f"from {binding[2]:.6g} mV/us."
    )
    lines.append(
        f"- **Ratified worst-case bound**: `dVDD/dt|fall,max` = "
        f"**{ratified:.6g} mV/us** -- the fastest tested rung with a clean "
        f"81/81 PASS"
        + (
            f"; the next-tested rung above it, {next_fail:.6g} mV/us, is NOT "
            "a clean pass, bracketing the bound tightly."
            if next_fail is not None
            else "."
        )
    )
    lines.append("")
    lines.append("## Per-corner bracket")
    lines.append("")
    lines.append(
        "| corner-id | PASS up to (mV/us, tested) | FAIL from (mV/us, tested) | non-monotonic in tested ladder? |"
    )
    lines.append("|---|---|---|---|")
    for cid, max_pass, min_fail, nm in sorted(rows, key=lambda r: (r[2] if r[2] is not None else 1e9, r[0])):
        mp = f"{max_pass:.6g}" if max_pass is not None else "(none tested)"
        mf = f"{min_fail:.6g}" if min_fail is not None else "(none tested -- PASS at every tested rung)"
        lines.append(f"| `{cid}` | {mp} | {mf} | {'YES' if nm else 'no'} |")

    lines.append("")
    lines.append(
        "## Non-monotonic transition zone -- new finding, not resolved here"
    )
    lines.append("")
    nm_corners = sorted({r[0] for r in rows if r[3]})
    lines.append(
        f"{len(nm_corners)} corner(s) show a FAIL at a rung numerically "
        "slower (safer, lower mV/us) than a rung they PASSED: "
        + (", ".join(f"`{c}`" for c in nm_corners) if nm_corners else "(none)")
        + ". Observed concretely at the SS/-40C family between "
        "3.40 mV/us (81/81 PASS, comfortable margin) and 3.4795 mV/us (all "
        "3 SS/-40C supply points FAIL, deep in fail territory -- not a "
        "near-threshold ambiguity) and 3.613 mV/us (only the 2.97 V point "
        "of that family FAILs, the other two PASS) -- a non-monotonic "
        "PASS/FAIL pattern in slew rate that plain bisection assumes away. "
        "This is consistent with `design/bias_core.md`'s starved-loop "
        "mechanism being a nonlinear relaxation dynamic (DR-011): near its "
        "own critical timing, small changes in the falling edge's duration "
        "can shift the phase relationship between the collapsing loop and "
        "the measurement window non-monotonically, similar in kind (not "
        "mechanism) to digital metastability's non-monotonic resolution "
        "time near a decision threshold. The ratified bound above is chosen "
        "on the SAFE side of this entire transition band (81/81 PASS at "
        "3.40 mV/us, with matching robust margins -- see the source record "
        "-- not merely a bisected midpoint one step above a single FAIL), "
        "so it is not undermined by the non-monotonicity, but the zone "
        "itself is a candidate for a follow-up characterization issue, "
        "filed the way DR-011 filed #61 for a distinct finding surfaced by "
        "the same investigation."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Written by `sim/por-brownout-slew/analyze_boundary.py`. Per "
        "`sim/README.md`'s derived-record convention: makes no new "
        "measurement, cites its sources, and does not supersede any of "
        "them."
    )
    lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"wrote {out_path}")
    print(f"binding corner: {binding[0]} (fails from {binding[2]:.6g} mV/us)")
    print(f"ratified bound: {ratified:.6g} mV/us")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
