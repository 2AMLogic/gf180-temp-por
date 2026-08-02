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
| [`sim/por-output-chain-pulse/`](../sim/por-output-chain-pulse/) — record `20260801-031819-fce635f` | [`por-reset-pulse`](../spec/target-spec.md#por-reset-pulse) ≥1 ms at nominal **and 3× IBIAS**, the deasserted level (push-pull, [`por-drive`](../spec/target-spec.md#por-drive)), no early release, and this cell's own share of [`por-iq`](../spec/target-spec.md#por-iq) in both the asserted and released states |
| [`sim/por-output-chain-deglitch/`](../sim/por-output-chain-deglitch/) — record `20260801-032128-309621f` | the deglitch **dwell time** ([`por-brownout`](../spec/target-spec.md#por-brownout)'s `[TBD-#12]`) at nominal **and half** IBIAS, capture of a *qualifying* 10 µs dip, regeneration of the full pulse after it, and the no-early/no-double-pulse chatter edge case |
| [`sim/por-output-chain-floor/`](../sim/por-output-chain-floor/) — record `20260801-032940-d59d7c4` | [`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) against a slow 0 V → VDD ramp, with `POR_RAW` held low **and** driven to the rail, plus [`por-polarity`](../spec/target-spec.md#por-polarity) (degrades to *asserted* near 0 V) |

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
| `XMNAP1`, `XMNAP2` | 4 µm / 0.5 µm | release-NAND parallel pull-ups |
| `XMNAN1`, `XMNAN2` | 2 µm / 0.5 µm | release-NAND series pull-down stack |
| `XMAST` | 0.5 µm / 10 µm | startup-assist keeper on `RSTB` |
| `XMOP` | 1 µm / 1 µm | output pull-up |
| `XMON` | 10 µm / 0.5 µm | output pull-down — **20:1 in W/L against `XMOP`** |

Three of these are load-bearing enough to justify their own section.

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
| [`por-reset-pulse`](../spec/target-spec.md#por-reset-pulse) | ≥1 ms, no maximum | **4.215 … 7.752 ms** at nominal `IBIAS`; **1.579 … 2.822 ms** at 3× `IBIAS` | min at **FF / −40 °C / 2.97 V** | **PASS** — 4.2× margin at nominal, 1.58× with a 3× `IBIAS` error |
| [`por-brownout`](../spec/target-spec.md#por-brownout) `[TBD-#12]` | deglitch dwell ≤ 10 µs | **1.86 … 4.58 µs** at nominal `IBIAS`; **3.61 … 8.88 µs** at half | max at **SS / −40 °C / 3.63 V** (as the row predicts) | **PASS** — the published dwell is **4.58 µs worst-case**, 2.2× under `T_dip,min` |
| [`por-brownout`](../spec/target-spec.md#por-brownout) | a qualifying 10 µs dip re-asserts and regenerates the full pulse | `RESETn` back to a valid low in **1.84 … 4.57 µs** end-to-end; stays asserted for the rest of the run | — | **PASS** |
| [`por-reset-valid-floor`](../spec/target-spec.md#por-reset-valid-floor) | `V(RESETn) ≤ min(0.1 × VDD, 0.3 V)` for all VDD ≥ 0 | max ratio **0.0055 × VDD**; max absolute **1.70 mV** | ratio at **SF / +125 °C**, absolute at **SS / −40 °C** | **PASS** — 18× under the ratio limit, 176× under the absolute one |
| [`por-polarity`](../spec/target-spec.md#por-polarity) | active low, degrades to *asserted* near 0 V | held ≤1.70 mV through the whole 0 V → VDD ramp, with `POR_RAW` low **and** driven to the rail | — | **PASS** |
| [`por-drive`](../spec/target-spec.md#por-drive) | push-pull, both states driven | deasserted level = **full rail** (2.96999 / 3.29999 / 3.62999 V into 5 pF) | — | **PASS** |
| [`por-iq`](../spec/target-spec.md#por-iq) | shared <1 µA | this cell's own draw **24.96 … 31.58 nA** asserted, 19.47 … 25.41 nA released | max at **FF / +125 °C / 3.63 V** | **PASS** — see [Iq budget](#iq-budget) |

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

### The achieved valid-low floor is 1.70 mV, not exactly 0 V

`por-reset-valid-floor` targets 0 V with an acceptance fallback of ≤0.4 V
"if #12 demonstrates 0 V is unreachable, with the achieved floor stated". The
honest statement: **0 V is not reachable in the strict sense** — the output is
a leakage divider, so `V(RESETn)` is strictly positive at any VDD > 0 — but
the *specified* criterion (`≤ min(0.1 × VDD, 0.3 V)`) is met outright, with
18× margin on the ratio, so the ≤0.4 V fallback is not invoked. The achieved
floor, stated as the row requires:

- **Absolute**: `V(RESETn) ≤ 1.70 mV` at every point of a 0 V → VDD ramp, all
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
| `RESETn` during chatter, pulse still running | no **early release** | ≤ 5.03 nV |
| `RESETn` after release, same chatter | no spurious **re-assertion** | ≥ 2.96999 V |
| pulse width measured through the chatter | neither truncated nor **restarted** | 4.215 … 7.751 ms — the same distribution as the un-chattered pulse |

The last row is the real discriminator, and it is why the check is two-sided
rather than a bare `≥1 ms`: a glitch that *did* get through would have reset
the timer at 1.2 ms and pushed the release ~0.9 ms later than the
un-chattered pulse recorded in `sim/por-output-chain-pulse/`. A one-sided
minimum would have called that a pass.

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

Across the whole grid this cell's asserted-state draw is **24.96 … 31.58 nA**
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
| pulse | **3× nominal** (1.5 µA) | more current ⇒ *faster* timer ⇒ shorter pulse ⇒ threatens the ≥1 ms floor | ≥ **1.579 ms** at every point |
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
directly (1.70 mV worst case, ≤0.0055 × VDD), including the pathological case
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

## Reproducing the evidence

```bash
python3 design/netlist.py --check            # schematic ↔ committed netlist
python3 sim/build_tb.py --check              # netlist ↔ testbench fragments
python3 sim/run_corners.py por-output-chain-pulse    -j 8
python3 sim/run_corners.py por-output-chain-deglitch -j 8
python3 sim/run_corners.py por-output-chain-floor    -j 8
```

Each run mints a **new** record id; `sim/` is append-only, so none of them
overwrites the records cited at the top of this document.

## Out of scope here, on purpose

| Not here | Where |
| --- | --- |
| The threshold itself, VPOR↑/VPOR↓ and hysteresis | `por_comparator`, #10 |
| The real `IBIAS` source, its tolerance, and how one mirror feeds three consumers | `bias_core`, #11 |
| Ramp-rate envelope, brownout on a real bring-up sequence, observed pulse **maximum** across corners (DR-007 declines to cap it in wave 1) | POR testbench suite, #14 |
| Monte Carlo mismatch on the pulse and dwell distributions | #15 |
| Layout, MIM stacking, measured area | #16, #17 |
| Amending the ratified `target-spec.md` rows this document fills (`por-brownout`'s dwell TBD, the `por-reset-pulse` load, the `por-reset-valid-floor` achieved floor, and the fastest-timer-corner parenthetical) | a decision record via #1 |
