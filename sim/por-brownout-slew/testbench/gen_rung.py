#!/usr/bin/env python3
"""(Re)generate ``testbench/stimulus.spice`` + ``testbench/tb.json`` for one
falling-slew ladder rung of the #60 characterization.

    python3 sim/por-brownout-slew/testbench/gen_rung.py --slew-mvus 7.667 \\
        --label b-slew-7.667mvus

Per ``sim/README.md``: "``testbench/`` is not versioned per record -- it
holds the current testbench netlist(s) ... used to generate records. If the
testbench itself changes in a way that could affect comparability across
records, note that in the new record's summary." This experiment's one free
variable across records is the dip's falling SLEW RATE (the ladder DR-011
proposes: 2300 / 23.00 / 15.33 / 11.50 / 7.67 / 2.30 / 0.77 mV/us) -- 1.0 V
dip target, 50 us dwell, cold start and settle are held fixed at
``sim/por-brownout/``'s own values, per DR-011 decision 4 and the curator's
design notes on #60 ("isolate slew").

WHY SLEW, NOT EDGE DURATION, IS THE SWEPT PARAMETER: a first version of this
script swept the PWL edge DURATION directly (holding it fixed across the
81-point grid). A quick single-corner smoke test caught the bug that design
implied: the dip target is a fixed ABSOLUTE voltage (1.0 V), not a fixed
DELTA below vdd_val, so the same edge duration produces a ~14 % FASTER
actual slew at the +10 % supply corner than at the -10 % one (e.g. at
edge=0.3 ms: 8.77 mV/us at vdd=3.63 V vs 6.57 mV/us at vdd=2.97 V) --
conflating the very quantity DR-011 asks #60 to characterize with the supply
axis. Instead, the PWL edge TIME is written as a ``.param`` expression in
``vdd_val`` (the harness's own per-point supply), so every point in a rung's
81-point grid experiences the SAME actual dVDD/dt regardless of which supply
corner it lands on -- the direct, unconflated characterization DR-011 asks
for. (dip_shape.spice already establishes the "PWL breakpoint time is a
``{...}`` expression over harness/testbench ``.param``s" idiom this reuses.)

This script writes the CURRENT rung's stimulus + manifest; run
``python3 sim/build_tb.py por-brownout-slew`` and then
``python3 sim/run_corners.py por-brownout-slew ...`` after it to produce
that rung's record. Each record's own "Claim" text and the frozen
``netlist-snapshots/<record-id>.spice`` say which rung it was, so nothing is
lost even though ``testbench/`` itself is overwritten between rungs.

WHY NOT A SINGLE PARAMETERIZED DECK ACROSS RUNGS TOO: run_corners.py sweeps
one FIXED netlist across the PVT grid; the target slew is a testbench design
choice, not a PVT axis, so it is swept by re-generating the testbench
between full-grid runs -- the same "testbench changes between records,
append-only records survive it" idiom sim/README.md's worked example
describes for a schematic revision.

WHY NOT EVENT ("meas ... when ...") MEASUREMENTS: at a FAILING rung, RESETn
never crosses valid-low inside the (short, dip-only) simulated window, so a
"when" measurement would report "not found" and the harness would mark the
whole point an ERROR rather than a clean FAIL. Every measurement below is
therefore a "min ... from ... to ..." or "find ... at ..." over a window
that always has a value, exactly as the curator's #60 design notes
recommend ("the cheaper, cleaner discriminator" -- min BIAS_OK/VDD in dip --
"confirm RESETn reaching valid-low agrees").
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TESTBENCH_DIR = Path(__file__).resolve().parent

# Fixed by design (DR-011 decision 4 / #60's curator notes): identical to
# sim/por-brownout/testbench/stimulus.spice's own dip, isolating the one
# free variable (falling slew rate) that #60 characterizes.
T_DIP_MS = 20.0  # dip start -- matches sim/por-brownout/, 3 ms margin over
# sim/temp-por-top-release/'s slowest release (16.95 ms, ss/-40C/3.63V)
DIP_V = 1.0
T_DWELL_MS = 0.05  # 50 us, sim/por-brownout/'s own qualifying dwell
NOMINAL_SUPPLY_V = 3.3
SUPPLY_TOLERANCE = 0.10
# Recovery-edge margin: DR-011's own 81-point po-brownout record shows the
# recovery-triggered reassert lands at 51.26-51.58 us after dip start (i.e.
# within ~1 us of the recovery edge finishing) at EVERY one of 81 corners
# for that deck's 1 us edge -- a near-PVT-independent margin. 60 us of
# post-recovery-edge headroom is generous slack on top of that observation.
RECOVERY_MARGIN_MS = 0.06

MANIFEST_NAME = "tb.json"
STIMULUS_NAME = "stimulus.spice"


def edge_ms_at(vdd: float, slew_mvus: float, dip_v: float = DIP_V) -> float:
    """Edge duration (ms) that realizes ``slew_mvus`` for a dip starting at
    ``vdd`` and ending at ``dip_v``. mV/us is numerically V/ms (1 mV/us =
    1e-3 V / 1e-6 s = 1e3 V/s = 1 V/ms), so edge_ms = delta_V / slew_mvus."""
    return (vdd - dip_v) / slew_mvus


def render_stimulus(slew_mvus: float, label: str) -> str:
    t_dip = T_DIP_MS
    t_dwell = T_DWELL_MS
    # Worst-case (longest) edge sets the header's illustrative timeline and
    # is used nowhere in the actual PWL, which computes edge_ms from
    # {vdd_val} at elaboration time for EVERY point in the grid.
    vdd_max = NOMINAL_SUPPLY_V * (1 + SUPPLY_TOLERANCE)
    edge_illustrative = edge_ms_at(vdd_max, slew_mvus)
    return f"""\
* por-brownout-slew -- stimulus half of the testbench fragment.
* GENERATED by testbench/gen_rung.py --slew-mvus {slew_mvus!r} --label {label!r}
* Do not hand-edit -- re-run the generator to change the rung.
*
* The other half is a verbatim copy of design/netlist/temp_por_top.spice,
* appended by sim/build_tb.py to produce tb_por_brownout_slew.spice.
*
* Netlist FRAGMENT: no .include / .lib / .temp / .control / .end -- the
* harness owns those. Parameters it supplies: vdd_val, vdd_nom, temp_c.
*
* WHAT THIS RUNG SUBSTANTIATES (issue #60 / DR-011 decision 2)
*
* Same 1.0 V / 50 us qualifying dip as sim/por-brownout/'s parent record,
* with ONE variable: the falling SLEW RATE, here {slew_mvus:.6g} mV/us --
* held CONSTANT across the whole 81-point grid by writing the PWL edge time
* as an expression in {{vdd_val}} (see gen_rung.py's module docstring for why
* a fixed EDGE DURATION would not do this -- the dip target is a fixed
* absolute voltage, not a fixed delta below vdd_val, so a fixed duration
* would silently vary the realized slew by supply corner).
* Depth (1.0 V) and dwell (50 us) are held fixed, well inside por-brownout's
* other two qualifying-dip clauses, per DR-011 decision 4 and control E/A
* (which already show neither is the discriminator) -- isolating slew.
*
* WHY THE RECOVERY EDGE IS STILL PRESENT: por-brownout's own 81-point
* record shows a FAILING rung's RESETn does not stay silent forever -- it
* reasserts on the RECOVERY edge (the rail RISING back to vdd_val), at
* 51.26-51.58 us after dip start on that deck's 1 us edge. Cutting the
* stimulus off at dip-end would make a failing rung's own sanity/attribution
* measurement (resetn_ratio_min_overall) read "never resolves at all",
* which is not this rung's claim -- the claim is narrower: whether it
* resolves DURING the dip. The recovery edge is included, but the long
* (35 ms) further hold sim/por-brownout/ uses to check pulse regeneration
* and chatter is NOT -- this experiment does not re-derive those.
*
* ONE DUT, ONE TRAN, staged as a timeline (illustrative edge duration shown
* at the WORST-CASE, i.e. longest, supply corner, vdd={vdd_max:.4g} V; the
* actual edge duration used at each grid point is computed from that
* point's own {{vdd_val}} so the realized SLEW, not the edge duration, is
* what stays fixed across the grid):
*
*   0    ->  1 ms       cold start: VDD ramps 0 -> vdd_val in 1 ms, exactly
*                        as sim/por-brownout/ and sim/temp-por-top-release/.
*    1   -> {t_dip:g} ms       held at vdd_val -- rail settled, RESETn released.
*   {t_dip:g}   -> ~{t_dip + edge_illustrative:g} ms   VDD dips from vdd_val to {DIP_V:g} V at
*                        {slew_mvus:.6g} mV/us ({edge_illustrative:g} ms edge at this corner's vdd).
*   ~{t_dip + edge_illustrative:g} -> ~{t_dip + edge_illustrative + t_dwell:g} ms  held at {DIP_V:g} V for {t_dwell*1e3:g} us (50 us,
*                        sim/por-brownout/'s own qualifying dwell -- 5x T_dip,min).
*   ~{t_dip + edge_illustrative + t_dwell:g} -> ~{t_dip + 2*edge_illustrative + t_dwell:g} ms  VDD recovers from {DIP_V:g} V to vdd_val
*                        at the same {slew_mvus:.6g} mV/us magnitude.
*   ~{t_dip + 2*edge_illustrative + t_dwell:g} -> end  held at vdd_val -- {RECOVERY_MARGIN_MS*1e3:g} us of margin
*                        for a recovery-edge reassert to complete (see
*                        above); NOT a pulse-regeneration or chatter check.

* All .param values and PWL breakpoint expressions below are in SPICE base
* units (seconds, volts) -- no "m"/"u" suffixes on expressions -- because
* two pitfalls surfaced while developing this generator (each confirmed via
* a standalone ngspice smoke test, see the module docstring):
*   1. A ``.param`` whose RHS references ANOTHER ``.param`` (e.g.
*      ``.param t_edge = (vdd_val-dip_v)/slew_mvus``) does not evaluate on
*      this ngspice build ("Undefined parameter"/"Cannot compute
*      substitute") -- only a VALUE FIELD (a source/PWL breakpoint) may
*      combine multiple independently-defined ``.param``s via ``{{...}}``.
*      The edge-time formula is therefore written out in full at every
*      breakpoint instead of through an intermediate ``.param``.
*   2. Appending a literal SI suffix directly after a ``{{...}}`` expression
*      (e.g. ``{{t_dip+t_edge}}m``) re-applies that suffix to a value that,
*      if t_dip/t_edge are already in seconds, is already in base units --
*      silently scaling it by another 1e-3. Every quantity below is kept in
*      seconds throughout instead.
.param dip_v = {DIP_V!r}
.param t_dip = {t_dip * 1e-3!r}
.param t_dwell = {t_dwell * 1e-3!r}
.param slew_mvus = {slew_mvus!r}
* mV/us is numerically V/ms (see gen_rung.py's edge_ms_at()); the *1e-3
* below converts that ms-valued ratio to the seconds every other quantity
* in this PWL is expressed in.

vsup vdd 0 PWL(
+ 0                                                                 0
+ 1e-3                                                              {{vdd_val}}
+ {{t_dip}}                                                          {{vdd_val}}
+ {{t_dip+(vdd_val-dip_v)/slew_mvus*1e-3}}                           {{dip_v}}
+ {{t_dip+(vdd_val-dip_v)/slew_mvus*1e-3+t_dwell}}                   {{dip_v}}
+ {{t_dip+2*(vdd_val-dip_v)/slew_mvus*1e-3+t_dwell}}                 {{vdd_val}}
+ {{t_dip+2*(vdd_val-dip_v)/slew_mvus*1e-3+t_dwell+{RECOVERY_MARGIN_MS * 1e-3!r}}} {{vdd_val}}
+ )

Cpp ptat 0 1p
Cpc ctat 0 1p
Rlp ptat 0 1T
Rlc ctat 0 1T
Crn resetn 0 5p

xdut vdd 0 ptat ctat resetn temp_por_top
"""


def render_manifest(slew_mvus: float, label: str) -> dict:
    t_dip = T_DIP_MS
    t_dwell = T_DWELL_MS
    vdd_lo = NOMINAL_SUPPLY_V * (1 - SUPPLY_TOLERANCE)
    vdd_nom = NOMINAL_SUPPLY_V
    vdd_hi = NOMINAL_SUPPLY_V * (1 + SUPPLY_TOLERANCE)
    edge_max = edge_ms_at(vdd_hi, slew_mvus)
    # tran stop time must cover the WORST-CASE (longest) edge across the
    # grid -- the +10% supply corner, since edge_ms scales with vdd_val at
    # fixed slew.
    t_dip_end_max = t_dip + edge_max + t_dwell
    t_end = t_dip_end_max + edge_max + RECOVERY_MARGIN_MS

    # WHY A PER-SUPPLY BRANCH, NOT ONE SHARED WINDOW: gen_rung.py's own
    # smoke test (see module docstring) proved ngspice's `meas ... from=/
    # to=` does NOT accept `{...}` .param-expression substitution -- only
    # netlist CARDS (the PWL source) get that from numparam; `.control`
    # block commands read literal text. A single window sized to the
    # worst-case (longest) edge would therefore bleed into a shorter-edge
    # corner's own recovery edge (a real false-PASS risk: DR-011 shows the
    # recovery-edge reassert can land within a fraction of a microsecond of
    # the recovery edge starting); a window sized to the shortest edge would
    # instead cut a longer-edge corner off before its OWN falling edge even
    # reaches the dip floor. Neither fixed literal window is correct for
    # every corner. Branching on a MEASURED (not param) settled-VDD value
    # -- confirmed working via a standalone ngspice smoke test -- lets each
    # of the three known supply points (vdd_nom +/- supply_tolerance, fixed
    # by this manifest) use its OWN exactly-computed literal window.
    def windows(vdd: float) -> dict[str, float]:
        edge = edge_ms_at(vdd, slew_mvus)
        dip_end = t_dip + edge + t_dwell
        return {
            "dip_end": dip_end,
            "vdd_sample": t_dip + edge + t_dwell * 0.5,
            "floor_sample": t_dip + edge + t_dwell * 0.9,
        }

    branches = [(vdd_hi, windows(vdd_hi)), (vdd_nom, windows(vdd_nom)), (vdd_lo, windows(vdd_lo))]
    # Thresholds bisect the three known, fixed (nominal_supply_v /
    # supply_tolerance are NOT CLI-overridden by this experiment) supply
    # points -- not a general-purpose supply classifier.
    thresh_hi = (vdd_hi + vdd_nom) / 2
    thresh_lo = (vdd_nom + vdd_lo) / 2

    def branch_meas(w: dict[str, float]) -> list[str]:
        return [
            f"  meas tran bok_r_min min bok_r from={t_dip:g}m to={w['dip_end']:g}m",
            f"  meas tran rst_r_min min rst_r from={t_dip:g}m to={w['dip_end']:g}m",
            f"  meas tran praw_r_min min praw_r from={t_dip:g}m to={w['dip_end']:g}m",
            f"  meas tran vrst_floor find v(resetn) at={w['floor_sample']:g}m",
            f"  meas tran vdd_dip find v(vdd) at={w['vdd_sample']:g}m",
        ]

    analyses = [
        f"tran 20u {t_end:g}m",
        f"meas tran vrst_pre find v(resetn) at={t_dip - 0.1:g}m",
        "let bok_r = v(xdut.bias_ok)/(v(vdd)+0.001)",
        "let rst_r = v(resetn)/(v(vdd)+0.001)",
        "let praw_r = v(xdut.por_raw)/(v(vdd)+0.001)",
        f"meas tran rst_r_min_overall min rst_r from={t_dip:g}m to={t_end:g}m",
        # settled VDD (before the dip starts) selects which of the three
        # known supply corners' own exact literal window applies.
        f"meas tran vdd_settled find v(vdd) at={t_dip - 0.1:g}m",
        f"if vdd_settled > {thresh_hi:g}",
        *branch_meas(branches[0][1]),
        "else",
        f"if vdd_settled > {thresh_lo:g}",
        *branch_meas(branches[1][1]),
        "else",
        *branch_meas(branches[2][1]),
        "end",
        "end",
    ]

    measure = {
        "resetn_pre_dip_v": "vrst_pre",
        "vdd_dip_v": "vdd_dip",
        "bias_ok_ratio_min_in_dip": "bok_r_min",
        "resetn_ratio_min_in_dip": "rst_r_min",
        "por_raw_ratio_min_in_dip": "praw_r_min",
        "resetn_ratio_min_overall": "rst_r_min_overall",
        "resetn_floor_in_dip_mv": "vrst_floor*1e3",
    }

    checks = {
        "resetn_pre_dip_v": {
            "min": 2.8,
            "description": "sanity: RESETn is released before the dip starts.",
        },
        "vdd_dip_v": {
            "max": 1.05,
            "description": "sanity: the dip actually reached its programmed depth "
            f"({DIP_V:g} V, below VPOR-downarrow,min = 2.22 V at every corner).",
        },
        "bias_ok_ratio_min_in_dip": {
            "max": 0.5,
            "description": "THE CHEAP DISCRIMINATOR (curator #60 notes): BIAS_OK/VDD "
            "must resolve toward 0 during the dip, not ride the rail near 1.0 "
            "(a false valid, DR-011's starved-loop-window signature).",
        },
        "resetn_ratio_min_in_dip": {
            "max": 0.1,
            "description": "THE #60 CLAIM ITSELF: RESETn/VDD must reach the spec's "
            "own valid-low ratio bound (<=0.1xVDD, spec/target-spec.md#por-reset-"
            "valid-floor) DURING the dip (measured over each supply corner's own "
            "exact literal window, selected by a settled-VDD branch -- see "
            "gen_rung.py) at this falling slew rate. PASS at every corner is the "
            "falling-slew-boundary ratification criterion.",
        },
        "resetn_ratio_min_overall": {
            "max": 0.15,
            "description": "sanity/attribution: RESETn must EVENTUALLY reach a "
            "near-valid-low ratio somewhere in dip+recovery-edge+margin, whether or "
            "not it did so during the dip itself -- confirms a failing rung is a "
            "recovery-edge reassert (DR-011), not a testbench that never resets at "
            "all.",
        },
    }

    return {
        "name": "por-brownout-slew",
        "description": (
            f"Falling-slew boundary rung '{label}': same 1.0 V / 50 us qualifying "
            f"dip as sim/por-brownout/, falling slew = {slew_mvus:.6g} mV/us, held "
            "constant across the 81-point grid (edge duration computed per-point "
            "from that point's own vdd_val -- see gen_rung.py). Issue #60 / "
            "DR-011 decision 2."
        ),
        "claim": (
            "spec/target-spec.md#por-brownout clause (c) -- dVDD/dt|fall,max "
            f"characterization, rung '{label}' ({slew_mvus:.6g} mV/us): does "
            "RESETn reach the spec's own valid-low ratio bound DURING the dip at "
            "this falling slew rate, across the full 81-point grid? DR-011 "
            "decision 2 requires this full-grid characterization before the "
            "clause may be ratified. Deterministic corners only (design.ngspice "
            "sets sw_stat_mismatch=0); mismatch is #15's job."
        ),
        "netlist": "tb_por_brownout_slew.spice",
        "nominal_supply_v": NOMINAL_SUPPLY_V,
        "supply_tolerance": SUPPLY_TOLERANCE,
        "temperatures_c": [-40, 27, 125],
        "corners": ["full"],
        "options": ["reltol=1e-4", "abstol=1e-13", "vntol=1e-8", "method=gear"],
        "analyses": analyses,
        "measure": measure,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slew-mvus", type=float, required=True, help="falling slew rate, mV/us"
    )
    parser.add_argument(
        "--label", required=True, help="rung label, e.g. 'b-slew-7.667mvus'"
    )
    args = parser.parse_args(argv)

    stimulus_path = TESTBENCH_DIR / STIMULUS_NAME
    manifest_path = TESTBENCH_DIR / MANIFEST_NAME

    stimulus_path.write_text(render_stimulus(args.slew_mvus, args.label))
    manifest = render_manifest(args.slew_mvus, args.label)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"wrote {stimulus_path}")
    print(f"wrote {manifest_path}")
    print(f"rung '{args.label}': slew={args.slew_mvus:.6g} mV/us (fixed across grid)")
    print("next: python3 sim/build_tb.py por-brownout-slew")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
