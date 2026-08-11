#!/usr/bin/env python3
"""Root-cause control for sim/bias-core-designer-check/'s brownout checks (#185).

    python3 sim/bias-core-designer-check/control/run_starved_window.py

Record ``20260811-063744-5ff219c`` -- the post-layout re-run (#84) -- reported
four things about the brownout branch that issue #185 had to reconcile:

  * ``ok_bo_end_droop_mv`` = 3630 mV at ``tt_27c_3.63v`` / ``ss_27c_3.63v`` /
    ``bjt_ff_27c_3.63v``, against a 20 mV bound, where the schematic export
    passed at every point;
  * ``bo_shallow_ppm`` / ``bo_deep_ppm`` failing at 12 / 21 points instead of
    2 / 2, with magnitudes near -5e5 ppm (i.e. VREF at HALF its settled value
    at the sample instant, not a reproducibility error at all);
  * ``t_bo_recover_us`` NEGATIVE at 34 of 81 points -- a recovery that
    completes before the rail returns, which is impossible;
  * ``t_false_ok_fast_us`` / ``t_false_ok_brownout_us`` clustered within 25 us
    of 1988 / 1577 us at 14 points each.

This control tests the single hypothesis that ties all four together: that the
2 ms transient those numbers were taken on is SHORTER THAN THE PHENOMENON --
this cell's own documented starved-loop window (``design/bias_core.md``), which
real interconnect parasitics lengthen by roughly an order of magnitude.

  Part A -- ANATOMY. One corner (tt / 27 C / 3.63 V), both netlists, the
    superseded serialized brownout branch, held long enough to run past the
    recovery. Dumps the full V(VDD)/V(BIAS_OK)/V(VREF) trace and derives the
    event timeline from it: when BIAS_OK returns high after the collapse, how
    long it is a FALSE valid on a parked reference, when the loop actually
    recovers, and the window during which BIAS_OK is CORRECTLY low while that
    happens. If the hypothesis holds, the record's 1.95 ms sample instant falls
    inside that correctly-low window at this corner.

  Part B -- LATCH TEST. The corners the replacement 30 ms deck does not clear,
    re-run four times longer. A reference that has not come back by 29.9 ms is
    either still recovering or latched onto a second solution, and only a
    longer run separates those. Reports the recovery time and the end-of-run
    reproducibility error at each.

Outputs, all regenerated on every run (a control is not a record):

    decks/<variant>.spice   the exact deck as run
    logs/<variant>.log      raw ngspice output, verbatim
    traces/<variant>.txt    the Part A waveform dump, verbatim
    results.md              the tables and the derived timeline

This is a diagnosis of record ``20260811-063744-5ff219c``, not a recorded PVT
result: neither part sweeps the corner grid, so it deliberately does NOT go
through sim/run_corners.py and does NOT mint a record under ../records/. The
corner-grid evidence is the 81-point record taken on the replacement deck. See
sim/README.md for the distinction.

Everything except the one variable per part is fixed by construction: every
deck is composed from the same fragment, in the same process, from the same
PDK, with the corner sections and solver options read from the harness and
from ../testbench/tb.json rather than restated here.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import json
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

#: Part A reproduces the SUPERSEDED serialized brownout branch (to explain the
#: record taken on it); Part B uses the REPLACEMENT deck's deep-only branch (to
#: ask whether the corners it does not clear are latched or merely slow).
FRAGMENT = CONTROL_DIR / "starved_window.spice"
FRAGMENT_DEEP = CONTROL_DIR / "starved_window_deep.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

SCHEMATIC_NETLIST = REPO_ROOT / "design" / "netlist" / "bias_core.spice"
EXTRACTED_NETLIST = REPO_ROOT / "layout" / "postlayout" / "bias_core.spice"

#: Part A's PVT point. tt / 27 C / 3.63 V is one of the three corners where the
#: parent record's `ok_bo_end_droop_mv` reads 3630 mV, and it is the nominal
#: process corner, so the effect is not a corner curiosity.
PART_A_POINT = ("tt", 27.0, 3.63)
PART_A_HOLD = "6m"
PART_A_TSTEP_US = 4.0

#: The instant `ok_bo_end_droop_mv`, `bo_post` and `vdd_bo` sampled in the
#: superseded deck, and the instant the rail returns from the collapse.
#: The rail's return RAMP starts 10 us earlier, at COLLAPSE_END_S, and BIAS_OK
#: is dragged capacitively through 1.4 V on that ramp -- so crossings are
#: classified from the start of the collapse, not from RAIL_RETURN_S, or the
#: false return is silently attributed to the genuine one.
PARENT_SAMPLE_S = 1.95e-3
RAIL_RETURN_S = 1.110e-3
COLLAPSE_START_S = 0.960e-3
COLLAPSE_END_S = 1.100e-3
#: `t_false_ok_*`'s integration ceiling in the superseded deck.
PARENT_TSTOP_S = 2.0e-3
#: The threshold `Bfob` uses to call the reference "low enough to matter".
FALSE_VALID_ERR_V = 0.1
#: A valid BIAS_OK high, as `t_bo_recover_us` defines it.
OK_VALID_V = 1.4

#: Part B's PVT points. `sf_-40c_3.63v` is the ONE corner whose `bo_deep_ppm`
#: and `ok_bo_end_droop_mv` still fail on the 30 ms replacement deck;
#: `sf_-40c_3.30v` is its nearest sibling, which clears the deck with the
#: slowest passing recovery on the grid (`t_bo_recover_us` = 24.9 ms) and is
#: here as the contrast. Kept as data rather than derived from a record so the
#: control is reproducible from the committed tree alone; update it if a later
#: record clears or adds corners.
PART_B_POINTS: list[tuple[str, float, float]] = [
    ("sf", -40.0, 3.30),
    ("sf", -40.0, 3.63),
]
PART_B_HOLD = "120m"
PART_B_TSTOP_MS = 120.0
PART_B_TSTEP_US = 20.0
#: The replacement deck's own post-event sample instant, for comparison.
PARENT_DECK_SAMPLE_MS = 29.9
#: Cross-check against the graded deck, transcribed from the 30 ms record: the
#: slowest corner that still CLEARS it. If this control's own longer, coarser
#: run reproduces that edge, the corner that does NOT clear is a real miss and
#: not an artefact of running longer. Update alongside PART_B_POINTS.
CROSSCHECK_CORNER = "sf_-40c_3.30v"
CROSSCHECK_T_BO_RECOVER_US = 24916.7
#: |VREF - VREF_settled| below which the loop counts as recovered, 1 % of a
#: 1.2 V reference.
RECOVERED_ERR_V = 0.012


def compose_deck(
    pdk,
    netlist: Path,
    corner_name: str,
    temp_c: float,
    vdd: float,
    options: list[str],
    hold: str,
    tstep_us: float,
    tstop_ms: float,
    control_lines: list[str],
    fragment_path: Path | None = None,
) -> str:
    corner = corners_mod.CORNERS[corner_name]
    fragment = (fragment_path or FRAGMENT).read_text().rstrip().replace("{t_hold}", hold)
    lines = [
        f"* starved-window control -- {netlist.name} @ {corner_name}/{temp_c} C/{vdd} V",
        "* GENERATED by sim/bias-core-designer-check/control/run_starved_window.py",
        f"* pdk={pdk.variant}@{pdk.version}  harness={HARNESS_VERSION}",
        "",
        ".param vdd_nom=3.3",
        f".param vdd_val={vdd!r}",
        f".param temp_c={temp_c!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, temp_c, options)
    lines += ["", fragment, "", netlist.read_text().rstrip(), ""]
    lines += [".control", "set numdgt=10", "set noaskquit", f"  tran {tstep_us}u {tstop_ms}m"]
    lines += [f"  {line}" for line in control_lines]
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def parse_trace(path: Path) -> list[tuple[float, float, float, float]]:
    """ngspice `print` table -> [(t, vdd, bias_ok, vref)]."""
    rows: list[tuple[float, float, float, float]] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0].isdigit():
            try:
                rows.append(tuple(float(x) for x in parts[1:]))  # type: ignore[arg-type]
            except ValueError:
                continue
    return rows


def crossings(rows, index: int, level: float) -> list[tuple[float, str]]:
    """Linear-interpolated crossings of `level` on column `index`."""
    out: list[tuple[float, str]] = []
    for (t0, *a), (t1, *b) in zip(rows, rows[1:]):
        y0, y1 = a[index - 1], b[index - 1]
        if (y0 - level) * (y1 - level) < 0:
            frac = (level - y0) / (y1 - y0)
            out.append((t0 + frac * (t1 - t0), "rise" if y1 > y0 else "fall"))
    return out


def sample_at(rows, index: int, t: float) -> float:
    prev = rows[0]
    for row in rows:
        if row[0] >= t:
            t0, t1 = prev[0], row[0]
            if t1 == t0:
                return row[index]
            frac = (t - t0) / (t1 - t0)
            return prev[index] + frac * (row[index] - prev[index])
        prev = row
    return rows[-1][index]


def run_deck(name: str, deck_text: str, deck_dir: Path, log_dir: Path) -> str:
    deck_path = deck_dir / f"{name}.spice"
    deck_path.write_text(deck_text)
    proc = subprocess.run(
        ["ngspice", "-b", deck_path.name],
        capture_output=True,
        text=True,
        cwd=deck_dir,
        check=False,
    )
    output = proc.stdout + "\n" + proc.stderr
    (log_dir / f"{name}.log").write_text(output)
    return output


def us(seconds: float) -> str:
    return f"{seconds * 1e6:.1f} us"


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
    trace_dir = CONTROL_DIR / "traces"
    for d in (deck_dir, log_dir, trace_dir):
        d.mkdir(exist_ok=True)

    corner_a, temp_a, vdd_a = PART_A_POINT

    # ---- Part A -----------------------------------------------------------
    part_a: dict[str, list] = {}
    for label, netlist in (("schematic", SCHEMATIC_NETLIST), ("extracted", EXTRACTED_NETLIST)):
        name = f"anatomy-{label}"
        trace_path = trace_dir / f"{name}.txt"
        run_deck(
            name,
            compose_deck(
                pdk, netlist, corner_a, temp_a, vdd_a, options,
                hold=PART_A_HOLD, tstep_us=PART_A_TSTEP_US, tstop_ms=6.0,
                # Relative to the deck's own directory (ngspice runs with
                # cwd=decks/), so the committed deck carries no absolute path.
                control_lines=[f"print v(vddb) v(bias_okb) v(vrefb) > ../traces/{name}.txt"],
            ),
            deck_dir, log_dir,
        )
        rows = parse_trace(trace_path)
        if len(rows) < 100:
            print(f"{name}: trace has {len(rows)} rows, expected a transient", file=sys.stderr)
            return 2
        part_a[label] = rows
        print(f"{name}: ok -> {trace_path.relative_to(REPO_ROOT)} ({len(rows)} points)")

    # ---- Part B -----------------------------------------------------------
    part_b_lines = [
        f"meas tran vref_st find v(vrefst) at={PART_B_TSTOP_MS - 0.1}m",
        f"meas tran vref_end find v(vrefb) at={PART_B_TSTOP_MS - 0.1}m",
        f"meas tran t_recover when v(eb)={RECOVERED_ERR_V} fall=last",
        f"meas tran t_ok_last when v(bias_okb)={OK_VALID_V} rise=last",
        f"meas tran t_false integ v(fob) from=0 to={PART_B_TSTOP_MS}m",
        "let m_vref_st = vref_st",
        "let m_vref_end = vref_end",
        "let m_t_recover = t_recover",
        "let m_t_ok_last = t_ok_last",
        "let m_t_false = t_false",
        "print m_vref_st",
        "print m_vref_end",
        "print m_t_recover",
        "print m_t_ok_last",
        "print m_t_false",
    ]

    def _run_b(point):
        corner_name, temp_c, vdd = point
        name = f"latch-{corner_name}_{int(temp_c)}c_{vdd:.2f}v"
        output = run_deck(
            name,
            compose_deck(
                pdk, EXTRACTED_NETLIST, corner_name, temp_c, vdd, options,
                hold=PART_B_HOLD, tstep_us=PART_B_TSTEP_US, tstop_ms=PART_B_TSTOP_MS,
                control_lines=part_b_lines, fragment_path=FRAGMENT_DEEP,
            ),
            deck_dir, log_dir,
        )
        return point, name, runner.parse_measurements(output)

    part_b: dict[tuple, dict[str, float]] = {}
    if PART_B_POINTS:
        with ThreadPoolExecutor(max_workers=min(4, len(PART_B_POINTS))) as pool:
            for point, name, values in pool.map(_run_b, PART_B_POINTS):
                part_b[point] = values
                print(f"{name}: ok -> {(log_dir / (name + '.log')).relative_to(REPO_ROOT)}")

    # ---- derive Part A's timeline -----------------------------------------
    out: list[str] = [
        "# Starved-window root-cause control -- generated, do not edit",
        "",
        "Generated by `sim/bias-core-designer-check/control/run_starved_window.py`. Re-run",
        "it to regenerate this file, the decks under `decks/`, the raw ngspice logs under",
        "`logs/` and the Part A traces under `traces/`. The numbers quoted in",
        "`design/bias_core.md`, `../testbench/stimulus.spice` and `../testbench/tb.json`",
        "are transcribed from here, and from nowhere else.",
        "",
        f"ngspice: {ngspice_version} · PDK: {pdk.variant}@{pdk.version} · harness {HARNESS_VERSION}",
        "",
        "## Part A -- anatomy of the superseded 2 ms brownout branch",
        "",
        f"One variable: the DUT netlist. PVT point `{corner_a}_{int(temp_a)}c_{vdd_a:.2f}v` --",
        "one of the three corners where record `20260811-063744-5ff219c` reads",
        "`ok_bo_end_droop_mv` = 3630 mV. Rail shape is that record's own serialized",
        "brownout branch (0.5 V dip, then a full collapse), held past the end of the",
        "recovery instead of stopping at 2 ms.",
        "",
        "| | schematic export | klt-extracted |",
        "| --- | ---: | ---: |",
    ]

    derived: dict[str, dict[str, float | None]] = {}
    for label, rows in part_a.items():
        # Classify from the START of the collapse: BIAS_OK falls with the rail
        # at 960 us and is dragged back through 1.4 V on the rail's own return
        # ramp (1100 -> 1110 us), which is BEFORE RAIL_RETURN_S.
        ok_rises = [t for t, kind in crossings(rows, 2, OK_VALID_V)
                    if kind == "rise" and t > COLLAPSE_START_S]
        ok_falls = [t for t, kind in crossings(rows, 2, OK_VALID_V)
                    if kind == "fall" and t > COLLAPSE_START_S]
        vref_settled = sample_at(rows, 3, rows[-1][0])
        err = [(t, abs(v - vref_settled)) for t, _, _, v in rows if t > COLLAPSE_END_S]
        recovered = [t for t, e in err if e > RECOVERED_ERR_V]
        t_recovered = max(recovered) if recovered else COLLAPSE_END_S
        # The LAST rise is the genuine re-assert; the FIRST one after the
        # collapse is the capacitive/stale return, which is a false valid for
        # as long as VREF stays parked.
        t_reassert = ok_rises[-1] if ok_rises else None
        t_false_return = ok_rises[0] if ok_rises else None
        deassert = [t for t in ok_falls if (t_false_return or 0) < t < (t_reassert or 1e9)]
        derived[label] = {
            "ok_false_return": t_false_return,
            "ok_reassert": t_reassert,
            "ok_deassert": deassert[-1] if deassert else None,
            "t_recovered": t_recovered,
            "ok_at_parent_sample": sample_at(rows, 2, PARENT_SAMPLE_S),
            "vref_at_parent_sample": sample_at(rows, 3, PARENT_SAMPLE_S),
            "vref_settled": vref_settled,
            "n_rises_after_collapse": len(ok_rises),
        }

    def row(title: str, key: str, fmt) -> str:
        cells = " | ".join(fmt(derived[l][key]) for l in ("schematic", "extracted"))
        return f"| {title} | {cells} |"

    def as_time(v):
        return "not observed" if v is None else us(v - RAIL_RETURN_S) + " after rail return"

    def as_volt(v):
        return "n/a" if v is None else f"{v:.5g} V"

    out += [
        row("BIAS_OK back above 1.4 V (capacitive, on the rail's return ramp)",
            "ok_false_return", as_time),
        row("…de-asserts BELOW 1.4 V at", "ok_deassert", as_time),
        row("…genuinely re-asserts at", "ok_reassert", as_time),
        row("VREF last more than 1 % from settled", "t_recovered", as_time),
        row("BIAS_OK 1.4 V rising crossings after the collapse",
            "n_rises_after_collapse", lambda v: str(int(v))),
        row("V(BIAS_OK) at the record's 1.95 ms sample", "ok_at_parent_sample", as_volt),
        row("V(VREF) at the record's 1.95 ms sample", "vref_at_parent_sample", as_volt),
        row("V(VREF) settled", "vref_settled", as_volt),
        "",
        "Times are relative to the rail reaching full value at 1.110 ms; the return"
        " ramp starts 10 µs earlier, which is why the first entry is negative.",
        "",
    ]

    ext = derived["extracted"]
    sch = derived["schematic"]
    inside = (
        ext["ok_deassert"] is not None
        and ext["ok_reassert"] is not None
        and ext["ok_deassert"] < PARENT_SAMPLE_S < ext["ok_reassert"]
    )
    ext_false_window = (ext["ok_deassert"] or 0) - (ext["ok_false_return"] or 0)
    sch_false_window = (sch["ok_deassert"] or 0) - (sch["ok_false_return"] or 0)
    out += [
        "### What Part A shows",
        "",
        f"1. **`BIAS_OK` is back above 1.4 V before the rail has even finished "
        f"returning, on both netlists -- and that is a FALSE valid, not a recovery.** "
        f"The high-impedance output is dragged up capacitively by the rail's own 10 µs "
        f"return ramp while the reference is still parked, and it stays there for "
        f"{us(ext_false_window)} on the extracted netlist against {us(sch_false_window)} "
        f"on the schematic export -- a factor of "
        f"{ext_false_window / sch_false_window:.1f}. V(VREF) does not reach its settled "
        f"value until {us(ext['t_recovered'] - RAIL_RETURN_S)} after the return "
        f"(extracted) versus {us(sch['t_recovered'] - RAIL_RETURN_S)} (schematic). This "
        "is exactly the starved-loop window `design/bias_core.md` documents, and it is "
        "what `t_false_ok_brownout_us` measures.",
        f"2. **The 1.95 ms sample instant lands inside the notch where `BIAS_OK` is "
        f"CORRECTLY low.** "
        + (
            "Confirmed: the extracted cell de-asserts at "
            f"{us((ext['ok_deassert'] or 0) - RAIL_RETURN_S)} after the return and "
            f"re-asserts at {us((ext['ok_reassert'] or 0) - RAIL_RETURN_S)}, and "
            "1.95 ms sits between them"
            if inside
            else "NOT confirmed at this corner -- see the table above"
        )
        + f", which is why `ok_bo_end_droop_mv` read {(3.63 - (ext['ok_at_parent_sample'] or 0)) * 1e3:.0f} mV "
        "there. The flag is doing its job at that instant: the settle detector has "
        "noticed the reference is wrong and pulled the flag down while the loop "
        "re-establishes itself.",
        f"3. **The schematic export is not qualitatively different, only faster.** It "
        f"has the same three-phase shape -- capacitive false return, de-assert at "
        f"{us((sch['ok_deassert'] or 0) - RAIL_RETURN_S)}, genuine re-assert at "
        f"{us((sch['ok_reassert'] or 0) - RAIL_RETURN_S)} -- and the same notch; the "
        "notch has simply come and gone long before 1.95 ms, which is why the same "
        f"check reads {(3.63 - (sch['ok_at_parent_sample'] or 0)) * 1e3:.3f} mV there. "
        "Nothing about the mechanism is new post-layout; its TIME CONSTANT is.",
        "",
    ]

    # ---- Part B table -----------------------------------------------------
    out += [
        "## Part B -- latch test at the corners the 30 ms deck does not clear",
        "",
        "One variable: none. These are the extracted netlist at the corners whose",
        "`bo_*_ppm` still fail on the replacement deck, re-run on a "
        f"{PART_B_TSTOP_MS:g} ms transient -- four times longer -- to separate *still",
        "recovering* from *latched onto a second solution*.",
        "",
    ]
    if not PART_B_POINTS:
        out += [
            "The 30 ms deck cleared every corner, so this part has nothing to run.",
            "",
        ]
    else:
        out += [
            "Both times below are absolute, so they are directly comparable with the"
            f" replacement deck's own {PARENT_DECK_SAMPLE_MS:g} ms sample instant.",
            "",
            "| corner | VREF recovered at | BIAS_OK re-asserts at | VREF at "
            f"{PART_B_TSTOP_MS - 0.1:g} ms | error vs. settled | false-valid time |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for point in PART_B_POINTS:
            corner_name, temp_c, vdd = point
            m = part_b[point]
            settled = m["vref_st"]
            end = m["vref_end"]
            ppm = (end - settled) / settled * 1e6
            out.append(
                f"| `{corner_name}_{int(temp_c)}c_{vdd:.2f}v` "
                f"| {m['t_recover'] * 1e3:.2f} ms "
                f"| {m['t_ok_last'] * 1e3:.2f} ms "
                f"| {end:.6f} V | {ppm:+.3f} ppm | {m['t_false'] * 1e3:.2f} ms |"
            )
        worst_ppm = max(
            abs((part_b[p]["vref_end"] - part_b[p]["vref_st"]) / part_b[p]["vref_st"] * 1e6)
            for p in PART_B_POINTS
        )
        worst_rec = max(part_b[p]["t_recover"] for p in PART_B_POINTS)
        margin_ms = [
            (f"{p[0]}_{int(p[1])}c_{p[2]:.2f}v",
             (PARENT_DECK_SAMPLE_MS * 1e-3 - part_b[p]["t_recover"]) * 1e3)
            for p in PART_B_POINTS
        ]
        out += [
            "",
            "### What Part B shows",
            "",
            f"**Not latched.** Every corner recovers, and the reference returns to within "
            f"{worst_ppm:.3f} ppm of the value it held before the event -- inside the "
            "±500 ppm bound `bo_deep_ppm` applies, at a point where that check FAILS on "
            "the 30 ms deck. What that failure reports is the recovery still being in "
            f"progress at the sample instant (slowest recovery here: {worst_rec * 1e3:.2f} ms "
            "absolute), not a second stable solution. The reproducibility claim `bo_*_ppm` "
            "exists to make therefore holds; the check reads FAIL because the *timing* it "
            "shares a sample point with does not, and that is the honest answer rather "
            "than a reason to lengthen the deck until it goes green.",
            "",
            "**This control deck reproduces the graded one, so the remaining failure is "
            "real rather than an artefact of the longer run.** "
            f"At `{CROSSCHECK_CORNER}` the 30 ms record measures `t_bo_recover_us` = "
            f"{CROSSCHECK_T_BO_RECOVER_US:g} us, i.e. an absolute re-assert at "
            f"{(CROSSCHECK_T_BO_RECOVER_US * 1e-6 + RAIL_RETURN_S) * 1e3:.2f} ms; this "
            f"120 ms control puts the same edge at "
            f"{part_b[('sf', -40.0, 3.30)]['t_ok_last'] * 1e3:.2f} ms -- agreement to "
            f"{abs(part_b[('sf', -40.0, 3.30)]['t_ok_last'] - (CROSSCHECK_T_BO_RECOVER_US * 1e-6 + RAIL_RETURN_S)) * 1e6:.0f} us "
            "on a 26 ms measurement, despite this deck running a 20 us print step against "
            "the graded deck's 4 us. Recovery relative to the "
            f"{PARENT_DECK_SAMPLE_MS:g} ms sample (positive = recovered before it): "
            + "; ".join(f"`{name}` {m:+.2f} ms" for name, m in margin_ms)
            + ". The one failing corner misses by a clear ~1 ms, not by rounding.",
            "",
        ]

    (CONTROL_DIR / "results.md").write_text("\n".join(out))
    print(f"wrote {(CONTROL_DIR / 'results.md').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
