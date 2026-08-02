# DR-016: `por-ramp-rate`'s release-edge chatter is a relaxation loop through the shared `IBIAS` node — fixed by a release latch, not by re-sizing the trip detector

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #56
- **Supersedes**: [DR-015](DR-015-por-ramp-rate-chatter-root-cause.md)

## Context

`sim/por-ramp-rate/records/20260802-000004-32fbaa0.md` (81-point PVT grid,
full four-cell assembly, all four ratified test rates) measures `RESETn`
chattering — crossing its 1.0 V release threshold more than once — at up to
60 of 81 points per rate, up to 109.6 µs against a ≤1 ns bound. 21/81 PASS,
and **every** failure in that record is a chatter failure: `vddrel_*` (no
early release) and `t_release_*` (liveness) pass at all 81 points and all
four rates.

[DR-015](DR-015-por-ramp-rate-chatter-root-cause.md) correctly ruled out
`design/bias_core.md`'s starved-loop window and correctly observed that
`TRIP`/`RSTB` toggle in lock-step with `RESETn`, but stopped at "a marginal
transition somewhere inside `por_output_chain`'s trip detector /
release-NAND / `XMAST` loop" and filed no fix. That localisation was
**wrong**, and the reason it was wrong matters: the loop does not close
inside `por_output_chain` at all.

`sim/por-ramp-rate/control/run_chatter_probe.py` now runs the same three PVT
+ rate points in **four arms**, each an asserted single-line edit away from
the committed `design/netlist/temp_por_top.spice`, and traces the shared-bias
nodes as well as the release path:

| Arm | Edit | `RESETn` crossings (`tt_27c` @ 10 V/s, 1 V/s; `tt_-40c` @ 10 V/s) |
| --- | --- | --- |
| `asbuilt` | none (with `XMRLK`) | 1, 1, 1 |
| `nokeeper` | `XMRLK` deleted (the circuit the record measured) | **3, 3**, 1 |
| `nokeeper_en_vdd` | `XMRLK` deleted, `temp_core.EN` tied to `VDD` | 1, 1, 1 |
| `nokeeper_en_vss` | `XMRLK` deleted, `temp_core.EN` tied to `VSS` | 1, 1, 1 |

At the top level, **`temp_core`'s `EN` pin is `RESETn`** — the sensor is held
disabled while reset is asserted, per
[DR-010](DR-010-shared-ibias-disabled-consumer-contract.md). So `RESETn`'s
own release adds `temp_core`'s mirror diode to the shared `IBIAS` node and
steps that node **down by 34.4 mV** (`tt`/27 °C; 28.0 mV at −40 °C) across a
window in which `VDD` moves only 3.2 mV. `por_output_chain`'s starve
reference `NDL` follows (−25.5 mV — most of a decade in weak inversion),
which halves the nA sink that sets the trip detector's stage-A balance point,
so `ND1` drifts back up (28.3 mV → 569 mV within 300 µs) until `XMDBNI`
re-conducts, `TRIP` collapses, and `RESETn` **re-asserts** — which disables
`temp_core`, restores `IBIAS`, and restarts the cycle.

That single mechanism accounts for both features of the record that made the
finding look like something else:

- **Ramp-rate independence** — the trigger is a *load step* on the shared
  node and the period is set by `ND1`'s own nA/fF drift; `dVDD/dt` appears
  nowhere in the loop.
- **Temperature dependence** — in the cold the step is smaller (−28.0 mV) and
  `ND1`'s drift peaks at 425.7 mV instead of 569.0 mV, short of `XMDBNI`'s
  conduction point. The −40 °C corners never close the loop.

The two `nokeeper_en_*` arms are the proof: cutting the `RESETn` →
`temp_core.EN` → `IBIAS` path — in **either** direction, permanently enabled
or permanently disabled — removes the chatter entirely without touching a
single device in `por_output_chain`. An instability internal to the trip
detector could not have been fixed that way.

Full writeup: `design/por_output_chain.md`, "The release-edge chatter — a
relaxation loop through the shared `IBIAS` node". Full evidence:
`sim/por-ramp-rate/control/results.md`.

## Decision

**One device is added to `design/por_output_chain.sch`: `XMRLK`, an nfet
1 µm / 1 µm from `ND1` to `VSS` with its gate on `RESETn` — a release latch,
the counterpart of the `XMAST` keeper that already latches the *asserted*
state.** Once `RESETn` is high, `ND1` is held at `VSS`, `TRIP` stays at the
rail, and the release is one-way regardless of where the shared node's
operating point drifts afterwards.

No other device changes. No target-spec value is added, removed or relaxed by
this record; `spec/target-spec.md`'s `por-ramp-rate` row is amended to cite
the corrected root cause and the fix, and its measured result is replaced
with the new full-grid record. The row's status remains `pending #1` **on the
starved-loop-window sub-issue alone** — the chatter sub-issue this record
resolves is now closed by measurement, but `design/bias_core.md`'s
architecture-level `por-iq`-vs-bandwidth tension is untouched and still
belongs to #1.

The fix is safe on the three properties that would otherwise make a latch
dangerous in a POR:

- **It cannot arm prematurely.** `RSTB` = NAND(`TRIP`, `PGDG`), so `PGDG` low
  pins `RSTB` high and `RESETn` low *regardless of `TRIP`*. The latch can only
  arm once the deglitched rail is already good. The below-floor default —
  `ND1` pinned high, `TRIP` pinned low, `RESETn` asserted, no static current —
  is unchanged, because `RESETn` low means `XMRLK` is off.
- **Brownout re-arming is unaffected.** `PGDG` falls → `RSTB` rises →
  `RESETn` falls → `XMRLK` opens, all before `ND1` has to move; `XMDIS` then
  discharges `TIM` into an undisturbed trip detector exactly as before.
- **It costs no static current.** In the released state it sinks the same
  sub-nA `XMDAPI` subthreshold leg `XMDANT` was already sinking; it adds no
  crowbar path; in the asserted state it is off.

**A general clause is added to DR-010's shared-`IBIAS` contract.** DR-010
stated it statically ("a disabled consumer must present high impedance").
This record adds the dynamic half: **enabling or disabling a consumer steps
the shared node's operating point by tens of millivolts, and every nA-biased
decision hanging off that node moves with it.** A decision the shared node
can walk back must be *latched*, not left as a standing analog comparison —
especially when the consumer being switched is gated by the very output that
decision produces.

## Alternatives considered

- **Re-size the trip detector / release NAND / `XMAST` loop (DR-015's own
  recommendation).** Rejected on the evidence: the `nokeeper_en_*` arms show
  the chatter is not a property of that loop's internal margins at all, so
  any sizing change would have been tuning a symptom. Worse, it would have
  been tuning *against* a moving bias — the −34 mV step is a real operating
  point the block occupies, so a margin bought at one corner is not a margin
  at another. (Sizing may still be the wrong shape of answer for other
  reasons: it costs Iq against `por-iq`, which is already 2.37× over budget.)
- **Stop gating `temp_core` with `RESETn` (tie `EN` high, or gate it on
  `BIAS_OK`).** Rejected — the `nokeeper_en_vdd` arm shows it works, but it
  discards DR-010's whole reason for existing (the sensor must not draw or
  disturb while reset is asserted) and would re-cost `por-iq` during reset.
  It also does not generalise: the next consumer gated on `RESETn` would
  reintroduce the same loop.
- **Stiffen the shared `IBIAS` node so enabling a consumer does not move
  it.** Rejected as not buildable inside this budget: the node is a
  sub-µA-class mirror reference by construction, and making its impedance low
  enough that a third diode load does not move it by tens of millivolts means
  spending orders of magnitude more current than `por-iq` has.
- **Accept the chatter and re-cost the spec row.** Rejected outright. The row
  forbids a double pulse for a reason a downstream system cares about, the
  effect is a genuine multi-edge `RESETn`, and CLAUDE.md forbids relaxing a
  ratified row to make a result pass. It is also unnecessary: the defect is
  fixable by one device.
- **Leave DR-015 standing and file this as an addendum.** Rejected — DR-015's
  central localisation claim ("originates entirely inside `por_output_chain`'s
  trip detector") is contradicted by the loop-break arms, and a wrong
  localisation left in the record would misdirect any future work on this
  cell. Per the template, a `proposed` record that is wrong is superseded,
  not edited.

## Consequences

- **`design/por_output_chain.sch` gains one device** (27 → 28 MOS), so
  `design/netlist/por_output_chain.spice` and
  `design/netlist/temp_por_top.spice` are no longer byte-identical to what
  DR-014/DR-015 recorded, every generated testbench under `sim/*/testbench/`
  is regenerated by `sim/build_tb.py`, and `layout/` regains a 28th drawn
  device in `por_output_chain` (and `temp_por_top` with it), re-checked
  DRC/LVS-clean by `layout/run_checks.sh`.
- **Every experiment that instantiates `por_output_chain` is re-verified**,
  not just `por-ramp-rate`: the three cell-level records
  (`por-output-chain-pulse`, `-deglitch`, `-floor`) and the assembly-level
  `temp-por-top-release` and `por-glitch`. Their new records are the evidence
  that this device changed the one thing it was meant to and nothing else.
- **`sim/por-ramp-rate/`'s 21/81 result is superseded by a full-grid re-run**
  with the latch in place. Because that record's only failing checks were the
  four `chatter_*` bounds, the re-run is the whole test of this decision.
- **`por-glitch` is not affected by this record and does not improve.** Its
  mechanism ([DR-014](DR-014-por-glitch-vdd-level-immunity.md)) runs through
  `PGDG` collapsing with `VDD`, which forces `RSTB` high and opens this latch
  by design. See [DR-017](DR-017-por-glitch-representative-depth.md) for that
  half of #56.
- **What becomes harder.** The release is now genuinely irreversible until
  `PGDG` falls. Any future change that makes `PGDG` less trustworthy — a
  wider deglitch dwell, a different power-good source — inherits a
  correspondingly larger responsibility, because `PGDG` is now the *only*
  path that can re-assert reset once the latch has armed. That is stated here
  so it is not rediscovered later.
