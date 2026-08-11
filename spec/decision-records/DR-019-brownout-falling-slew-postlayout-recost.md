# DR-019: Re-cost `por-brownout`'s `dVDD/dt|fall,max` to 2.30 mV/µs against the extracted netlist

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #188

## Context

[`spec/target-spec.md#por-brownout`](../target-spec.md#por-brownout) clause
(c) ratifies **`dVDD/dt|fall,max` = 3.40 mV/µs** — the fastest falling rail a
qualifying brownout dip may present and still be guaranteed to re-assert
`RESETn`. That number came from #60's 81-point falling-slew ladder on
`design/netlist/temp_por_top.spice`, bracketed "PASS at 3.40 mV/µs, FAIL from
3.4795 mV/µs" and tightened by #74 to "FAIL from 3.46 mV/µs"
(`sim/por-brownout-slew/records/20260802-134958-dd0cd60-boundary.md`).

**That bracket was measured on a netlist that is now superseded for this
row.** #87's post-layout re-run of the one rung its testbench carried
(3.46 mV/µs) went 80/81 → 75/81, which moved the transition band down toward
the bound but did not measure the bound itself. #188 ran the missing rung and
then walked the ladder down. Every rung below was run against
[`layout/postlayout/temp_por_top.spice`](../../layout/postlayout/temp_por_top.spice)
(#82/PR #180's `klt extract --parasitics` + `klt lvs` extraction, 159/159 nets
paired), on the same stimulus, manifest and 81-point PVT grid as its schematic
sibling — the DUT is the only variable:

| Rung | Extracted record | Schematic | Extracted |
| ---: | --- | ---: | ---: |
| 2.30 mV/µs | [`20260811-111437-88888f3`](../../sim/por-brownout-slew/records/20260811-111437-88888f3.md) | 81/81 | **81/81** |
| 2.40 mV/µs | [`20260811-111307-0c68175`](../../sim/por-brownout-slew/records/20260811-111307-0c68175.md) | — | **81/81** |
| 2.45 mV/µs | [`20260811-111125-794bf81`](../../sim/por-brownout-slew/records/20260811-111125-794bf81.md) | — | **81/81** |
| 2.50 mV/µs | [`20260811-110956-0aae891`](../../sim/por-brownout-slew/records/20260811-110956-0aae891.md) | — | **80/81** (`ss_-40c_2.97v`) |
| **3.40 mV/µs — the ratified bound** | [`20260811-110825-73ef5e3`](../../sim/por-brownout-slew/records/20260811-110825-73ef5e3.md) | 81/81 | **76/81** |
| 3.46 mV/µs | [`20260811-063855-6d69544`](../../sim/por-brownout-slew/records/20260811-063855-6d69544.md) (#87) | 80/81 | **75/81** |

The ratified bound **does not hold on the extracted netlist**: at 3.40 mV/µs
five corners fail — `ss_-40c_{2.97,3.30,3.63}v` and
`res_ss_-40c_{2.97,3.30}v`, the SS/−40 °C family this row already names as
binding. The extracted netlist's own transition edge sits between **2.45 and
2.50 mV/µs**
([`20260811-111437-88888f3-boundary`](../../sim/por-brownout-slew/records/20260811-111437-88888f3-boundary.md),
a derived record over the six rungs above), against 3.44/3.46 mV/µs on the
schematic ladder.

**It is the same mechanism, deeper — not a new one.**
[`sim/por-brownout-slew/control/postlayout_margin_results.md`](../../sim/por-brownout-slew/control/postlayout_margin_results.md)
runs #74's own event-timeline deck against both netlists at the binding
`ss`/−40 °C family and measures [DR-011](DR-011-brownout-falling-slew-limit.md)'s
own state variable, `V_sg` (= VDD − `PG`, the overdrive on `bias_core`'s PMOS
mirror bank):

| At 3.40 mV/µs, `ss` / −40 °C | 2.97 V | 3.30 V | 3.63 V |
| --- | ---: | ---: | ---: |
| min `V_sg`, schematic | +22.7 mV | −85.8 mV | −116.1 mV |
| min `V_sg`, extracted | **−100.5 mV** | **−252.5 mV** | **−297.5 mV** |
| peak `NDG`/VDD (deglitch ramp), schematic | 0.626 | 0.670 | 0.706 |
| peak `NDG`/VDD, extracted | **0.000** | **0.000** | **0.000** |

The extraction drives the mirror bank 2–3× further off at the same falling
slew, and past the point where `por_output_chain`'s deglitch ramp starts at
all: `POR_RAW` rides the rail at 0.999 for the whole dip, so the FAIL is
DR-011's mode (i) — **no decision** — not a late one. Below the bound the
same control shows the ordinary cost of the extraction rather than a
collapse: at every rung both arms pass, and the extracted arm's
`RESETn`-valid-low margin is a roughly constant −140 to −180 µs against the
schematic's, with `POR_RAW` asserting ~68 µs → ~145 µs after the dip starts.

## Decision

**`spec/target-spec.md#por-brownout` clause (c)'s `dVDD/dt|fall,max` moves
from 3.40 mV/µs to 2.30 mV/µs**, [CWC], binding corner unchanged
(SS / −40 °C, now binding at 2.97 V rather than 3.30 V). Clauses (a) and (b)
— the VPOR↓,min depth and the `T_dip,min` ≥ 10 µs dwell — are untouched.

**The number is chosen on margin, not on the bracket.** The mechanical
bracket over the extracted ladder is 2.45 mV/µs (the fastest clean 81/81
rung). This record does not ratify it, for the reason
`sim/por-brownout-slew/testbench/README.md` already states about the
schematic bound: the bound sits on the safe side of the whole transition, not
one bisection step below a FAIL. The yardstick used here is the margin the
*outgoing* bound carried — `+108.8 µs` of dip window left when `RESETn`
reached valid-low, at the worst supply of the binding family: the schematic
arm of the same control that measures the extracted arm below, reproducing
#74's own `+108.7 µs`
([`control/results.md`](../../sim/por-brownout-slew/control/results.md)) to
within the 0.1 µs its coarser event grid resolves — and the incoming bound is
the ladder value at which the extracted netlist has at least that much:

| Candidate | Worst-supply margin, extracted (`ss`/−40 °C) | vs. the outgoing bound's +108.8 µs |
| ---: | ---: | --- |
| 2.45 mV/µs | +29.7 µs (2.97 V) | 0.27× — **rejected** |
| 2.40 mV/µs | +119.6 µs (2.97 V) | 1.10× |
| **2.30 mV/µs** | **+209.8 µs** (2.97 V) | **1.93×** |

2.30 mV/µs is also a rung of DR-011's own proposed ladder (2300 / 23.00 /
15.33 / 11.50 / 7.67 / **2.30** / 0.77 mV/µs) rather than a bisection
artefact, it is 8 % below the lowest extracted rung that fails anywhere
(2.50 mV/µs) with two clean 81/81 rungs of buffer in between, and the
schematic netlist also passes 81/81 there
(`sim/por-brownout-slew/records/20260802-113700-3c3e728.md`), so the new bound
is met at **both** netlist levels rather than only the one it was measured on.

This is a **weakening of a guarantee**, stated plainly: a system whose supply
falls at between 2.30 and 3.40 mV/µs through the POR threshold was covered by
this block's brownout clause before this record and is not covered after it.
Nothing about the circuit changed; the measurement got more accurate.

## Alternatives considered

- **Ratify 2.45 mV/µs, the mechanical bracket.** Rejected. It is a clean
  81/81 verdict with 29.7 µs of dip window behind it at the binding point —
  a 2 % slew change away from a FAIL, on the steepest part of the margin
  curve (2.45 → 2.40 mV/µs is worth +90 µs). The schematic bound was never
  set that way and the non-monotonic behaviour #74 documented in this same
  band is exactly the reason not to start.
- **Ratify 2.40 mV/µs.** Rejected, though it does clear the yardstick at
  1.10×. It clears it by 10 %, on a curve whose local slope is ~90 µs per
  0.05 mV/µs; 2.30 mV/µs clears it by 93 % and costs a further 4 % of slew
  envelope that no consumer of this block has asked for.
- **Leave 3.40 mV/µs ratified and route the post-layout miss to a new issue**,
  as [#85 did](../target-spec.md#por-hysteresis) for `por-hysteresis`'s
  post-layout `ss_-40c_3.63v` overrun (→ #187). Rejected **for this row**:
  that pattern is right for a verification-only issue that is not chartered
  to decide, and #85 was one. #188 is the issue chartered to resolve this
  finding, the missing measurement it was filed for has now been made, and
  leaving a ratified bound standing that is measurably violated at five
  corners of the netlist that represents the shipped part is the "silently
  keep the number" failure mode from the other direction.
- **Re-cost against a re-drawn layout instead** — i.e. treat the boundary
  shift as a layout defect and fix `PG`'s loading. Rejected as out of scope
  for a spec decision, and not yet supported by measurement: the extraction
  adds only 68.1 fF and 5.08 kΩ on `PG` itself (`R_6`/`C_6`), against
  DR-011's ≈1.25 pF estimate for that node, so a single-net explanation is
  not established. See Consequences for the follow-up this leaves open.
- **Declare the extracted result the only one that counts and retire the
  schematic ladder.** Rejected. `sim/README.md` keeps both provenances as
  evidence and the schematic ladder is what DR-011 decision 2 was satisfied
  against; the two are now recorded as two ladders on the same axis, not one
  ladder with a moved rung (`sim/por-brownout-slew/_rung_record.py` refuses
  to mix them).

## Consequences

**The row's measured verdict does not change, and that is worth saying
first.** `sim/por-brownout/` is 0/81 at both netlist levels before and after
this record, because that experiment's own deck presents a ~1970 mV/µs edge —
~860× the new bound, ~580× the old one — and DR-011 already states that
re-assertion is not guaranteed there. This record moves the *envelope inside
which the guarantee applies*, which is measured by `sim/por-brownout-slew/`.

**The falling-slew envelope narrows by 32 %.** Any integrator statement of
the form "this block re-asserts reset on a brownout" is now qualified by
2.30 mV/µs rather than 3.40 mV/µs. For a rail falling from 3.63 V to below
VPOR↓,min = 2.22 V, that is a minimum fall time of 613 µs where 415 µs used
to suffice.

**The sub-boundary regime is unaffected and still defective.** #61 /
[DR-013](DR-013-por-brownout-spurious-assert.md)'s spurious `POR_RAW` assert
above VPOR↑,max is a separate finding at slews *below* this bound, its
mechanism is still unidentified, and this record neither addresses nor
worsens it. Post-layout it has a smaller footprint (`design/temp_por_top.md`),
which is not a fix.

**Why the extraction moves this boundary at all is not root-caused here, and
is left open.** What is measured is that it does, that the state variable is
DR-011's, and that the collapse is 2–3× deeper at the same slew. What is
*not* measured is which nets' parasitics carry it: `PG`'s own extracted
68.1 fF is ~5 % of DR-011's estimate for that node and cannot explain a 28 %
boundary shift alone, and the extraction loads 136 of 159 nets (ΣC 5880.2 fF).
A per-net attribution — most directly, re-running the ladder against the
extracted netlist with individual parasitic pairs removed — is the follow-up
that would say whether this is addressable in layout or is intrinsic to the
starved loop at this bias level. It is filed separately rather than done
here, because this record needs only the boundary, and the boundary is
measured.

**`por-brownout`'s `pending #1` status is unchanged.** This record settles
clause (c)'s number against the extracted netlist; the row still awaits #1's
ratification pass, still carries DR-013's open sub-boundary defect, and still
carries DR-014/DR-017's `VDD`-level-glitch scoping gap.

**No `sim/` evidence is edited.** Every record above stands with the
PASS/FAIL column its own `tb.json` encoded when it ran — the ladder's checks
are on `resetn_ratio_min_in_dip`, not on the ratified slew, so no testbench
threshold encodes the number this record moves and none needs updating.
`spec/target-spec.md`'s prose is what changes.

**A second finding from the same investigation is *not* a consequence of this
record and is recorded to keep it from being mis-attributed.** #87's
post-layout `por-brownout` record reported a `t_reassert_us` slip
(51.26–51.58 → 51.67–64.25 µs) and a lost re-assert at `ss_-40c_2.97v`,
against the schematic baseline `20260801-233807-32fbaa0`. That baseline's own
frozen netlist snapshot differs from today's schematic netlist by exactly one
device — `XMRLK`, the release latch [DR-016](DR-016-por-ramp-rate-chatter-release-latch.md)
added — so the comparison spanned two changes. Re-running the schematic grid
on today's netlist
([`20260811-112115-9807e3f`](../../sim/por-brownout/records/20260811-112115-9807e3f.md))
gives 8 lost re-asserts and 52.01–66.24 µs, i.e. **worse than the extracted
netlist on both counts**, and a three-arm control
([`sim/por-brownout/control/recovery_results.md`](../../sim/por-brownout/control/recovery_results.md))
attributes the change to `XMRLK` rather than to the extraction: `POR_RAW`
still asserts on the recovery edge in every arm, so what is lost is
propagation, which is precisely what a one-way release latch is for. Both
numbers are outside this row's guaranteed envelope by ~580× in slew either
way; DR-011's Consequences sentence "the block recovers; it does not latch up
or stay released" is the claim that needs narrowing, and that is routed to
its own follow-up rather than settled here.
