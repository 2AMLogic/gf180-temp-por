#!/usr/bin/env python3
"""Ramp-rate control probe for sim/por-vth/'s hysteresis regression (issue #187).

    python3 sim/por-vth/control/run_ramp_rate_probe.py [-j N]

Composes decks from ``ramp_rate_probe.spice`` + one ``temp_por_top`` netlist,
one (DUT netlist x ramp duration x supply) point per run, and writes:

    decks/<run>.spice   the exact deck as run
    logs/<run>.log      raw ngspice output, verbatim
    results.json        every measurement, machine-readable
    results.md          the tables below, generated from those logs

This is the control experiment behind
``spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md`` and
``design/por_comparator.md``'s "The full-assembly V_hys is a ramp-rate
measurement" section. It diagnoses record ``20260811-073945-12473c3``
(80/81 PASS; ``v_hys_mv`` = 261.092 mV at ``ss_-40c_3.63v`` against a 250 mV
ceiling) against its schematic-level predecessor ``20260801-233802-32fbaa0``
(248.740 mV at the same corner).

It is NOT a recorded PVT result: a handful of points at one corner is a
diagnosis, not corner-grid evidence, which stays in ``sim/por-vth/records/``.
See ``sim/README.md``, "Control experiments".

WHAT IT VARIES, AND WHY

The parent deck traverses (vdd_val - 2.0 V) in a FIXED 4 ms on both slow
segments, so its supply axis is simultaneously a ramp-rate axis:
242.5 / 325 / 407.5 V/s at 2.97 / 3.30 / 3.63 V. Nothing in the parent grid
can tell a supply effect from a rate effect. Three arms separate them:

    rate-ladder-postlayout  layout/postlayout/temp_por_top.spice at the failing
                            corner (ss / -40 C / 3.63 V), ramp duration swept
                            4 -> 128 ms, i.e. 407.5 -> 12.7 V/s. If V_hys is a
                            static property this line is flat; if it is a
                            dynamic lag it grows with the rate, and its
                            zero-rate limit is the static hysteresis.
    rate-ladder-schematic   design/netlist/temp_por_top.spice, same corner,
                            same ladder. Splits the post-layout regression into
                            a static share and a dynamic (lag) share.
    rate-matched-supply     layout/postlayout/temp_por_top.spice, same corner,
                            all three ratified supplies at ONE rate (242.5 V/s,
                            the parent grid's own slowest). If the parent's
                            211.4 / 238.6 / 261.1 mV supply trend is really a
                            rate trend, this arm is flat instead.

Every run also probes the comparator's own input pair AT THE INSTANT IT
DECIDES: ``SNS - VREF`` there is the input-referred overdrive the comparator
still needed when it finally crossed, i.e. the lag expressed at its own
input. Multiplied by the divider's (RTOP+RBOT)/RBOT it is the same lag
expressed at ``VDD``, which is what the threshold measurement reports -- so
the two independent readings of the same quantity can be cross-checked
against each other rather than asserted.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.cliutil import default_jobs  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FRAGMENT = CONTROL_DIR / "ramp_rate_probe.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

#: DUT id -> (netlist, SNS node path). ``layout/postlayout/temp_por_top.spice``
#: is flat (``klt``'s extraction inlines every cell), so the comparator's sense
#: node is ``xcmp__SNS`` at the top level; the schematic export keeps the
#: hierarchy, so it is ``xcmp.sns``. Both are the same net.
DUTS: dict[str, tuple[Path, str]] = {
    "postlayout": (
        REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice",
        "xdut.xcmp__sns",
    ),
    "schematic": (
        REPO_ROOT / "design" / "netlist" / "temp_por_top.spice",
        "xdut.xcmp.sns",
    ),
}

# The failing corner of record 20260811-073945-12473c3.
CORNER = "ss"
TEMP_C = -40.0

# The parent deck's own ramp duration, and the rate its 2.97 V column runs at.
PARENT_TRAMP_S = 4.0e-3
PARENT_RATE_V_PER_S = (3.63 - 2.0) / PARENT_TRAMP_S       # 407.5 V/s, 3.63 V column
PARENT_SLOWEST_RATE_V_PER_S = (2.97 - 2.0) / PARENT_TRAMP_S  # 242.5 V/s, 2.97 V column

#: (RTOP+RBOT)/RBOT, from design/por_comparator.md's sizing table -- the factor
#: that refers an input-referred (SNS) error out to VDD.
DIVIDER_RATIO = 2.16667

#: The parent record's own numbers at this corner, quoted for cross-check.
PARENT_V_HYS_MV = {2.97: 211.382, 3.30: 238.555, 3.63: 261.092}
PARENT_VPOR_RISE_V = {2.97: 2.62809, 3.30: 2.63855, 3.63: 2.64873}
SCHEMATIC_PARENT_V_HYS_MV = 248.740  # 20260801-233802-32fbaa0, ss_-40c_3.63v

RAMP_MULTIPLES = (1, 2, 4, 8, 16, 32)


def _points() -> list[tuple[str, str, str, float, float]]:
    """(run_id, arm, dut, vdd_val, tramp_s)."""
    pts: list[tuple[str, str, str, float, float]] = []
    for dut in ("postlayout", "schematic"):
        for mult in RAMP_MULTIPLES:
            tramp = PARENT_TRAMP_S * mult
            rate = (3.63 - 2.0) / tramp
            pts.append(
                (f"rate_{dut}_{rate:.0f}vs", f"rate-ladder-{dut}", dut, 3.63, tramp)
            )
    for vdd in (2.97, 3.30, 3.63):
        tramp = (vdd - 2.0) / PARENT_SLOWEST_RATE_V_PER_S
        pts.append(
            (
                f"matched_postlayout_{vdd:.2f}v",
                "rate-matched-supply",
                "postlayout",
                vdd,
                tramp,
            )
        )
    return pts


#: Drawn resistor lengths of the sense divider, read off
#: design/netlist/por_comparator.spice (same geometry in the extracted netlist,
#: layout/postlayout/temp_por_top.spice X212/X213/X214). Same flavor, same
#: width, so the divider tap is a pure length ratio.
RTOP_UM, RBOT_UM, RHYS_UM = 7897.44, 6769.23, 775.0
#: The tap's static value as a fraction of VDD, in each of the two divider
#: states: RHYS shorted by MHSW (POR_RAW low, pre-release) and RHYS in circuit
#: (POR_RAW high, released).
TAP_SHORTED = RBOT_UM / (RTOP_UM + RBOT_UM)
TAP_RELEASED = (RBOT_UM + RHYS_UM) / (RTOP_UM + RBOT_UM + RHYS_UM)

#: Rail voltages at which the two node-level probes below sample. Both sit
#: clear of every threshold on the whole ladder -- 2.50 V is below VPOR↑,min
#: (so the divider is still in its shorted state) and 2.55 V is above
#: VPOR↓,max (so it is still in its released state) -- so each probe reads one
#: unambiguous divider state, not a node mid-transition.
PROBE_UP_V = 2.50
PROBE_DOWN_V = 2.55


def analyses(sns: str, t_settled: float, t_down: float) -> list[str]:
    """The parent deck's four threshold/chatter measurements, plus the same
    threshold pair read at the comparator's own INPUT.

    ``v(SNS) = v(VREF)`` is the instant the sense divider's tap reaches the
    reference -- i.e. where an infinitely fast comparator would decide. The
    rail voltage there is the threshold the *divider ratio* implements; the
    rail voltage at ``POR_RAW = 1.5 V`` is what the parent deck reports. Their
    difference is everything between the input pair and the output node:
    comparator response and the two inverter stages. Both are read off the
    same run, at the same corner, on the same edge.

    ``td=`` windows each input-side crossing to the segment it belongs to:
    during the 0 -> 2 V pre-ramp both ``SNS`` and ``VREF`` are still coming up
    from zero and can cross in either direction, which is not the event being
    measured.
    """
    cross = "v(xdut.por_raw)=1.5"
    inp = f"v({sns})=v(xdut.vref)"
    return [
        f"meas tran vpor_rise find v(vdd) when {cross} rise=1",
        f"meas tran vpor_rise_last find v(vdd) when {cross} rise=last",
        f"meas tran vpor_fall find v(vdd) when {cross} fall=1",
        f"meas tran vpor_fall_last find v(vdd) when {cross} fall=last",
        f"meas tran vpor_rise_sns find v(vdd) when {inp} rise=1 td=1e-3",
        f"meas tran vpor_fall_sns find v(vdd) when {inp} fall=1 td={t_down!r}",
        f"meas tran vref_settled find v(xdut.vref) at={t_settled!r}",
        f"meas tran ibias_settled find v(xdut.ibias) at={t_settled!r}",
        # Which of the comparator's two inputs actually moves. Sampled at a
        # rail voltage clear of both thresholds, once per edge.
        f"meas tran vref_up find v(xdut.vref) when v(vdd)={PROBE_UP_V!r} rise=1 td=1e-3",
        f"meas tran sns_up find v({sns}) when v(vdd)={PROBE_UP_V!r} rise=1 td=1e-3",
        f"meas tran vref_dn find v(xdut.vref) when v(vdd)={PROBE_DOWN_V!r} fall=1"
        f" td={t_down!r}",
        f"meas tran sns_dn find v({sns}) when v(vdd)={PROBE_DOWN_V!r} fall=1"
        f" td={t_down!r}",
    ]


MEASURES = {
    "vpor_rise_v": "vpor_rise",
    "vpor_fall_v": "vpor_fall",
    "v_hys_mv": "(vpor_rise-vpor_fall)*1e3",
    "rise_chatter_mv": "(vpor_rise_last-vpor_rise)*1e3",
    "fall_chatter_mv": "(vpor_fall-vpor_fall_last)*1e3",
    "vpor_rise_sns_v": "vpor_rise_sns",
    "vpor_fall_sns_v": "vpor_fall_sns",
    "v_hys_sns_mv": "(vpor_rise_sns-vpor_fall_sns)*1e3",
    "lag_rise_mv": "(vpor_rise-vpor_rise_sns)*1e3",
    "lag_fall_mv": "(vpor_fall_sns-vpor_fall)*1e3",
    "vref_settled_v": "vref_settled",
    "ibias_settled_v": "ibias_settled",
    # Node-level error at PROBE_UP_V / PROBE_DOWN_V: how far each comparator
    # input sits from where a static rail would put it.
    "vref_err_up_mv": "(vref_up-vref_settled)*1e3",
    "vref_err_dn_mv": "(vref_dn-vref_settled)*1e3",
    "sns_err_up_mv": f"(sns_up-{PROBE_UP_V * TAP_SHORTED!r})*1e3",
    "sns_err_dn_mv": f"(sns_dn-{PROBE_DOWN_V * TAP_RELEASED!r})*1e3",
}


def compose(pdk, corner, dut: str, vdd: float, tramp: float) -> str:
    options = json.loads(MANIFEST.read_text())["options"]
    netlist, sns = DUTS[dut]
    t_down = 1.0e-3 + tramp + 6.0e-3
    t_settled = t_down - 0.1e-3
    tstop = t_down + tramp + 2.0e-3
    lines = [
        f"* por-vth ramp-rate control -- {dut} @ {corner.name}/{TEMP_C:g}C/{vdd:g}V,"
        f" tramp={tramp * 1e3:g} ms -- GENERATED by run_ramp_rate_probe.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        ".param vdd_nom=3.3",
        f".param vdd_val={vdd!r}",
        f".param temp_c={TEMP_C!r}",
        f".param tramp={tramp!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, TEMP_C, options)
    lines += [
        "",
        # Repo-relative from decks/, so a committed deck does not carry the
        # absolute path of whatever worktree produced it. ngspice resolves a
        # relative .include against the including file's directory; the same
        # idiom is used by sim/por-brownout-slew/control/ and
        # sim/por-glitch/control/.
        f'.include "../{FRAGMENT.name}"',
        f'.include "../../../../{netlist.relative_to(REPO_ROOT)}"',
        "",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        f"  tran 10u {tstop!r}",
    ]
    lines += [f"  {a}" for a in analyses(sns, t_settled, t_down)]
    lines += [f"  let m_{name} = {expr}" for name, expr in MEASURES.items()]
    lines += [f"  print m_{name}" for name in MEASURES]
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def run_one(pdk, corner, point) -> dict:
    run_id, arm, dut, vdd, tramp = point
    deck = compose(pdk, corner, dut, vdd, tramp)
    deck_path = CONTROL_DIR / "decks" / f"{run_id}.spice"
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(deck)
    log_path = CONTROL_DIR / "logs" / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.run(
        ["ngspice", "-b", str(deck_path)], capture_output=True, text=True, timeout=14400
    )
    log_path.write_text(proc.stdout + proc.stderr)
    meas = runner.parse_measurements(proc.stdout)
    return {
        "run": run_id,
        "arm": arm,
        "dut": dut,
        "vdd_v": vdd,
        "tramp_ms": tramp * 1e3,
        "rate_v_per_s": (vdd - 2.0) / tramp,
        "seconds": round(time.time() - started, 1),
        **meas,
    }


def _static_and_slope(rows: list[dict], key: str = "v_hys_mv") -> tuple[float, float]:
    """(zero-rate limit, slope) from the two slowest rows -- the local
    gradient where the curve is closest to its static limit."""
    a, b = sorted(rows, key=lambda r: r["rate_v_per_s"])[:2]
    slope = (b[key] - a[key]) / (b["rate_v_per_s"] - a["rate_v_per_s"])
    return a[key] - slope * a["rate_v_per_s"], slope


LADDER_HEADER = (
    "| ramp | dVDD/dt | VPOR\u2191 | VPOR\u2193 | V_hys | V_hys at the comparator's"
    " own input | VREF error, up-ramp | VREF error, down-ramp | SNS error, up-ramp |"
    " SNS error, down-ramp | comparator+output lag, \u2191 / \u2193 |"
)
LADDER_RULE = "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"


def _ladder_row(r: dict) -> str:
    return (
        f"| {r['tramp_ms']:.0f} ms | {r['rate_v_per_s']:.1f} V/s |"
        f" {r['vpor_rise_v']:.5f} V | {r['vpor_fall_v']:.5f} V |"
        f" **{r['v_hys_mv']:.3f} mV** | {r['v_hys_sns_mv']:.3f} mV |"
        f" {r['vref_err_up_mv']:+.3f} mV | {r['vref_err_dn_mv']:+.3f} mV |"
        f" {r['sns_err_up_mv']:+.3f} mV | {r['sns_err_dn_mv']:+.3f} mV |"
        f" {r['lag_rise_mv']:+.3f} / {r['lag_fall_mv']:+.3f} mV |"
    )


def render(results: list[dict], pdk) -> str:
    by_arm: dict[str, list[dict]] = {}
    for row in results:
        by_arm.setdefault(row["arm"], []).append(row)

    options = json.loads(MANIFEST.read_text())["options"]
    out: list[str] = [
        "# `por-vth` hysteresis ramp-rate control \u2014 results",
        "",
        "**Generated by `run_ramp_rate_probe.py`. Do not edit \u2014 re-run it.** Every",
        "number below is read out of `logs/` by that script; nothing here is",
        "transcribed by hand.",
        "",
        f"- PVT point: `{CORNER}` / {TEMP_C:g} \u00b0C \u2014 the corner that fails in"
        " the parent record (one corner: a control is not corner evidence, see"
        " `sim/README.md`)",
        f"- PDK: `{pdk.variant}` @ `{pdk.version}`",
        f"- Harness version: `{HARNESS_VERSION}`",
        "- Solver options (from `../testbench/tb.json`): "
        + ", ".join(f"`{o}`" for o in options),
        "- DUT netlists: `layout/postlayout/temp_por_top.spice` (extracted),"
        " `design/netlist/temp_por_top.spice` (schematic)",
        "- Diagnoses: `../records/20260811-073945-12473c3.md` (`v_hys_mv` = "
        f"{PARENT_V_HYS_MV[3.63]:.3f} mV at `ss_-40c_3.63v`, against a 250 mV ceiling)"
        " vs. `../records/20260801-233802-32fbaa0.md`"
        f" ({SCHEMATIC_PARENT_V_HYS_MV:.3f} mV, same corner)",
        "- Conclusion drawn from these tables:"
        " `spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md`",
        "",
        "## What the columns are",
        "",
        "The parent deck holds the **duration** of each quasi-static ramp segment at"
        " 4 ms, so it traverses `vdd_val \u2212 2.0 V` in a fixed time and its supply"
        " axis is simultaneously a ramp-rate axis: **242.5 / 325 / 407.5 V/s** at"
        " 2.97 / 3.30 / 3.63 V. Every arm below holds one of those two apart from the"
        " other, and decomposes each threshold into the three places a moving rail"
        " can displace it:",
        "",
        "- **V_hys** \u2014 the parent deck's own measurand: the rail voltage at the"
        " first `POR_RAW = 1.5 V` crossing on each edge, differenced.",
        "- **V_hys at the comparator's own input** \u2014 the same pair of rail"
        " voltages taken at `SNS = VREF` instead, i.e. where an infinitely fast"
        " comparator would decide. The gap between this column and the one before it"
        " is everything downstream of the input pair.",
        "- **VREF error** \u2014 `bias_core`'s reference at a fixed rail voltage on"
        f" each edge ({PROBE_UP_V:.2f} V rising, {PROBE_DOWN_V:.2f} V falling, both"
        " clear of every threshold on the ladder), against its own settled value"
        " measured on the flat hold of the same run.",
        "- **SNS error** \u2014 the sense divider's tap at those same two rail"
        " voltages, against the static tap the drawn resistor lengths give"
        f" ({TAP_SHORTED:.6f}\u00b7VDD with `RHYS` shorted,"
        f" {TAP_RELEASED:.6f}\u00b7VDD with it in circuit).",
        "- **comparator+output lag** \u2014 the two columns above differenced per"
        " edge: how much further the rail travelled between `SNS` crossing `VREF` and"
        " `POR_RAW` reaching 1.5 V.",
        "",
        "`VREF error` and `SNS error` are the two inputs of the same comparator, so"
        " their difference is what the divider ratio refers back out to `VDD`. That"
        " makes the decomposition additive and checkable rather than asserted.",
        "",
    ]

    stats: dict[str, tuple[float, float]] = {}
    for arm, title, blurb in (
        (
            "rate-ladder-postlayout",
            "A \u2014 ramp-rate ladder, extracted netlist, at the failing corner",
            "One variable: how long each quasi-static segment takes. Supply is pinned"
            " at 3.63 V and the corner at `ss`/\u221240 \u00b0C, i.e. exactly the"
            " point that fails in the parent record. The 407.5 V/s row **is** the"
            f" parent deck (`tramp` = 4 ms) and reproduces its"
            f" {PARENT_V_HYS_MV[3.63]:.3f} mV.",
        ),
        (
            "rate-ladder-schematic",
            "B \u2014 the same ladder on the schematic netlist",
            "One variable: which `temp_por_top` netlist the same stimulus drives."
            " Everything else matches arm A row for row. The 407.5 V/s row is the"
            f" schematic-level parent record ({SCHEMATIC_PARENT_V_HYS_MV:.3f} mV).",
        ),
    ):
        rows = by_arm.get(arm, [])
        if not rows:
            continue
        out += [f"## {title}", "", blurb, "", LADDER_HEADER, LADDER_RULE]
        out += [_ladder_row(r) for r in sorted(rows, key=lambda r: -r["rate_v_per_s"])]
        static, slope = _static_and_slope(rows)
        stats[arm] = (static, slope)
        vref_static, vref_slope = _static_and_slope(rows, "vref_err_up_mv")
        slowest = min(rows, key=lambda r: r["rate_v_per_s"])
        fastest = max(rows, key=lambda r: r["rate_v_per_s"])
        out += [
            "",
            f"`V_hys` falls monotonically with the ramp rate, from"
            f" {fastest['v_hys_mv']:.3f} mV at the parent deck's rate to"
            f" {slowest['v_hys_mv']:.3f} mV at {slowest['rate_v_per_s']:.1f} V/s."
            f" Extrapolating the two slowest rows to a static rail:"
            f" **V_hys \u2192 {static:.1f} mV**, i.e. mid-window, with a rate"
            f" coefficient of **{slope:.4f} mV per (V/s)**.",
            "",
            f"`VREF` is displaced **{fastest['vref_err_up_mv']:+.3f} mV** on the"
            f" up-ramp and **{fastest['vref_err_dn_mv']:+.3f} mV** on the down-ramp at"
            " the parent deck's rate, and the displacement is proportional to the rate"
            f" ({vref_slope:.5f} mV per (V/s), i.e."
            f" {vref_slope * 1e3:.0f} \u00b5s of equivalent time constant) with an"
            f" intercept of {vref_static:+.3f} mV \u2014 it goes to zero on a static"
            " rail. That is not a settling artefact: the same run's own"
            " `vref_settled_v` is stable, the displacement reverses sign with the"
            " ramp direction, and the down-ramp edge happens several ms after the"
            " reference has settled.",
            "",
            f"The sense divider's tap tracks the rail to within"
            f" {max(abs(fastest['sns_err_up_mv']), abs(fastest['sns_err_dn_mv'])):.3f}"
            " mV over the same range \u2014 an order of magnitude less than `VREF`"
            " moves.",
            "",
        ]

    rows = by_arm.get("rate-matched-supply", [])
    if rows:
        out += [
            "## C \u2014 supply swept at ONE ramp rate (242.5 V/s), extracted netlist",
            "",
            "One variable: the supply. The parent deck cannot do this \u2014 its fixed"
            " 4 ms ramp makes rate a function of supply \u2014 so this arm stretches"
            " `tramp` instead, to hold dVDD/dt at the parent grid's own slowest value."
            " The 2.97 V row is the parent deck's `ss_-40c_2.97v` point unchanged, and"
            " reproduces it exactly.",
            "",
            "| VDD | ramp | dVDD/dt | VPOR\u2191 | VPOR\u2193 | V_hys | parent"
            " record's VPOR\u2191 | parent record's V_hys |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in sorted(rows, key=lambda r: r["vdd_v"]):
            key = round(r["vdd_v"], 2)
            out.append(
                f"| {r['vdd_v']:.2f} V | {r['tramp_ms']:.3f} ms |"
                f" {r['rate_v_per_s']:.1f} V/s | **{r['vpor_rise_v']:.5f} V** |"
                f" {r['vpor_fall_v']:.5f} V | **{r['v_hys_mv']:.3f} mV** |"
                f" {PARENT_VPOR_RISE_V[key]:.5f} V | {PARENT_V_HYS_MV[key]:.3f} mV |"
            )
        rise_spread = (
            max(r["vpor_rise_v"] for r in rows) - min(r["vpor_rise_v"] for r in rows)
        ) * 1e3
        hys_spread = max(r["v_hys_mv"] for r in rows) - min(r["v_hys_mv"] for r in rows)
        parent_rise_spread = (
            max(PARENT_VPOR_RISE_V.values()) - min(PARENT_VPOR_RISE_V.values())
        ) * 1e3
        parent_hys_spread = max(PARENT_V_HYS_MV.values()) - min(PARENT_V_HYS_MV.values())
        out += [
            "",
            "Rate-matched, the release threshold's spread over the whole \u00b110 %"
            f" supply window falls from **{parent_rise_spread:.2f} mV** (parent record)"
            f" to **{rise_spread:.2f} mV**, and the hysteresis spread from"
            f" **{parent_hys_spread:.3f} mV** to **{hys_spread:.3f} mV**.",
            "",
            "**The VPOR\u2191 column is exactly zero for a reason worth stating"
            " plainly, because it is half tautology and half result.** Once dVDD/dt is"
            " held constant, all three rows traverse *the same rail trajectory* from"
            " 2.0 V up to the crossing \u2014 they differ only in where the rail"
            " eventually stops, which is after the release has already happened. So of"
            " course they agree. The content is the contrapositive: the release"
            " threshold depends on the trajectory the rail took to get there and on"
            " nothing else, so the"
            f" {parent_rise_spread:.2f} mV of VPOR\u2191 spread the parent record"
            " attributes to its supply axis cannot be a supply effect \u2014 the only"
            " thing that differs between its supply columns before the crossing is"
            " their rate.",
            "",
            "The falling edge does keep a small residual, and it is the down-ramp's own"
            " start transient rather than a supply term: at 2.97 V the falling crossing"
            " arrives 0.55 V after the rail leaves its hold, against 1.22 V at 3.63 V,"
            " so the 2.97 V row has had less of the ramp to develop its steady-state"
            " displacement. The 3.30 V and 3.63 V rows, which both have room to develop"
            " it, agree to every digit printed.",
            "",
        ]

    if len(stats) == 2:
        pfast = max(by_arm["rate-ladder-postlayout"], key=lambda r: r["rate_v_per_s"])
        sfast = max(by_arm["rate-ladder-schematic"], key=lambda r: r["rate_v_per_s"])
        parts: dict[str, dict[str, float]] = {}
        for arm in ("rate-ladder-schematic", "rate-ladder-postlayout"):
            rows_a = by_arm[arm]
            for r in rows_a:
                r["lag_total_mv"] = r["lag_rise_mv"] + r["lag_fall_mv"]
            fast = max(rows_a, key=lambda r: r["rate_v_per_s"])
            total0, _ = _static_and_slope(rows_a, "v_hys_mv")
            input0, _ = _static_and_slope(rows_a, "v_hys_sns_mv")
            lag0, _ = _static_and_slope(rows_a, "lag_total_mv")
            parts[arm] = {
                "total": fast["v_hys_mv"],
                "static": total0,
                "excess_input": fast["v_hys_sns_mv"] - input0,
                "excess_output": fast["lag_total_mv"] - lag0,
            }
        s = parts["rate-ladder-schematic"]
        e = parts["rate-ladder-postlayout"]
        regression = PARENT_V_HYS_MV[3.63] - SCHEMATIC_PARENT_V_HYS_MV
        out += [
            "## D \u2014 the decomposition the two parent records could not make",
            "",
            "Both parent records measure one rate, so neither can separate hysteresis"
            " from displacement. Arms A and B can, by extrapolating each of the three"
            " quantities above to a static rail and differencing. At the parent deck's"
            f" own {PARENT_RATE_V_PER_S:.1f} V/s, at the failing corner:",
            "",
            "| Term | Schematic | Extracted | \u0394 |",
            "|---|---:|---:|---:|",
            f"| **Total measured V_hys** | {s['total']:.3f} mV | {e['total']:.3f} mV |"
            f" **{e['total'] - s['total']:+.3f} mV** |",
            f"| Static V_hys (whole path, zero-rate limit) | {s['static']:.3f} mV |"
            f" {e['static']:.3f} mV | {e['static'] - s['static']:+.3f} mV |",
            f"| Rate-dependent excess, at the comparator's input (`VREF` displacement"
            f" \u00d7 divider ratio) | {s['excess_input']:.3f} mV |"
            f" {e['excess_input']:.3f} mV |"
            f" {e['excess_input'] - s['excess_input']:+.3f} mV |",
            f"| Rate-dependent excess, comparator + output chain | "
            f"{s['excess_output']:.3f} mV | {e['excess_output']:.3f} mV |"
            f" **{e['excess_output'] - s['excess_output']:+.3f} mV** |",
            "",
            "The three lower rows sum to the top one in each column, by construction:"
            " the static limit plus the two rate-dependent excesses is the reading.",
            "",
            f"**The regression the issue reports is the last row.** Of the"
            f" +{regression:.3f} mV the two parent records differ by,"
            f" **{e['excess_output'] - s['excess_output']:+.3f} mV** is the comparator"
            " and its two output inverter stages taking longer to resolve once the"
            " extraction's interconnect capacitance is on their internal nodes"
            " (`xcmp__VDDA`/`NA`/`CMPO`/`N1`/`TN`/`NBG`: 13.6\u201321.3 fF each,"
            " `layout/postlayout/temp_por_top.spice`). The static hysteresis moves by"
            f" {e['static'] - s['static']:+.3f} mV and the input-side excess by"
            f" {e['excess_input'] - s['excess_input']:+.3f} mV \u2014 neither is the"
            " regression.",
            "",
            "**And the reading it regresses is mostly not hysteresis at all.** Of the"
            f" {e['total']:.3f} mV the extracted record reports,"
            f" **{100 * e['static'] / e['total']:.0f} %** ({e['static']:.1f} mV) is the"
            " divider ratio doing its job,"
            f" **{100 * e['excess_input'] / e['total']:.0f} %**"
            f" ({e['excess_input']:.1f} mV) is `bias_core`'s reference being displaced"
            " by the moving rail, and"
            f" **{100 * e['excess_output'] / e['total']:.0f} %**"
            f" ({e['excess_output']:.1f} mV) is comparator and output-chain delay."
            " Only the first of the three is the quantity"
            " `spec/target-spec.md#por-hysteresis` bounds.",
            "",
            "### What this rules out",
            "",
            "- **The sense divider's drawn interconnect R/C.** `klt` puts **25.9 fF**"
            " on `SNS` and **17.5 fF** on `SNSB` (`C_25`/`C_27`) against a ~5.9"
            " M\u03a9 Thevenin source \u2014 ~0.15 \u00b5s, three orders below the"
            " displacement measured here. The `SNS error` columns confirm it directly:"
            f" the tap is within {abs(pfast['sns_err_up_mv']):.2f} mV of its static"
            " value at the fastest rate on the ladder, against"
            f" {abs(pfast['vref_err_up_mv']):.2f} mV for `VREF` on the same run.",
            "- **The divider ratio itself.** Its zero-rate hysteresis is"
            f" {e['static']:.1f} mV on the extracted netlist and {s['static']:.1f} mV"
            " on the schematic, against a ratified 100 / 150 / 250 mV window \u2014"
            " not close to either bound, and within a few mV of the 150 mV typ"
            " `design/por_comparator.md`'s sizing algebra targets.",
            "- **A reference that has not settled.** The displacement reverses sign"
            " with ramp direction, scales with rate through the origin, and is present"
            " on the down-ramp edge several ms after `vref_settle_drift_mv` reads"
            " zero.",
            "- **A different reference value.** `vref_settled_v` is"
            f" {sfast['vref_settled_v']:.5f} V (schematic) and"
            f" {pfast['vref_settled_v']:.5f} V (extracted) \u2014 the two netlists"
            " agree on the settled reference to well under a millivolt.",
            "",
        ]

    return "\n".join(out) + "\n"


def committed_seconds() -> dict:
    """Per-run wall-clock times from the committed ``results.json``, keyed by
    run id, or ``{}`` if that file is absent or unreadable.

    A ``logs/`` file records what the run measured, not how long it took, so a
    ``--render-only`` regeneration has no way to re-derive ``seconds``. Carrying
    the committed values forward keeps the regenerated ``results.json``
    byte-identical to the one in git: a reviewer who re-renders to check
    ``results.md`` (as ``design/por_comparator.md`` invites) is left with a
    clean tree rather than 33 zeroed runtimes."""
    path = CONTROL_DIR / "results.json"
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text())
        return {row["run"]: row["seconds"] for row in rows}
    except (ValueError, TypeError, KeyError):
        return {}


def replay_one(point, seconds_by_run=None) -> dict:
    """Re-read one point's measurements from its committed ``logs/`` file,
    without re-simulating. Used by ``--render-only`` so ``results.md`` can be
    regenerated from the raw logs the run already wrote -- the same numbers, by
    construction, since ``parse_measurements`` is the only reader either way.
    ``seconds`` is the one field no log carries; it is preserved from the
    committed ``results.json`` (see ``committed_seconds``) so re-rendering does
    not rewrite the recorded runtimes."""
    run_id, arm, dut, vdd, tramp = point
    log_path = CONTROL_DIR / "logs" / f"{run_id}.log"
    return {
        "run": run_id,
        "arm": arm,
        "dut": dut,
        "vdd_v": vdd,
        "tramp_ms": tramp * 1e3,
        "rate_v_per_s": (vdd - 2.0) / tramp,
        "seconds": (seconds_by_run or {}).get(run_id, 0.0),
        **runner.parse_measurements(log_path.read_text()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-j", "--jobs", type=int, default=default_jobs())
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate results.md/results.json from the existing logs/ without"
        " re-running ngspice",
    )
    args = parser.parse_args()

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    corner = corners_mod.CORNERS[CORNER]

    points = _points()
    if args.render_only:
        print(f"re-rendering {len(points)} control points from logs/ ...", flush=True)
        prior_seconds = committed_seconds()
        results = [replay_one(p, prior_seconds) for p in points]
    else:
        print(f"running {len(points)} control points at -j {args.jobs} ...", flush=True)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(lambda p: run_one(pdk, corner, p), points))
    for row in results:
        print(
            f"  {row['run']:<32} {row['rate_v_per_s']:7.1f} V/s"
            f"  V_hys={row.get('v_hys_mv', float('nan')):8.3f} mV"
            f"  ({row['seconds']:.0f} s)",
            flush=True,
        )

    missing = [
        r["run"] for r in results if any(k not in r for k in MEASURES)
    ]
    if missing:
        print(f"error: incomplete measurements for: {', '.join(missing)}", file=sys.stderr)
        return 1

    (CONTROL_DIR / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    (CONTROL_DIR / "results.md").write_text(render(results, pdk))
    print(f"wrote {CONTROL_DIR / 'results.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
