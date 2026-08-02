# `sim/por-brownout-slew/` — falling-slew boundary characterization (#60)

DR-011 root-caused `por-brownout`'s 0/81 failure to the rail's **falling
slew rate**, not its dip depth or dwell, and added a third qualifying
clause: `(c) falls no faster than dVDD/dt|fall,max`. DR-011 decision 2
forbade ratifying that bound from its own one-corner control evidence and
required a full 81-point characterization — this experiment.

## What varies, what is held fixed

Every rung shares the same 1.0 V dip target and 50 µs dwell as
`sim/por-brownout/`'s own qualifying dip (DR-011 decision 4: depth and
duration are already shown not to be the discriminator; only slew is
isolated here). The **one** free variable is the falling slew rate,
`slew_mvus`, held CONSTANT across the whole 81-point grid per rung by
writing the PWL edge time as an expression in `{vdd_val}` — see
`gen_rung.py`'s module docstring for why a fixed edge DURATION would not do
this (the dip target is a fixed absolute voltage, not a fixed delta below
`vdd_val`, so a fixed duration silently varies the realized slew by supply
corner).

## Workflow: adding a rung

```bash
# 1. Generate the rung's stimulus + tb.json (overwrites testbench/ in place —
#    testbench/ is not versioned per record, per sim/README.md; only the
#    frozen netlist-snapshots/<record-id>.spice preserves what actually ran)
python3 sim/por-brownout-slew/testbench/gen_rung.py \
    --slew-mvus 3.40 --label k-slew-3.40mvus

# 2. Rebuild the frozen testbench netlist from the current stimulus
python3 sim/build_tb.py por-brownout-slew

# 3. Run the full 81-point grid, minting a new append-only record
python3 sim/run_corners.py por-brownout-slew -j 16 \
    --claim "spec/target-spec.md#por-brownout clause (c) -- dVDD/dt|fall,max characterization, rung k-slew-3.40mvus"
```

Each record's own `Claim` line embeds the rung label and slew rate it ran,
so nothing about which rung produced which record is lost even though
`testbench/` itself is overwritten between rungs.

## Search strategy used (issue #60's design notes)

Sweep the control's own ladder (2300 / 23.00 / 15.33 / 11.50 / 7.67 / 2.30 /
0.77 mV/µs), refined by bisection once a corner's bracket is found. In
practice: `2.30` (81/81 PASS) and `7.667` (51/81 PASS, mostly −40 °C
failures) bracketed the transition; bisecting toward the binding corner (SS
/ −40 °C, matching this row's own architectural prediction) converged in a
handful of further full-grid rungs to a tight bracket: **PASS at 3.40 mV/µs,
FAIL from 3.4795 mV/µs**.

**The transition is not a single clean threshold.** Between roughly
3.48–4.2 mV/µs the SS/−40 °C family's three supply points do not fail in a
monotonic order as slew increases — e.g. 3.4795 mV/µs fails all three
2.97/3.30/3.63 V points, while the numerically faster (less safe) 3.613
mV/µs fails only the 2.97 V point. This knife-edge, non-monotonic behaviour
is consistent with `design/bias_core.md`'s starved-loop mechanism being a
nonlinear relaxation dynamic: near its own critical timing, small changes in
the falling edge's duration can shift the phase relationship between the
collapsing loop and the measurement window non-monotonically. The ratified
bound is chosen on the safe side of the *entire* transition band (a clean
81/81 PASS with robust per-point margins at 3.40 mV/µs — not merely one
bisection step above a single observed FAIL), so it is not undermined by
that non-monotonicity, but the zone itself is flagged as worth a follow-up
characterization rather than resolved here.

**Follow-up (#74).** Three additional full-grid rungs (3.42/3.44/3.46 mV/µs)
and an event-timing control at the `ss`/−40 °C binding family map the band's
shape and its mechanism: it is a race between the shrinking dip window and
`por_output_chain`'s deglitch dwell, realized far past its documented
ceiling because the near-boundary edge has not finished falling when
`POR_RAW` trips — see
[`sim/por-brownout-slew/records/20260802-134958-dd0cd60-transition-band.md`](../records/20260802-134958-dd0cd60-transition-band.md)
and `design/bias_core.md`'s "starved-loop window" section. The earliest
observed FAIL also moved down from 3.4795 to **3.46 mV/µs** (`ss`/−40 °C/
3.30 V); the ratified 3.40 mV/µs bound is unaffected (every PASS margin at or
below it is ≥108.7 µs, well clear of the band).

## Where the result lands

- Per-corner bracket table + binding-corner identification:
  [`sim/por-brownout-slew/analyze_boundary.py`](../analyze_boundary.py)
  (a **derived** record per `sim/README.md` — no new simulation, just
  recombines each rung record's own `pass/fail` column) →
  `sim/por-brownout-slew/records/<latest-record-id>-boundary.md`.
- Ratified bound: `spec/target-spec.md#por-brownout` clause (c),
  `dVDD/dt|fall,max = 3.40 mV/µs`.
- DR-011 decision 2's gate: satisfied by this full-grid characterization;
  `por-brownout`'s `pending #1` status is unchanged pending #1's own overall
  ratification pass.
- Non-monotonic band shape + mechanism (#74):
  [`sim/por-brownout-slew/analyze_transition_band.py`](../analyze_transition_band.py)
  (also derived; reads the rung records above plus
  [`control/results.json`](../control/results.json)) →
  `sim/por-brownout-slew/records/<latest-record-id>-transition-band.md`.
