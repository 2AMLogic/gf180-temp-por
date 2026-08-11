#!/usr/bin/env python3
"""Post-layout counterpart of the #74 deglitch-race margin table (#188).

    python3 sim/por-brownout-slew/control/run_postlayout_margin.py
    python3 sim/por-brownout-slew/control/run_postlayout_margin.py --report-only

WHAT THIS ADDS

`run_band_mechanism.py` (#74) established what the ladder's PASS/FAIL column
is the outcome of: a race between `por_output_chain`'s deglitch dwell --
realized under a bias collapse that is still in progress -- and the dip
window closing. At `ss`/-40 C its margin column is what says the ratified
`dVDD/dt|fall,max = 3.40 mV/us` is not a bisected midpoint but a bound with
real room behind it (+108.7 us at 2.97 V, +180.1 us at 3.30 V, +220.6 us at
3.63 V).

That margin was measured on the schematic export. #87's post-layout re-run
of the `n-slew-3.46mvus` rung went 80/81 -> 75/81, which moved the transition
band's lower edge down toward the bound; #188's post-layout rung at the bound
itself then measured **76/81** (`../records/20260811-110825-73ef5e3.md`), so
the room behind 3.40 mV/us is not merely reduced post-layout, it is gone.

The post-layout ladder below the bound (2.50 mV/us 80/81; 2.45, 2.40 and
2.30 mV/us 81/81 each) locates the extracted netlist's own transition edge
between 2.45 and 2.50 mV/us. The VERDICT question is therefore settled by
those grid records, and what is left is the MARGIN question this control
answers: at a candidate re-costed bound, is there real room behind the
verdict, or is the candidate just one bisection step below a FAIL? That is
the same question `results.md`'s margin column answered for the schematic
bound, asked again at the binding family only.

METHOD

Five rungs spanning the post-layout ladder -- the four full-grid rungs #188
recorded (2.30 / 2.40 / 2.45 / 2.50 mV/us) plus the ratified 3.40 mV/us --
at the same binding family (`ss` / -40 C, all three supplies -- the supply
axis is kept for the reason #74 keeps it: the three points do not agree with
each other), run against BOTH netlists:

  * `sch` -- design/netlist/temp_por_top.spice (the schematic export), and
  * `ext` -- layout/postlayout/temp_por_top.spice (#82/PR #180's klt
    extraction).

Every deck is built by `run_band_mechanism.deck()` itself, with the netlist
as its one parameter, so the two arms cannot drift apart in what they
measure. The `sch` arm is re-run here rather than transcribed from
`results.md` so both arms come from the same host, ngspice build and PDK
install; its numbers should reproduce that record's, and a reader can check
that they do.

Post-layout caveat, per sim/README.md's "Netlist provenance" rule: the
extracted netlist carries layout/postlayout/AUDIT.md's `temp_por_top` row --
238 drawn devices with one ideal splice (`temp_core`'s undrawn `XCC`, #177,
not on any node in this path), 136/159 nets carrying parasitics, 23
body/well/plate ties taken from the schematic, and two deck-name
substitutions (klayout-tools#315/#323).

This is a diagnosis, not a recorded PVT result: a one-corner-family sweep is
not evidence about the corner grid, so -- exactly as `run_band_mechanism.py`
does -- it does NOT go through sim/run_corners.py and does NOT mint a record
under ../records/. The corner-grid evidence for the post-layout verdict is
the 3.40 mV/us rung record itself.

Outputs, all regenerated on every run (a control is not a record):

    decks/pl-<arm>-<slew>mvus-<vdd>v.spice   the exact deck as run
    logs/pl-<arm>-<slew>mvus-<vdd>v.log      raw ngspice output, verbatim
    postlayout_margin_results.md             the comparison table

The `pl-` prefix keeps these variants out of `run_band_mechanism.py`'s own
`a-`/`b-` namespace, so neither script can overwrite the other's decks or
logs.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, cliutil, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

# run_band_mechanism.py is not an importable module name from here (it lives
# beside this file, not on sys.path as a package), so load it by path. Reuse
# rather than copy is the whole point: its deck() carries the measurement
# list both arms must share.
_spec = importlib.util.spec_from_file_location(
    "run_band_mechanism", CONTROL_DIR / "run_band_mechanism.py"
)
band = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(band)

#: arm label -> DUT netlist.
ARMS: dict[str, Path] = {
    "sch": REPO_ROOT / "design" / "netlist" / "temp_por_top.spice",
    "ext": REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice",
}

#: The post-layout ladder, plus the bound it is being read against. 2.30 /
#: 2.40 / 2.45 are the extracted netlist's clean-PASS rungs (81/81 each),
#: 2.50 is the lowest extracted rung that fails anywhere (80/81), and 3.40
#: is the ratified bound, which the extracted netlist fails at 76/81.
SLEWS_MVUS = [2.30, 2.40, 2.45, 2.50, 3.40]

RATIFIED_MVUS = 3.40


def variant_name(arm: str, vdd: float, slew_mvus: float) -> str:
    return f"pl-{arm}-{slew_mvus:g}mvus-{vdd:.2f}v"


def read_logs() -> dict[str, dict[str, float]]:
    """Re-derive this control's variants from the logs already on disk.

    Scoped to the ``pl-`` prefix so ``--report-only`` reads only this
    script's own runs and never `run_band_mechanism.py`'s.
    """
    log_dir = CONTROL_DIR / "logs"
    return {
        path.stem: runner.parse_bare_measurements(path.read_text())
        for path in sorted(log_dir.glob("pl-*.log"))
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report_only = "--report-only" in argv

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    options = cliutil.load_manifest(band.MANIFEST)["options"]

    if report_only:
        results = read_logs()
        if not results:
            print("no pl-* logs to report from -- run without --report-only first",
                  file=sys.stderr)
            return 1
    else:
        jobs: list[tuple[str, str]] = []
        for slew in SLEWS_MVUS:
            for vdd in band.SUPPLIES_V:
                for arm, netlist in ARMS.items():
                    jobs.append(
                        (
                            variant_name(arm, vdd, slew),
                            band.deck(pdk, options, vdd, slew, None, netlist),
                        )
                    )
        print(
            f"running {len(jobs)} decks "
            f"({len(ARMS)} arms x {len(SLEWS_MVUS)} rungs x "
            f"{len(band.SUPPLIES_V)} supplies) at {band.CORNER} /"
            f" {band.TEMP_C} C ..."
        )
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            results = dict(
                zip(
                    [name for name, _ in jobs],
                    pool.map(lambda job: runner.run_deck(*job, CONTROL_DIR), jobs),
                )
            )

    write_results(pdk, results)
    print(f"wrote {CONTROL_DIR / 'postlayout_margin_results.md'}")
    return 0


def write_results(pdk, res: dict[str, dict[str, float]]) -> None:
    def g(name, key):
        return res.get(name, {}).get(key)

    def window_close_s(vdd: float, slew: float) -> float:
        return band.T_DIP_S + band.edge_s(vdd, slew) + band.T_DWELL_S

    def us_after_dip(name, key):
        t = g(name, key)
        return None if t is None else (t - band.T_DIP_S) * 1e6

    def fmt_us(value, never="**never**"):
        return never if value is None else f"{value:.1f}"

    lines: list[str] = []
    lines.append("# Post-layout deglitch-race margin at the ratified bound — results")
    lines.append("")
    lines.append(
        "**Generated by `run_postlayout_margin.py`. Do not edit — re-run it.** "
        "Every number below is read out of `logs/pl-*.log` by that script; "
        "nothing here is transcribed by hand."
    )
    lines.append("")
    lines.append(
        "The post-layout counterpart of `results.md`'s (#74) event-timeline "
        "margin column, at the binding family `ss` / −40 °C, for the five "
        "rungs at and around `spec/target-spec.md#por-brownout` clause (c)'s "
        f"ratified `dVDD/dt|fall,max = {RATIFIED_MVUS:g} mV/µs`. See this "
        "script's module docstring for why the schematic arm is re-run here "
        "rather than quoted."
    )
    lines.append("")
    lines.append(
        f"PDK `{pdk.variant}` @ `{pdk.version}`, harness {HARNESS_VERSION}. "
        "`sch` = `design/netlist/temp_por_top.spice`; `ext` = "
        "`layout/postlayout/temp_por_top.spice` (#82/PR #180), which carries "
        "`layout/postlayout/AUDIT.md`'s `temp_por_top` caveats — 238 drawn "
        "devices, 1 ideal (`temp_core`'s undrawn `XCC`, #177, not on any node "
        "in this path)."
    )
    lines.append("")
    lines.append("## Margin: dip window close − `RESETn` valid-low")
    lines.append("")
    lines.append(
        "All times are µs after the dip starts. *window closes* is "
        "`edge + 50 µs dwell`, the end of the window `../testbench/tb.json` "
        "measures `resetn_ratio_min_in_dip` over — so a positive margin is a "
        "PASS at that point and a negative one (or a `RESETn` that never "
        "reaches valid-low) is the FAIL the grid records."
    )
    lines.append("")
    lines.append(
        "| slew (mV/µs) | supply | arm | window closes | `POR_RAW` asserts | "
        "`PGDG` falls | `RESETn` valid-low | margin | Δ margin (ext − sch) |"
    )
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    for slew in SLEWS_MVUS:
        for vdd in band.SUPPLIES_V:
            close_us = (window_close_s(vdd, slew) - band.T_DIP_S) * 1e6
            margins: dict[str, float | None] = {}
            for arm in ARMS:
                name = variant_name(arm, vdd, slew)
                t_rst = us_after_dip(name, "t_rst")
                margins[arm] = None if t_rst is None else close_us - t_rst
            for arm in ARMS:
                name = variant_name(arm, vdd, slew)
                m = margins[arm]
                if arm == "ext" and m is not None and margins["sch"] is not None:
                    delta = f"{m - margins['sch']:+.1f}"
                else:
                    delta = "—"
                flag = "" if (m is not None and m > 0) else " **FAIL**"
                lines.append(
                    f"| {slew:g} | {vdd:.2f} V | {arm} | {close_us:.1f} | "
                    f"{fmt_us(us_after_dip(name, 't_praw'))} | "
                    f"{fmt_us(us_after_dip(name, 't_pgdg'))} | "
                    f"{fmt_us(us_after_dip(name, 't_rst'))} | "
                    f"{('—' if m is None else f'{m:+.1f}')}{flag} | {delta} |"
                )
    lines.append("")
    lines.append("## The state behind the verdict")
    lines.append("")
    lines.append(
        "`V_sg` (= VDD − `PG`) is the overdrive on `bias_core`'s PMOS mirror "
        "bank — the state variable [DR-011]"
        "(../../../spec/decision-records/DR-011-brownout-falling-slew-limit.md) "
        "measures its starved-loop collapse on, where a NEGATIVE value means "
        "the bank is driven fully off and every bias below it is dead. "
        "`ndg_r_max` is how far `por_output_chain`'s deglitch ramp actually "
        "got inside the window (≈0.5–0.7 is the level the PASS rows cross; "
        "0 means it never moved); `rst_r_min` is the grid's own checked "
        "discriminator over the same window, bounded at 0.1."
    )
    lines.append("")
    lines.append(
        "| slew (mV/µs) | supply | arm | min `V_sg` (mV) | peak `NDG`/VDD | "
        "min `POR_RAW`/VDD | min `BIAS_OK`/VDD | min `RESETn`/VDD | "
        "grid verdict |"
    )
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---|")
    for slew in SLEWS_MVUS:
        for vdd in band.SUPPLIES_V:
            for arm in ARMS:
                name = variant_name(arm, vdd, slew)
                rst = g(name, "rst_r_min")
                verdict = "—" if rst is None else ("PASS" if rst <= 0.1 else "**FAIL**")

                def q(key, digits=3):
                    v = g(name, key)
                    return "—" if v is None else f"{v:.{digits}f}"

                vsg = g(name, "vsg_min")
                vsg_s = "—" if vsg is None else f"{vsg * 1e3:+.1f}"
                lines.append(
                    f"| {slew:g} | {vdd:.2f} V | {arm} | {vsg_s} | "
                    f"{q('ndg_r_max')} | "
                    f"{q('praw_r_min', 4)} | {q('bok_r_min', 4)} | "
                    f"{q('rst_r_min', 4)} | {verdict} |"
                )
    lines.append("")
    (CONTROL_DIR / "postlayout_margin_results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
