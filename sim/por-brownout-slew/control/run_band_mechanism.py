#!/usr/bin/env python3
"""Mechanism control for the non-monotonic SS/-40 C transition band (#74).

    python3 sim/por-brownout-slew/control/run_band_mechanism.py

#60's falling-slew ladder (`../records/*.md`) ratified `dVDD/dt|fall,max` at
3.40 mV/us, and surfaced -- without resolving -- a non-monotonic PASS/FAIL
band above it: at `ss`/-40 C the 3.4795 mV/us rung fails all three supply
points while the numerically FASTER 3.613 mV/us rung fails only 2.97 V.
`../records/20260802-120940-3c3e728-boundary.md` records that finding and
offers a hypothesis: DR-011's starved-loop relaxation dynamic shifting "the
phase relationship between the collapsing loop and the measurement window".

A grid record cannot test that hypothesis, because its pass/fail column is
the OUTCOME of the race, not its ingredients. This control measures the
ingredients directly, at the binding family (`ss` / -40 C, all three
supplies), on the same deck the grid ran:

  A. THE EVENT TIMELINE vs SLEW. For each rung: when the rail crosses
     VPOR-downarrow,min; when `POR_RAW` actually asserts and at what rail
     voltage; when the bias-starved deglitch finishes (`PGDG` falls); when
     `RESETn` reaches the spec's 0.1xVDD valid-low; and how much time was
     left in the dip window when it did. The grid's own verdict is
     recomputed from the same trace, so every row can be checked against
     the rung record it corresponds to.

     This separates the two failure modes the grid conflates under one
     "FAIL":
       (i)  NO DECISION -- `POR_RAW` never asserts during the dip at all
            (DR-011's starved loop; the 4.2 mV/us signature, where
            `bias_ok_ratio_min_in_dip` also rides the rail at 0.999), and
       (ii) LATE DECISION -- `POR_RAW` does assert and the rail-collapse-
            starved output chain simply does not finish before the dip
            window closes (the 3.4795 mV/us signature, where
            `por_raw_ratio_min_in_dip` is ~0 yet `resetn_ratio_min_in_dip`
            is 0.9987).

  B. SOLVER RESOLUTION. The same decks re-run with a 4x finer maximum
     timestep. If a knife-edge PASS/FAIL pattern is an artefact of where
     the adaptive timestep grid happens to land relative to the 50 us
     dwell, it moves when the timestep bound moves. If the event times and
     the verdicts are unchanged, the pattern is a property of the circuit,
     not of the integration.

  C. THE COLLAPSE ITSELF -- V_sg, the overdrive on bias_core's PMOS mirror
     bank, at the instant POR_RAW asserts and at its worst inside the dip.
     This is the state variable DR-011 measures the starved loop on, and
     the question it answers is whether a non-monotonic VERDICT sits on top
     of a non-monotonic STATE or a monotone one.

  D. THE DEGLITCH RAMP -- how far por_output_chain's NDG got before the dip
     window closed. A FAIL whose ramp stalls just short of the level the
     PASS rows cross at is a near-tangency between two collapsing analog
     timers, not a dead circuit.

Outputs, all regenerated on every run (a control is not a record):

    decks/<variant>.spice   the exact deck as run
    logs/<variant>.log      raw ngspice output, verbatim
    results.md              the comparison tables, generated from those logs
    results.json            the same numbers, machine-readable, so the
                            derived record that cites this control reads
                            them instead of transcribing them

``--report-only`` regenerates results.md / results.json from the logs
already on disk, without re-simulating.

This is a diagnosis of the ladder records listed above, not a recorded PVT
result: a one-corner-family sweep is not evidence about the corner grid, so
it deliberately does NOT go through sim/run_corners.py and does NOT mint a
record under ../records/. See sim/README.md for the distinction. The
corner-grid evidence for the band's shape is the rung records themselves.

Everything except the swept variable is fixed by construction: every deck is
composed from the same fragment, in the same process, from the same PDK,
with the corner sections and solver options read from the harness and from
../testbench/tb.json rather than restated here.

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

# The corner family the band lives in. Unlike sim/por-brownout/control/,
# which took one point because its parent record's failure had 0.0045 %
# spread over the whole grid, this control MUST keep the supply axis: the
# very thing being diagnosed is that the three ss/-40 C supply points do not
# agree with each other. Process and temperature are fixed at the binding
# corner identified by ../records/20260802-120940-3c3e728-boundary.md.
CORNER = "ss"
TEMP_C = -40.0
SUPPLIES_V = [2.97, 3.30, 3.63]

# Held fixed, identical to ../testbench/gen_rung.py's own constants -- these
# are the parent rungs' stimulus, not free variables of this control.
T_DIP_S = 20.0e-3
DIP_V = 1.0
T_DWELL_S = 50.0e-6
RECOVERY_MARGIN_S = 60.0e-6

# Part A ladder, mV/us. Every slew that ../records/ already ran a full grid
# at is included verbatim so each control row can be checked against that
# rung's own recorded verdict; the rest fill in the band between them.
SLEWS_MVUS = [
    3.351, 3.40, 3.42, 3.44, 3.46, 3.4795, 3.52, 3.56, 3.613, 3.70, 3.85,
    4.00, 4.20,
]

# Part B: the two rungs whose disagreement IS the reported non-monotonicity,
# re-run with a 4x finer maximum timestep (the decks otherwise identical).
RESOLUTION_SLEWS_MVUS = [3.4795, 3.613]
TSTEP_S = 20.0e-6  # the grid's own `tran 20u ...`
FINE_TMAX_S = 5.0e-6

FRAGMENT = CONTROL_DIR / "slew_dip.spice"
ASSEMBLY_NETLIST = REPO_ROOT / "design" / "netlist" / "temp_por_top.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

# VPOR-downarrow,min, ratified (spec/target-spec.md#por-vth-fall). Used only
# as the instant the rail enters the region where a correct POR_RAW
# assertion is expected, not as a pass/fail bound.
VPOR_FALL_MIN_V = 2.22

# The ratified valid-low ratio (spec/target-spec.md#por-reset-valid-floor),
# and the bound ../testbench/tb.json checks `resetn_ratio_min_in_dip`
# against. Read here rather than restated: see load_bounds().
RESETN_RATIO_KEY = "resetn_ratio_min_in_dip"

# ngspice prints `name = value` for find/when and `name = value at= t` for
# min/max; both forms have to parse or every min/max silently reads as absent.
_MEAS_RE = re.compile(r"^\s*([a-z_0-9]+)\s*=\s*([-+0-9.eE]+)\s*(?:at=.*)?$")


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def edge_s(vdd: float, slew_mvus: float) -> float:
    """Edge duration (s) realizing ``slew_mvus`` for a dip from ``vdd`` to
    DIP_V. Identical arithmetic to ../testbench/gen_rung.py's edge_ms_at();
    mV/us is numerically V/ms, so edge_ms = delta_V / slew_mvus."""
    return (vdd - DIP_V) / slew_mvus * 1e-3


def deck(pdk, options: list[str], vdd: float, slew_mvus: float,
         tmax_s: float | None) -> str:
    corner = corners_mod.CORNERS[CORNER]
    edge = edge_s(vdd, slew_mvus)
    t_dip_end = T_DIP_S + edge + T_DWELL_S
    t_end = T_DIP_S + 2 * edge + T_DWELL_S + RECOVERY_MARGIN_S
    t_pre = T_DIP_S - 100e-6
    deck_dir = CONTROL_DIR / "decks"

    def n(value: float) -> str:
        return f"{value:.10g}"

    lines = [
        f"* por-brownout-slew band-mechanism control @ {CORNER} / {TEMP_C} C /"
        f" {vdd} V / {slew_mvus:.6g} mV/us"
        " -- GENERATED by run_band_mechanism.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        f".param vdd_nom={vdd!r}",
        f".param vdd_val={vdd!r}",
        f".param temp_c={TEMP_C!r}",
        "",
        f'.include "{pdk.design_include}"',
    ]
    lines += [f'.lib "{pdk.model_lib}" {section}' for section in corner.sections]
    lines += ["", f".temp {TEMP_C!r}"]
    lines += [f".options {option}" for option in options]
    lines += [
        "",
        f".param t_dip={n(T_DIP_S)}",
        f".param t_edge={n(edge)}",
        f".param t_dwell={n(T_DWELL_S)}",
        f".param t_margin={n(RECOVERY_MARGIN_S)}",
        f".param dip_v={DIP_V!r}",
        "",
        f'.include "{os.path.relpath(FRAGMENT, deck_dir)}"',
        f'.include "{os.path.relpath(ASSEMBLY_NETLIST, deck_dir)}"',
        "",
        ".control",
        "set numdgt=8",
        "set noaskquit",
        (
            f"tran {n(TSTEP_S)} {n(t_end)}"
            if tmax_s is None
            else f"tran {n(TSTEP_S)} {n(t_end)} 0 {n(tmax_s)}"
        ),
        # Rail-NORMALISED logic levels, for the reason ../testbench/tb.json
        # and sim/por-brownout/control/ both give: during the dip the rail
        # IS 1.0 V, so an absolute threshold cannot tell "asserted" from
        # "riding the rail down while still a solid logic HIGH".
        "let bok_r = v(xdut.bias_ok)/(v(vdd)+0.001)",
        "let praw_r = v(xdut.por_raw)/(v(vdd)+0.001)",
        "let rst_r = v(resetn)/(v(vdd)+0.001)",
        "let pgdg_r = v(xdut.xpor.pgdg)/(v(vdd)+0.001)",
        # NDG is the deglitch capacitor node itself: it has to traverse CDG
        # at (starved) I/C before XMG1 flips PGDG. Rail-normalised for the
        # same reason as the rest -- XMG1's trip point moves with the rail.
        "let ndg_r = v(xdut.xpor.ndg)/(v(vdd)+0.001)",
        # V_sg, the overdrive on bias_core's PMOS mirror bank -- the node
        # DR-011 measures the collapse on.
        "let vsg = v(vdd)-v(xdut.xbias.pg)",
        "",
        f"meas tran vdd_pre find v(vdd) at={n(t_pre)}",
        f"meas tran rst_pre find v(resetn) at={n(t_pre)}",
        f"meas tran vsg_pre find vsg at={n(t_pre)}",
        # when the rail enters the region where an assertion is expected
        f"meas tran t_vpor when v(vdd)={VPOR_FALL_MIN_V} fall=1 td={n(T_DIP_S)}",
        # the decision, and the rail it was taken at
        f"meas tran t_praw when praw_r=0.5 fall=1 td={n(T_DIP_S)}",
        "meas tran vdd_at_praw find v(vdd) when praw_r=0.5 fall=1"
        f" td={n(T_DIP_S)}",
        f"meas tran vsg_at_praw find vsg when praw_r=0.5 fall=1 td={n(T_DIP_S)}",
        # the deglitch finishing, and the output reaching valid-low
        f"meas tran t_pgdg when pgdg_r=0.5 fall=1 td={n(T_DIP_S)}",
        f"meas tran t_rst when rst_r=0.1 fall=1 td={n(T_DIP_S)}",
        f"meas tran vdd_at_rst find v(vdd) when rst_r=0.1 fall=1 td={n(T_DIP_S)}",
        f"meas tran t_bok when bok_r=0.5 fall=1 td={n(T_DIP_S)}",
        # the grid's own three discriminators, recomputed over the grid's own
        # window so each row is checkable against its rung record
        f"meas tran praw_r_min min praw_r from={n(T_DIP_S)} to={n(t_dip_end)}",
        f"meas tran rst_r_min min rst_r from={n(T_DIP_S)} to={n(t_dip_end)}",
        f"meas tran bok_r_min min bok_r from={n(T_DIP_S)} to={n(t_dip_end)}",
        f"meas tran vsg_min min vsg from={n(T_DIP_S)} to={n(t_dip_end)}",
        # How far the deglitch ramp actually got before the window closed,
        # and how far PGDG was dragged with it. These two are what separate
        # "the deglitch never started" from "the deglitch ran out of time by
        # a hair" -- the distinction a PASS/FAIL column cannot carry.
        f"meas tran ndg_r_max max ndg_r from={n(T_DIP_S)} to={n(t_dip_end)}",
        f"meas tran ndg_r_close find ndg_r at={n(t_dip_end)}",
        f"meas tran pgdg_r_min min pgdg_r from={n(T_DIP_S)} to={n(t_dip_end)}",
        f"meas tran rst_r_min_overall min rst_r from={n(T_DIP_S)} to={n(t_end)}",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def parse_measurements(output: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in output.splitlines():
        match = _MEAS_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:
                continue
    return found


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
    return parse_measurements(output)


def read_logs() -> dict[str, dict[str, float]]:
    """Re-derive every variant's measurements from the logs already on disk.

    Used by ``--report-only``, which regenerates ``results.md`` /
    ``results.json`` from the raw ngspice output of the previous run without
    re-simulating. The logs are the verbatim record of that run, so this is a
    re-read of the same evidence, not a second measurement.
    """
    log_dir = CONTROL_DIR / "logs"
    return {
        path.stem: parse_measurements(path.read_text())
        for path in sorted(log_dir.glob("*.log"))
    }


def variant_name(vdd: float, slew_mvus: float, part: str) -> str:
    return f"{part}-{slew_mvus:g}mvus-{vdd:.2f}v"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report_only = "--report-only" in argv

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    manifest = load_manifest()
    options = manifest["options"]

    if report_only:
        results = read_logs()
        if not results:
            print("no logs to report from -- run without --report-only first",
                  file=sys.stderr)
            return 1
        write_results(pdk, manifest, results)
        print(f"wrote {CONTROL_DIR / 'results.md'} from "
              f"{len(results)} existing log(s)")
        return 0

    jobs: list[tuple[str, str]] = []
    for slew in SLEWS_MVUS:
        for vdd in SUPPLIES_V:
            jobs.append(
                (
                    variant_name(vdd, slew, "a"),
                    deck(pdk, options, vdd, slew, None),
                )
            )
    for slew in RESOLUTION_SLEWS_MVUS:
        for vdd in SUPPLIES_V:
            jobs.append(
                (
                    variant_name(vdd, slew, "b"),
                    deck(pdk, options, vdd, slew, FINE_TMAX_S),
                )
            )

    print(
        f"running {len(jobs)} decks at {CORNER} / {TEMP_C:g} C /"
        f" {', '.join(f'{v:g}' for v in SUPPLIES_V)} V ..."
    )
    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
        results = dict(
            zip(
                [name for name, _ in jobs],
                pool.map(lambda job: run_deck(*job), jobs),
            )
        )
    missing = [n for n, r in results.items() if "vdd_pre" not in r]
    if missing:
        print(f"  WARNING: {len(missing)} deck(s) produced no measurements: "
              f"{', '.join(sorted(missing)[:5])}")

    write_results(pdk, manifest, results)
    print(f"wrote {CONTROL_DIR / 'results.md'}")
    return 0


def bound_for(manifest: dict, key: str) -> float:
    return float(manifest["checks"][key]["max"])


def write_results(pdk, manifest, res: dict[str, dict[str, float]]) -> None:
    rst_bound = bound_for(manifest, RESETN_RATIO_KEY)

    def g(name, key):
        return res.get(name, {}).get(key)

    def us_after_dip(name, key):
        t = g(name, key)
        if t is None:
            return None
        return (t - T_DIP_S) * 1e6

    def fmt_us(value, digits=1):
        return "**never**" if value is None else f"{value:.{digits}f}"

    def verdict(name):
        v = g(name, "rst_r_min")
        if v is None:
            return "—"
        return "PASS" if v <= rst_bound else "**FAIL**"

    lines: list[str] = []
    lines.append(
        "# `por-brownout-slew` non-monotonic-band mechanism control — results"
    )
    lines.append("")
    lines.append(
        "**Generated by `run_band_mechanism.py`. Do not edit — re-run it.** "
        "Every number below is read out of `logs/` by that script; nothing "
        "here is transcribed by hand."
    )
    lines.append("")
    lines.append(
        f"- PVT points: `{CORNER}` / {TEMP_C:g} °C / "
        + ", ".join(f"{v:g} V" for v in SUPPLIES_V)
        + " (one corner family — a control is not corner evidence, see "
        "`sim/README.md`; the corner-grid evidence for this band is the rung "
        "records under `../records/`)"
    )
    lines.append(f"- PDK: `{pdk.variant}` @ `{pdk.version}`")
    lines.append(f"- Harness version: `{HARNESS_VERSION}`")
    lines.append(
        "- Solver options (from `../testbench/tb.json`): "
        f"`{'`, `'.join(manifest['options'])}`"
    )
    lines.append(
        "- DUT netlist: `design/netlist/temp_por_top.spice` "
        f"(sha256 `{runner.sha256_file(ASSEMBLY_NETLIST)[:12]}…`)"
    )
    lines.append(
        "- Diagnoses: the non-monotonic band reported in "
        "`../records/20260802-120940-3c3e728-boundary.md` § *Non-monotonic "
        "transition zone*"
    )
    lines.append(
        f"- `PASS`/`FAIL` below is `{RESETN_RATIO_KEY} ≤ {rst_bound:g}`, "
        "recomputed from this control's own trace over the same window "
        "`../testbench/tb.json` uses — so each row is directly checkable "
        "against the rung record at the same slew."
    )
    lines.append("")
    lines.append(
        "All times are **µs after the dip starts** (the dip start, 20 ms, is "
        "the same in every deck). *window closes* is the end of the dip "
        "window the grid measures over, `t_dip + edge + 50 µs dwell`; a "
        "`RESETn` valid-low later than that is a FAIL no matter how close it "
        "came."
    )
    lines.append("")

    lines.append("## A — event timeline vs falling slew")
    lines.append("")
    lines.append(
        "One variable per table: the falling slew rate. Reading the columns "
        "left to right is reading the causal chain — rail crosses VPOR↓,min "
        "→ `POR_RAW` asserts → the bias-starved deglitch finishes (`PGDG` "
        "falls) → `RESETn` reaches 0.1×VDD — against the clock that decides "
        "the verdict (*window closes*)."
    )
    lines.append("")
    for vdd in SUPPLIES_V:
        lines.append(f"### {CORNER} / {TEMP_C:g} °C / {vdd:g} V")
        lines.append("")
        lines.append(
            "| slew (mV/µs) | edge (µs) | window closes | VDD<VPOR↓,min at | "
            "`POR_RAW` asserts | rail there | `PGDG` falls | deglitch Δ | "
            "`RESETn` valid-low | margin to close | min `POR_RAW`/VDD | "
            "min `RESETn`/VDD | verdict |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for slew in SLEWS_MVUS:
            name = variant_name(vdd, slew, "a")
            edge_us = edge_s(vdd, slew) * 1e6
            close_us = edge_us + T_DWELL_S * 1e6
            t_praw = us_after_dip(name, "t_praw")
            t_pgdg = us_after_dip(name, "t_pgdg")
            t_rst = us_after_dip(name, "t_rst")
            dg = (
                f"{t_pgdg - t_praw:.1f}"
                if (t_praw is not None and t_pgdg is not None)
                else "—"
            )
            margin = f"{close_us - t_rst:+.1f}" if t_rst is not None else "—"
            praw_min = g(name, "praw_r_min")
            rst_min = g(name, "rst_r_min")
            vdd_praw = g(name, "vdd_at_praw")
            lines.append(
                f"| {slew:g} | {edge_us:.1f} | {close_us:.1f} | "
                f"{fmt_us(us_after_dip(name, 't_vpor'))} | "
                f"{fmt_us(t_praw)} | "
                + (f"{vdd_praw:.4f} V" if vdd_praw is not None else "—")
                + f" | {fmt_us(t_pgdg)} | {dg} | {fmt_us(t_rst)} | "
                f"{margin} | "
                + (f"{praw_min:.4f}" if praw_min is not None else "—")
                + " | "
                + (f"{rst_min:.4f}" if rst_min is not None else "—")
                + f" | {verdict(name)} |"
            )
        lines.append("")

    lines.append(
        "A **never** in the `POR_RAW` column is DR-011's starved loop: no "
        "decision was taken during the dip at all. A `POR_RAW` time with a "
        "negative *margin to close* is the other failure mode entirely — the "
        "decision was taken, and the output chain, starved by the same "
        "collapse, did not finish propagating it before the dip window ran "
        "out."
    )
    lines.append("")
    lines.append(
        "`VPOR↑`/`VPOR↓` are ratified at 2.47–2.73 V / 2.22–2.63 V, so a "
        "*rail there* entry above 2.63 V is an assertion earlier than the "
        "ratified band allows — the separate defect DR-011 filed as #61, "
        "visible here but not this control's subject."
    )
    lines.append("")

    lines.append("## B — is it the solver? 4× finer maximum timestep")
    lines.append("")
    lines.append(
        f"One variable: the integration's maximum timestep. Part A runs the "
        f"grid's own `tran {TSTEP_S*1e6:g}u` with no `tmax`; the rows below "
        f"are the same decks with `tmax = {FINE_TMAX_S*1e6:g} µs`. The two "
        "rungs chosen are the pair whose disagreement **is** the reported "
        "non-monotonicity. If a knife-edge verdict were an artefact of where "
        "the timestep grid lands relative to the 50 µs dwell, tightening the "
        "bound would move it."
    )
    lines.append("")
    lines.append(
        "| slew (mV/µs) | supply | `RESETn` valid-low, coarse | fine | Δ | "
        "min `RESETn`/VDD, coarse | fine | verdict, coarse | fine |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for slew in RESOLUTION_SLEWS_MVUS:
        for vdd in SUPPLIES_V:
            a, b = variant_name(vdd, slew, "a"), variant_name(vdd, slew, "b")
            ta, tb = us_after_dip(a, "t_rst"), us_after_dip(b, "t_rst")
            delta = (
                f"{tb - ta:+.2f}" if (ta is not None and tb is not None) else "—"
            )
            ra, rb = g(a, "rst_r_min"), g(b, "rst_r_min")
            lines.append(
                f"| {slew:g} | {vdd:g} V | {fmt_us(ta, 2)} | {fmt_us(tb, 2)} | "
                f"{delta} | "
                + (f"{ra:.4f}" if ra is not None else "—")
                + " | "
                + (f"{rb:.4f}" if rb is not None else "—")
                + f" | {verdict(a)} | {verdict(b)} |"
            )
    lines.append("")

    lines.append("## C — the collapse itself")
    lines.append("")
    lines.append(
        "`V_sg` = `VDD − PG` is the overdrive on `bias_core`'s PMOS mirror "
        "bank, the node DR-011 measures the starved-loop collapse on "
        "(776.2 mV pre-dip → −74.4 mV, 8 µs into a 1 µs edge). Here it is at "
        "the instant `POR_RAW` asserts and at its worst point inside the dip "
        "window, for every Part A deck — the state variable the timeline "
        "above is a consequence of."
    )
    lines.append("")
    lines.append(
        "| slew (mV/µs) | "
        + " | ".join(f"V_sg @ `POR_RAW`, {v:g} V" for v in SUPPLIES_V)
        + " | "
        + " | ".join(f"min V_sg in dip, {v:g} V" for v in SUPPLIES_V)
        + " |"
    )
    lines.append("|---" * (1 + 2 * len(SUPPLIES_V)) + "|")
    for slew in SLEWS_MVUS:
        cells = []
        for vdd in SUPPLIES_V:
            v = g(variant_name(vdd, slew, "a"), "vsg_at_praw")
            cells.append("—" if v is None else f"{v*1e3:.1f} mV")
        for vdd in SUPPLIES_V:
            v = g(variant_name(vdd, slew, "a"), "vsg_min")
            cells.append("—" if v is None else f"{v*1e3:.1f} mV")
        lines.append(f"| {slew:g} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "V_sg pre-dip, for reference: "
        + ", ".join(
            f"{vdd:g} V → "
            + (
                "—"
                if g(variant_name(vdd, SLEWS_MVUS[0], "a"), "vsg_pre") is None
                else f"{g(variant_name(vdd, SLEWS_MVUS[0], 'a'), 'vsg_pre')*1e3:.1f} mV"
            )
            for vdd in SUPPLIES_V
        )
        + " (identical at every slew — the dip has not started yet)."
    )
    lines.append("")

    lines.append("## D — the deglitch ramp that runs out of time")
    lines.append("")
    lines.append(
        "`NDG` is `por_output_chain`'s deglitch capacitor node: it has to "
        "traverse `CDG` at I/C before `XMG1` flips `PGDG`, and both the "
        "current and `XMG1`'s trip point are collapsing with the rail while "
        "it does. `design/por_output_chain.md` sizes that dwell at "
        "1.86–4.58 µs at nominal `IBIAS` (8.88 µs at half) — the numbers "
        "below are the same dwell running on whatever bias survives the "
        "brownout. *ramp at close* is `NDG`/VDD at the instant the dip "
        "window ends; *lowest PGDG* is how far `PGDG` was dragged down "
        "before the window closed (1.0 = never moved, ~0 = flipped)."
    )
    lines.append("")
    for vdd in SUPPLIES_V:
        lines.append(f"### {CORNER} / {TEMP_C:g} °C / {vdd:g} V")
        lines.append("")
        lines.append(
            "| slew (mV/µs) | peak `NDG`/VDD in dip | ramp at close | "
            "lowest `PGDG`/VDD in dip | verdict |"
        )
        lines.append("|---|---|---|---|---|")
        for slew in SLEWS_MVUS:
            name = variant_name(vdd, slew, "a")
            nmax, nclose = g(name, "ndg_r_max"), g(name, "ndg_r_close")
            pmin = g(name, "pgdg_r_min")
            lines.append(
                f"| {slew:g} | "
                + (f"{nmax:.4f}" if nmax is not None else "—")
                + " | "
                + (f"{nclose:.4f}" if nclose is not None else "—")
                + " | "
                + (f"{pmin:.4f}" if pmin is not None else "—")
                + f" | {verdict(name)} |"
            )
        lines.append("")
    lines.append(
        "A FAIL row whose peak `NDG`/VDD sits just short of the level the "
        "PASS rows cross at is a **near-tangency**, not a dead circuit: the "
        "ramp and the falling trip point it is chasing come close and "
        "separate again. That is the shape that makes the verdict "
        "non-monotonic in slew while every state variable in section C "
        "stays monotone."
    )
    lines.append("")

    (CONTROL_DIR / "results.md").write_text("\n".join(lines) + "\n")

    # Machine-readable twin of the tables above, for the derived record that
    # cites this control (`../analyze_transition_band.py`). Written from the
    # same parsed logs in the same pass, so the record's mechanism figures
    # are READ from here rather than transcribed by hand out of results.md --
    # the "generated, never transcribed twice" rule in sim/README.md.
    payload = {
        "generated_by": "sim/por-brownout-slew/control/run_band_mechanism.py",
        "corner": CORNER,
        "temp_c": TEMP_C,
        "supplies_v": SUPPLIES_V,
        "slews_mvus": SLEWS_MVUS,
        "resolution_slews_mvus": RESOLUTION_SLEWS_MVUS,
        "tstep_s": TSTEP_S,
        "fine_tmax_s": FINE_TMAX_S,
        "t_dip_s": T_DIP_S,
        "dip_v": DIP_V,
        "t_dwell_s": T_DWELL_S,
        "resetn_ratio_bound": rst_bound,
        "pdk": f"{pdk.variant}@{pdk.version}",
        "harness_version": HARNESS_VERSION,
        "variants": {},
    }
    for part, slews in (("a", SLEWS_MVUS), ("b", RESOLUTION_SLEWS_MVUS)):
        for slew in slews:
            for vdd in SUPPLIES_V:
                name = variant_name(vdd, slew, part)
                if name not in res:
                    continue
                edge = edge_s(vdd, slew)
                payload["variants"][name] = {
                    "part": part,
                    "slew_mvus": slew,
                    "vdd_v": vdd,
                    "edge_us": edge * 1e6,
                    "window_close_us": (edge + T_DWELL_S) * 1e6,
                    "measurements": res[name],
                }
    (CONTROL_DIR / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
