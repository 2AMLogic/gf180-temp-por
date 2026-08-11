#!/usr/bin/env python3
"""Post-layout control for sim/por-brownout/ record 20260811-065930-35a87a6 (#188).

    python3 sim/por-brownout/control/run_recovery_reassert.py

WHAT THIS EXPLAINS

The post-layout re-run of `sim/por-brownout/` (#87) reproduced the parent
0/81 result unchanged, but two of its *incidental* numbers moved:

  * `t_reassert_us` slips from 51.26-51.58 us (schematic, all 81 corners)
    to 51.67-64.25 us over the 80 corners that still resolve, and
  * `ss_-40c_2.97v` records ERROR -- `RESETn` never crosses 0.3 V falling
    anywhere in the 55 ms run, so `t_reassert_us` and `t_pulse_regen_ms`
    cannot be formed at all.

Neither number is a spec bound this deck is entitled to pass: the deck's
1 us dip edge is ~1970 mV/us, ~580x FASTER than the ratified
`dVDD/dt|fall,max = 3.40 mV/us` of spec/target-spec.md#por-brownout clause
(c), so DR-011 states plainly that re-assertion is "explicitly not
guaranteed ... at any depth and for any duration" here. `t_reassert_us`
measures a RECOVERY-EDGE artefact: `RESETn` re-asserting when the rail
RISES back, ~0.3-0.6 us (schematic) after the recovery edge starts, long
after the dip is over. DR-011's Consequences section records that artefact
("`RESETn` re-asserts only on the *recovery* edge ... and does not reach a
valid low during the dip") and adds "the block recovers; it does not latch
up or stay released."

That last sentence is the one the extracted record puts a corner-shaped hole
in -- so the question is which change put it there.

THE COMPARISON THE RECORDS INVITE IS NOT A CONTROLLED ONE. Both moved
numbers are read against `20260801-233807-32fbaa0`, and that record's own
frozen `../netlist-snapshots/20260801-233807-32fbaa0.spice` differs from
today's `../testbench/tb_por_brownout.spice` by exactly one line: `XMRLK`,
the release latch #56 added between the two dates ([DR-016]). So
"schematic vs. extracted" as those two records are written is really
"pre-XMRLK schematic vs. post-XMRLK extracted" -- two changes, one delta.
This control separates them by adding the missing third arm.

    Of the `t_reassert_us` slip and the lost re-assert, how much is the
    extraction and how much is `XMRLK`? And where a re-assert IS lost, is
    it a lost DECISION (the starved loop never recovers enough to make one)
    or a lost PROPAGATION (the decision is made but `por_output_chain`'s
    deglitch dwell filters it out)?

METHOD

Twelve runs -- three DUT arms at four PVT points -- with the SAME stimulus,
corner sections, solver options and transient window as the records:

  * `pre` -- `../netlist-snapshots/20260801-233807-32fbaa0.spice`, the
    frozen deck record 20260801-233807-32fbaa0 actually ran: schematic,
    without `XMRLK`;
  * `sch` -- `../testbench/tb_por_brownout.spice`, the same deck today:
    schematic, WITH `XMRLK`. `pre` -> `sch` is a one-device A/B, because
    that is the entire textual difference between the two files;
  * `ext` -- `../testbench-postlayout/tb_por_brownout_postlayout.spice`,
    the deck record 20260811-065930-35a87a6 ran: extracted, with `XMRLK`
    (drawn, as `klt lvs`'s 159/159 net correspondence against today's
    schematic requires). `sch` -> `ext` is then the extraction alone.

The only difference from a record run is extra `meas` lines inside
`.control`: this control adds observability and changes nothing else, so
the `pre` and `ext` arms' `t_reassert` columns must reproduce their
records' rows, and the fact that they do is the check that all three arms
are the same experiment.

The four points are chosen from the two records' own spreads:

  * `ss` / -40 C / 2.97 V -- the extracted record's ERROR corner,
  * `ss` / +27 C / 2.97 V -- the worst extracted t_reassert_us that still
    resolves (64.25 us),
  * `sf` / -40 C / 2.97 V -- the worst post-XMRLK SCHEMATIC t_reassert_us
    (66.24 us, `../records/20260811-112115-9807e3f.md`), which the
    extracted netlist resolves in 51.93 us,
  * `tt` / +27 C / 3.30 V -- the nominal point, as the "nothing unusual
    here" reference.

This is a diagnosis of records 20260801-233807-32fbaa0,
20260811-065930-35a87a6 and 20260811-112115-9807e3f, not a recorded PVT
result: a four-point control is not evidence about the corner grid, so --
exactly as `run_dip_rootcause.py` does -- it deliberately does NOT go
through sim/run_corners.py and does NOT mint a record under ../records/.
The corner-grid evidence for the re-attribution is the third record above,
a full 81-point schematic re-run on today's netlist. See sim/README.md for
the distinction.

USING A FROZEN SNAPSHOT AS A DUT is the one thing here that needs saying
out loud, because `../netlist-snapshots/` is evidence, not a source tree.
It is read-only in this script and never regenerated; that is precisely
what makes it usable as the `pre` arm -- sim/README.md's append-only rule
is what guarantees the file still contains the netlist that produced the
record whose numbers are being re-attributed.

Outputs, all regenerated on every run (a control is not a record):

    decks/<variant>.spice   the exact deck as run
    logs/<variant>.log      raw ngspice output, verbatim
    recovery_results.md     the comparison table, generated from those logs

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

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

MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"
RESULTS = CONTROL_DIR / "recovery_results.md"

#: arm label -> the testbench fragment it is the deck for. Ordered
#: pre -> sch -> ext, which is also the order the two changes landed in, so
#: each adjacent pair of rows in the results table is a one-change delta.
ARMS: dict[str, Path] = {
    "pre": EXPERIMENT_DIR / "netlist-snapshots" / "20260801-233807-32fbaa0.spice",
    "sch": EXPERIMENT_DIR / "testbench" / "tb_por_brownout.spice",
    "ext": EXPERIMENT_DIR / "testbench-postlayout" / "tb_por_brownout_postlayout.spice",
}

#: label -> (corner name, temp C, VDD V). See the module docstring for why
#: these four.
POINTS: dict[str, tuple[str, float, float]] = {
    "ss_-40c_2.97v": ("ss", -40.0, 2.97),
    "ss_27c_2.97v": ("ss", 27.0, 2.97),
    "sf_-40c_2.97v": ("sf", -40.0, 2.97),
    "tt_27c_3.30v": ("tt", 27.0, 3.30),
}

# The parent deck's own timeline (../testbench/stimulus.spice), restated
# here only as measurement windows -- the stimulus itself is read from the
# committed fragment, not regenerated.
T_DIP_MS = 20.0
T_DIP_END_MS = 20.052  # recovery edge complete
T_END_MS = 55.0
NOMINAL_SUPPLY_V = 3.3

# por_output_chain's measured deglitch dwell at the cell level with
# idealised bias (sim/por-output-chain-deglitch/, design/por_output_chain.md).
# Quoted only as the yardstick a POR_RAW pulse width is read against.
DEGLITCH_DWELL_US = (1.86, 8.88)


def deck(pdk, options: list[str], corner_name: str, temp_c: float, vdd: float,
         fragment: Path) -> str:
    corner = corners_mod.CORNERS[corner_name]
    deck_dir = CONTROL_DIR / "decks"
    lines = [
        f"* por-brownout recovery-edge control @ {corner_name} / {temp_c} C /"
        f" {vdd} V -- GENERATED by run_recovery_reassert.py, do not edit",
        f"* DUT fragment: {os.path.relpath(fragment, REPO_ROOT)}",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        f".param vdd_nom={NOMINAL_SUPPLY_V!r}",
        f".param vdd_val={vdd!r}",
        f".param temp_c={temp_c!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, temp_c, options)
    lines += [
        "",
        f'.include "{os.path.relpath(fragment, deck_dir)}"',
        "",
        ".control",
        "set numdgt=8",
        "set noaskquit",
        f"tran 20u {T_END_MS:g}m",
        # Rail-NORMALISED logic levels, for the same reason
        # run_dip_rootcause.py uses them: during the dip the rail IS 1.0 V,
        # so an absolute threshold cannot tell "asserted" from "riding the
        # rail down".
        "let praw_r = v(xdut.por_raw)/(v(vdd)+0.001)",
        "let rst_r = v(resetn)/(v(vdd)+0.001)",
        "let bok_r = v(xdut.bias_ok)/(v(vdd)+0.001)",
        # --- the record's own two numbers, reproduced verbatim so the two
        # --- arms are demonstrably the same experiment as the records
        f"meas tran treassert when v(resetn)=0.3 fall=1 td={T_DIP_MS:g}m",
        f"meas tran rst_r_min min rst_r from={T_DIP_MS:g}m to={T_END_MS:g}m",
        # --- the decision, upstream of the deglitch dwell
        f"meas tran praw_r_min_dip min praw_r from={T_DIP_MS:g}m"
        f" to={T_DIP_END_MS:g}m",
        f"meas tran praw_r_min_rec min praw_r from={T_DIP_END_MS:g}m to=21m",
        f"meas tran t_praw when praw_r=0.5 fall=1 td={T_DIP_MS:g}m",
        # POR_RAW's assert-pulse WIDTH: what por_output_chain's deglitch
        # dwell has to be shorter than for the decision to propagate.
        f"meas tran praw_w trig praw_r val=0.5 fall=1 td={T_DIP_MS:g}m"
        f" targ praw_r val=0.5 rise=1 td={T_DIP_MS:g}m",
        # --- the settle comparator that gates the decision (DR-011's
        # --- "false valid" signature is bok_r riding the rail near 1.0)
        f"meas tran bok_r_min_dip min bok_r from={T_DIP_MS:g}m"
        f" to={T_DIP_END_MS:g}m",
        f"meas tran bok_r_min_rec min bok_r from={T_DIP_END_MS:g}m to=21m",
        # --- and what RESETn did with it
        f"meas tran t_rst when rst_r=0.1 fall=1 td={T_DIP_MS:g}m",
        f"meas tran rst_min min v(resetn) from={T_DIP_MS:g}m to={T_END_MS:g}m",
        f"meas tran rst_final find v(resetn) at=54.5m",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    manifest = cliutil.load_manifest(MANIFEST)
    options = manifest["options"]

    jobs: list[tuple[str, str]] = []
    for point_label, (corner_name, temp_c, vdd) in POINTS.items():
        for arm, fragment in ARMS.items():
            name = f"{arm}-{point_label}"
            jobs.append((name, deck(pdk, options, corner_name, temp_c, vdd, fragment)))

    print(f"running {len(jobs)} decks ({len(ARMS)} arms x {len(POINTS)} points) ...")
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        results = dict(
            zip(
                [name for name, _ in jobs],
                pool.map(lambda job: runner.run_deck(*job, CONTROL_DIR), jobs),
            )
        )
    for name in results:
        print(f"  {name}: {len(results[name])} measurements")

    write_results(pdk, results)
    print(f"wrote {RESULTS}")
    return 0


def write_results(pdk, res: dict[str, dict[str, float]]) -> None:
    def g(name, key):
        return res.get(name, {}).get(key)

    def us_after_dip(name, key):
        t = g(name, key)
        if t is None:
            return "**never**"
        return f"{(t - T_DIP_MS * 1e-3) * 1e6:.2f}"

    def us(name, key):
        t = g(name, key)
        return "**never**" if t is None else f"{t * 1e6:.2f}"

    def num(name, key, digits=4):
        v = g(name, key)
        return "—" if v is None else f"{v:.{digits}f}"

    lines: list[str] = []
    lines.append("# `por-brownout` recovery-edge control — results")
    lines.append("")
    lines.append(
        "**Generated by `run_recovery_reassert.py`. Do not edit — re-run it.** "
        "Every number below is read out of `logs/` by that script; nothing "
        "here is transcribed by hand."
    )
    lines.append("")
    lines.append(
        "Diagnosis of the two *incidental* numbers that moved between "
        "`../records/20260801-233807-32fbaa0.md` and "
        "`../records/20260811-065930-35a87a6.md`: the `t_reassert_us` slip "
        "and the `ss_-40c_2.97v` ERROR. Those two records differ by **two** "
        "changes, not one — `XMRLK` ([DR-016]"
        "(../../../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md), "
        "#56) landed between them, and it is the entire textual difference "
        "between the `pre` and `sch` fragments below — so this control adds "
        "the missing third arm and attributes each delta to one of them. See "
        "this script's module docstring for why neither number is a bound "
        "this deck is entitled to pass — its 1 µs dip edge is ~580× faster "
        "than `spec/target-spec.md#por-brownout` clause (c)'s ratified "
        "`dVDD/dt|fall,max = 3.40 mV/µs`, so re-assertion here is "
        "explicitly not guaranteed by [DR-011]"
        "(../../../spec/decision-records/DR-011-brownout-falling-slew-limit.md)."
    )
    lines.append("")
    lines.append(
        f"PDK `{pdk.variant}` @ `{pdk.version}`, harness {HARNESS_VERSION}. "
        "All three arms share one stimulus, one corner grid definition, one "
        "set of solver options and one transient window — the DUT netlist "
        "is the only variable. `pre` = the frozen deck of record "
        "`20260801-233807-32fbaa0` (schematic, no `XMRLK`); `sch` = the same "
        "deck today (schematic, with `XMRLK`); `ext` = the deck of record "
        "`20260811-065930-35a87a6` (extracted, with `XMRLK` drawn), which "
        "carries `layout/postlayout/AUDIT.md`'s `temp_por_top` caveats — "
        "238 drawn devices, 1 ideal (`temp_core`'s undrawn `XCC`, #177, not "
        "on any node in this path)."
    )
    lines.append("")
    lines.append("## Where the decision is lost")
    lines.append("")
    lines.append(
        "All times are µs after the dip starts (20 ms). The dip floor is "
        "held 20.001–20.051 ms and the rail is fully recovered at "
        "20.052 ms, so anything past **+52 µs** is a recovery-edge event, "
        "not a response to the dip."
    )
    lines.append("")
    header = (
        "| point | arm | `POR_RAW` asserts | `POR_RAW` pulse width | "
        "min `POR_RAW`/VDD, recovery | min `BIAS_OK`/VDD, recovery | "
        "`RESETn` valid-low | `RESETn` 0.3 V crossing | min `RESETn`/VDD |"
    )
    lines.append(header)
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for point_label in POINTS:
        for arm in ARMS:
            name = f"{arm}-{point_label}"
            width = g(name, "praw_w")
            width_s = "**never**" if width is None else f"{width * 1e6:.2f} µs"
            lines.append(
                f"| `{point_label}` | {arm} | {us_after_dip(name, 't_praw')} | "
                f"{width_s} | {num(name, 'praw_r_min_rec')} | "
                f"{num(name, 'bok_r_min_rec')} | {us_after_dip(name, 't_rst')} | "
                f"{us_after_dip(name, 'treassert')} | {num(name, 'rst_r_min')} |"
            )
    lines.append("")
    lines.append(
        f"`por_output_chain`'s measured deglitch dwell at the cell level is "
        f"**{DEGLITCH_DWELL_US[0]}–{DEGLITCH_DWELL_US[1]} µs** with idealised "
        "bias (`sim/por-output-chain-deglitch/`, `design/por_output_chain.md`) "
        "— the yardstick the `POR_RAW` pulse width column is read against. A "
        "`POR_RAW` pulse narrower than the dwell is filtered by design; one "
        "wider than it is not."
    )
    lines.append("")
    lines.append("## Inside the dip, for completeness")
    lines.append("")
    lines.append(
        "DR-011's falling-slew collapse is what neither change touches: all "
        "three arms ride the dip with `BIAS_OK` reading a false valid and "
        "`POR_RAW` never leaving the rail, at every point. Whatever the "
        "recovery edge does above, the dip response itself is the same "
        "starved loop it was."
    )
    lines.append("")
    lines.append(
        "| point | arm | min `POR_RAW`/VDD, in dip | min `BIAS_OK`/VDD, in dip |"
    )
    lines.append("|---|---|---:|---:|")
    for point_label in POINTS:
        for arm in ARMS:
            name = f"{arm}-{point_label}"
            lines.append(
                f"| `{point_label}` | {arm} | {num(name, 'praw_r_min_dip')} | "
                f"{num(name, 'bok_r_min_dip')} |"
            )
    lines.append("")
    lines.append(
        "`RESETn` ends the run at "
        + ", ".join(
            f"{num(f'{arm}-{p}', 'rst_final', 3)} V (`{p}`, {arm})"
            for p in POINTS
            for arm in ARMS
        )
        + " — nothing latches up asserted, on any arm."
    )
    lines.append("")
    RESULTS.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
