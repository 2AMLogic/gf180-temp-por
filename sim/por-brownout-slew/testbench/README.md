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
# 1. Generate the rung's stimulus + BOTH tb.json manifests (overwrites
#    testbench/ and testbench-postlayout/ in place — neither is versioned per
#    record, per sim/README.md; only the frozen
#    netlist-snapshots/<record-id>.spice preserves what actually ran)
python3 sim/por-brownout-slew/testbench/gen_rung.py \
    --slew-mvus 3.40 --label k-slew-3.40mvus \
    --postlayout-supersedes 20260802-120940-3c3e728

# 2. Rebuild the frozen testbench netlists (schematic + post-layout) from the
#    current stimulus
python3 sim/build_tb.py por-brownout-slew

# 3. Run the full 81-point grid, minting a new append-only record
python3 sim/run_corners.py por-brownout-slew -j 16 \
    --claim "spec/target-spec.md#por-brownout clause (c) -- dVDD/dt|fall,max characterization, rung k-slew-3.40mvus"

# 3b. …or the same rung against the EXTRACTED netlist (#86/#87), which reads
#     testbench-postlayout/tb.json rather than testbench/tb.json
python3 sim/run_corners.py sim/por-brownout-slew/testbench-postlayout -j 16 \
    --supersedes 20260802-120940-3c3e728
```

Each record's own `Claim` line embeds the rung label and slew rate it ran,
so nothing about which rung produced which record is lost even though
`testbench/` itself is overwritten between rungs.

**Why the generator writes the post-layout manifest too (#188).**
`sim/build_tb.py`'s `POSTLAYOUT_FRAGMENTS` builds the extracted-netlist
*fragment* into `testbench-postlayout/`, but `sim/README.md` describes that
directory's `tb.json` as hand-authored — which is fine for an experiment
whose manifest is written once, and wrong for this one, whose manifest is
**regenerated per rung** (every rung shifts the per-supply measurement
windows, because the edge duration that realizes a given slew depends on the
rung). A hand-maintained post-layout copy would silently run the new rung
against the previous rung's windows. `gen_rung.py` therefore emits both from
the same `render_manifest()` output; the only differences are the netlist
name, the two provenance fields `sim/harness/testbench.py` requires for
`"extracted"`, and the appended POST-LAYOUT sentences — exactly the delta #87
landed by hand, which the generator reproduced byte-for-byte for the
`n-slew-3.46mvus` rung it was written against.

One sentence of that delta has since been re-worded, so the byte-for-byte
correspondence holds against #87's manifest as of commit `442ffd9` and not
after it: #87's claim text opened "Post-layout re-run (#87, under #18)",
which is a true sentence about the rung #87 itself ran and a false one about
every later rung the same generator emits (the post-layout ladder below the
ratified bound was run for #188, not #87). It now names the harness — "the
#86/#87 extracted-netlist harness (under #18)" — which stays true whichever
issue commissions the rung.

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

## The post-layout ladder (#188)

Since #86/#87 a rung can be run against the extracted netlist too, and the
two ladders are **different ladders on the same axis** — `_rung_record.py`
refuses to mix them, and `analyze_boundary.py --provenance extracted` reduces
the second one. The extracted ladder is short because it only had to answer
one question and then bracket the answer:

| Rung | schematic | extracted |
| ---: | ---: | ---: |
| 2.30 mV/µs | 81/81 | **81/81** |
| 2.40 mV/µs | — | **81/81** |
| 2.45 mV/µs | — | **81/81** |
| 2.50 mV/µs | — | 80/81 (`ss_-40c_2.97v`) |
| 3.40 mV/µs (the bound ratified from the schematic ladder) | 81/81 | **76/81** |
| 3.46 mV/µs | 80/81 | 75/81 |

The transition edge moves from 3.44/3.46 to **2.45/2.50 mV/µs**, and
`spec/target-spec.md#por-brownout` clause (c) is re-cost to **2.30 mV/µs** by
[DR-019](../../../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md).
Choosing 2.30 rather than the mechanical bracket 2.45 follows the same rule
the section above states for the schematic bound — the safe side of the whole
transition, not one bisection step below a FAIL — with the margin made
numeric by
[`control/postlayout_margin_results.md`](../control/postlayout_margin_results.md):
+209.8 µs of dip window at 2.30 mV/µs against +29.7 µs at 2.45 mV/µs, read
against the +108.8 µs the outgoing bound carried on the schematic netlist.

The binding corner also shifts inside the same family, from `ss_-40c_3.30v`
to `ss_-40c_2.97v`, so the extracted boundary record's own binding-corner
line is not a transcription of the schematic one.

## Where the result lands

- Per-corner bracket table + binding-corner identification:
  [`sim/por-brownout-slew/analyze_boundary.py`](../analyze_boundary.py)
  (a **derived** record per `sim/README.md` — no new simulation, just
  recombines each rung record's own `pass/fail` column) →
  `sim/por-brownout-slew/records/<latest-record-id>-boundary.md`, one per
  provenance (`--provenance schematic|extracted`, defaulting to the #60
  ladder the script was written for).
- Ratified bound: `spec/target-spec.md#por-brownout` clause (c),
  `dVDD/dt|fall,max = 2.30 mV/µs` (was 3.40 mV/µs from the schematic ladder;
  re-cost against the extracted netlist by DR-019, #188).
- Post-layout margin behind that bound, at the binding family:
  [`control/run_postlayout_margin.py`](../control/run_postlayout_margin.py)
  (a **control**, not a record) → `control/postlayout_margin_results.md`.
- DR-011 decision 2's gate: satisfied by this full-grid characterization;
  `por-brownout`'s `pending #1` status is unchanged pending #1's own overall
  ratification pass.
- Non-monotonic band shape + mechanism (#74):
  [`sim/por-brownout-slew/analyze_transition_band.py`](../analyze_transition_band.py)
  (also derived; reads the rung records above plus
  [`control/results.json`](../control/results.json)) →
  `sim/por-brownout-slew/records/<latest-record-id>-transition-band.md`.
