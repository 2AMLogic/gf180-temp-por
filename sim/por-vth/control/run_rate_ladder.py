#!/usr/bin/env python3
"""Ramp-rate control for sim/por-vth/'s fixed-duration confound (issue #206).

    python3 sim/por-vth/control/run_rate_ladder.py [-j N]

The parent deck (``../testbench/stimulus.spice`` before this issue) held the
DURATION of each quasi-static ramp segment at a fixed 4 ms, so it traversed
``vdd_val - 2.0 V`` in a fixed time and its ramp RATE was a function of the
supply: 242.5 / 325 / 407.5 V/s at 2.97 / 3.30 / 3.63 V, a 1.68x spread. The
supply axis of the 81-point grid was therefore simultaneously a ramp-rate
axis, and no measurement on that grid could separate the two -- see
``sim/por-vth/records/20260811-073945-12473c3.md`` (``v_hys_mv`` = 261.092 mV
at ``ss_-40c_3.63v`` against a 250 mV ceiling).

This is the SECOND, distinct control under this experiment's ``control/``
directory, per ``sim/README.md``'s "one control/ may hold more than one
control" rule: ``run_ramp_rate_probe.py`` (issue #187/#218, DR-021) already
answers *why* the post-layout reading exceeded its ceiling (a three-term
decomposition into static hysteresis / VREF displacement / comparator delay).
This control answers a narrower, downstream question -- *which* constant
rate the production stimulus should now run at, and *how much* residual
displacement that choice still carries -- at the exact two rates the fixed
deck uses (242.5 V/s production, 121.25 V/s guard) rather than at
``run_ramp_rate_probe.py``'s dyadic ladder (which does not include either).
Its own supply-matched arm C independently reproduces that script's Arm C
242.5 V/s row (215.655 mV there vs. 215.660 mV here, same corner, same rate,
two different harness runs -- the ~0.005 mV gap is run-to-run/precision
noise, not a discrepancy) as a cross-check that both controls are measuring
the same thing.

This control answers the two questions the fix needs evidence for, at the
binding corner (`ss` / -40 C):

    rate-ladder-<dut>      dVDD/dt swept 407.5 -> 60.6 V/s at VDD = 3.63 V,
                            on both the schematic and the extracted netlist,
                            INCLUDING the exact two rates the fixed
                            production stimulus uses (242.5 and 121.25 V/s).
                            V_hys(dVDD/dt) directly, so the chosen production
                            rate's residual displacement, and the
                            quasi-staticity guard's rate-gap bound, are both
                            measured numbers, not guesses.
    rate-matched-supply    the extracted netlist, VDD in {2.97, 3.30, 3.63} V,
                            all three held at ONE rate (242.5 V/s -- the
                            parent grid's own slowest, and the production
                            stimulus's chosen rate). If the parent's supply
                            trend was really a rate trend, this arm is flat
                            (or nearly so) instead.

Outputs, all regenerated on every run (a control is not a record), prefixed
``sel_`` so they never collide with ``run_ramp_rate_probe.py``'s own
``decks/``/``logs/`` filenames in this shared directory:

    decks/sel_<variant>.spice   the exact deck as run
    logs/sel_<variant>.log      raw ngspice output, verbatim
    rate_selection_results.md   the comparison tables, generated from those logs

This is a diagnosis, not a recorded PVT result: a handful of points at one
corner is not evidence about the corner grid, so it deliberately does NOT go
through sim/run_corners.py and does NOT mint a record under ../records/. The
corner-grid evidence for the fixed production stimulus is
../records/*.md (new records minted after this control), per sim/README.md.

Everything except the swept variable is fixed by construction: every deck is
composed from the same fragment (``rate_ladder.spice``) in the same process,
from the same PDK, with the corner sections and solver options read from the
harness and from ``../testbench/tb.json`` rather than restated here.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import argparse
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

FRAGMENT = CONTROL_DIR / "rate_ladder.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

# The binding corner of record 20260811-073945-12473c3.
CORNER = "ss"
TEMP_C = -40.0

#: DUT id -> netlist path.
DUTS: dict[str, Path] = {
    "postlayout": REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice",
    "schematic": REPO_ROOT / "design" / "netlist" / "temp_por_top.spice",
}

# The parent deck's own historical rate (4 ms fixed duration at 3.63 V), the
# chosen production rate (the parent grid's own slowest -- what its 2.97 V
# column already ran at), the chosen quasi-staticity-guard rate (half that),
# and two slower rungs to pin down the asymptote/slope.
RATES_V_PER_S = (407.5, 242.5, 121.25, 60.625)

#: (VDD, label) for the rate-matched-supply arm, all at the chosen production
#: rate. 3.63 V duplicates the ladder's own 242.5 V/s rung by construction
#: (same tramp, same corner, same DUT) -- included anyway so results.md's
#: table is self-contained and the duplication is itself the cross-check.
MATCHED_RATE_V_PER_S = 242.5
MATCHED_SUPPLIES_V = (2.97, 3.30, 3.63)


def tramp_s(vdd: float, rate_v_per_s: float) -> float:
    return (vdd - 2.0) / rate_v_per_s


def compose(pdk, corner, options: list[str], dut: str, vdd: float, tramp: float) -> str:
    netlist = DUTS[dut]
    deck_dir = CONTROL_DIR / "decks"
    t1 = 1.0e-3 + tramp
    t2 = t1 + 6.0e-3
    t3 = t2 + tramp
    t4 = t3 + 2.0e-3
    tstop = t4
    rate = (vdd - 2.0) / tramp
    lines = [
        f"* por-vth rate-ladder control -- {dut} @ {corner.name}/{TEMP_C:g}C/{vdd:g}V,"
        f" tramp={tramp * 1e3:g} ms ({rate:.1f} V/s)"
        " -- GENERATED by run_rate_ladder.py, do not edit",
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
        # absolute path of whatever worktree produced it -- same idiom as
        # sim/por-brownout-slew/control/ and sim/por-glitch/control/.
        f'.include "{os.path.relpath(FRAGMENT, deck_dir)}"',
        f'.include "{os.path.relpath(netlist, deck_dir)}"',
        "",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        f"tran 10u {tstop!r}",
        "meas tran vpor_rise find v(vdd) when v(xdut.por_raw)=1.5 rise=1",
        "meas tran vpor_rise_last find v(vdd) when v(xdut.por_raw)=1.5 rise=last",
        "meas tran vpor_fall find v(vdd) when v(xdut.por_raw)=1.5 fall=1",
        "meas tran vpor_fall_last find v(vdd) when v(xdut.por_raw)=1.5 fall=last",
        f"meas tran vref_settle find v(xdut.vref) at={t2 - 0.1e-3!r}",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def _points() -> list[tuple[str, str, str, float, float]]:
    """(run_id, arm, dut, vdd_val, tramp_s)."""
    pts: list[tuple[str, str, str, float, float]] = []
    for dut in ("postlayout", "schematic"):
        for rate in RATES_V_PER_S:
            pts.append(
                (f"sel_rate_{dut}_{rate:.2f}vs", f"rate-ladder-{dut}", dut, 3.63, tramp_s(3.63, rate))
            )
    for vdd in MATCHED_SUPPLIES_V:
        pts.append(
            (
                f"sel_matched_postlayout_{vdd:.2f}v",
                "rate-matched-supply",
                "postlayout",
                vdd,
                tramp_s(vdd, MATCHED_RATE_V_PER_S),
            )
        )
    return pts


def run_one(pdk, corner, options: list[str], point: tuple[str, str, str, float, float]) -> dict:
    run_id, arm, dut, vdd, tramp = point
    deck = compose(pdk, corner, options, dut, vdd, tramp)
    meas = runner.run_deck(run_id, deck, CONTROL_DIR)
    row = {
        "run": run_id,
        "arm": arm,
        "dut": dut,
        "vdd_v": vdd,
        "tramp_ms": tramp * 1e3,
        "rate_v_per_s": (vdd - 2.0) / tramp,
    }
    row.update(meas)
    if "vpor_rise" in row and "vpor_fall" in row:
        row["v_hys_mv"] = (row["vpor_rise"] - row["vpor_fall"]) * 1e3
    return row


LADDER_HEADER = "| tramp | dVDD/dt | VPOR↑ | VPOR↓ | V_hys | VREF (settled) |"
LADDER_RULE = "|---:|---:|---:|---:|---:|---:|"


def _ladder_row(r: dict) -> str:
    return (
        f"| {r['tramp_ms']:.3f} ms | {r['rate_v_per_s']:.2f} V/s |"
        f" {r['vpor_rise']:.5f} V | {r['vpor_fall']:.5f} V |"
        f" **{r['v_hys_mv']:.3f} mV** | {r['vref_settle']:.6f} V |"
    )


def _static_and_slope(rows: list[dict]) -> tuple[float, float]:
    """(zero-rate limit, slope) from the two slowest rows -- the local
    gradient closest to the static limit."""
    a, b = sorted(rows, key=lambda r: r["rate_v_per_s"])[:2]
    slope = (b["v_hys_mv"] - a["v_hys_mv"]) / (b["rate_v_per_s"] - a["rate_v_per_s"])
    return a["v_hys_mv"] - slope * a["rate_v_per_s"], slope


def render(results: list[dict], pdk, options: list[str]) -> str:
    by_arm: dict[str, list[dict]] = {}
    for row in results:
        by_arm.setdefault(row["arm"], []).append(row)

    out: list[str] = [
        "# `por-vth` ramp-rate SELECTION control — results",
        "",
        "**Generated by `run_rate_ladder.py`. Do not edit — re-run it.** Every",
        "number below is read out of `logs/` by that script; nothing here is",
        "transcribed by hand. This is the SECOND control under this",
        "directory (`sim/README.md`'s \"one `control/` may hold more than one",
        "control\" rule) — `run_ramp_rate_probe.py`'s `results.md` (issue",
        "#187/#218, DR-021) already root-causes *why* the post-layout reading",
        "exceeded its ceiling; this one measures the two specific rates",
        "(242.5 / 121.25 V/s) the fixed production stimulus now uses, which",
        "are not rungs on that script's dyadic ladder. Its own `decks/`/`logs/`",
        "filenames are `sel_`-prefixed so they never collide with that",
        "script's outputs in this shared directory.",
        "",
        f"- PVT point: `{CORNER}` / {TEMP_C:g} °C — the binding corner of"
        " `../records/20260811-073945-12473c3.md` (one corner: a control is"
        " not corner evidence, see `sim/README.md`)",
        f"- PDK: `{pdk.variant}` @ `{pdk.version}`",
        f"- Harness version: `{HARNESS_VERSION}`",
        "- Solver options (from `../testbench/tb.json`): " + ", ".join(f"`{o}`" for o in options),
        "- DUT netlists: `layout/postlayout/temp_por_top.spice` (extracted),"
        " `design/netlist/temp_por_top.spice` (schematic)",
        "- Decision this control informs:"
        " `sim/por-vth/testbench/stimulus.spice`'s chosen `dvdd_dt_v_per_s`"
        " (issue #206)",
        "- Companion control: `sim/por-vth/control/results.md`"
        " (`run_ramp_rate_probe.py`, issue #187/#218, DR-021) -- the"
        " decomposition this selection builds on.",
        "",
        "## A/B — ramp-rate ladder at the binding corner, VDD = 3.63 V",
        "",
        "One variable: how long each quasi-static segment takes. The"
        " 407.5 V/s row **is** the historical parent deck (`tramp` = 4 ms)"
        " and reproduces its record: 261.092 mV (extracted),"
        " 248.740/248.741 mV (schematic).",
        "",
    ]
    for dut in ("postlayout", "schematic"):
        rows = sorted(by_arm.get(f"rate-ladder-{dut}", []), key=lambda r: -r["rate_v_per_s"])
        if not rows:
            continue
        out += [f"### {dut}", "", LADDER_HEADER, LADDER_RULE]
        out += [_ladder_row(r) for r in rows]
        static, slope = _static_and_slope(rows)
        out += [
            "",
            f"Zero-rate limit (extrapolated from the two slowest rungs): "
            f"**{static:.3f} mV**, local slope **{slope:.4f} mV/(V/s)**.",
            "",
        ]

    matched = sorted(by_arm.get("rate-matched-supply", []), key=lambda r: r["vdd_v"])
    if matched:
        out += [
            "## C — supply swept at ONE ramp rate"
            f" ({MATCHED_RATE_V_PER_S:g} V/s), extracted netlist",
            "",
            "One variable: the supply. The historical parent deck could not do"
            " this -- its fixed 4 ms ramp made rate a function of supply -- so"
            " this arm stretches `tramp` instead, to hold dVDD/dt at the"
            " parent grid's own slowest value (its native 2.97 V rate).",
            "",
            "| VDD | tramp | dVDD/dt | VPOR↑ | VPOR↓ | V_hys |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in matched:
            out.append(
                f"| {r['vdd_v']:.2f} V | {r['tramp_ms']:.3f} ms | {r['rate_v_per_s']:.2f} V/s |"
                f" **{r['vpor_rise']:.5f} V** | {r['vpor_fall']:.5f} V |"
                f" **{r['v_hys_mv']:.3f} mV** |"
            )
        rise_spread_mv = (max(r["vpor_rise"] for r in matched) - min(r["vpor_rise"] for r in matched)) * 1e3
        hys_spread_mv = max(r["v_hys_mv"] for r in matched) - min(r["v_hys_mv"] for r in matched)
        out += [
            "",
            f"Rate-matched, `VPOR↑` spreads **{rise_spread_mv:.3f} mV** and"
            f" `V_hys` spreads **{hys_spread_mv:.3f} mV** over the whole"
            " ±10 % supply window, against the historical parent record's"
            " 20.64 mV / 49.710 mV (`vpor_rise_v` 2.62809-2.64873 V,"
            " `v_hys_mv` 211.382-261.092 mV, same corner, fixed-4ms deck).",
            "",
        ]

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
    corner = corners_mod.CORNERS[CORNER]

    (CONTROL_DIR / "decks").mkdir(exist_ok=True)
    (CONTROL_DIR / "logs").mkdir(exist_ok=True)

    points = _points()
    jobs = args.jobs or min(cliutil.default_jobs(), len(points))
    print(f"running {len(points)} points at -j {jobs} ...")
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(
            pool.map(lambda p: run_one(pdk, corner, options, p), points)
        )

    missing = [r["run"] for r in results if "v_hys_mv" not in r]
    if missing:
        print(f"missing measurements for: {', '.join(missing)}", file=sys.stderr)
        return 2

    body = render(results, pdk, options)
    (CONTROL_DIR / "rate_selection_results.md").write_text(body)
    print(f"wrote {(CONTROL_DIR / 'rate_selection_results.md').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
