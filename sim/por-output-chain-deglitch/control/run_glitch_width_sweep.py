#!/usr/bin/env python3
"""Glitch-width sweep for sim/por-output-chain-deglitch/ (issue #182).

    python3 sim/por-output-chain-deglitch/control/run_glitch_width_sweep.py

The deglitch dwell's LOWER bound is a glitch-rejection bound, and
`design/por_output_chain.md` records a real prior failure at it: with
`CDG` = 98 fF the dwell measured 1.07 us and a **1 us** `POR_RAW` glitch
propagated through to `PGDG`, restarting the one-shot at 30/81 PVT points.
`../testbench/stimulus.spice` therefore applies 1 us chatter and asserts that
`PGDG` does not move.

That check answers "is 1 us rejected?" but not "by how much?". Post-layout
(`records/20260811-055634-d0ee17d.md`) the answer to the second question got
materially worse without the first one changing: `pgdg_min_during_chatter`
falls from 2.94 V to 2.54 V against the same 2.5 V bound. This sweep measures
the margin directly -- it walks the glitch WIDTH until the filter stops
rejecting, for the schematic and the post-layout netlist, at the two fast
corners where the dwell is shortest -- so the lower-bound margin can be
quoted as a ratio against the 1 us the testbench applies instead of inferred
from a dwell number compared to a historical one.

Writes:

    decks/w_<variant>__<point>__<width>.spice   the exact deck as run
    decks/dut_<variant>.spice                   the DUT netlist it includes
    logs/w_<variant>__<point>__<width>.log      raw ngspice output, verbatim
    width_results.md                            the sweep table

This is a **control experiment, not a record** -- it overwrites its own
outputs in place on every run, and two corners is a diagnosis, not corner-grid
evidence (see ``sim/README.md``, "Control experiments"). No traces are kept:
the verdict here is four scalars per run, all of them in the logs.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FRAGMENT = CONTROL_DIR / "glitch_width_sweep.spice"
SCHEMATIC_NETLIST = REPO_ROOT / "design" / "netlist" / "por_output_chain.spice"
POSTLAYOUT_NETLIST = REPO_ROOT / "layout" / "postlayout" / "por_output_chain.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

STOP_S = 1.08e-3
TSTEP_S = 20e-9
EDGE_S = 0.1e-6  # POR_RAW edge rate, same as ../testbench/stimulus.spice
GLITCH_START_S = 1000.0e-6  # POR_RAW reaches 0 here; the glitch is measured from here

# Glitch widths in microseconds. 1.0 us is the width ../testbench/stimulus.spice
# applies and the width the historical CDG = 98 fF failure let through.
WIDTHS_US = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 4.0]

VARIANTS = [
    ("schematic", SCHEMATIC_NETLIST),
    ("postlayout", POSTLAYOUT_NETLIST),
]

# The two fast corners: the schematic record's shortest dwell and the
# post-layout record's shortest dwell (and its worst pgdg_min_during_chatter).
POINTS: list[tuple[str, str, float, float]] = [
    ("ff_125c_2.97v", "ff", 125.0, 2.97),
    ("ff_125c_3.63v", "ff", 125.0, 3.63),
]


def main() -> int:
    try:
        pdk = find_pdk()
        ngspice_version = runner.ngspice_version()
    except (PdkNotFound, runner.NgspiceMissing) as exc:
        print(exc, file=sys.stderr)
        return 3

    options = list(json.loads(MANIFEST.read_text()).get("options", []))
    deck_dir = CONTROL_DIR / "decks"
    log_dir = CONTROL_DIR / "logs"
    for d in (deck_dir, log_dir):
        d.mkdir(exist_ok=True)

    for variant, path in VARIANTS:
        (deck_dir / f"dut_{variant}.spice").write_text(path.read_text())

    results: dict[tuple[str, str, float], dict[str, float]] = {}

    for variant, _ in VARIANTS:
        for point_id, corner_name, temp_c, vdd in POINTS:
            for width_us in WIDTHS_US:
                run_id = f"w_{variant}__{point_id}__{width_us:g}us"
                deck_path = deck_dir / f"{run_id}.spice"
                log_path = log_dir / f"{run_id}.log"
                deck_path.write_text(
                    compose_deck(pdk, variant, corner_name, temp_c, vdd, width_us, options, deck_dir)
                )
                proc = subprocess.run(
                    ["ngspice", "-b", deck_path.name],
                    capture_output=True,
                    text=True,
                    cwd=deck_dir,
                    check=False,
                    timeout=1800,
                )
                output = proc.stdout + "\n" + proc.stderr
                log_path.write_text(output)
                meas = runner.parse_bare_measurements(output)
                missing = [k for k in ("pgdgmin", "timbefore", "timafter", "pgdgbmax") if k not in meas]
                if missing:
                    print(f"{run_id}: missing measurements {missing}", file=sys.stderr)
                    print(output[-3000:], file=sys.stderr)
                    return 2
                results[(variant, point_id, width_us)] = meas
                print(
                    f"{run_id}: pgdg_min {meas['pgdgmin']:.4f} V, "
                    f"TIM {meas['timbefore']:.4f} -> {meas['timafter']:.4f} V"
                )

    write_results(results, pdk, ngspice_version)
    print(f"wrote {(CONTROL_DIR / 'width_results.md').relative_to(REPO_ROOT)}")
    return 0


def compose_deck(
    pdk,
    variant: str,
    corner_name: str,
    temp_c: float,
    vdd: float,
    width_us: float,
    options: list[str],
    deck_dir: Path,
) -> str:
    corner = corners_mod.CORNERS[corner_name]
    fragment_rel = os.path.relpath(FRAGMENT, deck_dir)
    width_s = width_us * 1e-6
    t_lo = GLITCH_START_S - EDGE_S
    t_hi = GLITCH_START_S
    t_end = GLITCH_START_S + width_s
    t_up = t_end + EDGE_S
    # TIM is sampled just before the glitch and at its minimum over the 40 us
    # after it: a glitch that reaches PGDG fires XMDIS and slams TIM to VSS.
    lines = [
        f"* por-output-chain-deglitch glitch-width sweep -- {variant} @ {corner_name} /"
        f" {temp_c:g} C / {vdd:g} V, {width_us:g} us glitch"
        " -- GENERATED by run_glitch_width_sweep.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}",
        "",
        f".param vdd_val={vdd!r}",
        f".param t_glitch_lo={t_lo!r}",
        f".param t_glitch_hi={t_hi!r}",
        f".param t_glitch_end={t_end!r}",
        f".param t_glitch_up={t_up!r}",
        f".param stop_s={STOP_S!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, temp_c, options)
    lines += [
        "",
        f'.include "{fragment_rel}"',
        f'.include "dut_{variant}.spice"',
        "",
        f".tran {TSTEP_S!r} {{stop_s}}",
        "",
        f".meas tran timbefore find v(xdut1.tim) at={GLITCH_START_S - 1e-6!r}",
        f".meas tran pgdgmin min v(xdut1.pgdg) from={t_lo!r} to={t_end + 40e-6!r}",
        f".meas tran pgdgbmax max v(xdut1.pgdgb) from={t_lo!r} to={t_end + 40e-6!r}",
        f".meas tran timafter min v(xdut1.tim) from={t_lo!r} to={t_end + 40e-6!r}",
        "",
        ".end",
        "",
    ]
    return "\n".join(lines)


def verdict(meas: dict[str, float]) -> str:
    """Did the glitch get through the filter?

    Functional criterion, not a voltage one: a glitch that reaches PGDG drives
    PGDGB high, fires XMDIS, and discharges the one-shot's TIM -- which is
    exactly what restarted the timer at 30/81 points in the historical
    CDG = 98 fF failure. TIM only ever *rises* while the filter is rejecting
    (XMPT is still charging it), so any material fall is XMDIS having
    conducted, and the size of the fall says how far the pulse was set back.
    PGDG merely drooping is not the failure; losing timer charge is.
    """
    lost = (meas["timbefore"] - meas["timafter"]) / meas["timbefore"]
    if lost > 0.5:
        return "**through**"
    if lost > 0.01:
        return "partial"
    return "rejected"


def write_results(results: dict, pdk, ngspice_version: str) -> None:
    lines: list[str] = [
        "# por-output-chain-deglitch glitch-width sweep -- generated, do not edit",
        "",
        "Generated by `sim/por-output-chain-deglitch/control/run_glitch_width_sweep.py`"
        " (issue #182). Re-run it to regenerate this file, the decks under `decks/`"
        " and the raw ngspice logs under `logs/`. The numbers quoted in"
        " `design/por_output_chain.md` are transcribed from here, and from nowhere"
        " else.",
        "",
        "This is a **control experiment, not a record**: two corners walking one"
        " stimulus parameter is a diagnosis, and this directory is overwritten in"
        " place on every run. The corner-grid evidence for"
        " [`por-brownout`](../../../spec/target-spec.md#por-brownout) stays in"
        " `sim/por-output-chain-deglitch/records/` (`sim/README.md`, \"Control"
        " experiments\").",
        "",
        f"- ngspice: `{ngspice_version}`",
        f"- PDK: `{pdk.variant}@{pdk.version}` ({pdk.source})",
        f"- harness: `{HARNESS_VERSION}`",
        "",
        "`rejected` = the one-shot's `TIM` keeps its charge (it loses under 1 %);"
        " `partial` = `TIM` lost 1-50 % of it, i.e. the pulse was set back but not"
        " restarted; `**through**` = `TIM` lost more than half its pre-glitch charge, i.e."
        " `XMDIS` fired and the reset pulse restarted -- the failure mode"
        " `design/por_output_chain.md` records at `CDG` = 98 fF.",
        "",
    ]

    for point_id, _, _, _vdd in POINTS:
        lines += [
            f"## `{point_id}`",
            "",
            "| glitch width | `schematic` `PGDG` min | verdict | `postlayout` `PGDG` min | verdict |",
            "| ---: | ---: | --- | ---: | --- |",
        ]
        for width_us in WIDTHS_US:
            sch = results[("schematic", point_id, width_us)]
            pl = results[("postlayout", point_id, width_us)]
            marker = " **(the testbench's chatter width)**" if width_us == 1.0 else ""
            lines.append(
                f"| {width_us:g} us{marker} | {sch['pgdgmin']:.4f} V | {verdict(sch)} |"
                f" {pl['pgdgmin']:.4f} V | {verdict(pl)} |"
            )
        lines.append("")
        for variant, _ in VARIANTS:
            last_ok = None
            first_bad = None
            for width_us in WIDTHS_US:
                v = verdict(results[(variant, point_id, width_us)])
                if v == "rejected":
                    last_ok = width_us
                elif first_bad is None:
                    first_bad = width_us
            if first_bad is None:
                lines.append(f"- `{variant}`: rejected every width swept, up to {WIDTHS_US[-1]:g} us.")
            else:
                lines.append(
                    f"- `{variant}`: rejects cleanly up to {last_ok:g} us and is"
                    f" disturbed by {first_bad:g} us -- i.e. {last_ok / 1.0:.2f}x the 1 us"
                    f" glitch ../testbench/stimulus.spice applies."
                )
        lines.append("")

    (CONTROL_DIR / "width_results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
