#!/usr/bin/env python3
"""Root-cause control for sim/por-brownout/ record 20260801-233807-32fbaa0 (#55).

    python3 sim/por-brownout/control/run_dip_rootcause.py

The parent record measured `resetn_floor_in_dip_mv` = 999.959-1000 mV at all
81 corners: RESETn does not leave the dip rail during a 1.0 V / 50 us
qualifying dip. #55's hypothesis was that the 1.0 V dip target sits below
bias_core's own operating floor (`vdd_ref90_v` = 1.127-1.788 V), leaving
por_comparator / por_output_chain without the drive to pull RESETn down.

This control tests that hypothesis by varying, one at a time, the three
things it depends on:

  A. dip DEPTH, at the parent deck's own 1 us edge. If the hypothesis holds,
     a dip that stops ABOVE bias_core's floor must behave differently from
     one that goes below it.
  B. dip EDGE RATE, at the parent deck's own 1.0 V depth. The parent deck's
     edge is not a ratified quantity -- spec/target-spec.md#por-ramp-rate
     ratifies a rate envelope for 0 -> VDD ramps only -- so it is a free
     variable that has to be swept before any conclusion is drawn from a
     single choice of it.
  C. IBIAS actually reaching por_output_chain during the dip, at the cell
     level with POR_RAW driven correctly low. This is the direct read of
     "does the cell retain pull-down capability when its bias is starved",
     measured both as reachability (does RESETn get to a valid low, and how
     fast) and as capability (how much current the cell sinks with RESETn
     clamped at the 100 mV valid-low bound).
  D. a counterfactual: the same assembly deck with a VDD-referenced hold
     capacitor added on bias_core's PMOS mirror gate, which is the one node
     the A/B traces implicate. This is a HYPOTHESIS PROBE, not a proposed
     design -- see results.md.
  E. dip DURATION, at the parent deck's own 1 us edge and 1.0 V depth. A and
     B on their own cannot separate "the rail fell too fast for the loop to
     track" from "the dip was over before the loop could respond", because
     lengthening B's edge lengthens the time below VPOR-downarrow too. E
     holds the edge at the parent's 1 us and varies only the dwell, so the
     boundary it finds is a RESPONSE TIME -- which is the number
     spec/target-spec.md#por-brownout's T_dip,min row actually needs.

Outputs, all regenerated on every run (a control is not a record):

    decks/<variant>.spice   the exact deck as run
    logs/<variant>.log      raw ngspice output, verbatim
    nets/<variant>.spice    patched DUT netlist, part D only
    results.md              the comparison tables, generated from those logs

This is a diagnosis of record 20260801-233807-32fbaa0, not a recorded PVT
result: a one-corner sweep is not evidence about the corner grid, so it
deliberately does NOT go through sim/run_corners.py and does NOT mint a
record under ../records/. See sim/README.md for the distinction.

Everything except the one variable per part is fixed by construction: every
deck is composed from the same fragment, in the same process, from the same
PDK, with the corner sections and solver options read from the harness and
from ../testbench/tb.json rather than restated here.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

# The one PVT point the control is taken at. tt / 27 C / 3.30 V is the
# nominal point of the parent grid, and the parent record's failure has
# 0.0045 % spread across all 81 corners, so no corner is more informative
# than any other -- which is exactly why one point is enough here.
CORNER = "tt"
TEMP_C = 27.0
VDD_V = 3.3

# Dip start, fixed for every variant: the parent deck's own 20 ms, by which
# point sim/temp-por-top-release/ has RESETn released at every corner.
T_DIP_MS = 20.0
# Cell-level decks release in 4.215-7.752 ms (design/por_output_chain.md),
# so they dip earlier; 15 ms leaves ~2x margin on the slowest cell-level pulse.
T_DIP_CELL_MS = 15.0
# The parent deck's own dwell, 5x T_dip,min.
T_DWELL_MS = 0.05

ASSEMBLY_FRAGMENT = CONTROL_DIR / "dip_shape.spice"
CELL_FRAGMENT = CONTROL_DIR / "starved_chain.spice"
ASSEMBLY_NETLIST = REPO_ROOT / "design" / "netlist" / "temp_por_top.spice"
CELL_NETLIST = REPO_ROOT / "design" / "netlist" / "por_output_chain.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

# VPOR-downarrow, typical, as MEASURED on this same assembly by
# sim/por-vth/records/20260801-233802-32fbaa0.md (2.38722-2.45092 V over the
# grid). Used only as the instant at which the A/B decks sample the
# comparator's two inputs -- "what does the comparator see at the moment the
# rail crosses its own assert threshold" -- not as a pass/fail bound.
VPOR_FALL_V = 2.39

# Part A: dip depth, at the parent deck's 1 us edge. 2.30 V is ABOVE
# bias_core's worst-case operating floor (1.788 V) and still below
# VPOR-downarrow,min (2.22 V)... 1.90 V is above the floor at most corners,
# 1.50 V and 1.00 V are below it.
DEPTHS_V = [2.30, 1.90, 1.50, 1.00]
EDGE_PARENT_MS = 0.001  # the parent deck's 1 us

# Part B: dip edge duration, at the parent deck's 1.0 V depth. The 0.15 and
# 0.2 ms points bracket design/bias_core.md's independently derived PG slew
# capability (~21 mV/us); without them the boundary is only known to lie
# somewhere in the 7.67...23 mV/us decade, which is too loose to compare.
EDGES_MS = [0.001, 0.1, 0.15, 0.2, 0.3, 1.0, 3.0]

# Part C: current still reaching IBIAS during the dip, as a fraction of the
# 500 nA nominal design/por_output_chain.md is drawn against.
IBIAS_A = [("1x", 500e-9), ("0.5x", 250e-9), ("0.1x", 50e-9), ("0x", 0.0)]

# Part D: the counterfactual hold capacitor on bias_core's PMOS mirror gate
# PG, referenced to VDD. 50 um x 50 um MIM at 2 fF/um^2 = 5 pF per unit.
#
# The third row re-runs the same counterfactual against a 100x longer dwell.
# It exists because the 50 us row shows POR_RAW asserting and RESETn NOT
# following, and that gap has two possible readings: an independent defect
# in por_output_chain, or simply POR_RAW arriving too late for a
# bias-starved deglitch to finish inside a 50 us dwell. Only a longer dwell
# separates them.
BOOTSTRAP = [("none", None, T_DWELL_MS), ("20p", 4, T_DWELL_MS),
             ("20p-long", 4, 5.0)]

# Part E: dip dwell, at the parent deck's 1 us edge and 1.0 V depth. 0.05 ms
# is the parent deck's own dwell; the rest bracket the 326-1567 us brownout
# recovery time design/bias_core.md already measures for the starved loop.
DWELLS_MS = [0.05, 0.2, 0.5, 1.0, 2.0, 5.0]

# VPOR-downarrow,min, ratified (spec/target-spec.md#por-vth-fall). The
# spec's qualifying-dip condition is stated against THIS rail, not against
# the dip floor, so the honest "how long was the dip" column is the time the
# rail spends below it -- which is longer than the programmed dwell by the
# two edge transits.
VPOR_FALL_MIN_V = 2.22

# ngspice prints `name = value` for find/when and `name = value at= t` for
# min/max; both forms have to parse or every min/max silently reads as absent.
_MEAS_RE = re.compile(r"^\s*([a-z_0-9]+)\s*=\s*([-+0-9.eE]+)\s*(?:at=.*)?$")


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def deck_header(pdk, options: list[str]) -> list[str]:
    corner = corners_mod.CORNERS[CORNER]
    lines = [
        f"* por-brownout root-cause control @ {CORNER} / {TEMP_C} C /"
        f" {VDD_V} V -- GENERATED by run_dip_rootcause.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        f".param vdd_nom={VDD_V!r}",
        f".param vdd_val={VDD_V!r}",
        f".param temp_c={TEMP_C!r}",
        "",
        f'.include "{pdk.design_include}"',
    ]
    lines += [f'.lib "{pdk.model_lib}" {section}' for section in corner.sections]
    lines += ["", f".temp {TEMP_C!r}"]
    lines += [f".options {option}" for option in options]
    return lines


def patched_bias_core(mult: int, out_path: Path) -> Path:
    """Write temp_por_top.spice with a VDD-referenced hold cap on PG.

    The ONLY difference from the committed netlist is the one added line.
    Part D is a hypothesis probe about which node is responsible; it is not
    a design change and nothing else in the repo reads this file.
    """
    text = ASSEMBLY_NETLIST.read_text()
    extra = (
        "* --- CONTROL-ONLY hypothesis probe (#55), not part of the design ---\n"
        "XCBOOT VDD PG cap_mim_2f0_m3m4_noshield"
        f" c_width=50u c_length=50u m={mult}\n"
    )
    out: list[str] = []
    in_bias = False
    for line in text.split("\n"):
        if line.startswith(".subckt bias_core"):
            in_bias = True
        if in_bias and line.strip() == ".ends":
            out.append(extra.rstrip("\n"))
            in_bias = False
        out.append(line)
    out_path.write_text("\n".join(out))
    return out_path


def assembly_deck(
    pdk, options, name, dip_v, edge_ms, netlist: Path, dwell_ms=T_DWELL_MS
) -> str:
    t_end_ms = T_DIP_MS + 2 * edge_ms + dwell_ms + 1.0
    t_dip_end_ms = T_DIP_MS + edge_ms + dwell_ms
    deck_dir = CONTROL_DIR / "decks"
    lines = deck_header(pdk, options)
    lines += [
        "",
        f".param t_dip={T_DIP_MS}m",
        f".param t_edge={edge_ms}m",
        f".param t_dwell={dwell_ms}m",
        f".param dip_v={dip_v}",
        "",
        f'.include "{os.path.relpath(ASSEMBLY_FRAGMENT, deck_dir)}"',
        f'.include "{os.path.relpath(netlist, deck_dir)}"',
        "",
        ".control",
        "set numdgt=8",
        "set noaskquit",
        f"tran 20u {t_end_ms}m",
        # Rail-NORMALISED logic levels. An absolute threshold is meaningless
        # here: during the dip the rail IS 1.0-2.3 V, so "v(por_raw) crosses
        # 1.5 V" is satisfied by POR_RAW simply following the rail down while
        # still being a solid logic HIGH. The ratio is what distinguishes
        # "asserted" from "riding the rail", and for RESETn it is also the
        # form the spec bound takes (por-reset-valid-floor: <= 0.1 x VDD).
        "let praw_r = v(xdut.por_raw)/(v(vdd)+0.001)",
        "let rst_r = v(resetn)/(v(vdd)+0.001)",
        "let bok_r = v(xdut.bias_ok)/(v(vdd)+0.001)",
        # the two comparator inputs, and the PMOS mirror's overdrive, AT THE
        # INSTANT the rail crosses its own measured assert threshold
        f"meas tran t_vpor when v(vdd)={VPOR_FALL_V} fall=1 td={T_DIP_MS}m",
        # how long the rail is below the RATIFIED VPOR-downarrow,min -- the
        # rail the spec's qualifying-dip condition is written against
        f"meas tran t_vddlo when v(vdd)={VPOR_FALL_MIN_V} fall=1 td={T_DIP_MS}m",
        f"meas tran t_vddhi when v(vdd)={VPOR_FALL_MIN_V} rise=1 td={T_DIP_MS}m",
        "meas tran vref_pre find v(xdut.vref) at=19.9m",
        "meas tran pg_pre find v(xdut.xbias.pg) at=19.9m",
        "meas tran vdd_pre find v(vdd) at=19.9m",
        "meas tran vref_at_vpor find v(xdut.vref) when"
        f" v(vdd)={VPOR_FALL_V} fall=1 td={T_DIP_MS}m",
        "meas tran sns_at_vpor find v(xdut.xcmp.sns) when"
        f" v(vdd)={VPOR_FALL_V} fall=1 td={T_DIP_MS}m",
        "meas tran pg_at_vpor find v(xdut.xbias.pg) when"
        f" v(vdd)={VPOR_FALL_V} fall=1 td={T_DIP_MS}m",
        # ... and 8 us after the edge starts, a fixed offset every variant
        # shares, so the reference's collapse is comparable across edge rates
        "meas tran vref_p8 find v(xdut.vref) at="
        f"{T_DIP_MS + 0.008}m",
        "meas tran vdd_p8 find v(vdd) at=" f"{T_DIP_MS + 0.008}m",
        "meas tran pg_p8 find v(xdut.xbias.pg) at=" f"{T_DIP_MS + 0.008}m",
        # the decision, and what it did to the output
        f"meas tran praw_r_min min praw_r from={T_DIP_MS}m to={t_dip_end_ms}m",
        f"meas tran t_praw when praw_r=0.5 fall=1 td={T_DIP_MS}m",
        f"meas tran vdd_at_praw find v(vdd) when praw_r=0.5 fall=1 td={T_DIP_MS}m",
        f"meas tran biasok_r_min min bok_r from={T_DIP_MS}m to={t_dip_end_ms}m",
        f"meas tran rst_r_min min rst_r from={T_DIP_MS}m to={t_dip_end_ms}m",
        f"meas tran rst_min min v(resetn) from={T_DIP_MS}m to={t_dip_end_ms}m",
        f"meas tran t_rst when rst_r=0.1 fall=1 td={T_DIP_MS}m",
        f"meas tran vdd_at_rst find v(vdd) when rst_r=0.1 fall=1 td={T_DIP_MS}m",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def cell_deck(pdk, options, name, ibias_a) -> str:
    t_edge_ms = 0.001
    t_dip_end_ms = T_DIP_CELL_MS + t_edge_ms + T_DWELL_MS
    deck_dir = CONTROL_DIR / "decks"
    lines = deck_header(pdk, options)
    lines += [
        "",
        f".param t_dip={T_DIP_CELL_MS}m",
        f".param t_edge={t_edge_ms}m",
        f".param t_dwell={T_DWELL_MS}m",
        f".param ibias_a={ibias_a!r}",
        "",
        f'.include "{os.path.relpath(CELL_FRAGMENT, deck_dir)}"',
        f'.include "{os.path.relpath(CELL_NETLIST, deck_dir)}"',
        "",
        ".control",
        "set numdgt=8",
        "set noaskquit",
        f"tran 20u {t_dip_end_ms}m",
        "let rst_r = v(resetn)/(v(vdd)+0.001)",
        f"meas tran rst_pre find v(resetn) at={T_DIP_CELL_MS - 0.1}m",
        f"meas tran rst_min min v(resetn) from={T_DIP_CELL_MS}m to={t_dip_end_ms}m",
        f"meas tran rst_r_min min rst_r from={T_DIP_CELL_MS}m to={t_dip_end_ms}m",
        f"meas tran rst_end find v(resetn) at={t_dip_end_ms}m",
        f"meas tran t_assert when rst_r=0.1 fall=1 td={T_DIP_CELL_MS}m",
        f"meas tran ndg_end find v(xdut.ndg) at={t_dip_end_ms}m",
        f"meas tran pgdg_end find v(xdut.pgdg) at={t_dip_end_ms}m",
        # capability probe: current sunk by the clamped DUT, pre-dip and at
        # the end of the dwell
        f"meas tran isink_pre find i(vforce) at={T_DIP_CELL_MS - 0.1}m",
        f"meas tran isink_end find i(vforce) at={t_dip_end_ms}m",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def run_deck(name: str, text: str) -> dict[str, float]:
    deck_dir = CONTROL_DIR / "decks"
    log_dir = CONTROL_DIR / "logs"
    deck_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    deck_path = deck_dir / f"{name}.spice"
    deck_path.write_text(text)
    proc = subprocess.run(
        ["ngspice", "-b", deck_path.name],
        capture_output=True,
        text=True,
        cwd=deck_dir,
        check=False,
    )
    output = proc.stdout + "\n" + proc.stderr
    (log_dir / f"{name}.log").write_text(output)
    found: dict[str, float] = {}
    for line in output.splitlines():
        match = _MEAS_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:
                continue
    return found


def fmt(value, digits=4, unit="", missing="—"):
    if value is None:
        return missing
    return f"{value:.{digits}f}{unit}"


def main() -> int:
    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    manifest = load_manifest()
    options = manifest["options"]

    nets_dir = CONTROL_DIR / "nets"
    nets_dir.mkdir(exist_ok=True)

    jobs: list[tuple[str, str]] = []

    for depth in DEPTHS_V:
        name = f"a-depth-{depth:.2f}v"
        jobs.append(
            (name, assembly_deck(pdk, options, name, depth, EDGE_PARENT_MS,
                                 ASSEMBLY_NETLIST))
        )
    for edge in EDGES_MS:
        name = f"b-edge-{edge:g}ms"
        jobs.append(
            (name, assembly_deck(pdk, options, name, 1.0, edge, ASSEMBLY_NETLIST))
        )
    for label, current in IBIAS_A:
        name = f"c-ibias-{label}"
        jobs.append((name, cell_deck(pdk, options, name, current)))
    for label, mult, dwell in BOOTSTRAP:
        name = f"d-cboot-{label}"
        netlist = ASSEMBLY_NETLIST
        if mult is not None:
            netlist = patched_bias_core(mult, nets_dir / f"{name}.spice")
        jobs.append(
            (
                name,
                assembly_deck(
                    pdk, options, name, 1.0, EDGE_PARENT_MS, netlist,
                    dwell_ms=dwell,
                ),
            )
        )
    for dwell in DWELLS_MS:
        name = f"e-dwell-{dwell:g}ms"
        jobs.append(
            (
                name,
                assembly_deck(
                    pdk, options, name, 1.0, EDGE_PARENT_MS, ASSEMBLY_NETLIST,
                    dwell_ms=dwell,
                ),
            )
        )

    print(f"running {len(jobs)} decks at {CORNER} / {TEMP_C} C / {VDD_V} V ...")
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        results = dict(
            zip(
                [name for name, _ in jobs],
                pool.map(lambda job: run_deck(*job), jobs),
            )
        )
    for name in results:
        print(f"  {name}: {len(results[name])} measurements")

    write_results(pdk, manifest, results)
    print(f"wrote {CONTROL_DIR / 'results.md'}")
    return 0


def write_results(pdk, manifest, res: dict[str, dict[str, float]]) -> None:
    def g(name, key):
        return res.get(name, {}).get(key)

    def sg(name, key, digits=4, unit=""):
        v = g(name, key)
        return "—" if v is None else f"{v:.{digits}f}{unit}"

    def vsg(name, at):
        vdd, pg = g(name, f"vdd_{at}"), g(name, f"pg_{at}")
        if at == "at_vpor":
            vdd, pg = VPOR_FALL_V, g(name, "pg_at_vpor")
        if pg is None:
            return "—"
        return f"{(vdd - pg) * 1e3:.1f}"

    def t_below_vpor_us(name):
        """How long the rail actually spends below the ratified
        VPOR-downarrow,min -- the spec's own qualifying-dip clock, which is
        longer than the programmed dwell by the two edge transits."""
        lo, hi = g(name, "t_vddlo"), g(name, "t_vddhi")
        if lo is None or hi is None:
            return "—"
        return f"{(hi - lo) * 1e6:.1f}"

    def crossing(name, edge_ms, t_key, v_key, never, dwell_ms=T_DWELL_MS):
        """Where a rail-normalised crossing happened, and whether it was in
        the dip at all -- the parent record's own failure is that RESETn
        asserts on the RECOVERY edge, after the dip is over."""
        t, v = g(name, t_key), g(name, v_key)
        if t is None or v is None:
            return never
        t_dip_end = (T_DIP_MS + edge_ms + dwell_ms) * 1e-3
        when = "in dip" if t <= t_dip_end + 1e-12 else "**on recovery**"
        dt_us = (t - T_DIP_MS * 1e-3) * 1e6
        dt = f"{dt_us:.1f} µs" if abs(dt_us) < 1000 else f"{dt_us/1000:.3f} ms"
        return f"{v:.4f} V, +{dt}, {when}"

    lines: list[str] = []
    lines.append("# `por-brownout` root-cause control — results")
    lines.append("")
    lines.append(
        "**Generated by `run_dip_rootcause.py`. Do not edit — re-run it.** "
        "Every number below is read out of `logs/` by that script; nothing "
        "here is transcribed by hand."
    )
    lines.append("")
    lines.append(
        f"- PVT point: `{CORNER}` / {TEMP_C:g} °C / {VDD_V:g} V "
        f"(one point — a control is not corner evidence, see `sim/README.md`)"
    )
    lines.append(f"- PDK: `{pdk.variant}` @ `{pdk.version}`")
    lines.append(f"- Harness version: `{HARNESS_VERSION}`")
    lines.append(
        f"- Solver options (from `../testbench/tb.json`): "
        f"`{'`, `'.join(manifest['options'])}`"
    )
    lines.append(
        f"- DUT netlists: `design/netlist/temp_por_top.spice` "
        f"(sha256 `{runner.sha256_file(ASSEMBLY_NETLIST)[:12]}…`), "
        f"`design/netlist/por_output_chain.spice` "
        f"(sha256 `{runner.sha256_file(CELL_NETLIST)[:12]}…`)"
    )
    lines.append(
        "- Diagnoses: `../records/20260801-233807-32fbaa0.md` "
        "(`resetn_floor_in_dip_mv` = 999.959–1000 mV, 0/81 PASS)"
    )
    lines.append(
        "- Conclusion drawn from these tables: "
        "`spec/decision-records/DR-011-brownout-falling-slew-limit.md`"
    )
    lines.append("")

    lines.append("## A — dip depth (parent deck's 1 µs edge)")
    lines.append("")
    lines.append(
        "One variable: how deep the dip goes. `bias_core`'s measured "
        "operating floor is `vdd_ref90_v` = 1.127–1.788 V "
        "(`design/bias_core.md`), so 2.30 V and 1.90 V are **above** it and "
        "1.50 V / 1.00 V are **below** it. `V_sg` is `VDD − PG`, the "
        "overdrive on `bias_core`'s PMOS mirror bank."
    )
    lines.append("")
    lines.append(
        "| dip depth | VREF @ VDD=2.39 V | SNS @ VDD=2.39 V | V_sg pre-dip | "
        "V_sg @ +8 µs | VREF @ +8 µs | POR_RAW asserts | "
        "min RESETn/VDD in dip | RESETn asserts |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for depth in DEPTHS_V:
        n = f"a-depth-{depth:.2f}v"
        lines.append(
            f"| {depth:.2f} V | "
            f"{sg(n,'vref_at_vpor',4,' V')} | {sg(n,'sns_at_vpor',4,' V')} | "
            f"{vsg(n,'pre')} mV | {vsg(n,'p8')} mV | {sg(n,'vref_p8',4,' V')} | "
            f"{crossing(n,EDGE_PARENT_MS,'t_praw','vdd_at_praw','**never**')} | "
            f"{sg(n,'rst_r_min',4)} | "
            f"{crossing(n,EDGE_PARENT_MS,'t_rst','vdd_at_rst','**never**')} |"
        )
    lines.append("")
    lines.append(
        f"VREF pre-dip is {sg('a-depth-1.00v','vref_pre',4,' V')} and V_sg "
        f"pre-dip is {vsg('a-depth-1.00v','pre')} mV at every depth — the dip "
        "has not started yet, so those two columns are a fixed reference "
        "point, not a variable."
    )
    lines.append("")

    lines.append("## B — dip edge rate (parent deck's 1.0 V depth)")
    lines.append("")
    lines.append(
        "One variable: how fast the rail falls. The parent deck's 1 µs edge "
        "is 2.30 V/µs; `spec/target-spec.md#por-ramp-rate` ratifies an "
        "envelope only for 0 → VDD **rising** ramps (1 V/s … 1 V/µs), so no "
        "ratified value governs this column."
    )
    lines.append("")
    lines.append(
        "| edge | slew | t below VPOR↓,min | VREF @ VDD=2.39 V | "
        "V_sg @ VDD=2.39 V | min BIAS_OK/VDD in dip | min POR_RAW/VDD in dip | "
        "POR_RAW asserts | min RESETn/VDD in dip | RESETn asserts |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for edge in EDGES_MS:
        n = f"b-edge-{edge:g}ms"
        slew = 2.3 / (edge * 1e3)  # V per us
        slew_s = f"{slew:.3f} V/µs" if slew >= 0.1 else f"{slew*1e3:.2f} mV/µs"
        edge_s = f"{edge*1e3:g} µs" if edge < 1 else f"{edge:g} ms"
        lines.append(
            f"| {edge_s} | {slew_s} | {t_below_vpor_us(n)} µs | "
            f"{sg(n,'vref_at_vpor',4,' V')} | {vsg(n,'at_vpor')} mV | "
            f"{sg(n,'biasok_r_min',4)} | {sg(n,'praw_r_min',4)} | "
            f"{crossing(n,edge,'t_praw','vdd_at_praw','**never**')} | "
            f"{sg(n,'rst_r_min',4)} | "
            f"{crossing(n,edge,'t_rst','vdd_at_rst','**never**')} |"
        )
    lines.append("")
    lines.append(
        "The two rail-normalised minima are the diagnostic pair. A value "
        "near **1.0** means the node rode the rail down without ever "
        "resolving — for `BIAS_OK` that is a **false valid**, `bias_core` "
        "asserting *bias is good* throughout the very collapse that starves "
        "it. A value near **0** means the node actually resolved."
    )
    lines.append("")
    lines.append(
        "`VPOR↑`/`VPOR↓` are ratified at 2.47–2.73 V / 2.22–2.63 V, so a "
        "`POR_RAW asserts` entry above 2.73 V is a **spurious** assertion at "
        "a rail that is still inside the ratified operating range, not a "
        "correct one."
    )
    lines.append("")

    lines.append("## C — `por_output_chain` alone at the 1.0 V dip rail")
    lines.append("")
    lines.append(
        "One variable: the current still reaching `IBIAS` during the dip. "
        "`POR_RAW` is **driven** low here, i.e. this half assumes the "
        "comparator did its job (on the assembly it does not). "
        "*Reachability* is the free-running DUT into 5 pF; *capability* is "
        "the twin DUT with `RESETn` clamped at the 100 mV valid-low bound."
    )
    lines.append("")
    lines.append(
        "| IBIAS in dip | RESETn pre-dip | RESETn reaches 0.1×VDD at | "
        "min RESETn in dip | RESETn @ end of 50 µs dwell | NDG @ end | "
        "PGDG @ end | I sunk @ 100 mV, released | I sunk @ 100 mV, in dip |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for label, current in IBIAS_A:
        n = f"c-ibias-{label}"
        t = g(n, "t_assert")
        t_s = "never" if t is None else f"{(t - T_DIP_CELL_MS*1e-3)*1e6:.2f} µs"
        ip, ie = g(n, "isink_pre"), g(n, "isink_end")
        # i(vforce) is positive when current flows INTO the clamp's + node,
        # i.e. when the cell is SOURCING against it (released state); the
        # sink current the asserted state delivers is therefore -i(vforce).
        ip_s = "—" if ip is None else f"{-ip*1e6:+.1f} µA"
        ie_s = "—" if ie is None else f"{-ie*1e6:+.1f} µA"
        lines.append(
            f"| {label} ({current*1e9:.0f} nA) | {sg(n,'rst_pre',4,' V')} | "
            f"{t_s} | {sg(n,'rst_min',6,' V')} | {sg(n,'rst_end',6,' V')} | "
            f"{sg(n,'ndg_end',4,' V')} | {sg(n,'pgdg_end',4,' V')} | "
            f"{ip_s} | {ie_s} |"
        )
    lines.append("")
    lines.append(
        "Sign convention: **positive = the cell is sinking**, i.e. pulling "
        "`RESETn` down against the clamp. The negative pre-dip column is the "
        "released state doing the opposite — `XMOP` sourcing into a clamp "
        "held 3.2 V below the rail — and is there only to show the probe is "
        "reading a real, state-dependent current."
    )
    lines.append("")

    lines.append("## D — counterfactual: hold `bias_core`'s mirror gate to VDD")
    lines.append("")
    lines.append(
        "One variable: a VDD-referenced MIM capacitor added on `PG`, "
        "`bias_core`'s PMOS mirror gate. **This is a hypothesis probe, not a "
        "proposed design** — 20 pF is 10 000 µm² of MIM, three times the "
        "whole one-shot capacitor, and nothing in `design/` is changed by "
        "this control. Its only purpose is to test whether `PG`'s inability "
        "to follow a falling rail is the *cause* of the collapse, by "
        "removing it."
    )
    lines.append("")
    lines.append(
        "| PG hold cap | dwell | VREF @ +8 µs | V_sg @ +8 µs | "
        "POR_RAW asserts | min RESETn/VDD in dip | RESETn asserts |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for label, _, dwell in BOOTSTRAP:
        n = f"d-cboot-{label}"
        dwell_s = f"{dwell*1e3:g} µs" if dwell < 1 else f"{dwell:g} ms"
        lines.append(
            f"| {label} | {dwell_s} | {sg(n,'vref_p8',4,' V')} | "
            f"{vsg(n,'p8')} mV | "
            f"{crossing(n,EDGE_PARENT_MS,'t_praw','vdd_at_praw','**never**',dwell)} | "
            f"{sg(n,'rst_r_min',4)} | "
            f"{crossing(n,EDGE_PARENT_MS,'t_rst','vdd_at_rst','**never**',dwell)} |"
        )
    lines.append("")
    lines.append(
        "The 50 µs `20p` row restores `POR_RAW` but **not** `RESETn`. The "
        "`20p-long` row is the same counterfactual against a 100× longer "
        "dwell, and it is what distinguishes *`por_output_chain` has an "
        "independent defect* from *`POR_RAW` simply arrived too late for a "
        "bias-starved deglitch to finish inside 50 µs*."
    )
    lines.append("")

    lines.append("## E — dip duration (parent deck's 1 µs edge and 1.0 V depth)")
    lines.append("")
    lines.append(
        "One variable: how long the dip lasts. A and B cannot separate *the "
        "rail fell too fast to track* from *the dip was over before the loop "
        "could respond*, because lengthening B's edge lengthens the time "
        "below VPOR↓ too. E holds the edge at the parent deck's own 1 µs and "
        "varies only the dwell, so the boundary it finds is a **response "
        "time** — the quantity `spec/target-spec.md#por-brownout`'s "
        "`T_dip,min` row is written against. `t below VPOR↓,min` is the "
        "spec's own clock (rail below the ratified 2.22 V), which exceeds "
        "the programmed dwell by the two edge transits."
    )
    lines.append("")
    lines.append(
        "| dwell | t below VPOR↓,min | POR_RAW asserts | "
        "min RESETn/VDD in dip | min RESETn in dip | RESETn asserts |"
    )
    lines.append("|---|---|---|---|---|---|")
    for dwell in DWELLS_MS:
        n = f"e-dwell-{dwell:g}ms"
        dwell_s = f"{dwell*1e3:g} µs" if dwell < 1 else f"{dwell:g} ms"
        lines.append(
            f"| {dwell_s} | {t_below_vpor_us(n)} µs | "
            f"{crossing(n,EDGE_PARENT_MS,'t_praw','vdd_at_praw','**never**',dwell)} | "
            f"{sg(n,'rst_r_min',4)} | {sg(n,'rst_min',6,' V')} | "
            f"{crossing(n,EDGE_PARENT_MS,'t_rst','vdd_at_rst','**never**',dwell)} |"
        )
    lines.append("")
    lines.append(
        "The parent record's own deck is the first row. `T_dip,min` is "
        "ratified at 10 µs; the spec's qualifying-dip clock for that row is "
        "the ~51 µs of `t below VPOR↓,min`, i.e. 5× the ratified minimum."
    )
    lines.append("")

    (CONTROL_DIR / "results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
