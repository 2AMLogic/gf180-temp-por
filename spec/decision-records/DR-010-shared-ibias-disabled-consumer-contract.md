# DR-010: Shared `IBIAS` — a disabled consumer presents high impedance

- **Status**: proposed
- **Date**: 2026-08-01
- **Decided by**: Loom Builder agent, issue #41

## Context

`design/netlist/temp_por_top.spice` wires `IBIAS` as a **single net** shared by
four cells: `bias_core` sources it, and `temp_core`, `por_comparator` and
`por_output_chain` all consume it. That sharing is DR-005's, and it is how the
block amortizes Iq and area across one bias core.

DR-005 startup ordering step 6 also holds `temp_core` disabled until POR
releases — `temp_core.EN` **is** `RESETn`. And `temp_core`'s disabled state
clamped the `IBIAS` *pin* to `VSS` through an `ENB`-gated `XMDIB` (1 µm/1 µm
nfet). That clamp was deliberate and documented, but its gating signal is the
one signal that cannot be true before POR. The result is a closed loop:

```
temp_core disabled → IBIAS shorted to VSS → por_comparator's tail mirror
starved → POR_RAW cannot go high → RESETn stays asserted → temp_core disabled
```

`sim/bias-core-ibias-sharing/records/20260801-054722-6cf5898.md` measured it
across the full 81-point PVT grid: the shared node sat at **1.0–6.6 mV** with a
disabled `temp_core` present, against **0.57–0.86 V** in an otherwise identical
control with `temp_core` absent, and `POR_RAW` never released. `VREF` was
unaffected in both branches, which is what identifies this as an interface
defect on one net rather than a fault inside any cell's own loop.

This is a **liveness** defect — the block never starts — not a magnitude miss.
Fixing it necessarily changes the contract on a net shared by three cells whose
designs are closed (#9, #10, #11, #12), which is what makes it a decision
record rather than an edit inside one cell's issue (CLAUDE.md: "Spec changes go
through `spec/` with a decision record"). `design/bias_core.md`, "The shared
`IBIAS` net", records the same finding independently and defers to this record.

## Decision

**A cell that consumes the shared `IBIAS` net must present high impedance to
that net whenever it is disabled. It may gate its own internal fan-out off the
node; it may never clamp, shunt or otherwise define the node itself.**

Concretely, and ratified as part of the `IBIAS` interface contract:

1. `temp_core`'s `XMDIB` is **deleted**. `XMPASS` (off) and `XMDNB` (`NBG` →
   `VSS`) already switch the local mirror off, so with `EN` low the pin is
   simply high-Z, which is what a shared node needs. Measured: the disabled
   cell now draws **≤ 0.152 nA** out of the shared node
   (`sim/temp-core-designer-check/records/20260801-073732-8b7e57f.md`,
   `ibias_dis_na`), against the 0.5 µA `IBIAS` convention.
2. The node's operating point is defined by the **always-on diode-connected
   input in `por_output_chain`** (`XMBD`, gate tied to drain, ungated by
   construction), together with `por_comparator`'s mirror input once `BIAS_OK`
   is high. At least one such always-on element must remain on the net; this
   is now an invariant of the interface, not an accident of one cell's
   topology.
3. `por_comparator`'s `XMDIB` is **kept**. It is gated on `BIAS_OKB`, and
   `BIAS_OK` is generated inside `bias_core` from `PB`/`NA`/`NBTOP`/`NKG` with
   no dependence on `IBIAS` compliance — so it is self-releasing and is not a
   member of the lockup loop. It holds the node down only until the bias core
   is up, which is the correct behaviour: nothing downstream should be timing
   or deciding before then.
4. A **single-cell testbench** that forces an ideal current into a disabled
   consumer's `IBIAS` pin must now terminate that current itself, modelling the
   rest of the shared net (a diode-connected `nfet_03v3` 4 µm/4 µm — a copy of
   `por_output_chain`'s `XMBD`). Relying on the DUT to sink a forced current in
   its disabled state is what disguised this defect as acceptable: it made a
   *testbench* condition look like a *system* requirement.

The interface table in `design/README.md`, the port contracts in
`design/temp_core.md` and `design/bias_core.md`, and the schematic annotation in
`design/temp_core.sch` all state this contract.

**No row of `spec/target-spec.md` is added, removed or relaxed by this record.**

## Alternatives considered

- **Give `bias_core` a `RESETn`/`EN` input and let it gate its own `IBIAS`
  output** (candidate 2 in #41 and in `design/bias_core.md`). **Rejected, and
  it is worse than the defect it would fix.** `por_comparator` and
  `por_output_chain` consume `IBIAS` *precisely while `RESETn` is asserted* —
  that is the entire window in which POR does its job. Gating the source on
  `RESETn` would starve them unconditionally instead of conditionally, turning
  a lockup that a clamp happened to cause into one the interface guarantees.
  The ~1 µA of `por-iq` budget it is credited with recovering
  (`design/bias_core.md`, "Iq apportionment") is not recoverable this way: that
  current is what biases the comparator's tail and the output chain's timer,
  so removing it removes the POR decision. The Iq overrun is real and remains
  open (see Consequences), but it is a magnitude problem for its own re-cost
  record through #1; it must not be paid for with liveness.
- **Split `IBIAS` into two nets, POR-side and sensor-side** (candidate 3).
  **Rejected on cost.** It works, but it needs a second always-on output leg in
  `bias_core`, a new port on `bias_core`, and top-level rewiring — i.e. it adds
  a second permanently-conducting mirror leg to a block whose `por-iq` row is
  already missed by 2.37×, and adds ports to a ratified interface. It buys
  isolation the contract above already delivers for free. Worth revisiting only
  if a future consumer genuinely cannot be made high-Z when disabled.
- **Keep `XMDIB` but put it in series with a diode**, so the disabled pin sees
  a diode drop rather than a short. **Rejected.** It removes the lockup and
  needs no testbench changes, but a disabled cell would still draw a share of
  the reference away from the consumers that need it — the wrong direction for
  `por-iq`, and it leaves "a disabled cell loads the shared node" standing as
  acceptable practice.
- **Re-gate `XMDIB` on a signal other than `EN`** (candidate 1 as literally
  worded). Nothing inside `temp_core` carries the required meaning ("this pin
  is not being driven"); synthesising it needs a comparator, for a node that
  does not need defining at all. Deleting the clamp *is* candidate 1, taken to
  its conclusion.

## Consequences

**Fixed, and measured.** The lockup is gone across the whole grid, and the
block now starts:

| Evidence | Before | After |
| --- | --- | --- |
| shared `IBIAS`, reset asserted, `temp_core` present (`sim/bias-core-ibias-sharing/`, 81 pts) | 1.0–6.6 mV | **0.568–0.861 V**, tracking the no-`temp_core` control to ≤ 3 µV |
| `POR_RAW` droop, same branch | pinned low | **≤ 0.005 mV** from the rail |
| `RESETn` release, full four-cell assembly (`sim/temp-por-top-release/`, 81 pts) | never released at any point | **releases at every point**, 5.61–16.95 ms |
| `PTAT` after release | never enabled | **1.003–1.716 V** — the sensor is genuinely enabled |
| disabled `temp_core`'s draw from the shared node | the whole reference | **≤ 0.152 nA** |

**A new full-assembly record exists.** `sim/temp-por-top-release/` is the first
corner record taken on `temp_por_top` as a whole rather than cell by cell —
`design/README.md` flagged its absence, and the lockup is exactly the class of
defect only a full-assembly testbench can witness (the two-cell integration
testbench that found it stops at `POR_RAW` and never reaches `RESETn`).

**Two `temp_core` records had to be re-run**, because their stimuli relied on
the deleted clamp to sink a forced ideal current into a disabled pin:
`sim/temp-core-designer-check/` and `sim/temp-core-startup/`. Both pass, and
both now carry the high-impedance invariant as an explicit check
(`ibias_dis_na` / `ibias_pre_dis_na`, bounded at 25 nA = 5 % of the `IBIAS`
convention). `temp_core`'s own disabled-state draw is unchanged at ≤ 0.69 nA,
and `por_comparator` / `por_output_chain` / `bias_core` netlists are untouched,
so their existing records still stand.

**`por-iq` is still missed, and this record does not fix it.** Measured on the
real assembly for the first time, in the state the row is defined in:
**0.657–2.385 µA against < 1 µA**, failing at 54 of 81 points
(`sim/temp-por-top-release/`, `iq_por_ua`). That is the same overrun
`design/bias_core.md`'s "Iq apportionment" derives at 2.37× by summing per-cell
records; the check is left at the ratified 1.0 µA and allowed to fail rather
than relaxed. It remains open work for its own re-cost record through #1,
alongside the `por-ramp-rate` tension in the same document.

**What got slightly harder.** A future `IBIAS` consumer can no longer be
verified standalone by forcing current into a disabled pin — its testbench must
model the shared net. That is a real cost, and it is the correct one: the
alternative is what produced this defect.

**What is now guarded.** The contract has teeth beyond prose: `ibias_dis_na`
and `ibias_pre_dis_na` fail a corner run if any future `temp_core` edit
re-introduces a clamp, and `sim/temp-por-top-release/`'s `t_release_ms` fails
if the block ever stops starting.
