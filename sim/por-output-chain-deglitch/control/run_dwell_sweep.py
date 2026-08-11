#!/usr/bin/env python3
"""Qualifying-dip DWELL sweep for sim/por-output-chain-deglitch/ (issue #251).

    python3 sim/por-output-chain-deglitch/control/run_dwell_sweep.py

Pins the exact `T_dip,min(new)` that
[DR-027](../../../spec/decision-records/DR-027-por-brownout-tdip-recost.md)
section 5 requires to be **measured, not extrapolated**.

WHY THIS EXISTS

`../testbench/stimulus.spice` applies a qualifying brownout dip on `POR_RAW`
of exactly `T_dip,min` and asserts that the deglitch filter output `PGDG`
reaches its 1.0 V trip inside that window. Since #221 re-cut the stress DUT's
bias to the current the assembly really delivers (91.0251 nA, DR-024), it
does not: at most of the 81 PVT points `NDG` is still charging toward the
inverter threshold when the 10 us window closes, so a crossing-time `.meas`
errors out of its search interval rather than reporting a number. DR-027 says
the fix is a longer `T_dip,min` and estimates 25-30 us from a `t = C*dV/I`
scaling argument; section 5 requires the actual number.

WHAT IS MEASURED, AND WHY IT IS THE RIGHT QUANTITY

Nothing in the filter depends on when the dip ENDS -- only on how long
`POR_RAW` has been low. So the minimum qualifying-dip duration at a PVT point
is exactly the `PGDG` crossing time under a dip long enough to contain it,
and one long-dip run per point measures it at full resolution instead of
bracketing it between ladder rungs. **Part A** does that at every one of the
81 points, for both netlist levels, at the stress bias and at the DR-005
nominal bias (so the 1/IBIAS scaling DR-027 section 3 argues from is
measured here rather than assumed).

**Part B** then re-runs a ladder of FINITE dip widths at the slowest points
Part A found, applying the parent testbench's own check (`PGDG` reaches
1.0 V within the dip window itself) at each width. Its job is to confirm the
equivalence the paragraph above asserts: the pass/fail flip must land on the
crossing time Part A measured. If it did not, Part A's number would not be a
`T_dip,min`.

**Part C** is the contingency DR-027 section 5 names: a point whose `NDG`
asymptotes BELOW the trip point never trips at any dwell, and re-costing
`T_dip,min` would not help it. Part A's long dip is 20x the DR-027 estimate,
so a point that has not crossed by the end of it is reported as **never**,
with the `PGDG` floor it settled at, rather than being rounded into the
worst-case crossing time.

THE RULE FOR T_dip,min(new), FIXED BEFORE THE SWEEP RAN

    T_dip,min(new) = the smallest multiple of TDIP_QUANTUM_US that is at
                     least MARGIN x the slowest crossing time measured at
                     the stress bias, over both netlist levels and all 81
                     points.

It is written down here, in the script that computes it, so that the reported
value is a function of the measurement rather than a number chosen after
seeing it. The parent grid re-run at `T_dip,min(new)` passes 81/81 for any
sufficiently large choice, so the grid alone cannot distinguish a measured
bound from an inflated one -- this rule, plus the worst-corner crossing time
and the realized margin printed beside it in `dwell_results.md`, is what
makes the difference checkable.

Writes:

    decks/d_<variant>__<bias>__<point>[__<width>].spice  the exact deck as run
    decks/dut_<variant>.spice                            the DUT netlist it includes
    logs/d_<variant>__<bias>__<point>[__<width>].log     raw ngspice output, verbatim
    dwell_results.md                                     the sweep tables

This is a **control experiment, not a record** -- it overwrites its own
outputs in place on every run (see ``sim/README.md``, "Control experiments").
It deliberately covers the full 81-point grid, which most controls do not,
because the quantity it is looking for is a worst-CORNER one; the append-only
corner-grid evidence for
[`por-brownout`](../../../spec/target-spec.md#por-brownout) is still the
records the parent testbench mints at the value pinned here, not this file.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FRAGMENT = CONTROL_DIR / "dwell_sweep.spice"
SCHEMATIC_NETLIST = REPO_ROOT / "design" / "netlist" / "por_output_chain.spice"
POSTLAYOUT_NETLIST = REPO_ROOT / "layout" / "postlayout" / "por_output_chain.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

VARIANTS = [
    ("schematic", SCHEMATIC_NETLIST),
    ("postlayout", POSTLAYOUT_NETLIST),
]

# The two bias arms. "stress" is the current sim/por-output-chain-ibias-sharing/
# measures the assembly actually delivering to this cell's IBIAS pin
# (91.0251 nA, post-layout record 20260811-142901-d43c0db) and is the arm
# T_dip,min(new) is pinned from. "nominal" is DR-005's 500 nA, carried so the
# 1/IBIAS scaling DR-027 section 3 argues from is measured, not assumed.
BIASES = [("stress", 91.0251e-9), ("nominal", 500e-9)]
PIN_BIAS = "stress"

TRIP_V = 1.0  # the PGDG trip point the parent testbench's check is written on
EDGE_S = 0.1e-6  # POR_RAW edge rate, same as ../testbench/stimulus.spice
T_DIP_S = 2.0e-3  # dip starts here; POR_RAW has been high since 300.1 us
SETTLE_MIN_S = 1.5e-3  # required POR_RAW-high time before the dip (asserted below)

# Part A's dip is open-ended: 600 us is ~20x DR-027 section 3's 25-30 us
# estimate, so a point that has not tripped by the end of it is reported as
# **never** (Part C) rather than as a very slow crossing.
PROBE_DIP_S = 600e-6

# Part B's finite widths, in microseconds -- the parent testbench's own check
# re-applied at each. 10 us is the outgoing T_dip,min.
LADDER_WIDTHS_US = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0]
LADDER_POINTS_PER_VARIANT = 3  # the slowest points Part A found

# --- the T_dip,min(new) rule, fixed before the sweep ran ---------------------
MARGIN = 1.10  # at least 10 % above the slowest measured crossing
TDIP_QUANTUM_US = 5.0  # rounded up to a multiple of this


def pin_tdip_us(worst_us: float) -> float:
    """T_dip,min(new) from the slowest measured crossing time. See the module
    docstring: this rule is the whole defence against an inflated bound."""
    return math.ceil(worst_us * MARGIN / TDIP_QUANTUM_US) * TDIP_QUANTUM_US


def grid_points(temps, supplies) -> list[tuple[str, str, float, float]]:
    """The parent testbench's own 81-point grid, in its own corner order."""
    points: list[tuple[str, str, float, float]] = []
    for corner_name in corners_mod.CORNER_SETS["full"]:
        for temp_c in temps:
            for vdd in supplies:
                point_id = f"{corner_name}_{temp_c:g}c_{vdd:.2f}v"
                points.append((point_id, corner_name, float(temp_c), float(vdd)))
    return points


def compose_deck(
    pdk,
    variant: str,
    corner_name: str,
    temp_c: float,
    vdd: float,
    ibias_a: float,
    dip_s: float,
    options: list[str],
    deck_dir: Path,
) -> str:
    corner = corners_mod.CORNERS[corner_name]
    fragment_rel = os.path.relpath(FRAGMENT, deck_dir)
    t_lo = T_DIP_S - EDGE_S
    t_hi = T_DIP_S
    t_end = T_DIP_S + dip_s
    t_up = t_end + EDGE_S
    stop_s = t_up + 20e-6
    lines = [
        f"* por-output-chain-deglitch dwell sweep -- {variant} @ {corner_name} /"
        f" {temp_c:g} C / {vdd:g} V, IBIAS {ibias_a * 1e9:g} nA,"
        f" {dip_s * 1e6:g} us dip"
        " -- GENERATED by run_dwell_sweep.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        f".param vdd_val={vdd!r}",
        f".param ibias_a={ibias_a!r}",
        f".param t_dip_lo={t_lo!r}",
        f".param t_dip_hi={t_hi!r}",
        f".param t_dip_end={t_end!r}",
        f".param t_dip_up={t_up!r}",
        f".param stop_s={stop_s!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, temp_c, options)
    lines += [
        "",
        f'.include "{fragment_rel}"',
        f'.include "dut_{variant}.spice"',
        "",
        f".tran {2e-6!r} {{stop_s}}",
        "",
        # the initial condition: PGDG must be settled at the rail before the
        # dip, or the crossing time below is measuring the tail of the
        # previous transition rather than the dwell
        f".meas tran pgdg_pre find v(xdut.pgdg) at={T_DIP_S - 1e-6!r}",
        f".meas tran ndg_pre find v(xdut.ndg) at={T_DIP_S - 1e-6!r}",
        # THE measurement: how long POR_RAW has to stay low before the filter
        # output reaches its trip point. Absent from the log => never tripped.
        f".meas tran t_trip when v(xdut.pgdg)={TRIP_V!r} fall=1 td={t_hi!r}",
        # the parent testbench's own check, re-applied over this dip window
        f".meas tran pgdg_min min v(xdut.pgdg) from={t_hi!r} to={t_end!r}",
        f".meas tran ndg_max max v(xdut.ndg) from={t_hi!r} to={t_end!r}",
        f".meas tran pgdg_end find v(xdut.pgdg) at={t_end!r}",
        "",
        ".end",
        "",
    ]
    return "\n".join(lines)


def run_all(jobs: list[tuple[str, str]], workers: int) -> dict[str, dict[str, float]]:
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as pool:
        return dict(
            zip(
                [name for name, _ in jobs],
                pool.map(lambda job: runner.run_deck(*job, CONTROL_DIR), jobs),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
        help="parallel ngspice runs (default: half the host's logical cores)",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="two PVT points and the schematic netlist only -- for checking the "
             "deck composes and runs, NOT for pinning a value",
    )
    args = parser.parse_args()

    try:
        pdk = find_pdk()
        ngspice_version = runner.ngspice_version()
    except (PdkNotFound, runner.NgspiceMissing) as exc:
        print(exc, file=sys.stderr)
        return 3

    assert T_DIP_S - 300.1e-6 >= SETTLE_MIN_S, "dip starts before the filter can settle"

    manifest = json.loads(MANIFEST.read_text())
    options = list(manifest.get("options", []))
    nominal = float(manifest["nominal_supply_v"])
    tol = float(manifest["supply_tolerance"])
    supplies = [
        round(nominal * (1 - tol), 2), round(nominal, 2), round(nominal * (1 + tol), 2)
    ]
    points = grid_points(manifest["temperatures_c"], supplies)

    variants = VARIANTS
    if args.smoke:
        variants = VARIANTS[:1]
        points = [p for p in points if p[0] in ("ss_-40c_2.97v", "ff_125c_3.63v")]

    deck_dir = CONTROL_DIR / "decks"
    (CONTROL_DIR / "logs").mkdir(exist_ok=True)
    deck_dir.mkdir(exist_ok=True)
    for variant, path in variants:
        (deck_dir / f"dut_{variant}.spice").write_text(path.read_text())

    # ---- Part A: crossing time, full grid, both netlists, both bias arms ----
    jobs: list[tuple[str, str]] = []
    for variant, _ in variants:
        for bias_label, ibias_a in BIASES:
            for point_id, corner_name, temp_c, vdd in points:
                jobs.append((
                    f"d_{variant}__{bias_label}__{point_id}",
                    compose_deck(pdk, variant, corner_name, temp_c, vdd, ibias_a,
                                 PROBE_DIP_S, options, deck_dir),
                ))
    print(f"Part A: {len(jobs)} decks ({PROBE_DIP_S * 1e6:g} us probe dip) ...")
    probe = run_all(jobs, args.jobs)

    def crossing_us(variant: str, bias_label: str, point_id: str) -> float | None:
        meas = probe.get(f"d_{variant}__{bias_label}__{point_id}", {})
        t = meas.get("t_trip")
        return None if t is None else (t - T_DIP_S) * 1e6

    worst_us = 0.0
    never: list[tuple[str, str]] = []
    for variant, _ in variants:
        for point_id, *_ in points:
            us = crossing_us(variant, PIN_BIAS, point_id)
            if us is None:
                never.append((variant, point_id))
            else:
                worst_us = max(worst_us, us)
    tdip_us = pin_tdip_us(worst_us)
    print(f"  slowest crossing at the {PIN_BIAS} bias: {worst_us:.3f} us"
          f" -> T_dip,min(new) = {tdip_us:g} us")
    if never:
        print(f"  !! {len(never)} point(s) never tripped inside"
              f" {PROBE_DIP_S * 1e6:g} us: {never}", file=sys.stderr)

    # ---- Part B: finite-width ladder at the slowest points ------------------
    ladder_points: list[tuple[str, str]] = []
    for variant, _ in variants:
        ranked = sorted(
            (p for p in points if crossing_us(variant, PIN_BIAS, p[0]) is not None),
            key=lambda p: crossing_us(variant, PIN_BIAS, p[0]),
            reverse=True,
        )
        ladder_points += [(variant, p[0]) for p in ranked[:LADDER_POINTS_PER_VARIANT]]

    by_id = {p[0]: p for p in points}
    ibias_pin = dict(BIASES)[PIN_BIAS]
    jobs = []
    for variant, point_id in ladder_points:
        _, corner_name, temp_c, vdd = by_id[point_id]
        for width_us in LADDER_WIDTHS_US:
            jobs.append((
                f"d_{variant}__{PIN_BIAS}__{point_id}__{width_us:g}us",
                compose_deck(pdk, variant, corner_name, temp_c, vdd, ibias_pin,
                             width_us * 1e-6, options, deck_dir),
            ))
    print(f"Part B: {len(jobs)} decks (finite-width ladder) ...")
    ladder = run_all(jobs, args.jobs)

    write_results(pdk, ngspice_version, variants, points, probe, ladder,
                  ladder_points, worst_us, tdip_us, never, args.smoke)
    print(f"wrote {(CONTROL_DIR / 'dwell_results.md').relative_to(REPO_ROOT)}")
    return 0


def write_results(pdk, ngspice_version, variants, points, probe, ladder,
                  ladder_points, worst_us, tdip_us, never, smoke) -> None:
    def meas(name: str, key: str):
        return probe.get(name, {}).get(key)

    def crossing_us(variant, bias_label, point_id):
        t = meas(f"d_{variant}__{bias_label}__{point_id}", "t_trip")
        return None if t is None else (t - T_DIP_S) * 1e6

    lines: list[str] = [
        "# por-output-chain-deglitch qualifying-dip dwell sweep"
        " — generated, do not edit",
        "",
        "Generated by `sim/por-output-chain-deglitch/control/run_dwell_sweep.py`"
        " (issue #251). Re-run it to regenerate this file, the decks under"
        " `decks/` and the raw ngspice logs under `logs/`. Every number quoted"
        " elsewhere for this sweep — the record minted at the value pinned"
        " below, `spec/target-spec.md#por-brownout`, DR-027 — is transcribed"
        " from here, and from nowhere else.",
        "",
        "This is a **control experiment, not a record**: it is overwritten in"
        " place on every run, and it substantiates no spec row on its own. The"
        " append-only corner-grid evidence for"
        " [`por-brownout`](../../../spec/target-spec.md#por-brownout) is the"
        " record `sim/por-output-chain-deglitch/` mints at the value pinned"
        " here (`sim/README.md`, \"Control experiments\"). It covers the full"
        " 81-point grid, which most controls do not, because the quantity it"
        " looks for is a worst-**corner** one.",
        "",
        f"- ngspice: `{ngspice_version}`",
        f"- PDK: `{pdk.variant}@{pdk.version}` ({pdk.source})",
        f"- harness: `{HARNESS_VERSION}`",
        f"- probe dip: {PROBE_DIP_S * 1e6:g} µs (open-ended — the crossing time,"
        " not the dip, is what is read)",
        f"- stress bias: {dict(BIASES)['stress'] * 1e9:g} nA"
        " (`sim/por-output-chain-ibias-sharing/`, DR-024);"
        f" nominal reference arm: {dict(BIASES)['nominal'] * 1e9:g} nA (DR-005)",
        f"- trip point: `PGDG` = {TRIP_V:g} V falling, the same threshold"
        " `../testbench/tb.json`'s own check is written on",
        "",
    ]
    if smoke:
        lines += ["> **SMOKE RUN — two PVT points, schematic only. Not a"
                  " pinned value.**", ""]

    lines += [
        "## The pinned value",
        "",
        "The rule, fixed in the script before the sweep ran (see its module"
        " docstring): `T_dip,min(new)` is the smallest multiple of"
        f" {TDIP_QUANTUM_US:g} µs that is at least {MARGIN:g}× the slowest"
        " crossing time measured at the stress bias, across both netlist"
        " levels and all 81 points.",
        "",
        f"- Slowest measured crossing (stress bias): **{worst_us:.3f} µs**",
        f"- **`T_dip,min(new)` = {tdip_us:g} µs**",
        f"- Realized margin over the slowest corner:"
        f" **{(tdip_us / worst_us - 1) * 100:.1f} %**"
        f" ({tdip_us - worst_us:.3f} µs)",
        "",
    ]
    if never:
        lines += [
            "> **CONTINGENCY (DR-027 §5): "
            f"{len(never)} point(s) never reached the trip point inside the"
            f" {PROBE_DIP_S * 1e6:g} µs probe dip.** For those points this is"
            " not a spec-only fix — see the *never trips* section below.",
            "",
        ]
    else:
        lines += [
            f"Every one of the {len(points) * len(variants) * len(BIASES)}"
            " (point, netlist, bias) runs reached the trip point"
            f" inside the {PROBE_DIP_S * 1e6:g} µs probe dip — DR-027 §1's"
            " reading (the filter is"
            " still on its way down when the old 10 µs window closes, not"
            " sitting on an asymptotic floor above trip) holds across the whole"
            " grid, and §5's contingency is not triggered.",
            "",
        ]

    # ---- Part A table -------------------------------------------------------
    lines += [
        "## Part A — crossing time, full grid",
        "",
        "How long `POR_RAW` must stay low before `PGDG` falls through"
        f" {TRIP_V:g} V. Nothing in the filter depends on when the dip *ends*,"
        " so this crossing time **is** the minimum qualifying-dip duration at"
        " that point; Part B confirms that equivalence against finite dips."
        " `PGDG` pre-dip is the initial condition — the filter output settled"
        " at the rail — and is there so a run that started from a"
        " not-yet-settled filter would be visible rather than silently biasing"
        " the answer.",
        "",
        "| point | "
        + " | ".join(
            f"`{variant}` {bias_label}"
            for bias_label, _ in BIASES
            for variant, _ in variants
        )
        + f" | stress/nominal (`{variants[-1][0]}`) |",
        "| --- |" + " ---: |" * (len(BIASES) * len(variants) + 1),
    ]
    for point_id, *_ in points:
        cells = []
        for bias_label, _ in BIASES:
            for variant, _ in variants:
                us = crossing_us(variant, bias_label, point_id)
                cells.append("**never**" if us is None else f"{us:.2f} µs")
        ratio_variant = variants[-1][0]
        s = crossing_us(ratio_variant, "stress", point_id)
        n = crossing_us(ratio_variant, "nominal", point_id)
        ratio = "—" if not s or not n else f"{s / n:.2f}×"
        lines.append(f"| `{point_id}` | " + " | ".join(cells) + f" | {ratio} |")
    lines += [
        "",
        "The last column is the measured 1/`IBIAS` scaling DR-027 §3 argues"
        f" from. The current ratio is {dict(BIASES)['nominal'] / dict(BIASES)['stress']:.2f}×"
        " (500 nA / 91.0251 nA); a measured dwell ratio near it means the"
        " deglitch node really is a capacitor discharged by the bias, which is"
        " the premise the estimate rested on.",
        "",
        "### Where the sweep binds",
        "",
    ]
    for variant, _ in variants:
        ranked = sorted(
            (p[0] for p in points if crossing_us(variant, PIN_BIAS, p[0]) is not None),
            key=lambda pid: crossing_us(variant, PIN_BIAS, pid),
            reverse=True,
        )
        if not ranked:
            continue
        top = ", ".join(
            f"`{pid}` ({crossing_us(variant, PIN_BIAS, pid):.2f} µs)"
            for pid in ranked[:3]
        )
        fast = ranked[-1]
        lines.append(
            f"- `{variant}`: slowest {top}; fastest `{fast}`"
            f" ({crossing_us(variant, PIN_BIAS, fast):.2f} µs)."
        )
    lines.append("")

    if never:
        lines += [
            "### Points that never trip (DR-027 §5 contingency)",
            "",
            "| variant | point | `PGDG` floor over the probe dip | `NDG` peak |",
            "| --- | --- | ---: | ---: |",
        ]
        for variant, point_id in never:
            name = f"d_{variant}__{PIN_BIAS}__{point_id}"
            lines.append(
                f"| `{variant}` | `{point_id}` |"
                f" {meas(name, 'pgdg_min'):.4f} V | {meas(name, 'ndg_max'):.4f} V |"
            )
        lines += [
            "",
            "A point in this table is **not** fixed by re-costing `T_dip,min`:"
            " its `NDG` settles below the inverter threshold, so no dwell"
            " reaches the trip point. DR-027 §5 is explicit that this re-opens"
            " the circuit question for that corner rather than being absorbed"
            " into a wider bound.",
            "",
        ]

    # ---- Part B table -------------------------------------------------------
    lines += [
        "## Part B — finite-width ladder at the slowest points",
        "",
        "The parent testbench's own check (`PGDG` reaches"
        f" {TRIP_V:g} V *within the dip window itself*) re-applied at a ladder"
        " of finite dip widths, at the points Part A found slowest. `trips`"
        " must appear exactly from the first width at or above that point's"
        " Part A crossing time — that is what makes the crossing time a"
        " `T_dip,min` rather than merely a number measured under a long dip.",
        "",
        "| variant | point | Part A crossing | "
        + " | ".join(f"{w:g} µs" for w in LADDER_WIDTHS_US)
        + " |",
        "| --- | --- | ---: |" + " ---: |" * len(LADDER_WIDTHS_US),
    ]
    for variant, point_id in ladder_points:
        cells = []
        for width_us in LADDER_WIDTHS_US:
            m = ladder.get(f"d_{variant}__{PIN_BIAS}__{point_id}__{width_us:g}us", {})
            floor = m.get("pgdg_min")
            if floor is None:
                cells.append("—")
            elif floor <= TRIP_V:
                cells.append(f"**trips** ({floor:.2f} V)")
            else:
                cells.append(f"{floor:.2f} V")
        cross = crossing_us(variant, PIN_BIAS, point_id)
        lines.append(
            f"| `{variant}` | `{point_id}` | {cross:.2f} µs | "
            + " | ".join(cells) + " |"
        )
    lines += [
        "",
        "Cells show the `PGDG` floor reached inside the dip; **trips** marks a"
        f" width at which it reaches the {TRIP_V:g} V trip point, i.e. a width"
        " at which the parent testbench's `por-brownout` check passes at that"
        " point. The outgoing `T_dip,min` is the 10 µs column.",
        "",
    ]

    (CONTROL_DIR / "dwell_results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
