#!/usr/bin/env python3
"""bias_core ramp-rate feedthrough coefficient, full PVT grid (issue #208).

    python3 sim/bias-core-designer-check/control/run_ramp_feedthrough.py [-j N]

`design/bias_core.md`'s "Ramp-rate feedthrough" note states the coefficient
of `VREF`'s displacement on a moving rail as a single number, **~2.4 us**
times the ramp rate, measured at `tt`/27 C via the `err_at_relv_mv` check in
`../testbench/tb.json`. Issue #208 was filed because a *different*
measurement -- `sim/por-vth/control/results.md` (issue #187/#218, DR-021),
taken on the full four-cell assembly at `ss`/-40 C -- found the same
mechanism running at **~49 us**, ~20x the quoted figure, at exactly the
corner where a nA-scale reference's node impedances are highest. Neither
measurement disputes the other's corner; the gap is that nothing had swept
the coefficient across the grid to see how it moves between them.

This control does that: bias_core ALONE (diode-loaded `IBIAS`, open `VREF`,
no `por_comparator`/output-chain downstream -- see `ramp_feedthrough.spice`),
driven by the same triangle-wave rail shape `sim/por-vth/control/
rate_ladder.spice` uses (0 -> 2.0 V pre-ramp, quasi-static ramp to `vdd_val`,
hold, quasi-static ramp back down), at the SAME two `tramp` values that
control's own ladder used at its two ends (4 ms and 16 ms), across the FULL
81-point PVT grid, on both the schematic and extracted netlists.

Choosing exactly those two `tramp` values is deliberate cross-checkability:
at `vdd_val` = 3.63 V they reproduce `sim/por-vth/control/results.md` Arm A's
own 407.5 V/s and 101.9 V/s rungs (`vdd_val - 2.0 = 1.63 V` over 4/16 ms), so
this control's `ss_-40c_3.63v` row can be checked directly against that
control's already-published +19.043/-20.756 mV (VREF error, up/down at
407.5 V/s) and its derived 49 us equivalent time constant -- a genuine
diagnosis this control's own grid can be judged against, not just a number
transcribed twice.

**Why the full 81-point grid, when `sim/README.md`'s "Control experiments"
convention scopes a control to "one or two points"**: issue #208's own
acceptance criteria require it -- the whole point being characterised is how
the coefficient VARIES across the grid, which a control that ran at one or
two points structurally cannot show. This stays a control and not a record
in every other respect: it makes no claim against a `spec/target-spec.md`
row (none exists for this coefficient), it is not gated behind
`sim/run_corners.py`, and re-running it overwrites `ramp_feedthrough_results.md`
and `results.json` rather than minting a new append-only record -- see
`sim/README.md`'s "Control experiments" section. The corner-grid EVIDENCE
this control produces lives in `decks/`/`logs/` (one deck+log per (netlist,
corner, tramp) point, 324 in total) and in `results.json`, both regenerated
on every run; `results.md` is prose generated from them, never edited by
hand.

At each (netlist, corner, tramp) point, ONE transient measures:

    vref_settle   V(VREF) during the flat top at `vdd_val`, the same
                  corner's own settled reference (t2 - 0.1 ms, matching
                  `rate_ladder.spice`'s own convention).
    vref_up       V(VREF) at V(VDD) = 2.50 V on the UP ramp (rise=1) --
                  identical sample point to `sim/por-vth/control/
                  rate_ladder.spice`'s "VREF error, up-ramp" column.
    vref_dn       V(VREF) at V(VDD) = 2.55 V on the DOWN ramp (fall=1) --
                  identical sample point to that control's "VREF error,
                  down-ramp" column.

`err_up_mv` / `err_dn_mv` are `(vref_up|dn - vref_settle) * 1e3`. Two
`tramp` points per corner give a rate (V/s) pair per direction; the earlier
control already demonstrated the displacement is proportional to rate
through the origin (intercept -0.097/-0.096 mV against tens-of-mV signals,
at `ss`/-40 C on both netlists) -- so the SECANT slope between this
control's two points is the coefficient, reported both as mV/(V/s) and as
an equivalent time constant in us (`slope_mV_per_Vps * 1000`, since
(mV/(V/s)) = (1e-3 V)/(V/s) = 1e-3 s = 1000 us... i.e. the same unit
identity `sim/por-vth/control/results.md` uses for its own 0.04861 mV/(V/s)
-> 49 us conversion).

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, cliutil, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FRAGMENT = CONTROL_DIR / "ramp_feedthrough.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

#: DUT id -> bias_core netlist path. Same two netlists
#: ../testbench/tb.json and ../testbench-postlayout/tb.json already run
#: designer-check against.
DUTS: dict[str, Path] = {
    "schematic": REPO_ROOT / "design" / "netlist" / "bias_core.spice",
    "postlayout": REPO_ROOT / "layout" / "postlayout" / "bias_core.spice",
}

#: (label, tramp seconds). Chosen to reproduce sim/por-vth/control/
#: rate_ladder.spice's own two end rungs at vdd_val = 3.63 V (407.5 and
#: 101.9 V/s) -- see module docstring.
TRAMPS_S: tuple[tuple[str, float], ...] = (
    ("t4ms", 4.0e-3),
    ("t16ms", 16.0e-3),
)

T_PRE_S = 1.0e-3
T_HOLD_S = 2.0e-3
T_TAIL_S = 1.0e-3

#: Fixed VDD sample points on the up/down ramp -- identical to
#: sim/por-vth/control/rate_ladder.spice's own "VREF error" columns, chosen
#: there to be clear of every POR threshold on its ladder. Both are below
#: the smallest vdd_val on this grid (2.97 V) and above bias_core's own
#: worst-case dropout (vdd_ref90_v <= 1.788 V, design/bias_core.md), so both
#: crossings occur on every corner/supply point.
VDD_SAMPLE_UP_V = 2.50
VDD_SAMPLE_DN_V = 2.55


def times(tramp: float) -> tuple[float, float, float, float]:
    """(t1, t2, t3, t4) -- ramp-up end, hold end, ramp-down end, tail end."""
    t1 = T_PRE_S + tramp
    t2 = t1 + T_HOLD_S
    t3 = t2 + tramp
    t4 = t3 + T_TAIL_S
    return t1, t2, t3, t4


def compose(pdk, options: list[str], dut: str, point, tramp: float) -> str:
    netlist = DUTS[dut]
    deck_dir = CONTROL_DIR / "decks"
    t1, t2, t3, t4 = times(tramp)
    lines = [
        f"* bias_core ramp-feedthrough control -- {dut} @ {point.corner_id},"
        f" tramp={tramp * 1e3:g} ms -- GENERATED by run_ramp_feedthrough.py,"
        " do not edit",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        ".param vdd_nom=3.3",
        f".param vdd_val={point.vdd!r}",
        f".param temp_c={point.temp_c!r}",
        f".param tramp={tramp!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, point.corner, point.temp_c, options)
    lines += [
        "",
        f'.include "{os.path.relpath(FRAGMENT, deck_dir)}"',
        f'.include "{os.path.relpath(netlist, deck_dir)}"',
        "",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        f"tran 5u {t4!r}",
        f"meas tran vref_settle find v(vref) at={t2 - 0.1e-3!r}",
        "meas tran vref_up find v(vref) when v(vdd)=2.50 rise=1",
        "meas tran vref_dn find v(vref) when v(vdd)=2.55 fall=1",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def _points(grid) -> list[tuple[str, str, object, float]]:
    """(run_id, dut, PvtPoint, tramp_s) for every (netlist, corner, tramp)."""
    pts: list[tuple[str, str, object, float]] = []
    for dut in DUTS:
        for point in grid:
            for label, tramp in TRAMPS_S:
                pts.append((f"ft_{dut}_{point.corner_id}_{label}", dut, point, tramp))
    return pts


def run_one(pdk, options: list[str], item: tuple[str, str, object, float]) -> dict:
    run_id, dut, point, tramp = item
    deck = compose(pdk, options, dut, point, tramp)
    meas = runner.run_deck(run_id, deck, CONTROL_DIR)
    row = {
        "run": run_id,
        "dut": dut,
        "corner_id": point.corner_id,
        "corner": point.corner.name,
        "temp_c": point.temp_c,
        "vdd_v": point.vdd,
        "tramp_ms": tramp * 1e3,
        "rate_v_per_s": (point.vdd - 2.0) / tramp,
    }
    row.update(meas)
    if {"vref_settle", "vref_up", "vref_dn"} <= row.keys():
        row["err_up_mv"] = (row["vref_up"] - row["vref_settle"]) * 1e3
        row["err_dn_mv"] = (row["vref_dn"] - row["vref_settle"]) * 1e3
    return row


def _coeffs(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """(dut, corner_id) -> {rate1, rate2, err_up1, err_up2, coeff_up_us, ...}"""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if "err_up_mv" not in row:
            continue
        by_key.setdefault((row["dut"], row["corner_id"]), []).append(row)

    out: dict[tuple[str, str], dict] = {}
    for key, group in by_key.items():
        if len(group) != 2:
            continue
        a, b = sorted(group, key=lambda r: r["rate_v_per_s"])
        d_rate = b["rate_v_per_s"] - a["rate_v_per_s"]
        slope_up = (b["err_up_mv"] - a["err_up_mv"]) / d_rate
        slope_dn = (b["err_dn_mv"] - a["err_dn_mv"]) / d_rate
        out[key] = {
            "dut": a["dut"],
            "corner_id": a["corner_id"],
            "corner": a["corner"],
            "temp_c": a["temp_c"],
            "vdd_v": a["vdd_v"],
            "rate1_v_per_s": a["rate_v_per_s"],
            "rate2_v_per_s": b["rate_v_per_s"],
            "err_up1_mv": a["err_up_mv"],
            "err_up2_mv": b["err_up_mv"],
            "err_dn1_mv": a["err_dn_mv"],
            "err_dn2_mv": b["err_dn_mv"],
            "coeff_up_mv_per_vps": slope_up,
            "coeff_dn_mv_per_vps": slope_dn,
            "tau_up_us": slope_up * 1000.0,
            "tau_dn_us": slope_dn * 1000.0,
            "vref_settled_v": b["vref_settle"],
        }
    return out


def render(coeffs: dict[tuple[str, str], dict], pdk, options: list[str]) -> str:
    by_dut: dict[str, list[dict]] = {}
    for (dut, _corner_id), row in coeffs.items():
        by_dut.setdefault(dut, []).append(row)

    out: list[str] = [
        "# `bias_core` ramp-rate feedthrough coefficient — full-grid control results",
        "",
        "**Generated by `run_ramp_feedthrough.py`. Do not edit — re-run it.**",
        "Every number below is read out of `logs/` by that script; nothing here",
        "is transcribed by hand. This is a SECOND control under this",
        "directory (`sim/README.md`'s \"one `control/` may hold more than one",
        "control\" rule) — `run_starved_window.py`'s `results.md` diagnoses the",
        "brownout-recovery window; this one diagnoses the ramp-rate feedthrough",
        "coefficient `design/bias_core.md`'s \"Ramp-rate feedthrough\" note",
        "quotes. Its own `decks/`/`logs/` filenames are `ft_`-prefixed so they",
        "never collide with that script's outputs in this shared directory.",
        "",
        f"- PDK: `{pdk.variant}` @ `{pdk.version}`",
        f"- Harness version: `{HARNESS_VERSION}`",
        "- Solver options (from `../testbench/tb.json`): "
        + ", ".join(f"`{o}`" for o in options),
        "- DUT netlists: `design/netlist/bias_core.spice` (schematic),"
        " `layout/postlayout/bias_core.spice` (extracted)",
        "- Corner grid: the full 81-point PVT grid (9 process corners x"
        " 3 temperatures x 3 supplies), per `sim/README.md` -- a deliberate"
        " widening of the \"control\" convention's usual one/two-point scope;"
        " see this script's own module docstring for why.",
        "- `tramp` values: 4 ms and 16 ms -- chosen to reproduce"
        " `sim/por-vth/control/results.md` Arm A's own 407.5 / 101.9 V/s"
        " rungs at `vdd_val` = 3.63 V, for direct cross-check.",
        "- Motivating measurement: `design/bias_core.md`'s \"Ramp-rate"
        " feedthrough\" note (**~2.4 us** x rate, at `tt`/27C) vs."
        " `sim/por-vth/control/results.md`'s **~49 us** at `ss`/-40C"
        " (issue #208).",
        "",
        "## What the columns are",
        "",
        "Two `tramp` points per (netlist, corner) give a rate (V/s) pair per"
        " direction. `sim/por-vth/control/results.md` already demonstrated the"
        " displacement is proportional to rate through the origin (intercept"
        " -0.097/-0.096 mV against tens-of-mV signals, at `ss`/-40C on both"
        " netlists) -- so the SECANT slope between this control's two points"
        " is the coefficient, reported as an equivalent time constant in us"
        " (`slope_mV_per_(V/s) * 1000`), matching that control's own unit"
        " convention (0.04861 mV/(V/s) -> 49 us).",
        "",
    ]

    for dut in ("schematic", "postlayout"):
        rows = by_dut.get(dut, [])
        if not rows:
            continue
        tau_up = [r["tau_up_us"] for r in rows]
        tau_dn = [r["tau_dn_us"] for r in rows]
        worst_up = max(rows, key=lambda r: r["tau_up_us"])
        worst_dn = min(rows, key=lambda r: r["tau_dn_us"])
        best_up = min(rows, key=lambda r: r["tau_up_us"])
        out += [
            f"## {dut} — {len(rows)}/81 corners",
            "",
            f"- Up-ramp coefficient: **{min(tau_up):.2f} … {max(tau_up):.2f} us**"
            f" (worst: `{worst_up['corner_id']}` at {max(tau_up):.2f} us,"
            f" best: `{best_up['corner_id']}` at {min(tau_up):.2f} us)",
            f"- Down-ramp coefficient magnitude:"
            f" **{min(abs(v) for v in tau_dn):.2f} … {max(abs(v) for v in tau_dn):.2f} us**"
            f" (worst: `{worst_dn['corner_id']}` at {worst_dn['tau_dn_us']:.2f} us)",
            "",
            "| corner | temp (C) | VDD (V) | tau_up (us) | tau_dn (us)"
            " | VREF settled (V) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in sorted(rows, key=lambda r: (r["corner"], r["temp_c"], r["vdd_v"])):
            out.append(
                f"| `{r['corner_id']}` | {r['temp_c']:g} | {r['vdd_v']:.2f} |"
                f" {r['tau_up_us']:.2f} | {r['tau_dn_us']:.2f} |"
                f" {r['vref_settled_v']:.6f} |"
            )
        out.append("")

    # Cross-check against sim/por-vth/control/results.md's own ss/-40c/3.63v
    # point (its "49 us" headline number).
    ss_rows = {
        dut: coeffs.get((dut, "ss_-40c_3.63v"))
        for dut in ("schematic", "postlayout")
    }
    if all(ss_rows.values()):
        out += [
            "## Cross-check against `sim/por-vth/control/results.md`",
            "",
            "That control measured bias_core's own displacement indirectly,",
            "through the full four-cell assembly, at ONE corner"
            " (`ss`/-40C/3.63V), at rates 407.5 and 101.9 V/s among others",
            " -- exactly this control's two `tramp` rungs at that supply.",
            " Both controls should read the same coefficient at that shared",
            " point, to within run-to-run/precision noise:",
            "",
            "| netlist | this control (tau_up / tau_dn, us) |"
            " `por-vth` control (~49 us, both directions) |",
            "|---|---:|---:|",
        ]
        for dut in ("schematic", "postlayout"):
            r = ss_rows[dut]
            out.append(
                f"| {dut} | {r['tau_up_us']:.2f} / {r['tau_dn_us']:.2f} | ~49 |"
            )
        out.append("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-j", "--jobs", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    manifest = cliutil.load_manifest(MANIFEST)
    options = manifest["options"]
    corners = corners_mod.resolve_corners(["full"])
    supplies = corners_mod.supply_points(manifest["nominal_supply_v"], manifest["supply_tolerance"])
    grid = corners_mod.build_grid(corners, manifest["temperatures_c"], supplies)

    (CONTROL_DIR / "decks").mkdir(exist_ok=True)
    (CONTROL_DIR / "logs").mkdir(exist_ok=True)
    # #216: force single-threaded ngspice. run_deck() (unlike run_point())
    # does not do this on its own -- a nested per-process OpenMP team sized
    # to the host's core count fights this script's own -j process-level
    # parallelism, measured 22x slower on an 8-core host. One .spiceinit in
    # the shared decks/ cwd covers every parallel point.
    runner.write_run_spiceinit(CONTROL_DIR / "decks")

    points = _points(grid)
    jobs = args.jobs or cliutil.default_jobs()
    print(f"running {len(points)} points ({len(grid)} corners x {len(DUTS)} nets x"
          f" {len(TRAMPS_S)} tramps) at -j {jobs} ...")
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(lambda item: run_one(pdk, options, item), points))

    missing = [r["run"] for r in rows if "err_up_mv" not in r]
    if missing:
        print(f"missing measurements for {len(missing)} point(s), e.g. {missing[:5]}", file=sys.stderr)
        return 2

    coeffs = _coeffs(rows)
    expected = len(DUTS) * len(grid)
    if len(coeffs) != expected:
        print(
            f"expected {expected} (netlist, corner) coefficient points, got {len(coeffs)}",
            file=sys.stderr,
        )
        return 2

    (CONTROL_DIR / "results.json").write_text(
        json.dumps({"raw": rows, "coefficients": list(coeffs.values())}, indent=2) + "\n"
    )
    body = render(coeffs, pdk, options)
    (CONTROL_DIR / "ramp_feedthrough_results.md").write_text(body)
    print(f"wrote {(CONTROL_DIR / 'ramp_feedthrough_results.md').relative_to(REPO_ROOT)}")
    print(f"wrote {(CONTROL_DIR / 'results.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
