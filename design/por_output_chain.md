# `por_output_chain` — deglitch, ≥1 ms one-shot, push-pull output

Sizing rationale, Iq budget and corner numbers for
`design/por_output_chain.sch` (issue #12). Topology per
[DR-004](../spec/decision-records/DR-004-reset-polarity-drive.md) and
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md);
pulse-width policy per
[DR-003](../spec/decision-records/DR-003-por-reset-pulse.md); device choices
per [`sim/devchar/SUMMARY.md`](../sim/devchar/SUMMARY.md) (issue #4, PR #22);
targets per [`spec/target-spec.md`](../spec/target-spec.md), ratified via
DR-008 on #1. **This document does not change any ratified value**; it fills
the two TBDs `target-spec.md` §"owned TBDs" assigns to #12 by *publishing*
measured numbers here, leaving the ratified table itself to a future decision
record.

Every number below that is not a device dimension comes from a recorded
evidence run, not from an estimate:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/por-output-chain-pulse/`](../sim/por-output-chain-pulse/) — record `20260802-205904-bdc077d` (re-run on the post-#56 cell; `20260801-031819-fce635f` measured it before `XMRLK`) | [`por-reset-pulse`](../spec/target-spec.md#por-reset-pulse) ≥1 ms at nominal **and 3× IBIAS**, the deasserted level (push-pull, [`por-drive`](../spec/target-spec.md#por-drive)), no early release, and this cell's own share of [`por-iq`](../spec/target-spec.md#por-iq) in both the asserted and released states |
| [`sim/por-output-chain-deglitch/`](../sim/por-output-chain-deglitch/) — record `20260802-205904-bdc077d` (re-run on the post-#56 cell; `20260801-032128-309621f` measured it before `XMRLK`) | the deglitch **dwell time** ([`por-brownout`](../spec/target-spec.md#por-brownout)'s `[TBD-#12]`) at nominal **and half** IBIAS, capture of a *qualifying* 10 µs dip, regeneration of the full pulse after it, and the no-early/no-double-pulse chatter edge case |
| [`sim/por-output-chain-floor/`](../sim/por-output-chain-floor/) — record `20260802-205904-bdc077d` (re-run on the post-#56 cell; `20260801-032940-d59d7c4` measured it before `XMRLK`) | [`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) against a slow 0 V → VDD ramp, with `POR_RAW` held low **and** driven to the rail, plus [`por-polarity`](../spec/target-spec.md#por-polarity) (degrades to *asserted* near 0 V) |

All three are **81-point PVT grids** (9 process corners × −40/27/125 °C ×
2.97/3.30/3.63 V), the full matrix CLAUDE.md mandates, and all three are
**deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the systematic + corner term
only. Mismatch is #15's Monte Carlo job. Ramp-rate envelope, brownout on a
real (non-idealised) bring-up sequence, and top-level interaction with a real
`bias_core`/`por_comparator` are #14's.

## What this cell is and is not

- It owns the **time domain**: deglitch dwell, the ≥1 ms one-shot, and the
  final release gate. Per DR-005's ownership split, **hysteresis** — static
  chatter rejection for a slowly-varying rail — lives in `por_comparator`
  (#10) and is *not* substitutable for the dwell sized here. Neither cell
  double-counts the other's mechanism.
- It owns **`RESETn` below the comparator's operating floor**, where
  `POR_RAW` is undefined by construction (DR-004). The startup-assist
  pull-down is therefore *not gated by `POR_RAW`*, and the evidence proves
  that by re-running the whole floor ramp with `POR_RAW` driven **to the
  rail** below the floor.
- It does **not** decide the threshold. `POR_RAW` arrives already hysteretic.

## Interface

Unchanged from the ports-only placeholder committed in PR #29; this issue
replaced the internals only, so `design/por_output_chain.sym` is untouched.

| Pin | Dir | Meaning |
| --- | --- | --- |
| `VDD`, `VSS` | inout | 3.3 V core-flavor supply pair (DR-001) |
| `IBIAS` | in | shared bias-mirror node from `bias_core` (#11). Same convention as `temp_core`/`por_comparator`: `bias_core` **sources** 0.5 µA into this pin; `XMBD` is the local mirror diode. **`XMBD` is load-bearing beyond this cell under [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)**: it is ungated and always on, which makes it the element that *defines* the shared node's operating point now that no consumer is permitted to clamp that node. Do not gate it without re-reading DR-010 — the contract requires at least one always-on diode-connected input to remain on the net. |
| `POR_RAW` | in | raw hysteretic threshold decision from `por_comparator` (#10), **active high** = "rail is above VPOR↑ and the comparator's decision is authoritative". Low — including *undriven*-low below the comparator floor — is the fail-safe sense. |
| `RESETn` | out | reset pad, **active low**, **push-pull** (DR-004). |

## Topology

```
 IBIAS ─┬─ XMBD                     500 nA local mirror diode
        │
        ├─ XMN1 ─ PDN ─ XMPD        1:50  → 10 nA PMOS reference leg
        └────────  NDL ─ XMND       1:1   → 10 nA NMOS reference leg

 POR_RAW ─┬─ XMDGPI ─┐                    deglitch: 50 nA tails,
          └─ XMDGNI ─┴─ NDG ─ CDG         NDG traverses 242 fF at I/C
                        │
                     XMG1 ─ PGDG ─ XMG2 ─ PGDGB    two restoring inverters

 PGDGB ─ XMTSW ─ TIM ─ CTIM                one-shot: 2.5 nA into 6.27 pF
       ─ XMDIS ─┘                          (XMDIS slams TIM to VSS on PGDG↓)

 TIM ─ XMDAPI ─ ND1 ─ XMDBNI ─ TRIP        trip detector: two nA-limited
                                            current comparators

 (TRIP, PGDG) ─ NAND ─ RSTB ─ XMOP/XMON ─ RESETn
                        ↑
                     XMAST                 startup-assist keeper
```

`RESETn` is released only when **`TRIP` (the timer has expired) AND `PGDG`
(the deglitched rail is good)**. That final gate is in this cell, not in
`por_comparator` — DR-005's ordering step 6.

### Why the release gate is a NAND and not a NOR

Because the below-floor behaviour is decided by which way the gate's *leakage
divider* falls when the bias core is dead and both inputs sit at their
dead-circuit default (low):

- A **NAND** pulls up through two *parallel* PMOS against a *series* NMOS
  stack. Both inputs low ⇒ `RSTB` is pinned to VDD by a divider tens of times
  in the pull-up's favour once the stack's own I_off reduction is counted.
  `RSTB` = VDD turns `XMON` fully on and holds `XMOP` fully off — **that is
  the startup-assist pull-down of DR-004/DR-005**, and it needs no separate
  always-on leg (and therefore no always-on current) at all.
- A **NOR** would land the other way and hand `RESETn` to leakage.

`XMAST` (0.5 µm / 10 µm PMOS, gate on `RESETn`) closes the loop: with
`RESETn` low it latches `RSTB` high independently of `TRIP`/`PGDG`, so the
assist survives even the pathological case where `por_comparator` drives
`POR_RAW` high *below* its own floor. It is ~40× weaker than the NAND's NMOS
stack, so the real release still wins, and it draws nothing in either settled
state (`RESETn` high ⇒ V_gs = 0).

## Device sizing and why

| Device | W / L | Role |
| --- | --- | --- |
| `XMBD` | 4 µm / 4 µm | local mirror diode off `IBIAS` (500 nA) |
| `XMN1` | 0.5 µm / 25 µm | 1:50 against `XMBD` → 10 nA into `PDN` |
| `XMPD`, `XMP2` | 2 µm / 10 µm | 10 nA PMOS reference and its copy into `NDL` |
| `XMND` | 2 µm / 10 µm | 10 nA NMOS reference leg |
| `XMDGPT`, `XMDGNT` | 10 µm / 10 µm | deglitch tails, 5× the 10 nA legs → ~50 nA each |
| `XMDGPI`, `XMDGNI` | 1 µm / 0.5 µm | deglitch input pair (switches, not gain devices) |
| `CDG` | 11 µm × 11 µm MIM | 242 fF — **the dwell-setting capacitor**, see below |
| `XMG1P` / `XMG1N` | 0.5/2 µm, 2/0.5 µm | restoring inverter, skewed **NMOS-strong** |
| `XMG2P` / `XMG2N` | 2/0.5 µm, 0.5/2 µm | restoring inverter, skewed **PMOS-strong** (mirror image) |
| `XMPT` | 0.5 µm / 10 µm | 1:4 against `XMPD` → **2.5 nA** timer charge current |
| `XMTSW` | 2 µm / 1 µm | admits the charge current only while `PGDG` is high |
| `XMDIS` | 1 µm / 1 µm | discharges `TIM` on `PGDG`↓ — deliberately *narrow* |
| `CTIM` | 4 × 28 µm × 28 µm MIM | 6.27 pF — the one-shot capacitor |
| `XMDAPI` | 2 µm / 1 µm | trip stage A input PMOS |
| `XMDANT` | 0.5 µm / 10 µm | 2.5 nA sink for stage A |
| `XMDBNI` | 1 µm / 1 µm | trip stage B input NMOS |
| `XMDBPT` | 0.5 µm / 10 µm | 2.5 nA source for stage B |
| `XMRLK` | 1 µm / 1 µm | **release latch** — holds `ND1` at `VSS` once `RESETn` is high (issue #56) |
| `XMNAP1`, `XMNAP2` | 4 µm / 0.5 µm | release-NAND parallel pull-ups |
| `XMNAN1`, `XMNAN2` | 2 µm / 0.5 µm | release-NAND series pull-down stack |
| `XMAST` | 0.5 µm / 10 µm | startup-assist keeper on `RSTB` |
| `XMOP` | 1 µm / 1 µm | output pull-up |
| `XMON` | 10 µm / 0.5 µm | output pull-down — **20:1 in W/L against `XMOP`** |

Four of these are load-bearing enough to justify their own section — the last
one, `XMRLK`, was added by issue #56 and is written up in
[The release-edge chatter](#the-release-edge-chatter--a-relaxation-loop-through-the-shared-ibias-node-not-a-local-instability).

### The one-shot is a current-starved ramp, and its trip is `VDD − V_sg`

A fixed ≥1 ms pulse inside a sub-µA budget rules out an RC outright: 1 ms
into a 6 pF capacitor needs ~160 MΩ, which is not buildable here (and the
resistor's own current would eat the budget). So `XMPT` sources ~2.5 nA into
`CTIM` = 6.27 pF, `XMTSW` admits it only once the *deglitched* power-good is
asserted, and `XMDIS` slams `TIM` back to `VSS` the instant `PGDG` falls —
which is what regenerates the **full** pulse after a brownout, as
[`por-brownout`](../spec/target-spec.md#por-brownout) requires.

`XMDIS` is 1 µm / 1 µm and not wide **on purpose**: at FF / +125 °C a wide
discharge device's own I_off is a sizeable fraction of a 2.5 nA charging
current, and the timer would simply never finish.

The **trip detector is the load-bearing sizing decision in this cell**, and it
is not a starved inverter. A starved inverter has no defined trip point
against a slow ramp: its pull-up stops winning at `TIM ≈ VDD − |V_tp|` and
its pull-down starts winning at `TIM ≈ V_tn`, and those are two *different*
mechanisms with opposite temperature coefficients. The first cut of this cell
did exactly that and measured a trip from 2.55 V at −40 °C down to 0.28 V at
FF / +125 °C — a **9× pulse-width swing**, and **0.57 ms at FF / +125 °C
against a 1 ms floor**. Replacing it with `XMDAPI` alone against the `XMDANT`
sink leaves **one** mechanism: `ND1` falls when the PMOS can no longer supply
2.5 nA, i.e. at `TIM = VDD − V_sg(2.5 nA)`. That trip is rail-referenced with
only a `V_sg(T)` correction, so the pulse spreads ~1.8× over the grid instead
of 9×, and it uses nearly the whole rail of ramp instead of the bottom half
volt.

**Consequence worth stating plainly, because it contradicts a parenthetical
in the ratified table.** `por-reset-pulse` says the ≥1 ms minimum "binds at
the fastest-timer corner: FF / +125 °C / 3.63 V (highest bias current, lowest
capacitance)" — which is right for a *generic* current-starved one-shot with
a fixed trip voltage. Because this trip is `VDD − V_sg` rather than a fixed
voltage, the measured minimum is at **FF / −40 °C / 2.97 V** instead:
low rail shortens the ramp, and cold raises `V_sg` and shortens it further.
The claim does not rest on guessing correctly — the ≥1 ms check is applied at
**all 81 points**, so the recorded minimum is measured, not inferred. This is
a note for #14 and for any later re-ratification of that parenthetical; it is
**not** a spec relaxation, since the ratified requirement (≥1 ms, everywhere)
is met with margin at every point.

### Deglitch dwell — `CDG` is bounded on *both* sides

`NDG` has to traverse `CDG` at I/C before `XMG1` flips, so a `POR_RAW`
excursion shorter than the dwell never reaches `PGDG`. The dwell that matters
for [`por-brownout`](../spec/target-spec.md#por-brownout) is the
`POR_RAW`-**falling** one (`NDG` rising, `XMDGPT` charging `CDG`).

- **Upper bound**: the dwell must stay under `T_dip,min` = 10 µs, or a
  qualifying brownout dip is *rejected* and the row is unsatisfiable. It
  scales as 1/`IBIAS`, so the bound has to hold at the slow end of whatever
  `IBIAS` tolerance #11 lands on.
- **Lower bound**: a dwell only marginally longer than the transient it is
  meant to reject does not reject it. This is not theoretical — the first cut
  used `CDG` = 7 µm × 7 µm (98 fF), giving a **1.07 µs** dwell at FF / +125 °C,
  against which a **1 µs** `POR_RAW` glitch propagated straight through to
  `PGDG` (down to 75 mV) and restarted the timer at **30 of the 81** PVT
  points. The full-grid deglitch record is what caught it.

`CDG` = 11 µm × 11 µm (242 fF) sits between them: the **shortest** dwell
anywhere on the grid is 1.86 µs (FF / +125 °C / 2.97 V) and the **longest** is
4.58 µs (SS / −40 °C / 3.63 V) at nominal `IBIAS`, 8.88 µs at *half* nominal.
The two bounds are only about 3× apart once the dwell's own PVT × `IBIAS`
spread is counted, so this capacitor is not free to grow — see
[Hand-off to #11](#hand-off-to-11-the-ibias-envelope-is-the-real-constraint).

**The lower bound is measured, not inferred from the dwell number.** A dwell
of *D* does not mean "glitches shorter than *D* are rejected" — `PGDG` is a
continuous function of how far `NDG` got, and a glitch that takes `NDG` most
of the way to `XMG1`'s trip still drops `PGDG` far enough to fire `XMDIS` and
restart the timer. So the bound is measured by walking the glitch width until
the one-shot's `TIM` loses charge, in
[`sim/por-output-chain-deglitch/control/width_results.md`](../sim/por-output-chain-deglitch/control/width_results.md).
At both fast corners the schematic rejects a `POR_RAW` glitch **cleanly up to
1.75 µs** and is disturbed by 2 µs — **1.75× the 1 µs chatter**
[`sim/por-output-chain-deglitch/testbench/stimulus.spice`](../sim/por-output-chain-deglitch/testbench/stimulus.spice)
applies. That 1 µs is itself an *assumption*: nothing in the ratified table
bounds how narrow a `POR_RAW` excursion this cell must reject, so the floor is
a design-chosen guard, and how much margin it deserves is a question for #14's
assembly-level sweeps (which is where the real chatter width near the
comparator's threshold gets observed), not one this cell can settle alone.

**The width margin is now on the corner grid too, not only in that control**
(#200). A control runs at two corners and is overwritten on its next run;
[`testbench/stimulus.spice`](../sim/por-output-chain-deglitch/testbench/stimulus.spice)
therefore applies a **third** chatter burst at **1.05 µs** — 5 % wider than the
1 µs the older checks use, and inside the 1.0 / 1.25 µs bracket the control
measures the post-layout rejection ceiling in — after the qualifying dip has
restarted the pulse, where it disturbs no pre-existing measurement. Records
[`20260811-110622-d5b0168`](../sim/por-output-chain-deglitch/records/20260811-110622-d5b0168.md)
(schematic) and
[`20260811-110752-d5b0168`](../sim/por-output-chain-deglitch/records/20260811-110752-d5b0168.md)
(extracted), **81/81 PASS** each:

| at 1.05 µs, worst of 81 points | schematic | extracted |
| --- | ---: | ---: |
| `pgdg_min_during_wide_chatter` | 2.932 V | 2.452 V |
| `tim_min_during_wide_chatter_v` (undisturbed ≈ 0.39–0.58 V) | 0.388 V | 0.395 V |
| `tim_loss_wide_pct` — timer charge lost | **none** (−0.092 %, `TIM` only rises) | **none** (−0.090 %) |

Two things that only a grid can say. First, the one-shot loses **no** charge at
any of the 81 points at either level: `tim_loss_wide_pct` is negative
everywhere, meaning `XMDIS` never conducted at all, so 1.05 µs is rejected —
not merely survived — as drawn. Second, the *sensitivity* is what post-layout
extraction changed, not the verdict: going from 1 µs to 1.05 µs costs the
schematic 9 mV of extra `PGDG` droop (2.941 → 2.932 V, +3 %) and the extracted
netlist 84 mV (2.536 → 2.452 V, **+19 %** on a droop that is already 15× the
schematic's). That is the same erosion the
[post-layout section](#root-cause-of-the-deglitch-asymmetry-and-why-cdg-is-not-resized-issue-182)
diagnoses, now visible as a slope on the grid rather than as one number in a
control. `tim_loss_wide_pct` and its 1 µs sibling `tim_loss_1us_pct` carry **no
bound** on purpose: they are the margin, and a bound on them would report only
the flip, never the movement that precedes it.

**The dwell is not simply `CDG · V_trip / I` either**, and the difference is
load-bearing for anything that changes the capacitance on this node. `NDG`'s
ramp does not start from the rail it was sitting on: when `POR_RAW` falls,
`XMDGPI` turns on with its source `NDGP` charged all the way to `VDD` (the
PMOS tail has been pushing 50 nA into an open circuit), and `NDGP`'s stored
charge is dumped into `NDG` before the pair settles back to carrying the tail
current. Decomposing the falling dwell as

```
dwell = (V_trip − V0) / slope
```

with `V0` the ramp's back-extrapolated intercept at the `POR_RAW` edge — see
[`sim/por-output-chain-deglitch/control/results.md`](../sim/por-output-chain-deglitch/control/results.md)
— gives, at FF / +125 °C / 3.63 V: `V0` = **0.101 V**, i.e. `NDG` starts the
dwell ~14 % of the way to a `V_trip` of 0.714 V, not at 0 V. The mirror-image
step happens on the rising edge through `NDGN`. Both steps always kick `NDG`
*toward* the trip, so **whatever capacitance sits on the two tail nodes
subtracts from the dwell**, while capacitance on `NDG` itself adds to it. The
schematic's own tail-node capacitance is only the devices' junctions and is
therefore small; the drawn layout's is not, which is the whole content of
[Root cause of the deglitch asymmetry](#root-cause-of-the-deglitch-asymmetry-and-why-cdg-is-not-resized-issue-182).

`XMG1`/`XMG2` are deliberately ratio-skewed (NMOS-strong, then the mirror
image). The skew is not about speed: it fixes each node's **leakage default**
while the bias core is dead below the comparator floor. `POR_RAW` low → `NDG`
high → `PGDG` low → `PGDGB` high, which grounds the timer node and leaves the
release NAND's PMOS pull-ups on — i.e. the deglitch chain's dead-circuit state
is the same state that asserts reset.

### `XMON` / `XMOP` are 20:1 in W/L because the floor is a *leakage* limit

The pull-up only ever has to move the 5 pF measurement load, so on drive
alone `XMOP` could be anything. But
[`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) asks
for `V(RESETn) ≤ 0.1 × VDD` at **every** VDD down to 0 V, and a MOSFET's
on/off ratio collapses towards 1 as VDD → 0 (`I_on/I_off ~ exp(VDD/nV_t)` is
only ~1.3× at VDD = 10 mV). No amount of *biasing* delivers the 10× the row
asks for down there. Only **geometry** does, which is why the output pair is
20:1 in W/L and the release NAND is deliberately PMOS-heavy / NMOS-light.

## Results against the ratified targets

| Row | Requirement | Measured (81-point grid) | Binding point | Verdict |
| --- | --- | --- | --- | --- |
| [`por-reset-pulse`](../spec/target-spec.md#por-reset-pulse) | ≥1 ms, no maximum | **4.217 … 7.755 ms** at nominal `IBIAS`; **1.580 … 2.823 ms** at 3× `IBIAS` | min at **FF / −40 °C / 2.97 V** | **PASS** — 4.2× margin at nominal, 1.58× with a 3× `IBIAS` error |
| [`por-brownout`](../spec/target-spec.md#por-brownout) `[TBD-#12]` | deglitch dwell ≤ 10 µs | **1.86 … 4.58 µs** at nominal `IBIAS`; **3.61 … 8.88 µs** at half | max at **SS / −40 °C / 3.63 V** (as the row predicts) | **PASS** — the published dwell is **4.58 µs worst-case**, 2.2× under `T_dip,min` |
| [`por-brownout`](../spec/target-spec.md#por-brownout) | a qualifying 10 µs dip re-asserts and regenerates the full pulse | `RESETn` back to a valid low in **1.84 … 4.57 µs** end-to-end; stays asserted for the rest of the run | — | **PASS** |
| [`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) | `V(RESETn) ≤ min(0.1 × VDD, 0.3 V)` for all VDD ≥ 0 | max ratio **0.0055 × VDD**; max absolute **1.74 mV** | ratio at **SF / +125 °C**, absolute at **SS / −40 °C** | **PASS** — 18× under the ratio limit, 172× under the absolute one |
| [`por-polarity`](../spec/target-spec.md#por-polarity) | active low, degrades to *asserted* near 0 V | held ≤1.74 mV through the whole 0 V → VDD ramp, with `POR_RAW` low **and** driven to the rail | — | **PASS** |
| [`por-drive`](../spec/target-spec.md#por-drive) | push-pull, both states driven | deasserted level = **full rail** (2.96999 … 3.63 V into 5 pF, i.e. the rail itself at every corner) | — | **PASS** |
| [`por-iq`](../spec/target-spec.md#por-iq) | shared <1 µA | this cell's own draw **24.96 … 31.63 nA** asserted, 19.47 … 25.41 nA released | max at **FF / +125 °C / 3.63 V** | **PASS** — see [Iq budget](#iq-budget) |

### The `RESETn` measurement load — `[TBD-#8/#12]`, now finalized

`por-reset-pulse` carries a provisional measurement load of **5 pF, no DC
load [P]** and names #8 and #12 as its owners. #8 is closed, so this issue
owns it. **The provisional value is adopted as-is**, for two reasons that are
now measured rather than asserted:

- The load does not move the answer that matters. It is charged/discharged by
  a push-pull driver whose pull-down is 20:1; the deassertion edge it is
  measured on takes nanoseconds against a millisecond pulse.
- A **DC** load would, and that is precisely why "no DC load" is the load and
  not an omission. The valid-low floor is a leakage divider (above); any DC
  pull-up on `RESETn` re-costs it directly. An integrator who adds an
  external pull-up is outside the specified interface (`por-drive`: no
  external pull-up in the specified interface).

### The achieved valid-low floor is 1.74 mV, not exactly 0 V

`por-reset-valid-floor` targets 0 V with an acceptance fallback of ≤0.4 V
"if #12 demonstrates 0 V is unreachable, with the achieved floor stated". The
honest statement: **0 V is not reachable in the strict sense** — the output is
a leakage divider, so `V(RESETn)` is strictly positive at any VDD > 0 — but
the *specified* criterion (`≤ min(0.1 × VDD, 0.3 V)`) is met outright, with
18× margin on the ratio, so the ≤0.4 V fallback is not invoked. The achieved
floor, stated as the row requires:

- **Absolute**: `V(RESETn) ≤ 1.74 mV` at every point of a 0 V → VDD ramp, all
  81 corners (worst at SS / −40 °C).
- **Relative**: `V(RESETn)/VDD ≤ 0.0055` for VDD ≥ 1 mV (worst at
  SF / +125 °C). Restricted to VDD < 100 mV — where the on/off ratio has
  essentially vanished and only geometry is holding the output down — the same
  0.0055 bound holds, which is the point of measuring that band separately: a
  whole-ramp maximum can hide a failure that exists only in the bottom decade.
- **Not gated by `POR_RAW`**: re-running the identical ramp with `POR_RAW`
  driven **to the rail** below the comparator floor changes the worst-case
  ratio by <1 part in 10⁵.

Below 1 mV the ratio is not evaluated (it is 0/0 to the solver's noise floor);
the absolute bound still applies there and is what makes the claim meaningful
at VDD → 0.

## The chatter / early-release / double-pulse edge case

`por-brownout` explicitly says dips "shorter than the deglitch dwell are
**not guaranteed** to assert reset — that rejection is DR-005's deliberate
deglitch function". The deglitch record applies three 1 µs `POR_RAW` glitches
**during** assertion and three more **after** release, on every corner:

| Observable | Requirement | Measured |
| --- | --- | --- |
| `PGDG` during sub-dwell chatter | must not move | ≥ 2.941 V (i.e. within ~30 mV of the rail at every corner) |
| `RESETn` during chatter, pulse still running | no **early release** | ≤ 5.20 nV |
| `RESETn` after release, same chatter | no spurious **re-assertion** | ≥ 2.96999 V |
| pulse width measured through the chatter | neither truncated nor **restarted** | 4.217 … 7.754 ms — the same distribution as the un-chattered pulse |

The last row is the real discriminator, and it is why the check is two-sided
rather than a bare `≥1 ms`: a glitch that *did* get through would have reset
the timer at 1.2 ms and pushed the release ~0.9 ms later than the
un-chattered pulse recorded in `sim/por-output-chain-pulse/`. A one-sided
minimum would have called that a pass.

**That result is at the cell level, with `IBIAS` idealised, and the glitch is
on `POR_RAW`.** Issue #56's two findings, below, are a full-assembly result
(`bias_core`-driven `IBIAS`, nothing idealised) with the glitch on `VDD`
itself, or with no glitch at all (a plain rail ramp) — a different attack
surface and a different mechanism from the one this section covers, even
though the vocabulary ("chatter", "deglitch") overlaps. Neither invalidates
the result above; both are additional, distinct findings this cell's cell-
level testbenches could not see.

## Two new findings from #14's assembly-level sweeps (issue #56)

`sim/por-ramp-rate/` (record `20260802-000004-32fbaa0`, 21/81 PASS) and
`sim/por-glitch/` (record `20260801-233813-32fbaa0`, 0/81 PASS) each surfaced
a full-assembly defect this cell's own cell-level records do not — both
root-caused here, with a committed, re-runnable control experiment behind
each claim (`sim/README.md`, "Control experiments").

**They resolve differently, and the difference is the point.** The first is a
real, fixable defect: one device (`XMRLK`) closes it, and the full 81-point ×
4-rate grid re-run backs that — record
[`20260802-205904-bdc077d`](../sim/por-ramp-rate/records/20260802-205904-bdc077d.md),
**81/81 PASS, `chatter_* = 0` at every corner and every rate**. The second
cannot be fixed by sizing anything in this cell at all — its mechanism has no
dependence on the deglitch dwell it was framed against, and its re-run with
`XMRLK` in place is **bit-for-bit the same 0/81**
([`20260802-205904-bdc077d`](../sim/por-glitch/records/20260802-205904-bdc077d.md)),
which is the intended outcome: the latch was not aimed at it. What #56 *did*
settle about `por-glitch` is where the `VDD`-glitch immunity boundary actually
is — see [below](#but-there-is-a-vdd-glitch-immunity-boundary-and-it-is-05065-v).

### The release-edge chatter — a relaxation loop through the shared `IBIAS` node, not a local instability

`por-ramp-rate`'s chatter (`RESETn` toggling more than once at the release
edge, up to 109.6 µs against a ≤1 ns bound, at up to 60 of 81 points per
rate) was hypothesised in #56 to be either `design/bias_core.md`'s
starved-loop mechanism operating at a smaller scale on slow ramps, or a
distinct effect. It is a third thing: **`RESETn`'s own release moves the
shared `IBIAS` node, and this cell's release decision is a function of that
node.** The loop is real positive feedback and it leaves `por_output_chain`
entirely.

`sim/por-ramp-rate/control/run_chatter_probe.py` runs three PVT + rate points
in **four arms**, each one asserted single-line edit away from the committed
`design/netlist/temp_por_top.spice`, tracing the release path *and* the
shared-bias nodes behind it. The arms are what make it a root cause rather
than a correlation:

| Arm | Edit vs. the committed netlist | `RESETn` crossings @ `tt_27c_3.30v` (10 V/s, 1 V/s) | @ `tt_-40c_3.30v` |
| --- | --- | --- | --- |
| `asbuilt` | none (`XMRLK` present) | 1, 1 | 1 |
| `nokeeper` | `XMRLK` deleted — the circuit the record measured | **3 (36.85 µs), 3 (36.32 µs)** | 1 |
| `nokeeper_en_vdd` | `XMRLK` deleted **and** `temp_core.EN` tied to `VDD` | 1, 1 | 1 |
| `nokeeper_en_vss` | `XMRLK` deleted **and** `temp_core.EN` tied to `VSS` | 1, 1 | 1 |

**The mechanism, in the order the trace shows it.** At the top level
(`design/netlist/temp_por_top.spice`) `temp_core`'s `EN` pin **is** `RESETn`
— the sensor is held disabled while reset is asserted, per DR-010. So:

1. `RESETn` releases. `temp_core` enables, and its `XMBD` mirror diode joins
   the shared `IBIAS` node alongside this cell's and `por_comparator`'s. The
   same source current now splits more ways, so the node steps **down**:
   **−34.4 mV** at `tt`/27 °C, **−28.0 mV** at `tt`/−40 °C, measured across a
   window in which `VDD` itself moves only **+3.2 mV**. It is a step in the
   shared bias, not a rail artefact.
2. This cell's own starve references follow it: `NDL` drops **−25.5 mV**
   (27 °C). In weak inversion that is most of a decade — the nA sink
   `XMDANT`, which is what sets `ND1`'s balance point against `XMDAPI`, is
   roughly halved.
3. `ND1` therefore drifts back **up** after the release: **28.3 mV → 569 mV**
   inside 300 µs at `tt`/27 °C. At ~0.55 V `XMDBNI` re-conducts, `TRIP`
   collapses from the rail, the release NAND takes `RSTB` back high and
   `RESETn` **re-asserts**.
4. Which disables `temp_core` again, restores `IBIAS`, restores `NDL`, lets
   `ND1` fall and `TRIP` recover — and the cycle repeats. A relaxation
   oscillator with a period set by the nA/fF constants of `ND1` and `TRIP`,
   which is why the measured windows are tens of microseconds and contain
   2–6 edges.

Everything the record shows follows from that, including the two features
that made it look like something else:

- **Ramp-rate independence.** The 10 V/s and 1 V/s points at the same corner
  chatter with near-identical windows (36.85 vs. 36.32 µs), a decade apart.
  Nothing in the loop above involves `dVDD/dt` — the trigger is a *load step*
  on the shared node, and the period is set by `ND1`'s own nA/fF drift, so
  `design/bias_core.md`'s slew-limited starved-loop window is ruled out (as
  is any comparator-threshold-noise story: `VREF`, `BIAS_OK` and `POR_RAW`
  each cross their threshold exactly once, well before the window opens, in
  every arm).
- **Temperature dependence.** The `IBIAS` step is *smaller* in the cold
  (−28.0 vs. −34.4 mV) **and** `ND1`'s post-release drift stops short:
  peak **425.7 mV** at −40 °C versus **569.0 mV** at 27 °C, against an
  `XMDBNI` conduction point that is *higher* in the cold. The cold corner
  simply never closes the loop. That is the whole −40 °C/27 °C split in the
  record, and it needed no appeal to "exponentially temperature-sensitive
  weak-inversion margin" in the abstract.

**The two `nokeeper_en_*` arms are the proof.** They change exactly one
thing — `temp_core`'s `EN` is tied to a rail instead of to `RESETn`, so the
output can no longer modulate the shared-node load — and the chatter vanishes
at every point. It vanishes in **both** directions, permanently enabled and
permanently disabled, which also rules out "temp_core enabled is just a
harder operating point". If the chatter were an instability inside this
cell's trip detector, neither tie could have touched it.

#### The fix: `XMRLK`, a release latch on `ND1`

The circuit's real defect is that **the release decision was never final**.
`XMAST` latches the *asserted* state (`RESETn` low holds `RSTB` high
independently of `TRIP`/`PGDG`) but there was no counterpart on the released
side, so `TRIP` had to keep winning an nA-scale comparison forever, against a
bias the release itself had just moved. `XMRLK` — one nfet, 1 µm / 1 µm,
`ND1` → `VSS`, gate `RESETn` — closes it symmetrically: once `RESETn` is
high, `ND1` is held at `VSS`, `TRIP` stays at the rail, and the release is
one-way regardless of where the nA balance drifts afterwards.

Three properties make it safe rather than merely effective:

- **It cannot latch prematurely.** `RSTB` = NAND(`TRIP`, `PGDG`), so `PGDG`
  low pins `RSTB` high and `RESETn` low *regardless of `TRIP`* — the latch
  can only arm after the deglitched rail is already good, which is after the
  one-shot has genuinely expired. The below-floor default (`ND1` pinned high,
  `TRIP` pinned low, `RESETn` asserted) is untouched, because `RESETn` low
  means `XMRLK` is off.
- **Re-arming after a brownout is unaffected.** `PGDG` falls → `RSTB` rises →
  `RESETn` falls → `XMRLK` opens, all before `ND1` has to move. `XMDIS`
  discharges `TIM` into an undisturbed trip detector exactly as before.
- **It costs no static current.** In the released state it sinks the same
  `XMDAPI` subthreshold leg `XMDANT` was already sinking (a few hundred pA
  with `TIM` parked at ~`VDD` − 0.58 V); it adds no crowbar path, and in the
  asserted state it is off. Sizing is the same 1 µm / 1 µm as `XMDBNI` — it
  only has to beat that sub-nA leg, three decades of margin.

**Verified, not argued**: `sim/por-ramp-rate/records/` re-runs the full
81-point PVT grid at all four ratified rates with `XMRLK` in place. Full
mechanism evidence:
[`sim/por-ramp-rate/control/results.md`](../sim/por-ramp-rate/control/results.md).
Decision record: [DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md),
which supersedes DR-015's "recorded, not fixed — and localised to this cell's
trip detector" framing.

#### What this says beyond `por-ramp-rate`

DR-010 established the shared-`IBIAS` contract as a *static* one: a disabled
consumer must present high impedance so the node is not clamped. This finding
adds a **dynamic** clause that no cell-level testbench could have surfaced —
**enabling or disabling a consumer steps the shared node's operating point by
tens of millivolts, and every nA-biased decision hanging off that node moves
with it.** Any future consumer gated on `RESETn` (or on anything else that a
consumer's own output controls) inherits the same loop. The general defence
is the one taken here: a decision that the shared node can walk back must be
latched, not left as a standing analog comparison.

### Why the deglitch dwell cannot reject a VDD-level glitch

`por-glitch`'s finding (`RESETn` droops during a 300 ns / 0.2 V supply
glitch and, at a subset of corners, is still low 5.5 ms later) was
hypothesised in #56 to be `bias_core` collapsing below its own operating
floor and losing the deglitch filter's bias current — the same theme as
issue #55. `sim/por-glitch/control/run_glitch_probe.py` traces `VDD`,
`POR_RAW`, `PGDG`, `VREF`, `BIAS_OK`, `TIM`, `TRIP` and `RESETn` through the
glitch and the following tens of milliseconds, at two points chosen to
bracket the record's "recovers" / "stuck" split (same process/temperature,
different `VDD`):

| Point | min `PGDG` during the 300 ns glitch | `TIM` immediately after | time from glitch-end to release |
| --- | ---: | ---: | ---: |
| `tt_27c_2.97v` (record: "recovers") | 0.499 V | 0.926 V | 5.076 ms |
| `tt_27c_3.30v` (record: "stuck" at 5.5 ms) | 0.496 V | 0.927 V | 6.106 ms |

That refutes the bias-collapse hypothesis directly: `VREF` and `BIAS_OK`
wobble but never drop out, and `POR_RAW`/`PGDG` are back at the rail within
microseconds of `VDD` recovering — `bias_core` does **not** take an
appreciable time to restart from this glitch, unlike the multi-hundred-µs
restart this document's own [starved-loop window](#the-starved-loop-window)
and its brownout-restart branch measure after a genuine, sustained rail
collapse. The real mechanism is simpler and is entirely inside this cell:

1. `PGDG` is produced by `XMG1`/`XMG2`, two plain ratioed inverters
   referenced to `VDD` itself — **not** to the deglitch dwell capacitor
   `CDG`, which sits only on the `POR_RAW` input side of the chain
   (`NDG`). When `VDD` itself collapses, `PGDG` collapses with it,
   instantaneously, with no RC lag: the table above shows `PGDG` diving to
   ~0.5 V during the 300 ns glitch at every point.
2. `XMDIS`'s gate is `PGDGB` (`PGDG`'s inverted complement), and it is wired
   — deliberately, per [Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides)
   above — to **slam `TIM` back to `VSS` the instant `PGDG` falls**, which is
   exactly the mechanism that correctly regenerates a full pulse after a
   genuine brownout. It does not, and structurally cannot, distinguish "`PGDG`
   fell because `POR_RAW` is genuinely bad" from "`PGDG` fell because `VDD`
   itself is what collapsed". Both readings above show `TIM` discharged to
   ~0.93 V immediately after the glitch ends — the one-shot has been fully
   reset, not merely disturbed.
3. `RESETn` then regenerates a complete, freshly-timed reset pulse from that
   discharged `TIM` — one low, then release, **5.08–6.11 ms** later at these
   two points. (Before `XMRLK` landed, that release edge carried the same
   tens-of-µs 3-crossing chatter
   [above](#the-release-edge-chatter--a-relaxation-loop-through-the-shared-ibias-node-not-a-local-instability),
   since it is the same trip detector doing the same thing regardless of what
   charged `TIM`; it is now a single clean crossing, which makes this deck an
   independent confirmation of that fix on a release path `por-ramp-rate`
   never exercises.) The pulse **width scales with `VDD`**
   (`design/por_output_chain.md`'s own "trip is `VDD − V_sg`" finding: a
   higher rail needs a bigger swing on `TIM` before it trips), which is
   exactly why record `20260801-233813-32fbaa0`'s lower-`VDD` corners
   complete inside its fixed 5.5 ms observation window ("recovers") and its
   higher-`VDD` corners do not ("stuck") — one mechanism, one window effect,
   not two different circuit behaviours and not a filter that has lost its
   state.

**Conclusion — this is architecture-level, not a sizing miss.** The deglitch
dwell (`CDG`, 1.86–8.88 µs) bounds how long a `POR_RAW`-only disturbance
takes to reach `PGDG` *while `VDD` itself holds steady* — that is the
mechanism [Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides)
above measures and it is correct on its own terms. It provides **no**
protection against a disturbance on `VDD` itself, because `PGDG`'s
`VDD`-referenced inverters have no time constant on that path at all — there
is nothing for a longer or shorter glitch to be compared against. Rejecting a
`VDD`-level glitch by *filtering* would need a genuinely new element (e.g. a
locally-reserved, rail-independent hold on `XMDIS`'s trigger, or an entirely
separate rail-collapse detector) — real new circuit topology, not a resize of
`CDG`; see
[DR-014](../spec/decision-records/DR-014-por-glitch-vdd-level-immunity.md).
Full mechanism evidence:
[`sim/por-glitch/control/results.md`](../sim/por-glitch/control/results.md).

### But there *is* a `VDD`-glitch immunity boundary, and it is 0.5–0.65 V

DR-014's mechanism argument came with a stronger claim than the two points
behind it could carry: that the block is unprotected against a `VDD`
disturbance "of *any* depth or duration". A two-axis sweep
(`sim/por-glitch/control/run_depth_sweep.py`, 56 runs, two PVT points, two
circuit arms) measures it. **The duration half is confirmed exactly; the
depth half is not.**

| 300 ns glitch, rail floor | with `XMRLK` (as drawn) | without `XMRLK` (pre-#56) |
| --- | --- | --- |
| 0.2 V (`por-glitch`'s own choice) … 0.5 V | reset regenerates | reset regenerates |
| **0.65 V** … 1.4 V | **`RESETn` never moves** | reset regenerates |
| 2.0 V … 2.8 V | `RESETn` never moves | `RESETn` never moves |

Both PVT points swept — `tt`/27 °C/3.30 V and `ss`/125 °C/2.97 V — give the
identical boundary in each arm. On the **duration** axis (0.2 V floor held
from 10 ns to 30 µs, spanning and overshooting the whole 1.86–8.88 µs dwell),
every run regenerates a pulse in both arms: three decades of duration, no
dependence, which is the dwell's absence from this path measured rather than
argued.

Two things fall out:

- **`XMRLK` buys more than a volt of rail floor**, as a side effect of making
  the release one-way. Without it, a glitch merely dragging `TIM` below its
  trip point re-asserts reset — a 300 ns dip to 1.4 V does it, a dip that
  never takes the rail near `VPOR↓` and that no spec row asks this block to
  respond to. With it, `TIM` can be disturbed freely; only a rail collapse
  deep enough to deassert `POR_RAW` *and* take `RESETn`'s own supply with it
  gets through.
- **0.2 V is not a representative glitch depth.** It is roughly 3× below the
  measured boundary and below the level at which this cell's push-pull output
  still has a supply to hold high with, so `por-glitch`'s 0/81 measures the
  rail collapsing rather than a deglitch decision. Above the boundary the
  dwell is visibly doing its designed job — at `ss`/125 °C with a 0.65 V
  floor, `POR_RAW` touches −23 mV for 100 ns and `RESETn` never moves.

Whether `por-glitch`'s check should therefore be re-cut at a depth above the
boundary, and whether "must never move" should become "must regenerate
exactly one correctly-shaped pulse", is a spec judgment on a ratified row and
belongs to #1 — recorded, with the number that judgment needs, in
[DR-017](../spec/decision-records/DR-017-por-glitch-representative-depth.md).
The testbench is left exactly as written and its 0/81 stands. Full evidence:
[`sim/por-glitch/control/depth_results.md`](../sim/por-glitch/control/depth_results.md).

## Iq budget

[`por-iq`](../spec/target-spec.md#por-iq) is **<1 µA**, quoted in the
`RESETn`-asserted / sensor-disabled state, and per DR-007's accounting rule 1
it is a **shared** budget across `bias_core` (#11), `por_comparator` (#10) and
this cell — not a per-cell allowance.

This cell's standing draw is the two 10 nA reference legs plus leakage. Every
other branch is a switched tail that conducts only while a node is slewing,
and the trip detector is nA-limited by construction (a CMOS inverter there
would sit in its own high-gain region for hundreds of microseconds against a
0.5 V/ms ramp and burn more than the whole budget on its own).

At the binding corner **FF / +125 °C / 3.63 V**:

| Item | Current | Note |
| --- | ---: | --- |
| `por_output_chain` own draw, `RESETn` asserted | **31.6 nA** | measured `iq_asserted_1x_na`; cross-checked from two other stimuli (`iq_ramp_top_na`, and the deglitch record's own pre-release sample) to the same value |
| `por_output_chain` own draw, `RESETn` released | 25.4 nA | lands in [`iq-total`](../spec/target-spec.md#iq-total), not `por-iq` |
| `por_comparator` own draw (#10, measured) | 292 nA | from `design/por_comparator.md` |
| Idealised `IBIAS` reference (bias_core's branch) | 500 nA | charged **once** to `por-iq` by rule 1; already inside #10's recorded `iq_run_ua` |
| **Running total against `por-iq`** | **~824 nA** | **~176 nA left** for `bias_core`'s own overhead |

Across the whole grid this cell's asserted-state draw is **24.96 … 31.63 nA**
— about **3 %** of the shared budget, and about 6 % of what is left after
#10's share.

**The 500 nA is deliberately not counted twice.** #10's `iq_run_ua` already
charges the full idealised reference to `por-iq` under rule 1; adding this
cell costs its own 31.6 nA and nothing more. What #11 must resolve is
**upstream of both**: `temp_core`, `por_comparator` and `por_output_chain`
each hang their *own* diode-connected NMOS off the shared `IBIAS` node, so a
single 0.5 µA source feeding all three does not deliver 0.5 µA to each — it
splits. That is a `bias_core` topology question (one mirror gate line
distributed to N consumers, versus N independent current outputs), it is
`target-spec.md` §5's already-flagged accounting risk, and this cell does not
pre-absorb it by relaxing anything. What this cell *does* do about it is
quantify its own tolerance to being wrong — see next.

## Hand-off to #11: the `IBIAS` envelope is the real constraint

Every internal current here is a ratio of `IBIAS`, so both time constants
scale as 1/`IBIAS`. `bias_core` has not landed, so rather than assert two
numbers against one idealised 0.5 µA source, each record runs **two identical
DUTs side by side on the same rail** at different `IBIAS`, chosen to stress
the target in the direction that can fail it:

| Record | Stress DUT | Why that direction | Result |
| --- | --- | --- | --- |
| pulse | **3× nominal** (1.5 µA) | more current ⇒ *faster* timer ⇒ shorter pulse ⇒ threatens the ≥1 ms floor | ≥ **1.580 ms** at every point |
| deglitch | **0.5× nominal** (0.25 µA) | less current ⇒ *slower* filter ⇒ longer dwell ⇒ threatens the ≤10 µs ceiling | ≤ **8.88 µs** at every point |

So the cell as drawn is proven over an `IBIAS` envelope of **0.5× … 3×
nominal** across the full PVT grid. That is the number #11 should design
against, and the two ends are not equally comfortable:

- The ≥1 ms floor has room to spare — it would survive roughly 4.7× nominal
  `IBIAS` before the fastest corner reached 1 ms.
- **The ≤10 µs dwell ceiling is the tighter side**: 8.88 µs at 0.5× leaves
  ~11 %, so `IBIAS` must not fall below about **0.44× nominal** at the
  SS / −40 °C corner. If #11 cannot hold that, the fix here is a *smaller*
  `CDG` (which costs glitch-rejection margin at the fast corner, per
  [Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides)) — a
  trade-off to make against #11's real numbers, not pre-emptively.

> **#11's real numbers are now in, and the 0.44× floor is not held (issue
> #221, [DR-024](../spec/decision-records/DR-024-por-output-chain-real-ibias-delivery.md)).**
> [`sim/por-output-chain-ibias-sharing/`](../sim/por-output-chain-ibias-sharing/)
> meters this cell's own `IBIAS` pin on the real four-cell shared node and
> measures **0.344×–1.155× nominal `RESETn`-asserted, 0.182×–0.608× nominal
> `RESETn`-released** — 61 of 81 PVT points under the 220 nA floor in the
> released state, worst `ss_-40c_2.97v` at 0.182×, identically at both netlist
> levels. The deglitch row's stress DUT above is therefore **no longer 0.5×**:
> it is re-cut to the measured worst case (91.0251 nA) and the ≤10 µs ceiling
> now **fails** at most corners. The "if #11 cannot hold that, shrink `CDG`"
> escape hatch is not sized for a 2.4× shortfall — DR-024 works the four
> available levers with arithmetic and routes them to
> [#235](https://github.com/2AMLogic/gf180-temp-por/issues/235) and
> [#236](https://github.com/2AMLogic/gf180-temp-por/issues/236). Read the row
> above as the *cell's own tolerance*, not as a claim that the assembly stays
> inside it.

## Below the operating floor

This is the regime DR-004 assigns to this cell, and it is the one place where
"no static current" and "defined output state" have to hold *simultaneously*
with the bias core dead. The chain of dead-circuit defaults:

1. Bias legs dead ⇒ `PDN` ≈ VDD, `NDL` ≈ 0.
2. `POR_RAW` low or undriven ⇒ `NDG` high ⇒ `PGDG` low ⇒ `PGDGB` high, which
   grounds `TIM`.
3. `XMDAPI` has V_sg = VDD (on) against a sink whose gate is at `NDL` ≈ 0
   (off) and which is 40× smaller in W/L ⇒ `ND1` pins **high**.
4. `XMDBNI` then has V_gs = VDD against an off PMOS source 20× smaller ⇒
   `TRIP` pins **low**.
5. `TRIP` low and `PGDG` low ⇒ the release NAND's two parallel PMOS against
   its series NMOS stack pin `RSTB` to **VDD**.
6. `RSTB` = VDD ⇒ `XMON` fully on, `XMOP` fully off ⇒ `RESETn` **asserted**,
   and `XMAST` latches step 5 independently of steps 1–4.

Every one of those steps is a *ratio* of geometries, not a bias condition,
which is what makes it work at 10 mV of rail. None of them carries static
current in the settled state. The floor record measures the end of that chain
directly (1.74 mV worst case, ≤0.0055 × VDD), including the pathological case
where `POR_RAW` is driven high below the comparator floor.

### Confirmed against a *starved* bias, not just a dead one (#55)

The floor record ramps the rail from 0 V, so the whole cell is cold together.
Issue #55 asked the harder version of the question — the cell **released and
warm**, then the rail collapsing to 1.0 V with `IBIAS` cut from under it — as
part of root-causing `sim/por-brownout/`'s 0/81 result.
`sim/por-brownout/control/results.md` § C drives `POR_RAW` low at that rail
and sweeps the current still reaching `IBIAS`:

| `IBIAS` in dip | `RESETn` reaches 0.1 × VDD at | `RESETn` at end of dwell | I sunk at the 100 mV valid-low bound |
| --- | --- | --- | --- |
| 500 nA (1×) | 3.70 µs | 0.000000 V | **+71.1 µA** |
| 250 nA (0.5×) | 4.60 µs | 0.000000 V | **+71.1 µA** |
| 50 nA (0.1×) | 6.40 µs | 0.000000 V | **+71.1 µA** |
| **0 nA** | 7.30 µs | 0.000000 V | **+71.1 µA** |

The sink current is *identical* down to zero bias, and the only thing losing
`IBIAS` costs is ~3.6 µs of turn-on delay. That is the dead-circuit chain
above doing exactly what it was sized to do: once `RSTB` is at VDD, `XMON`'s
gate drive is the rail, not the bias. **This cell is therefore not the
limiter in the `por-brownout` failure** — the decision never reaches it. See
[DR-011](../spec/decision-records/DR-011-brownout-falling-slew-limit.md).

One caveat this control did surface, and it belongs to this cell: the
deglitch dwell is bias-starved in that state too. On the assembly with
`POR_RAW` restored artificially at +19.6 µs into the dip, `RESETn` took until
+52.3 µs to resolve — roughly **33 µs** of deglitch against the
[1.86–8.88 µs](#deglitch-dwell--cdg-is-bounded-on-both-sides) measured at
nominal and half `IBIAS`. Nothing downstream should assume the published
dwell holds while the shared core is collapsed.

## Area — flagged for #17

Not a target this issue owns ([`area`](../spec/target-spec.md#area) is
`[TBD-#17]`), but the number should not be a floorplanning surprise:

- `CTIM` = 4 × 28 µm × 28 µm = **3 136 µm²** of MIM, plus `CDG` at 121 µm² —
  about **3 260 µm²**, ~0.0033 mm². The transistors are negligible beside it.
- The driver is the Iq budget again: at 2.5 nA, a 1 ms pulse needs ~2.5 pC,
  and 2 fF/µm² MIM turns that into area directly. Halving `CTIM` means
  halving the charge current to keep the pulse, and 1.25 nA is uncomfortably
  close to `XMDIS`'s own I_off at FF / +125 °C — which is the failure the
  narrow `XMDIS` above exists to avoid.
- MIM sits on metal 3/4, so it may be **stackable over** the resistor-heavy
  `por_comparator` divider rather than costing separate floor area. Whether
  that is allowed is a DRC/layout call for #17, not one to make here.

## Post-layout re-run (issue #86)

The three testbenches above were re-run against
[`layout/postlayout/por_output_chain.spice`](../layout/postlayout/por_output_chain.spice)
(#82/PR #180's direct-extraction flow) instead of `design/por_output_chain.sch`,
full 81-point PVT grid, same stimulus:

| Evidence | Netlist provenance | Supersedes (schematic record) |
| --- | --- | --- |
| [`sim/por-output-chain-pulse/records/20260811-055201-d0ee17d.md`](../sim/por-output-chain-pulse/records/20260811-055201-d0ee17d.md) | extracted | `20260802-205904-bdc077d` |
| [`sim/por-output-chain-deglitch/records/20260811-095259-865cea8.md`](../sim/por-output-chain-deglitch/records/20260811-095259-865cea8.md) | extracted | `20260802-205904-bdc077d` |
| [`sim/por-output-chain-floor/records/20260811-125812-8e43e14.md`](../sim/por-output-chain-floor/records/20260811-125812-8e43e14.md) | extracted | `20260802-205904-bdc077d` |

**All three are 81/81 PASS**, same as the schematic records they supersede —
no spec-row check that passed at the schematic level fails post-layout. The
deglitch and floor rows cite clean-tree re-runs rather than this cell's first
post-layout pass: `20260811-055634-d0ee17d` and `20260811-055424-d0ee17d`
were both minted against uncommitted work and are stamped "not citable as a
clean-tree result" in their own `Netlist provenance` field (`sim/README.md`
§ "Citing a 'taken against a dirty working tree' record").
`20260811-095259-865cea8` (used below, "Root cause of the deglitch
asymmetry") reproduces `…-055634-…`'s numbers exactly on a clean tree;
`20260811-125812-8e43e14` does the same for `…-055424-…`. Neither the pulse
row nor its record needed re-running — it was never stamped.

The **Supersedes** column above names the *schematic* record each row
displaces at the doc level, which for the two re-run rows is one link further
back than the record's own `Supersedes` field: `20260811-095259-865cea8`
supersedes `20260811-094940-4249351`, which supersedes the stamped
`20260811-055634-d0ee17d`, which supersedes `20260802-205904-bdc077d`;
`20260811-125812-8e43e14` reproduces the stamped `20260811-055424-d0ee17d`,
which supersedes the same schematic record. See
[#209](https://github.com/2AMLogic/gf180-temp-por/issues/209).

### What "extracted" means for this cell specifically

Per [`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md)'s
`por_output_chain` row: **33 drawn devices, 0 ideal** — every device in this
cell, including the deglitch one-shot's two MiM caps (`XCDG` and the 4×
`XCTIM` instances, 5 total), is drawn and extracted, not schematic-ideal. This
is a **stronger** result than #18's original framing anticipated (which
expected `XCDG`/`XCTIM` to still be schematic-ideal splices with parasitics
added only on the surrounding routing) — see the issue's own "Dependency
re-check" addendum. 18/30 nets carry first-order interconnect parasitics
(ΣR 66322 Ω, ΣC 828.6 fF total); the 12 nets without drawn interconnect are
body/plate/well ties the extraction deck's connectivity stack does not reach
(`NW1`→`VDD`, `XCDG`/`XCTIM`'s plate and `VSS` ties, `vsubs`→`VSS`), tied per
the schematic per AUDIT.md's "Body, well and plate ties" table. The 5 MiM caps
are extracted as `cap_mim_2f0_m4m5_noshield` and emitted as the
electrically-identical `cap_mim_2f0_m3m4_noshield` (klayout-tools#315 — same
2.0 fF/µm² device, stack-variant name only, not a splice or a schematic
fallback).

### `XMBD`/`IBIAS` watch item: confirmed clean

The Watch item this re-run was asked to check: that the extraction's spliced
parasitics do not introduce a spurious series device into the `IBIAS` path,
where `XMBD`'s local mirror diode has none by design. Confirmed clean by
inspection and by measurement:

- **Topology**: `layout/postlayout/por_output_chain.spice` ties `IBIAS`'s
  parasitic model as a **shunt** — `RIBIAS IBIAS IBIAS__par 4398.7`, then
  `CIBIAS IBIAS__par VSS 45.3 fF` — a pi-leg to an otherwise-unconnected
  `IBIAS__par` node, not a series element between the pin and `XMBD`/`XMN1`
  (both still tie directly to the `IBIAS` node itself). This is the same
  construction every other net in the extraction gets (see the `*__par`
  nodes throughout the file); `IBIAS` is not a special case.
- **Measurement**: `iq_asserted_1x_na` (this cell's own `IBIAS`-referenced
  draw) is **27.7701 nA post-layout vs. 27.7702 nA schematic** at
  `tt_27c_3.30v` — a 4-ppm difference, i.e. unchanged to the precision this
  harness reports. A series impedance in the `IBIAS` path would show up here
  as a DC operating-point shift (the mirror's own gate-source bias would
  move); it does not.

### The pulse-width / dwell-time delta

Per `layout/README.md`/`sim/README.md`'s framing (PR #180's own smoke sim on
this cell, `+2.09 %` on `t_release_ms` at `tt_27c_3.30v`): this is where "a
post-layout claim taken on these netlists should be a timing/edge claim," and
this record's full-grid numbers confirm that at the nominal corner and give
the shape across the whole PVT grid instead of one point.

**`por-reset-pulse` (the one-shot width) widens by ~1.9–2.4 %, uniformly**,
consistent with the added parasitic C/R loading a nA-scale current-starved
ramp:

| Quantity | Schematic | Post-layout | Δ |
| --- | ---: | ---: | ---: |
| `tpulse_1x_ms` min (`ff_-40c_2.97v`, the binding corner — unchanged) | 4.2172 | 4.31816 | **+2.40 %** |
| `tpulse_1x_ms` max (`ss_125c_3.63v`) | 7.75505 | 7.90046 | +1.88 % |
| `tpulse_3x_ms` min (`ff_-40c_2.97v`) | 1.57985 | 1.61748 | +2.38 % |
| `tpulse_3x_ms` max (`ss_125c_3.63v`) | 2.82289 | 2.87708 | +1.92 % |
| `tpulse_1x_ms` at `tt_27c_3.30v` (nominal, cross-check vs. PR #180's own smoke) | 5.78035 | 5.90136 | +2.093 % |

The binding corner is unchanged (`FF / −40 °C / 2.97 V`, per
["The one-shot is a current-starved ramp"](#the-one-shot-is-a-current-starved-ramp-and-its-trip-is-vdd--v_sg)
above) and the widening only *adds* margin against the ≥1 ms floor (4.32 ms
at nominal, 1.62 ms at 3× `IBIAS` — both still comfortably over 1 ms).
`por-reset-valid-floor` similarly widens with margin to spare: worst-case
ratio **0.0059 × VDD** (was 0.0055×, still 17× under the 0.1× limit) and
worst-case absolute **1.97 mV** (was 1.74 mV, still 152× under 300 mV).

**The deglitch dwell moves in *both* directions, and the falling-edge
(qualifying-dip) dwell shrinks — not grows — by a materially larger margin
than the pulse widens.** At matched corners (not just the grid's own
min/max, since the binding corner shifts):

| Corner | `dwell_pgdg_1x_us` schematic | post-layout | Δ |
| --- | ---: | ---: | ---: |
| `ff_125c_2.97v` | 1.86 | 1.34 | **−28.0 %** |
| `ff_125c_3.63v` | 2.01 | 1.28 | **−36.3 %** |
| `ss_-40c_2.97v` | 4.41 | 4.17 | −5.4 % |
| `ss_-40c_3.63v` | 4.58 | 4.06 | −11.4 % |

The grid-wide minimum (nominal `IBIAS`) drops from **1.86 µs to 1.28 µs**.
Every corner still **passes** the checked requirement — `dwell_pgdg_halfib_us`
(the half-`IBIAS` stress DUT the ceiling check runs against) has a grid
maximum of **8.03 µs post-layout vs. 8.88 µs schematic**, both under the
10 µs `T_dip,min` ceiling with margin to spare — but the *ceiling* was never
the tight side of this design's own margin. [Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides)
above documents a real prior failure at a **1.07 µs** dwell (the pre-resize
`CDG` = 98 fF cut, which let a 1 µs qualifying glitch through at 30/81
points): the schematic-level minimum (1.86 µs) sits **74 % above** that
failure point; the post-layout minimum (1.28 µs) sits only **20 % above** it.
Meanwhile the *other* direction of the same filter — `dwell_rise_1x_us`,
`POR_RAW` rising through `NDG`/`CDG` — **widens**, by a comparable magnitude
(+13.7 % at `ff_-40c_2.97v`, +11.7 % at `ss_125c_3.63v`), the same direction
as the one-shot pulse.

This asymmetry (one edge of the same RC filter shrinking, the other
widening, by percentages several times the ~2 % the DC-invariant devices
elsewhere in this cell would predict from a single ~39 fF shunt load on
`NDG`) was measured but not explained by #86, whose scope was verification,
not design; it was flagged and routed to a new tracking issue, #182 — now
diagnosed in
[Root cause of the deglitch asymmetry](#root-cause-of-the-deglitch-asymmetry-and-why-cdg-is-not-resized-issue-182)
below. Routing it rather than absorbing it silently was the right call: the *lower* bound this
design already treats as tight (["Deglitch dwell"](#deglitch-dwell--cdg-is-bounded-on-both-sides):
"this capacitor is not free to grow") has visibly less headroom against a real
extracted layout than the schematic ever measured, even though no ratified
check fails today.

### Reproducing this section's evidence

```bash
python3 sim/build_tb.py --check                                  # postlayout fragments <-> layout/postlayout/*.spice
python3 sim/run_corners.py sim/por-output-chain-pulse/testbench-postlayout
python3 sim/run_corners.py sim/por-output-chain-deglitch/testbench-postlayout
python3 sim/run_corners.py sim/por-output-chain-floor/testbench-postlayout
```

## Root cause of the deglitch asymmetry, and why `CDG` is not resized (issue #182)

Three control experiments under
[`sim/por-output-chain-deglitch/control/`](../sim/por-output-chain-deglitch/control/)
diagnose the delta the section above measured. They are diagnoses, not
records — the corner-grid evidence stays in `records/` (`sim/README.md`,
"Control experiments").

### First, re-verified — and this time on a clean tree

The post-layout grid was re-run against the same extracted netlist:
[`sim/por-output-chain-deglitch/records/20260811-095259-865cea8.md`](../sim/por-output-chain-deglitch/records/20260811-095259-865cea8.md),
**81/81 PASS**, reproducing `20260811-055634-d0ee17d`'s numbers exactly. That
matters beyond confirmation: the #86 record says of itself that it was "taken
against a **dirty working tree** … not citable as a clean-tree result", and
this one is clean, so the post-layout deglitch claim now rests on a record
whose inputs are all committed.

The two numbers to carry forward are **not** the two the erosion was first
reported in:

| what | post-layout | bound | headroom |
| --- | ---: | ---: | ---: |
| `dwell_pgdg_halfib_us`, grid max | 8.03 µs | ≤ 10 µs, ratified `T_dip,min` | **+19.7 %** |
| `pgdg_min_during_chatter`, grid min | 2.53616 V | ≥ 2.5 V | **+1.4 %** |

The ceiling — the *ratified* bound — is comfortable. The one that is 36 mV
from its limit is the chatter check at `ff_125c_2.97v`: the direct measurement
of "a 1 µs `POR_RAW` glitch does not move the filter output". Schematic-level
it read 2.94 V, a 29 mV droop; post-layout it reads 2.54 V, a 434 mV droop.
**That, not the dwell percentages, is the erosion.**

### What actually moved: not the trip point

Decomposing each edge's dwell as `(V_trip − V0) / slope`
([`control/results.md`](../sim/por-output-chain-deglitch/control/results.md),
`ff_125c_3.63v`, nominal `IBIAS`):

| | `V0` (ramp's start) | slope | `V_trip` (`NDG` at `PGDG` = 1.0 V) | journey `V_trip − V0` | dwell |
| --- | ---: | ---: | ---: | ---: | ---: |
| falling, schematic | 0.1012 V | +0.31625 V/µs | 0.7144 V | 0.6132 V | 2.009 µs |
| falling, post-layout | 0.3833 V | +0.26965 V/µs | 0.7207 V | 0.3374 V | 1.277 µs |
| | | −14.7 % | **+0.9 %** | −45.0 % | −36.4 % |
| rising, schematic | 3.2269 V | −0.23840 V/µs | 0.7040 V | 2.5229 V | 10.719 µs |
| rising, post-layout | 2.9270 V | −0.18129 V/µs | 0.7005 V | 2.2265 V | 12.407 µs |
| | | −24.0 % | **−0.5 %** | −11.7 % | **+15.7 %** |

**The `XMG1`/`XMG2` trip-point hypothesis is refuted.** `V_trip` moves by
under 1 % on either edge, and it could not have moved: `XMG1`'s trip is a DC
ratio between two devices whose `W`/`L` the extraction reproduces exactly, and
the extraction's parasitic model is *one series R into one lumped C per net*
([`layout/README.md`](../layout/README.md)), which is DC-invariant by
construction. The same fact is why `iq_asserted_1x_na` reads 27.7701 nA
post-layout against 27.7702 nA schematic.

What moved is `V0` — the level the ramp actually starts from — in **opposite
directions on the two edges but with the same sign of effect**: on both edges
the step kicks `NDG` *toward* the trip, so both journeys shorten. The falling
journey shortens by 45 % because it is short to begin with (`V_trip` sits at
only 20 % of the rail, the price of `XMG1`'s NMOS-strong skew); the rising
journey covers the other 80 % of the rail, so the *same-size* step shortens it
by only 12 % — less than the 24 % the slope lost. **That is the whole
asymmetry**: one absolute head-start step, one short journey and one long one.
It is not two mechanisms.

### Which parasitic: the tail nodes, not `CDG`'s own

`control/results.md` ablates the extraction's three deglitch-node
capacitances onto the schematic netlist, one group at a time
(`ff_125c_3.63v`, falling dwell):

| variant | `V0` | slope | dwell |
| --- | ---: | ---: | ---: |
| `schematic` | 0.1012 V | +0.31625 V/µs | 2.009 µs |
| `sch+cndg` — only the 38.58 fF on `NDG` | 0.0941 V | +0.26675 V/µs | **2.403 µs** |
| `sch+ctail` — only the 34.12 / 34.26 fF on `NDGP` / `NDGN` | 0.3952 V | +0.32764 V/µs | **1.000 µs** |
| `sch+call` — all three | 0.3478 V | +0.27768 V/µs | 1.356 µs |
| `postlayout` (the real extracted netlist) | 0.3833 V | +0.26965 V/µs | 1.277 µs |

Clean separation: the `NDG` shunt moves the **slope** and nothing else, and on
its own it *lengthens* the dwell by 20 %. The tail-node shunts move **`V0`**
and nothing else, and on their own they *halve* it. `sch+call` lands within
6 % of the real extracted netlist, so those three capacitances are essentially
the whole story (the residual is the extraction's larger drawn junction areas
and the other nets' parasitics).

The arithmetic is first-order but it closes: `NDGP` carries 34.1 fF and swings
~2.46 V when `XMDGPI` turns on (3.63 V down to the 1.17 V it tracks mid-ramp),
so it dumps ~84 fC; the falling ramp itself only has to move ~172 fC (`CDG`
242 fF plus the extraction's 38.6 fF on `NDG`, across the schematic's 0.613 V
journey). **A tail node carrying one seventh of `CDG` moves half the dwell**,
because it swings four times as far as the ramp does.

### Whether `CDG` has to grow: measured, and no

[`control/cdg_results.md`](../sim/por-output-chain-deglitch/control/cdg_results.md)
walks `XCDG`'s drawn dimensions on the post-layout netlist and measures both
bounds at each size — the ceiling as `dwell_pgdg_halfib_us` at
`ss_-40c_2.97v` (the corner the record's grid maximum lands on), the floor as
the glitch width at which the one-shot's `TIM` starts losing charge:

| `XCDG` | `CDG` | ceiling, half `IBIAS` | vs. the ratified 10 µs | floor, worst of the two fast corners |
| --- | ---: | ---: | --- | --- |
| 11 µm × 11 µm (as drawn) | 242 fF | 8.020 µs | +19.8 % headroom | rejects 1.00 µs |
| 12 µm × 12 µm | 288 fF | 9.770 µs | +2.3 % headroom | rejects 1.25 µs |
| 13 µm × 13 µm | 338 fF | 11.680 µs | **−16.8 % — fails** | rejects 1.75 µs |
| 14 µm × 14 µm | 392 fF | 13.750 µs | **−37.5 % — fails** | rejects ≥2.25 µs |

Restoring the schematic's measured floor (1.75 µs, i.e. 1.75× the 1 µs chatter
the testbench applies) needs 13 µm × 13 µm, which **breaks
[`por-brownout`](../spec/target-spec.md#por-brownout)'s ratified 10 µs
`T_dip,min`** — and CLAUDE.md is explicit that agents do not relax the ratified
spec to make results pass, so that size is not available. The one size that
still fits, 12 µm × 12 µm, buys the floor back only to 1.25 µs while leaving
2.3 % of ceiling headroom at a single corner of a grid whose own dwell spread
is 112 %; that is not margin, it is a coin flip.

**So `CDG` is not resized, and no decision record is filed** — nothing ratified
moves. `por-brownout`'s 10 µs ceiling is met post-layout with 19.7 % headroom
on the full grid (`20260811-095259-865cea8`; the 19.8 % in the table above is
this control deck's own single-corner re-measurement of the same point)
and stays exactly where [DR-008](../spec/decision-records/DR-008-target-spec-ratification.md)
put it. What changes is this document: the floor is now stated as a measured
glitch-rejection width rather than left implicit, and it is **1.00× post-layout
against 1.75× at the schematic level**.

### What this hands off

Two observations that are worth more than any capacitor in this cell:

- **The `IBIAS` envelope is still the real constraint, and now it has a
  number.** The ceiling check runs at *half* nominal `IBIAS` and reads 8.02 µs;
  at nominal `IBIAS` the same corner reads 4.17 µs. The dwell goes as
  1/`IBIAS`, so every 1 % of low-side `IBIAS` tolerance #11 recovers is ~1 % of
  ceiling headroom, and **21.8 % of it pays for the 12 µm × 12 µm resize
  outright** — with the floor margin that buys. See
  [Hand-off to #11](#hand-off-to-11-the-ibias-envelope-is-the-real-constraint).
- **Shrinking the tail nodes in layout is not free either.** It is tempting to
  read "the tail parasitic did this" as "route `NDGP`/`NDGN` shorter and the
  problem goes away". It does go away — and takes ceiling headroom with it, for
  exactly the same reason: `sch+cndg` (the `NDG` shunt with the tail shunts
  removed) reads 5.101 µs at `ss_-40c_2.97v` against the post-layout netlist's
  4.167 µs, which scales to ≈9.8 µs at half `IBIAS`, i.e. ~2 % under the
  ceiling. The two bounds move together whichever node is touched. Under the
  `IBIAS` tolerance assumed today there is no capacitance in this cell that
  separates them; a tighter `IBIAS` envelope is what creates the room.

Both are answered by **#199** —
[below](#199-the-two-hand-offs-answered). The verification
half — the measured rejection width belongs on the corner grid, not only in a
control that gets overwritten on the next run — is **done** (#200): the grid
now applies a 1.05 µs burst as well and records the one-shot's charge loss
across it at all 81 points, limit-free, in
[`20260811-110622-d5b0168`](../sim/por-output-chain-deglitch/records/20260811-110622-d5b0168.md)
(schematic) and
[`20260811-110752-d5b0168`](../sim/por-output-chain-deglitch/records/20260811-110752-d5b0168.md)
(extracted). Those two records reproduce every measurement of the records they
supersede **bit-for-bit** — the new burst sits after every pre-existing
measurement window — so the numbers this section quotes are unaffected by the
addition. See
[Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides) for what they
measure.

### #199: the two hand-offs, answered

**#11's `IBIAS` envelope — inside the safe window, with margin.**
`design/bias_core.md`'s own designer-check record already carries the number
this cell asked for: `ibias_na`, the current actually delivered out of the
`IBIAS` pin (not just `bias_core`'s total quiescent draw), is a **named
measurement** on the full 81-point PVT grid — deterministic corners only
(`design.ngspice` sets `sw_stat_mismatch=0`; mismatch on the mirror ratio is
#15's job, exactly as `design/bias_core.md` already states of this same
check) — not something #199 had to add. Post-layout
([`sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md`](../sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md),
unchanged from the schematic record to 4 significant figures):

| | Measured `IBIAS` | vs. 500 nA nominal | vs. this cell's 0.44×–4.7× envelope |
| --- | ---: | ---: | --- |
| minimum | 297.089 nA (`ss_-40c_2.97v`) | **0.594×** | 35.0 % above the 0.44× low-side bound |
| maximum | 1117.85 nA (`ff_125c_3.63v`) | **2.236×** | 52.4 % below the 4.7× high-side bound |

Both PVT-corner ends sit inside the envelope this document derived. The
tighter of the two — the low side, which is also the side that binds this
cell's own deglitch ceiling — lands at the **same corner**
(`ss_-40c_2.97v`) as the ceiling's own grid maximum
([Whether `CDG` has to grow: measured, and no](#whether-cdg-has-to-grow-measured-and-no)
above), so the comparison is corner-matched rather than two different grid
extremes talking past each other. `IBIAS`'s deterministic-corner spread —
0.594×–2.236×, i.e. 2.5:1 — sits comfortably inside the up to 10.7:1
(0.44×–4.7×) this cell can tolerate, with no change asked of #11 beyond what
it has already published. Question 2 is closed: favorable, no ratified value
moves, no resize follows.

> **Correction (issue #221, [DR-024](../spec/decision-records/DR-024-por-output-chain-real-ibias-delivery.md)):
> the paragraph above is wrong about what `ibias_na` measures.**
> `sim/bias-core-designer-check/`'s `ibias_na` is `bias_core`'s output into a
> **single** 2 µm / 2 µm diode load standing in for `por_comparator` alone
> ([`sim/bias-core-designer-check/testbench/stimulus.spice`](../sim/bias-core-designer-check/testbench/stimulus.spice)) —
> it never instantiates `por_output_chain`, so it is not the current this
> cell actually receives once the shared node is loaded by up to three
> consumer diodes at once, per [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md).
> [`sim/por-output-chain-ibias-sharing/`](../sim/por-output-chain-ibias-sharing/)
> (#221) instantiates all four cells and meters every consumer leg
> individually; it measures **0.344×–1.155× nominal `RESETn`-asserted and
> 0.182×–0.608× nominal `RESETn`-released**, both well under the 0.44× floor
> derived above, worst at `ss_-40c_2.97v` released (0.182×) — identically at
> both netlist levels. [Hand-off to #11](#hand-off-to-11-the-ibias-envelope-is-the-real-constraint)'s
> ceiling stress DUT is re-cut to this real number by DR-024, which now
> **fails** 79/81 (schematic,
> [`20260811-150038-58e15a8`](../sim/por-output-chain-deglitch/records/20260811-150038-58e15a8.md))
> / 57/81 (post-layout,
> [`20260811-150342-0c44407`](../sim/por-output-chain-deglitch/records/20260811-150342-0c44407.md))
> points on the deglitch ceiling check — see DR-024 for the full evidence, why
> the two cheapest circuit-level fixes do not close inside `por-iq`'s DR-018
> ceiling, and the two follow-up issues it routes the remaining levers to
> ([#235](https://github.com/2AMLogic/gf180-temp-por/issues/235), re-ratio the
> consumer mirror diodes;
> [#236](https://github.com/2AMLogic/gf180-temp-por/issues/236), the
> operator-only `T_dip,min` spec call). **No ratified row of
> `spec/target-spec.md` moves on this evidence**; the check is left failing
> rather than relaxed, per CLAUDE.md.

**#14's `POR_RAW` chatter width — not measurable from any deck committed so
far, and not something a post-processing pass can extract.** Question 1 asks
for the real-world width of a `POR_RAW` excursion near `por_comparator`'s
threshold on a live bring-up sequence, to compare against the 1.00 µs
post-layout floor above. None of #14's committed assembly-level decks
contain that event:

- [`sim/por-vth/`](../sim/por-vth/) is a **quasi-static** ramp built
  specifically so the bias core is settled at every instant across the
  threshold band; its `rise_chatter_mv` / `fall_chatter_mv` checks demand a
  **single** threshold crossing (±5 µV) and every recorded corner meets it —
  by construction, not by observation.
- [`sim/por-ramp-rate/`](../sim/por-ramp-rate/) checks the same thing at all
  four ratified rates (`chatter_*_us`, a ±1 ns band) and, since
  [DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md),
  passes 81/81. Its own control experiment states the reason directly:
  "POR_RAW, PGDG, VREF and BIAS_OK cross the 1.0 V threshold at most once at
  every point and in every arm, including the ones that show RESETn chatter"
  ([`sim/por-ramp-rate/control/results.md`](../sim/por-ramp-rate/control/results.md)) —
  the release-edge chatter this repository found and `XMRLK` fixed is a
  `RESETn`-side relaxation loop through the shared `IBIAS` node
  ([above](#the-release-edge-chatter--a-relaxation-loop-through-the-shared-ibias-node-not-a-local-instability)),
  not a `POR_RAW` excursion at all — `POR_RAW` itself never moves twice.
- [`sim/por-brownout/`](../sim/por-brownout/) applies a 50 µs / 1.0 V
  qualifying dip (5× `T_dip,min`), deliberately deep and unambiguous, not a
  narrow near-threshold toggle, and
  [`sim/por-brownout-spurious/`](../sim/por-brownout-spurious/)
  ([DR-013](../spec/decision-records/DR-013-por-brownout-spurious-assert.md))
  measures only a falling-slew spurious **assert instant**, not an excursion
  **width** — a different, already-tracked mechanism.

In every full-assembly transient recorded in `sim/` to date, `POR_RAW`
crosses its threshold cleanly, exactly once. There is no excursion event in
any existing record to extract a width from — reprocessing cannot produce
the measurement, because the data does not contain it. That is structural,
not a coverage gap: every deck above is a deterministic-corner run driven by
a clean, noiseless ramp or a single programmed dip; nothing in `sim/` today
injects the supply ripple or comparator-side dither that would make
`POR_RAW` chatter near threshold on a real board.
[DR-020](../spec/decision-records/DR-020-por-raw-chatter-width-out-of-reach.md)
records this finding and routes the choice of how to obtain that measurement
(a new noise-injection stimulus model, or reading #15's mismatch sweep once
it lands) to #1, mirroring how
[DR-017](../spec/decision-records/DR-017-por-glitch-representative-depth.md)
routed the equivalent `por-glitch` depth question. No ratified value moves —
`por-brownout`'s 10 µs `T_dip,min` ceiling and this cell's 1.00 µs post-layout
floor both stand exactly as measured above.

**Net effect on the design decision this issue exists to make**: `CDG` stays
at 11 µm × 11 µm, unchanged from
["Whether `CDG` has to grow"](#whether-cdg-has-to-grow-measured-and-no)
above. #11's envelope closes cleanly in this cell's favor; #14's real chatter
width remains an open question at the model-fidelity level, carried forward
by DR-020 rather than by this cell, since nothing sized here can answer it.

A third lever exists and is deliberately **not** taken here: `V_trip` sits at
20 % of the rail because `XMG1` is skewed NMOS-strong, and a trip nearer
mid-rail would make the falling journey ~2.5× longer and the same head-start
step ~18 % of it instead of ~46 %. But that skew is not about speed — it fixes
the deglitch chain's dead-circuit leakage default, which is what
[`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) and
[`por-polarity`](../spec/target-spec.md#por-polarity) rest on
([Deglitch dwell](#deglitch-dwell--cdg-is-bounded-on-both-sides)). Re-skewing
it is a re-spin of the cell and its layout, not a tweak.

### Reproducing this section's evidence

```bash
python3 sim/run_corners.py sim/por-output-chain-deglitch/testbench-postlayout -j 1
python3 sim/por-output-chain-deglitch/control/run_deglitch_asym_probe.py   # the decomposition + ablation
python3 sim/por-output-chain-deglitch/control/run_glitch_width_sweep.py    # the measured floor
python3 sim/por-output-chain-deglitch/control/run_cdg_tradeoff.py          # the CDG-resize tradeoff
```

`-j 1` is not a typo. ngspice's worker threads spin-wait, so `N` concurrent
points × `N` threads oversubscribe a busy host superlinearly: the 81-point
grid runs in 154 s at `-j 1` and does not finish at all at `-j 8` on the same
machine, where every point hits the harness's 300 s per-point timeout
(record `20260811-083430-4249351` is that abort, kept because `sim/` is
append-only).

Each script regenerates its own `results.md` / `width_results.md` /
`cdg_results.md`, its `decks/` and its raw `logs/` in place. The traces the
first one writes are git-ignored and regenerable (`sim/README.md`).

## Reproducing the evidence

```bash
python3 design/netlist.py --check            # schematic ↔ committed netlist
python3 sim/build_tb.py --check              # netlist ↔ testbench fragments
python3 sim/run_corners.py por-output-chain-pulse
python3 sim/run_corners.py por-output-chain-deglitch
python3 sim/run_corners.py por-output-chain-floor
python3 sim/run_corners.py por-ramp-rate              # assembly, all four rates
python3 sim/run_corners.py por-glitch                # assembly, VDD glitch
python3 sim/por-ramp-rate/control/run_chatter_probe.py   # issue #56, release-edge chatter
python3 sim/por-glitch/control/run_glitch_probe.py       # issue #56, VDD-glitch mechanism
python3 sim/por-glitch/control/run_depth_sweep.py        # issue #56, VDD-glitch depth/duration
bash layout/run_checks.sh por_output_chain               # DRC/LVS incl. XMRLK
```

Each `run_corners.py` invocation mints a **new** record id; `sim/` is
append-only, so none of them overwrites the records cited at the top of this
document. The two `control/` scripts are diagnoses, not records — they
overwrite their own outputs in place on every run, exactly as
`sim/bias-core-startup/control/` does (`sim/README.md`, "Control
experiments").

## Out of scope here, on purpose

| Not here | Where |
| --- | --- |
| The threshold itself, VPOR↑/VPOR↓ and hysteresis | `por_comparator`, #10 |
| The real `IBIAS` source, its tolerance, and how one mirror feeds three consumers | `bias_core`, #11 |
| Ramp-rate envelope, brownout on a real bring-up sequence, observed pulse **maximum** across corners (DR-007 declines to cap it in wave 1) | POR testbench suite, #14 |
| Monte Carlo mismatch on the pulse and dwell distributions | #15 |
| Layout, MIM stacking, measured area | #16, #17 |
| Amending the ratified `target-spec.md` rows this document fills (`por-brownout`'s dwell TBD, the `por-reset-pulse` load, the `por-reset-valid-floor` achieved floor, and the fastest-timer-corner parenthetical) | a decision record via #1 |
