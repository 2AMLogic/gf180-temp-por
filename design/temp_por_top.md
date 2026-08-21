# `temp_por_top` — the assembled block

The four cells each have their own design document
([`bias_core.md`](bias_core.md), [`temp_core.md`](temp_core.md),
[`por_comparator.md`](por_comparator.md),
[`por_output_chain.md`](por_output_chain.md)); the pad interface, the
hierarchy and the internal-net contracts are in
[`README.md`](README.md) → "Top-level pinout" / "Hierarchy". This document is
for what is only true of the **assembly** — claims no single-cell testbench
can make, because the thing under test is the loop between the cells rather
than any one of them.

Its first content is the post-layout re-run below. The assembly's
schematic-level story is already told where it happened: the shared-`IBIAS`
lockup and its fix in [`bias_core.md`](bias_core.md) and
[DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md),
the brownout falling-slew root cause in
[DR-011](../spec/decision-records/DR-011-brownout-falling-slew-limit.md), the glitch
response in [DR-014](../spec/decision-records/DR-014-por-glitch-vdd-level-immunity.md) /
[DR-017](../spec/decision-records/DR-017-por-glitch-representative-depth.md),
and the intermediate-falling-slew spurious assert in
[DR-013](../spec/decision-records/DR-013-por-brownout-spurious-assert.md).

## Post-layout re-run of the full-assembly suite (issue #87)

Every full-assembly POR dynamic-behaviour testbench was re-run against
[`layout/postlayout/temp_por_top.spice`](../layout/postlayout/temp_por_top.spice)
— #82/PR #180's direct `klt extract --parasitics` + `klt lvs` extraction of
the whole four-cell assembly — instead of `design/netlist/temp_por_top.spice`.
Same stimulus, same manifest, same 81-point PVT grid: each
`testbench-postlayout/tb.json` is a byte-for-byte copy of its schematic
sibling apart from the netlist it points at, so the DUT is the only variable
and a delta reads as circuit behaviour rather than as a testbench difference.

| Experiment | Extracted record | Supersedes (schematic) | Verdict, schematic → extracted |
| --- | --- | --- | --- |
| [`por-ramp-rate`](../sim/por-ramp-rate/) | [`20260811-081726-9b421f6`](../sim/por-ramp-rate/records/20260811-081726-9b421f6.md) | `20260802-205904-bdc077d` | 81/81 PASS → **81/81 PASS** |
| [`por-brownout`](../sim/por-brownout/) | [`20260811-065930-35a87a6`](../sim/por-brownout/records/20260811-065930-35a87a6.md) | `20260801-233807-32fbaa0` | 0/81 PASS → 0/81 PASS (81 FAIL → 80 FAIL + 1 ERROR) |
| [`por-brownout-slew`](../sim/por-brownout-slew/) (rung `n-slew-3.46mvus`) | [`20260811-063855-6d69544`](../sim/por-brownout-slew/records/20260811-063855-6d69544.md) | `20260802-134958-dd0cd60` | 80/81 PASS → **75/81 PASS** |
| [`por-brownout-spurious`](../sim/por-brownout-spurious/) | [`20260811-071019-9aaf2b8`](../sim/por-brownout-spurious/records/20260811-071019-9aaf2b8.md) | `20260802-122414-3c3e728` | 0/81 PASS → 10/81 PASS (76 FAIL + 5 ERROR → 15 FAIL + 56 ERROR) |
| [`por-glitch`](../sim/por-glitch/) | [`20260811-065152-1d1dd69`](../sim/por-glitch/records/20260811-065152-1d1dd69.md) | `20260802-205904-bdc077d` | 0/81 PASS → 0/81 PASS (identical failure set) |
| [`temp-por-top-release`](../sim/temp-por-top-release/) | [`20260819-173152-e58ed1a`](../sim/temp-por-top-release/records/20260819-173152-e58ed1a.md)<sup>†</sup> | `20260802-205904-bdc077d` | 27/81 PASS → 27/81 PASS (identical failure set) |

† Re-run again by #270 against the netlist with `temp_core`'s `XCC` drawn
(#259, DR-028) — superseding the row's original #87 extracted record,
[`20260811-064427-564950b`](../sim/temp-por-top-release/records/20260811-064427-564950b.md),
which stays on disk. Same 27/81 PASS, same failure set (all `iq_por_ua`); see
"§4" of the closing roll-up below for what that re-run establishes.

Reading that column needs care, because most of these experiments were already
failing before the re-run and for reasons this re-run does not touch:
`por-brownout` is DR-011's known 0/81 falling-slew failure, `por-glitch` is
DR-014/DR-017's known 300 ns glitch response, and `temp-por-top-release`'s 54
failures are all the one `por-iq` row. **The two numbers that changed for a
post-layout reason are `por-brownout-slew`'s (80 → 75, a regression) and
`por-brownout-spurious`'s (0 → 10, a *smaller* spurious-assert footprint, not
a fix)**; both are unpacked below. `por-ramp-rate` — the one experiment that
was fully green at the schematic level, and therefore the only one with a
clean result to lose — stays fully green: all four ratified ramp endpoints
release at or above `VPOR↑,min` with no chatter at any of the 81 points, and
the release rail moves by at most +0.11 %.

**Caveat on the `por-brownout-slew` row's schematic baseline** (per
[#209](https://github.com/2AMLogic/gf180-temp-por/issues/209)):
`20260802-134958-dd0cd60` is stamped "taken against a dirty working tree …
not citable as a clean-tree result" in its own `Netlist provenance` field.
The 80/81 → 75/81 direction and the failing-corner set are unaffected — this
is a full-assembly transient, not a per-cell deck, so it was not re-run
purely to clear the stamp — but the precise "80" half of that count rests on
a non-citable baseline per `sim/README.md`'s citation policy. #188's own
falling-slew re-cost ([DR-019](../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md))
does not depend on this row: it was measured from scratch against a clean
tree (`sim/por-brownout-slew/records/20260811-110825-73ef5e3.md` and
siblings), not from this comparison.

### What "extracted" means for this assembly

> **Update, 2026-08-19 (#259, #270).** The one ideal device described below
> is now **drawn**: `temp_core`'s `XCC` was laid out and routed onto `PG`/`NZ`
> per [DR-028](../spec/decision-records/DR-028-temp-core-xcc-draw-it.md),
> taking `temp_por_top` to **239 drawn devices, 0 ideal** (and, since #264
> routed the MiM plates, 145 nets rather than 159). Of the six experiments in
> the table above, only `temp-por-top-release` has actually been **re-run**
> against that current netlist (#270,
> [`20260819-173152-e58ed1a`](../sim/temp-por-top-release/records/20260819-173152-e58ed1a.md)) —
> #270's scope is the compensation-pole-dependent claims specifically, and the
> other five (`por-ramp-rate`, `por-brownout`, `por-brownout-slew`,
> `por-brownout-spurious`, `por-glitch`) measure POR ramp/brownout/glitch
> dynamics that do not turn on `temp_core`'s amplifier compensation, so they
> were left un-re-run rather than re-run for no reason. The paragraph below
> therefore still describes the **238-device, 1-ideal** netlist those five
> records were actually taken against — this repo's `sim/` set is
> append-only, so their own provenance fields are unedited and still
> accurate for the netlist state at the time they ran.

Per [`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md)'s
`temp_por_top` row **as it read at the time of #87's original re-run**: 238
drawn devices, 1 ideal. The single ideal device was `temp_core`'s `XCC` MiM
cap (here instance `xtemp`'s, on `xtemp__PG` / `xtemp__NZ`), which that
cell's layout did not draw yet at that point — reserved floor area, tracked
as #177 and drawn since #259. Every other device in the assembly, including
all 19 bipolars, all 77 resistors and the other 7 MiM caps, was drawn and
extracted already. 136 of 159 nets carried first-order interconnect R/C
across 272 parasitic cards (ΣR 280 923 Ω, ΣC 5880.2 fF); the 23 without were
isolated well/plate nets and the substrate global, tied where the
*schematic* puts them because the extraction deck's connectivity stack does
not reach them. Two deck substitutions were undone on the way out (27
`ppolyf_u_1k` → `ppolyf_u_3k`, klayout-tools#323; 7
`cap_mim_2f0_m4m5_noshield` → `cap_mim_2f0_m3m4_noshield`, klayout-tools#315)
— the drawn geometry is the schematic's in both cases, only the deck's name
for it differs. (For `temp-por-top-release`'s current, post-#259 figures —
239 drawn devices, 0 ideal, 145 nets — see §4 of the closing roll-up below.)

### The IR / cross-domain-coupling question, and why this netlist cannot answer it

[#18](https://github.com/2AMLogic/gf180-temp-por/issues/18) asked this
assembly-level re-run for one thing no per-cell re-run could give: **IR drop
and coupling between the temp-sensor domain and the always-on POR domain**,
across the seam `layout/README.md` describes ("What actually crosses the
seam": `IBIAS`, `RESETn`/`EN`, `VSS` and the POR domain's `VDD` riser, four
Metal3 columns over an unbroken moat). Reporting it as its own finding, as
that issue requires:

**The answer is that this netlist is structurally incapable of showing either,
and that is a property of the extraction flow, not of the layout.**
`klt extract --parasitics` emits, per net, exactly one series resistor into a
synthetic dangling `<net>__par` node and one capacitor from that node to the
substrate (`layout/postlayout.py`'s own `PAR_SUFFIX` comment). Every device
terminal stays on `<net>` itself. Concretely, for the four nets that cross the
seam:

| Net | Parasitic emitted | What it models | What it cannot model |
| --- | --- | --- | --- |
| `IBIAS` | `RIBIAS IBIAS IBIAS__par 10 641.6 Ω` + `CIBIAS IBIAS__par VSS 122.6 fF` | the net's total capacitance, loaded through its total resistance | no R between `bias_core`'s source and `temp_core`'s far-end tap |
| `RESETn` | `REN_RESETn … 5644.1 Ω` + `CEN_RESETn … 78.0 fF` | same | same, for the driver→`temp_core.EN` run |
| `VDD` | `RVDD … 12 215.8 Ω` + `CVDD … 373.9 fF` | rail capacitance | **no rail IR drop**: no DC current can flow through `RVDD`, whose far end feeds only a capacitor |
| `VSS` | `RVSS … 3387.0 Ω` + `CVSS … 1829.3 fF` | ground capacitance | same, for the ground return |

So: **no shared-rail IR drop develops anywhere in this deck by construction,
and there is no net-to-net coupling capacitance at all** — the extraction
produces no capacitor between any two circuit nets, only net-to-substrate
ones. The two effects #18 wanted are precisely the two the model omits. What
the model *does* carry, and carries honestly, is each crossing net's own
**RC loading**, and that is visibly what produces the timing deltas below.

This is a known, already-filed tool limitation, not a new one — the
friction protocol is satisfied by citing it rather than re-filing:
klayout-tools#338 and #592 document the in-path/distributed-resistance gap
(both closed, #592 explicitly deferring the model change), and it is scoped
for repair in the open epics klayout-tools#701 (Method-of-Moments field
solver — "real parasitic extraction (R, C, and coupling)") and #709 (PEX-aware
post-layout sim flow — "Phase 2 — coupling + distributed RC"). **Until one of
those lands, no post-layout record this repo can produce may be cited as
evidence about cross-domain IR or crosstalk**, and none of the records above
is written as if it were.

### What did move: a uniform ~2 % timing slowdown

Every reset-timing quantity in the suite lengthens by about the same 2 %,
which is the signature of a distributed capacitive load on current-starved
ramps rather than of any topology change:

| Quantity | Experiment | Schematic | Extracted | Δ |
| --- | --- | ---: | ---: | ---: |
| `t_release_ms`, grid min (`ff_125c_2.97v`) | `temp-por-top-release` | 5.61461 | 5.72718 | **+2.00 %** |
| `t_release_ms`, grid max (`ss_-40c_3.63v`) | `temp-por-top-release` | 16.9585 | 17.2907 | +1.96 % |
| `t_release_ms`, per-corner spread over all 81 points | `temp-por-top-release` | — | — | +1.85 % … +2.21 % |
| `t_pulse_regen_ms`, grid min (`ff_125c_2.97v`) | `por-brownout` | 4.74296 | 4.88409 | +2.98 % |
| `t_release_1vs_ms` (1 V/s ramp), grid max | `por-ramp-rate` | 2618.42 | 2618.81 | +0.01 % |
| `t_release_1mvs_ms` (1 V/µs ramp), grid min | `por-ramp-rate` | 4.74916 | 4.8921 | +3.01 % |

That figure is consistent with PR #180's own nominal smoke run on this cell
(`t_release_ms` +2.01 % at `tt_27c_3.30v`,
[`layout/postlayout/SMOKE.md`](../layout/postlayout/SMOKE.md)) and with the
+1.9–2.4 % the `por_output_chain` cell-level re-run measured on its own
one-shot ([`por_output_chain.md`](por_output_chain.md) → "Post-layout re-run").
It costs margin nowhere: the release-time guard band is 1–29 ms and the widest
corner is 17.3 ms.

`por-ramp-rate` is where that reads most clearly, because its four branches
span six decades of ramp rate in one deck. On the two **slow** ramps the
release time is set by how long the rail takes to reach threshold, and the
delta is nil (+0.01 % at 1 V/s, +0.11 % at 10 V/s); on the two **fast** ramps
it is set by the one-shot, and the delta is the same ~2–3 % everything else
shows. The one-shot is what the parasitics load, and the record separates the
two mechanisms without being asked to. Nothing costs a corner: all four
branches still release at or above the ratified `VPOR↑,min = 2.47 V`
(`vddrel_1vs_v` 2.573 → 2.573 V at its grid minimum) with zero chatter, so
`spec/target-spec.md#por-ramp-rate` holds post-layout at both ratified
endpoints and both interior decades.

One caveat on reading that experiment's *extremes*, so the tidy ~2 % figure is
not over-sold. The two fast branches' grid **maxima** move much further than
2 %, and in opposite directions — `t_release_100kvs_ms` 16.38 → 21.39 ms
(+31 %, binding corner moving `ss_-40c_3.63v` → `res_ss_-40c_3.63v`) and
`t_release_1mvs_ms` 27.16 → 17.89 ms (−34 %, `sf_-40c_3.63v` →
`fs_-40c_3.63v`). Their **minima** move by the ordinary +2.3 % / +3.0 % and do
not change corner. That signature — a stable minimum, a jumpy maximum, and a
migrating binding corner at the cold slow edge — is
[`bias_core.md`](bias_core.md)'s already-owned starved-loop window, whose
relaxation dynamic is nonlinear near its own critical timing (the same
non-monotonicity `sim/por-brownout-slew/testbench/README.md` documents for the
slew ladder). A 2 % change in loading can move it by tens of percent. Nothing
here breaches a bound — the guard is 1–3600 ms and the row's real criterion,
`vddrel_*`, is untouched — but the maxima in this experiment should be read as
samples of that window, not as a timing claim.


### What did not move: the `por-iq` overrun

[`spec/target-spec.md#por-iq`](../spec/target-spec.md) (<1 µA, RESETn
asserted, rail settled, sensor disabled) fails at **54 of 81 corners** on the
extracted netlist — exactly the same 54 corners, with the same values to four
digits, as on the schematic netlist:

| | Schematic `20260802-205904-bdc077d` | Extracted `20260811-064427-564950b` |
| --- | ---: | ---: |
| `iq_por_ua` grid min | 0.656669 | 0.656367 (**−0.05 %**) |
| `iq_por_ua` grid max | 2.38469 | 2.38347 (−0.05 %) |
| corners over the ratified 1.0 µA | 54 / 81 | 54 / 81 |

This settles a question the pre-layout evidence could not: the overrun is a
**design magnitude problem, not a layout one**. Every per-corner value moves
by −0.04 % to −0.05 %, i.e. the layout is very slightly *cheaper* than the
schematic ideal and nowhere near the 2.4× that would be needed. It is the
already-owned apportionment overrun [`bias_core.md`](bias_core.md) records,
now measured on the real assembled and drawn block. It had no tracking issue
of its own; it does now — see the routing table below.

### The #61 / DR-013 spurious assert: survives, with a smaller footprint

`sim/por-brownout-spurious/` exists to confirm or refute
[#61](https://github.com/2AMLogic/gf180-temp-por/issues/61) /
[DR-013](../spec/decision-records/DR-013-por-brownout-spurious-assert.md)'s
finding — that at *intermediate* falling slew rates `POR_RAW` asserts while the
rail is still inside the ratified operating range, above
`VPOR↑,max = 2.73 V`. #87 was asked to re-check it specifically with real
MOS-side parasitics in the loop. **It survives.** It is also visibly smaller:

| Branch (falling edge) | Corners asserting above 2.73 V, schematic | …extracted | No assert inside the branch window, schematic → extracted |
| --- | ---: | ---: | ---: |
| `b1`, 0.3 ms edge (7.67 mV/µs) | 45 / 81 | **13 / 81** | 5 → 56 |
| `b3`, 1.0 ms edge (2.30 mV/µs — the control's worst) | 79 / 81 | **33 / 81** | 0 → 30 |
| `b6`, 3.0 ms edge (0.77 mV/µs — expected clean) | 20 / 81 | **7 / 81** | 0 → 30 |

The defect is unambiguously still there: on the worst branch, a third of the
grid still asserts `POR_RAW` with the rail above `VPOR↑,max`, peaking at
3.22 V (`res_ss_125c_3.63v`) against a ratified 2.73 V. Nothing about the
extraction refutes DR-013.

**The shrinkage should not be read as an improvement.** The asserts that do
happen happen *later* — `t_praw_b3_us` moves from 56.34–315.83 µs to
155.28–319.36 µs, its grid minimum nearly tripling — which is the same ~2 %
per-decade response slowdown seen everywhere else in this suite, acting on a
measurement window that did not move with it. The record cannot distinguish
"no spurious assert at this corner" from "spurious assert after this branch's
window closed", and 30 of the 56/30/30 new n/a rows are on branches
(`b3`, `b6`) where the schematic run had none at all. Resolving that needs a
longer per-branch window, which is a follow-up rather than something to infer
here. The record's own per-point `ERROR` rows say n/a, and this document does
not upgrade that to "clean".

### Regressions, routed

`sim/README.md` and #87 both require a regression against the schematic-level
record to be routed to an owning issue rather than absorbed. Two were:

| Finding | Where | Routed to |
| --- | --- | --- |
| Falling-slew brownout response degrades: the 3.46 mV/µs rung goes 1/81 → 6/81 failures (all `SS`/`res_ss` at −40 °C), and `por-brownout`'s `ss_-40c_2.97v` stops re-asserting `RESETn` at all inside the 55 ms run (schematic: 51.58 µs) | `por-brownout-slew`, `por-brownout` | [#188](https://github.com/2AMLogic/gf180-temp-por/issues/188) — **closed; see below** |
| `spec/target-spec.md#por-iq` missed at 54/81 corners, unchanged post-layout — previously untracked by any issue | `temp-por-top-release` | [#189](https://github.com/2AMLogic/gf180-temp-por/issues/189) |

Everything else that fails in these records failed identically before the
re-run — `por-glitch` at 0/81 (DR-014 / DR-017's known 300 ns glitch
response, byte-for-byte the same failure set) and `por-brownout` at 0/81
(DR-011's falling-slew root cause) — and is not re-routed here.


### How #188 resolved: one bound moved, one delta re-attributed

Both rows in the table above were routed to #188; it ran the measurements
neither #87 nor this document could, and they came back with different
answers.

**The falling-slew bound really did move, and is re-cost.** #87 re-ran the
one rung `sim/por-brownout-slew/testbench/` happened to carry (3.46 mV/µs);
#188 ran the rung that matters — the ratified bound itself — and then walked
the ladder down. Against this same extracted netlist:

| Rung | Schematic | Extracted |
| ---: | ---: | ---: |
| 2.30 mV/µs ([`20260811-111437-88888f3`](../sim/por-brownout-slew/records/20260811-111437-88888f3.md)) | 81/81 | **81/81** |
| 2.40 mV/µs ([`20260811-111307-0c68175`](../sim/por-brownout-slew/records/20260811-111307-0c68175.md)) | — | **81/81** |
| 2.45 mV/µs ([`20260811-111125-794bf81`](../sim/por-brownout-slew/records/20260811-111125-794bf81.md)) | — | **81/81** |
| 2.50 mV/µs ([`20260811-110956-0aae891`](../sim/por-brownout-slew/records/20260811-110956-0aae891.md)) | — | 80/81 |
| **3.40 mV/µs — the ratified bound** ([`20260811-110825-73ef5e3`](../sim/por-brownout-slew/records/20260811-110825-73ef5e3.md)) | 81/81 | **76/81** |
| 3.46 mV/µs ([`20260811-063855-6d69544`](../sim/por-brownout-slew/records/20260811-063855-6d69544.md), #87) | 80/81 | 75/81 |

The transition edge that sat between 3.44 and 3.46 mV/µs on the schematic
export sits between **2.45 and 2.50 mV/µs** on the extracted one, and
`spec/target-spec.md#por-brownout` clause (c) is re-cost from 3.40 to
**2.30 mV/µs** by
[DR-019](../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md).

This is the same ~2 % loading story the section above tells, seen where the
circuit has no margin to absorb it. The mechanism is `bias_core.md`'s
starved-loop window, measured on its own state variable at the binding
`ss`/−40 °C family
([`sim/por-brownout-slew/control/postlayout_margin_results.md`](../sim/por-brownout-slew/control/postlayout_margin_results.md)):
at 3.40 mV/µs the extraction takes min `V_sg` from −116.1 mV to **−297.5 mV**
(3.63 V) and `por_output_chain`'s deglitch ramp never starts at all (peak
`NDG`/VDD 0.706 → **0.000**), so `POR_RAW` rides the rail for the whole dip —
DR-011's *no decision* mode rather than a late one. Below the bound both arms
pass and the extraction costs a roughly constant −140 to −180 µs of dip-window
margin, with `POR_RAW` asserting ~68 µs → ~145 µs after the dip starts. Which
nets' parasitics carry that is **not** established: `PG`'s own extracted
`R_6`/`C_6` pair is 5.08 kΩ and 68.1 fF against DR-011's ≈1.25 pF estimate for
that node, ~5 %, so a single-net explanation does not close a 28 % boundary
shift and a per-net attribution is left to
[#214](https://github.com/2AMLogic/gf180-temp-por/issues/214).

**The `por-brownout` delta was not the extraction's at all.** That row's two
moved numbers were read against `20260801-233807-32fbaa0`, whose own frozen
snapshot differs from today's schematic netlist by exactly one device —
`XMRLK`, the release latch [DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md)
added on 2026-08-02, after that record and before this layout. So the
comparison spanned two changes. Re-running the schematic grid on today's
netlist ([`20260811-112115-9807e3f`](../sim/por-brownout/records/20260811-112115-9807e3f.md))
gives the like-for-like baseline:

| | `t_reassert_us` | corners that never re-assert |
| --- | ---: | ---: |
| schematic, pre-`XMRLK` (`20260801-233807-32fbaa0`) | 51.26–51.58 µs | 0 / 81 |
| schematic, today (`20260811-112115-9807e3f`) | 52.01–66.24 µs | **8 / 81** |
| extracted (`20260811-065930-35a87a6`) | 51.67–64.25 µs | 1 / 81 |

Against that baseline the extraction **improves** both numbers — it recovers
the re-assert at 7 of the 8 lost corners and takes the worst case from
66.24 µs back to 51.93 µs. A three-arm control
([`sim/por-brownout/control/recovery_results.md`](../sim/por-brownout/control/recovery_results.md))
runs the frozen pre-`XMRLK` deck beside both of today's and makes the
attribution causal rather than chronological: `POR_RAW` still asserts on the
recovery edge in every arm, so what a lost re-assert loses is *propagation* —
which is what a one-way release latch is for — not the decision. The
`por-brownout` row of the verdict table above should therefore be read as
"0/81 → 0/81, with an incidental recovery-edge number that belongs to
`XMRLK`", not as a post-layout regression. All of it sits ~580× outside this
row's guaranteed falling-slew envelope either way (the deck's edge is
~1970 mV/µs); what needs narrowing is DR-011's "the block recovers; it does
not latch up or stay released", which is
[#215](https://github.com/2AMLogic/gf180-temp-por/issues/215), not a claim
this document can repair.


### `sim/por-iq/` is now re-derived post-layout — update: #83 landed, the row was re-costed, and #207 minted the record

`sim/por-iq/analyze_por_iq.py` publishes `spec/target-spec.md#por-iq` and
`#iq-total` by reducing **`sim/temp-accuracy-vt/`'s** raw per-point logs, not
this suite's. That experiment belonged to the temp-sensing domain re-run
(#83), which had no post-layout record at the time this section was first
written. **#83 has since merged** (PR #198,
[`sim/temp-accuracy-vt/records/20260811-084152-68c0017.md`](../sim/temp-accuracy-vt/records/20260811-084152-68c0017.md),
per [`temp_core.md`](temp_core.md) → "Post-layout re-run"): same 54/81 miss
against the then-ratified 1.0 µA ceiling, values within 0.05 % of the
schematic reading, confirming (not merely corroborating from this document's
`temp-por-top-release` column above) that the overrun is design-magnitude,
not layout. `spec/target-spec.md#por-iq`'s <1 µA target has since been
re-costed to **<3.0 µA** by
[DR-018](../spec/decision-records/DR-018-por-iq-recost.md) (issue #189,
closed) against exactly this measured apportionment — **81/81 PASS on both
netlist levels** against the re-costed ceiling.

**#207 closed the remaining publication gap.** `sim/por-iq/analyze_por_iq.py`
itself still checked the withdrawn <1 µA ceiling (a stale constant, not a
new finding — it predated DR-018), and `sim/por-iq/`'s own newest record was
still the schematic-level one from before the layout re-run. Both are fixed:
the script's `TARGET_POR_IQ_UA` now reads <3.0 µA (citing DR-018 inline), and
running it against `sim/temp-accuracy-vt/`'s post-layout record minted
[`sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md`](../sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md)
— **81/81 PASS** on both rows against the currently-ratified ceilings
(`por-iq` <3.0 µA [DR-018], `iq-total` <21 µA), same 0.656367–2.383469 µA
range already cited above. `sim/por-iq/` is no longer the one experiment
directory in `sim/` whose newest record is schematic-sourced. See "Closing
roll-up for issue #18" below for how this fits the tracking issue's overall
verdict.

## Closing roll-up for issue #18: post-layout extracted re-run of the full verification suite

[#18](https://github.com/2AMLogic/gf180-temp-por/issues/18) is the tracking
issue for re-running the entire pre-layout verification suite (temp-sensing
#13, POR #14, Monte Carlo #15) against the DRC/LVS-clean, parasitic-extracted
layout instead of the schematic netlist. Its six re-run dependencies —
#82 (the extraction bridge itself), #83 (temp-sensing, `temp_core.md`), #84
(bias/reference core, `bias_core.md`), #85 (POR comparator/threshold,
`por_comparator.md`), #86 (POR output chain, `por_output_chain.md`), and #87
(full-assembly POR dynamic behaviour, this document, above) — are all closed
and merged. This section is the roll-up #18's own acceptance criteria ask
for, and it does not relax that criteria: **the suite is not fully green on
the extracted netlist**, and this roll-up says so rather than rounding up.

### 1. The IR-drop / crosstalk watch item cannot be answered by this repo's tooling today

This is the most consequential thing this roll-up has to state, so it is
stated first and without qualification: **no post-layout record this repo
can produce may be cited as cross-domain IR-drop or crosstalk evidence.**
`klt extract --parasitics` emits, per net, exactly one series resistor into a
synthetic dangling `<net>__par` node and one capacitor from that node to
substrate (see "The IR / cross-domain-coupling question" above for the exact
cards on the four seam-crossing nets, `IBIAS`/`RESETn`/`VDD`/`VSS`). There is
no DC path through any `R<net>` — its far end feeds only a capacitor — so no
rail can develop IR drop in this deck by construction, and there is no
capacitor between any two circuit nets at all, so no net-to-net coupling term
is representable either. This is a property of the extraction model, not of
the layout: klayout-tools#338/#592 document and close the gap partway
(deferring the model change), and klayout-tools#701 (a Method-of-Moments
field solver) and #709 (a PEX-aware post-layout sim flow, "Phase 2 —
coupling + distributed RC") are the open epics that would eventually let a
future re-run answer this. Until one of those lands, a clean-looking
post-layout suite on this axis means "not tested," not "tested and passed" —
and every record in this repo, including this one, is written on that basis.

### 2. The one substantive, consistent finding: ~2 % uniform reset-timing lengthening

Every reset-timing quantity measured across all six children lengthens by
about the same 2 % post-layout — `t_release_ms` +1.96…+2.00 % across its grid
extremes, `t_pulse_regen_ms` +2.98 %, the one-shot pulse width
(`por_output_chain.md`) +1.88…+2.40 %, `por-ramp-rate`'s fast-branch minima
+2.3…+3.0 %. It is the signature of a distributed RC load on a current-starved
ramp, not a topology change, and it is consistent across cells, testbenches,
and both the cell-level and full-assembly netlists. It costs no ratified
corner anywhere in the suite (worst case, `temp-por-top-release`'s release
guard band is 1–29 ms against a 17.3 ms extracted maximum) — except at one
already-tight design margin, `por_output_chain`'s deglitch dwell floor, where
the *same* parasitic loading moves the qualifying-dip dwell in the *other*
direction (−28…−36 % at some corners, not +2 %): a real, if still-passing,
erosion of headroom against a floor this design already treats as tight,
diagnosed by #182 and tracked forward by #199/#200 rather than by this issue.

### 3. #61 / DR-013's spurious `POR_RAW` assert survives with real MOS-side parasitics

`sim/por-brownout-spurious/` (#87) re-checked
[#61](https://github.com/2AMLogic/gf180-temp-por/issues/61) /
[DR-013](../spec/decision-records/DR-013-por-brownout-spurious-assert.md)'s
finding — that at intermediate falling slew rates, `POR_RAW` asserts while
the rail is still above `VPOR↑,max = 2.73 V` — with real MOS-side parasitics
in the loop instead of the schematic ideal. **It survives.** On the worst
branch (`b3`, the 1.0 ms / 2.30 mV/µs edge), 33 of 81 corners still assert
above 2.73 V post-layout, peaking at 3.22 V. The footprint on all three
checked branches shrinks relative to the schematic record (79→33, 45→13,
20→7), but the asserts that remain also arrive later
(`t_praw_b3_us`'s grid minimum roughly triples), consistent with the same 2 %
per-decade slowdown from point 2 acting on a fixed measurement window — **the
shrinkage is not evidence of a fix**, and nothing about this re-run refutes
DR-013.

### 4. `temp_core`'s `XCC` is drawn (#259) — #270 re-ran every record whose claim depended on it

`layout/postlayout/AUDIT.md` reports **zero** ideal (undrawn) devices across
all five cells (`bias_core`, `por_comparator`, `por_output_chain`,
`temp_core`, `temp_por_top`). Until #259, `temp_core`'s `XCC` — the 12 × 12
µm MiM compensation cap on `PG`/`NZ` (instance `xtemp`'s
`xtemp__PG`/`xtemp__NZ` in the assembly) — was the one device this whole
five-cell suite still spliced in ideal, reserved floor area tracked as #177.
It is now drawn and routed
([DR-028](../spec/decision-records/DR-028-temp-core-xcc-draw-it.md)). Every
other device in the suite — all MOS, all 19 bipolars, all 77 resistors, and
the 8 MiM caps — was already drawn, extracted, and LVS-matched before #259;
no node in any of the five cells carries an ideal-device caveat today.

`XCC` sits in the amplifier's compensation path, so every record whose claim
turns on the loop's stability margin or the shape of its settling transient
carried a "schematic claim, not a post-layout one" caveat on that specific
point, independent of whatever else it established. Ten experiments in this
suite instantiate `temp_core` (directly, or as `xtemp` inside the assembly)
and therefore inherited that caveat:

| Experiment | Touches `temp_core`'s compensation pole? | Re-run by #270 against the drawn `XCC`? |
| --- | --- | --- |
| [`temp-core-designer-check`](../sim/temp-core-designer-check/) | Yes — the cell's own DC/transient operating point | **Yes** — [`20260819-172959-fd167d8`](../sim/temp-core-designer-check/records/20260819-172959-fd167d8.md) |
| [`temp-core-startup`](../sim/temp-core-startup/) | Yes — cold-start settling (`start_us`) | **Yes** — [`20260819-170120-47d2f2a`](../sim/temp-core-startup/records/20260819-170120-47d2f2a.md) |
| [`temp-accuracy-vt`](../sim/temp-accuracy-vt/) | Yes — assembled V(T) transfer | **Yes** — [`20260819-173345-2a37d6c`](../sim/temp-accuracy-vt/records/20260819-173345-2a37d6c.md) |
| [`temp-accuracy-mc`](../sim/temp-accuracy-mc/) | Yes — Monte Carlo mismatch on the settled point | **Yes** — [`20260819-171829-b403a17`](../sim/temp-accuracy-mc/records/20260819-171829-b403a17.md) |
| [`temp-por-top-release`](../sim/temp-por-top-release/) | Yes — full-assembly startup ordering, which includes `temp_core` settling | **Yes** — [`20260819-173152-e58ed1a`](../sim/temp-por-top-release/records/20260819-173152-e58ed1a.md) |
| `por-ramp-rate`, `por-brownout`, `por-brownout-slew`, `por-brownout-spurious`, `por-glitch` | No — POR ramp/brownout/glitch dynamics, not the sensing amplifier's loop | Not re-run — out of #270's scope; each experiment's existing record (table above) remains accurate for the netlist it was actually taken against |

All five re-run records supersede their pre-#259 extracted predecessors, are
taken against a clean working tree (no dirty-tree citation caveat), and each
is paired with a `<record-id>-postlayout-delta` derived record (or, for
`temp-accuracy-mc`, its `-breakdown` companion) re-evaluated against the same
schematic baseline #83/#87 used: **zero regressions** across all five. See
[`temp_core.md`](temp_core.md) → "Post-layout re-run (issue #83)" → "Loop
stability" for the full account of what that establishes and does not. In
short: the closed-loop *transient* behaviour these five testbenches
measure — settling time, freedom from a non-converging state, the settled
operating point, and (for `temp-por-top-release`) the assembled-block
ordering that depends on `temp_core` settling — is now measured through the
real drawn compensation cap, and it is unchanged from both the schematic and
the pre-#259 extracted result. A *quantified* small-signal stability margin
(phase margin, gain margin) was a testbench-coverage gap #270 could not close
by re-running existing decks — the gap was that no testbench in this suite,
extracted or schematic, had ever measured one at all. [#274](https://github.com/2AMLogic/gf180-temp-por/issues/274)
has since closed that gap:
[`sim/temp-core-loop-stability/`](../sim/temp-core-loop-stability/), record
[`20260819-182610-a4eebe7`](../sim/temp-core-loop-stability/records/20260819-182610-a4eebe7.md),
is this repo's first small-signal `.ac` loop-gain testbench, and across the
full 81-point PVT grid it measured phase margin from 34.2°
(`ff_-40c_2.97v`) to 47.1° (`ss_27c_3.63v`) and gain margin from 4.43 dB
(`res_ss_-40c_3.63v`) to 7.50 dB (`res_ff_125c_2.97v`). This is a
**schematic-level** record only (against `design/netlist/temp_core.spice`,
which already carries #259/DR-028's real drawn `XCC`) — a post-layout
re-run of this specific `.ac` testbench against the extracted netlist has
not been done, so that remains a disclosed, open gap. No
`spec/target-spec.md` bound was added: since no transient or AC record shows
evidence of an actual instability problem, promoting a specific phase/gain
margin requirement is left as a separate, deliberate decision for whenever
one is actually needed. See [`temp_core.md`](temp_core.md) → "Loop
stability" for the full account.

### Regressions and follow-ups, routed rather than absorbed

Per #18's own acceptance criteria ("any spec line that ... fails extracted
re-opens the corresponding design issue — the spec does not get relaxed to
pass") and `sim/README.md`'s append-only convention, every post-layout
regression or new finding from #83-#87 was routed to its own issue instead of
being resolved or absorbed inside the re-run issues themselves:

| Finding | Source | Issue | Status |
| --- | --- | --- | --- |
| `por-iq` missed at 54/81 corners — confirmed design-magnitude, not layout, on both netlist levels | #87 (this document) | [#189](https://github.com/2AMLogic/gf180-temp-por/issues/189) | **Closed** — resolved by [DR-018](../spec/decision-records/DR-018-por-iq-recost.md), re-costing the ceiling to <3.0 µA against measured apportionment; 81/81 PASS post-layout |
| Falling-slew brownout response degrades (3.46 mV/µs rung 1→6 failures; one corner stops re-asserting `RESETn`) | #87 | [#188](https://github.com/2AMLogic/gf180-temp-por/issues/188) | **Closed** — resolved by [DR-019](../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md), re-costing `por-brownout` clause (c) to 2.30 mV/µs; 81/81 PASS on both netlist levels |
| `bias-core-designer-check` / `bias-core-startup` regress: post-brownout `VREF` reproducibility and `BIAS_OK` droop/dip push past their bounds at several cold/fast-process corners | #84 (`bias_core.md`) | [#185](https://github.com/2AMLogic/gf180-temp-por/issues/185) | **Closed** — resolved by #222: three of the four flagged symptoms were the 2 ms deck integrating a longer-than-2-ms post-layout recovery window (a measurement artifact, not a design regression); the fourth is a genuine but already-understood cell property. Deck lengthened to 30 ms and restructured so it cannot score an impossible negative recovery as a PASS; no ratified bound moved, no `spec/decision-records/` entry (deliberately — nothing ratified changed) |
| `por-hysteresis` fails the 250 mV ceiling at the single worst full-assembly corner (`ss_-40c_3.63v`, 261.09 mV) | #85 (`por_comparator.md`) | [#187](https://github.com/2AMLogic/gf180-temp-por/issues/187) | **Closed** — root-caused by #218/[DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md): the 261.09 mV reading decomposes into 143.3 mV static hysteresis (unmoved), a ramp-rate-induced `VREF` displacement, and comparator/output-chain delay — the deck's fixed-duration ramp confounded supply level with `dVDD/dt`. `por-hysteresis` is scoped as the quasi-static value; no ratified bound moved. The confounded deck itself was then fixed by #206 (constant-`dVDD/dt` stimulus), and `spec/target-spec.md#por-hysteresis` now cites a re-cut record that is **81/81 PASS on both netlist levels**, the `ss_-40c_3.63v` point reading 215.655 mV — 34.3 mV inside the ceiling |
| Deglitch dwell's qualifying-dip floor has visibly less headroom post-layout than the schematic ever measured (root-caused, no ratified check fails) | #86 (`por_output_chain.md`, #182) | [#199](https://github.com/2AMLogic/gf180-temp-por/issues/199), [#200](https://github.com/2AMLogic/gf180-temp-por/issues/200) | **Closed** — #199 concluded (per [DR-020](../spec/decision-records/DR-020-por-raw-chatter-width-out-of-reach.md)) that no existing full-assembly deck contains a real-world `POR_RAW` excursion-width measurement to reprocess, and routed the open question to #1 rather than manufacturing a stimulus-model judgment unilaterally; #200 promoted the glitch-rejection *width margin* itself onto the full 81-point PVT grid at both netlist levels (schematic and extracted), **81/81 PASS**, no charge loss at any corner. `spec/target-spec.md` untouched by either issue |
| `sim/por-iq/`'s publishing script still checks the withdrawn <1 µA ceiling, and its post-layout re-derivation is unblocked now that #83 has landed | #18 (this roll-up) | [#207](https://github.com/2AMLogic/gf180-temp-por/issues/207) | **Closed** — script now checks the DR-018-recosted <3.0 µA ceiling, and `sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md` is the post-layout-derived record, 81/81 PASS on both rows |
| Three of this set's extracted records — and two of the schematic baselines they are compared against — are stamped "not citable as a clean-tree result" | #18 (this roll-up) | [#209](https://github.com/2AMLogic/gf180-temp-por/issues/209) | **Closed** — `sim/README.md` states the citation policy and `sim/tests/test_stamped_record_citations.py` enforces it; clean-tree successors now exist for all three sole-evidence extracted records (`bias-core-designer-check`, `bias-core-startup`, `por-output-chain-floor`, re-cited in `design/bias_core.md` / `design/por_output_chain.md`); the `por-brownout-slew` schematic baseline is caveated explicitly above rather than re-run (full-assembly transient, not a cheap per-cell deck) |
| `spec/target-spec.md#area`'s measured post-layout number was never recorded; the drawn assembly measures ~1.06 mm² against a ≤0.05 mm² planning bound | #18 (this roll-up) | [#211](https://github.com/2AMLogic/gf180-temp-por/issues/211) | **Closed** — resolved by [DR-022](../spec/decision-records/DR-022-area-post-layout-measurement.md), recording the measured 1.059 mm² footprint and the planning bound as not met (21.2× over); evidence wired into `layout/run_checks.sh` as regenerable `layout/reports/<cell>/stats.json` |

Everything else that fails on the extracted netlist failed identically
before the re-run (`por-brownout` at 0/81 per DR-011's falling-slew root
cause, `por-glitch` at 0/81 per DR-014/DR-017's known glitch response) and is
not re-routed here — the extraction confirms, rather than changes, those
already-owned findings.

### 5. Suite coverage: what "the full suite" actually means here

#18 asks for the *full* suite, so the accounting of what was and was not
re-run belongs in the roll-up rather than being left implicit.

`sim/` holds **20 experiment directories carrying a `testbench/tb.json`** —
the corner/Monte-Carlo runner's unit of work. **19 of the 20 now also carry a
`testbench-postlayout/` sibling and at least one record whose `Netlist
provenance` field reads `extracted (…)`**, against one of the five netlists in
`layout/postlayout/`. The complete set, and the document that interprets each,
is:

| Domain | Experiments re-run against the extracted netlist | Interpreted in |
| --- | --- | --- |
| Temp sensing (#83) | `temp-core-designer-check`, `temp-core-startup`, `temp-accuracy-vt`, `temp-accuracy-mc` | [`temp_core.md`](temp_core.md) → "Post-layout re-run (issue #83)" |
| Bias / reference core (#84) | `bias-core-designer-check`, `bias-core-startup`, `bias-core-ibias-sharing` | [`bias_core.md`](bias_core.md) → "Post-layout re-run (issue #84)" |
| POR comparator / threshold (#85) | `por-comparator-designer-check`, `por-threshold-mc`, `por-vth` | [`por_comparator.md`](por_comparator.md) → "Post-layout re-run (issue #85)" |
| POR output chain (#86, #182) | `por-output-chain-pulse`, `por-output-chain-deglitch`, `por-output-chain-floor` | [`por_output_chain.md`](por_output_chain.md) → "Post-layout re-run (issue #86)" and "Root cause of the deglitch asymmetry" |
| Full-assembly POR dynamics (#87) | `por-ramp-rate`, `por-brownout`, `por-brownout-slew`, `por-brownout-spurious`, `por-glitch`, `temp-por-top-release` | this document, above |

The one experiment with **no** post-layout re-run is `sim/smoke-bias/`, and
that is correct rather than an omission: its own `tb.json` claim field reads
"None — harness self-verification, not a spec claim", and its DUT is a
synthetic acceptance deck (ideal divider + a PDK poly-R/nfet bias leg + a
diode-connected vertical PNP) that exists nowhere in the layout. There is no
geometry to extract, so a post-layout re-run of it would not mean anything.

Two further directories sit outside the runner's discovery and so outside the
table above. `sim/devchar/` is the grandfathered pre-harness device
characterization `sim/README.md` explicitly leaves as-is. `sim/por-iq/` is a
*derivation* with no testbench of its own — it reduces
`sim/temp-accuracy-vt/`'s raw per-point logs. At the time this roll-up was
first written it was **the one experiment directory in `sim/` whose newest
record was still schematic-sourced after this whole re-run** — a publication
gap rather than an evidence gap (`por-iq`'s post-layout number was already
recorded in `temp-por-top-release`'s extracted record and cited from the
spec row), routed to #207 along
with the withdrawn-<1 µA ceiling that directory's script then still checked.
**#207 has since closed that gap**: the script checks the DR-018-recosted
<3.0 µA ceiling, and `sim/por-iq/`'s newest record,
[`20260811-084152-68c0017-por-iq-derived.md`](../sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md),
is now post-layout-derived — see "`sim/por-iq/` is now re-derived
post-layout" above.

**On the spec table itself**: only two rows of `spec/target-spec.md` cite
post-layout evidence in their own text today —
[`por-hysteresis`](../spec/target-spec.md#por-hysteresis) (pointing at #187)
and [`por-iq`](../spec/target-spec.md#por-iq) (via DR-018 and #87). Every other
row still names only its schematic-level record. Annotating each row
individually is deliberately *not* attempted here: one roll-up a reader can
check against [`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md) and
the record index above is more auditable than two dozen hand-edited per-row
provenance notes that would then drift independently. The two rows that do
carry a post-layout citation carry it because something *changed* there — a
routed regression and a re-cost — which is the case the spec table needs to
surface.

There was one exception worth naming separately, because it was a row the
post-layout gate was specifically supposed to close and, at the time this
roll-up was first written, had not: [`area`](../spec/target-spec.md#area)
read `[TBD-#17]` with a `≤0.05 mm²` planning bound whose own note said it was
"a planning bound to be replaced by the measured post-layout number," and
that measured number was recorded nowhere in this repository even though the
layout was drawn, assembled and #17 was closed. **#211 has since closed that
gap**: `klt stats` is now wired into `layout/run_checks.sh` as a regenerable
step for every cell, recorded at `layout/reports/<cell>/stats.json`, and
[DR-022](../spec/decision-records/DR-022-area-post-layout-measurement.md)
ratifies which of the three defensible area conventions the row means (the
assembled top cell's own bounding-box footprint) and records the result:
**1334 × 794 µm = 1.059 mm²**, ~21× the ≤0.05 mm² planning bound (the sum of
the four sub-cells' own boxes, 0.342 mm², is ~7× it) — consistent with the
poly-ladder area [`layout/floorplan.md`](../layout/floorplan.md) already
predicted would consume "essentially the whole block's ≤0.05 mm² wave-1
planning budget" on its own. The planning bound is retained, unchanged, and
recorded as **not met** rather than deleted or silently relaxed; no circuit
or layout change resulted from settling this.

### 6. Provenance: five records in this set were stamped "not citable as a clean-tree result" — audited and resolved by #209

`sim/harness/report.py` appends `— **taken against a dirty working tree** at
commit <sha>; not citable as a clean-tree result` to a record's `Netlist
provenance` field when the run was taken against uncommitted work. Auditing
that field across every record in `sim/*/records/` (as first done when this
roll-up was written) put five of the post-layout set in that category, and —
the part that propagates — two of the **schematic baselines** the
post-layout records are compared against:

- **Sole post-layout evidence for their experiment, stamped**:
  `bias-core-designer-check`'s `20260811-063744-5ff219c`,
  `bias-core-startup`'s `20260811-062115-5ff219c`, and
  `por-output-chain-floor`'s `20260811-055424-d0ee17d`. The first two were
  #185's entire post-layout evidence base.
- **Stamped but already superseded by a clean-tree record**:
  `por-output-chain-deglitch`'s `20260811-055634-d0ee17d` and
  `20260811-094940-4249351`, both superseded by the clean-tree
  `20260811-095259-865cea8` that the #182 section of
  [`por_output_chain.md`](por_output_chain.md) cites.
- **Stamped schematic baselines**: `por-brownout-slew`'s
  `20260802-134958-dd0cd60` — the baseline behind this document's own
  `por-brownout-slew` row above — and `temp-core-designer-check`'s
  `20260801-073732-8b7e57f`, whose comparison is benign (216/216 at both
  ends).

A delta is only as citable as the weaker of its two ends, so this bounded how
some of this suite's numbers could be quoted: the *direction* of every
finding stood regardless, and the qualitative changes (a corner that stops
re-asserting `RESETn` at all, a check that crosses a ratified ceiling) were
never in question, but a handful of precise deltas rested on a record the
harness itself marked non-citable. `sim/` is append-only, so none of this was
fixable in place.

**Resolved by [#209](https://github.com/2AMLogic/gf180-temp-por/issues/209).**
`sim/README.md` now states the citation policy the previous paragraph was
missing (§ "Citing a 'taken against a dirty working tree' record"). All three
sole-evidence decks are per-cell, cheap re-runs — `bias-core-designer-check`,
`bias-core-startup` and `por-output-chain-floor` were each re-run on a clean
tree, reproduced their stamped predecessor's numbers exactly, and are now the
records `design/bias_core.md` and `design/por_output_chain.md` cite.
`por-output-chain-deglitch` already had its clean-tree successor
(`20260811-095259-865cea8`); `design/por_output_chain.md`'s post-layout table
now cites it directly instead of the stamped `…-055634-…`. The two schematic
baselines are full-assembly / designer-check decks rather than cheap per-cell
ones, so neither was re-run purely to clear the stamp: `por-brownout-slew`'s
`…-dd0cd60` is caveated explicitly at its one citation site (above); DR-019's
own falling-slew re-cost does not depend on it, having been measured fresh
against a clean tree. `temp-core-designer-check`'s `…-8b7e57f` is cited only
for the qualitative "unchanged" finding in `design/temp_core.md`, which the
citation policy permits without a caveat.

**And the policy is enforced rather than merely written down**, because this
recurred while #209 was open: PR #222 (issue #185) minted two more stamped
records on the replacement 30 ms `bias-core-designer-check` deck —
`20260811-114539-9fcede8` (extracted) and `20260811-114349-9fcede8`
(schematic) — and cited them in `design/bias_core.md` with no caveat. That
deck is a 30 ms × 81-point transient rather than a cheap per-cell one, so
those two are caveated at the citation site rather than re-run, and
`sim/tests/test_stamped_record_citations.py` now fails CI on any
`design/*.md` section that cites a stamped record without naming the caveat.

### Verdict: #18 closes now

**#18 closes with this roll-up, rather than staying open as a living
tracking issue pending #185/#187/#188/#199/#200/#207/#209/#211.** The literal
wording of #18's acceptance criteria ("full suite green ... across all PVT
corners") is not met, and this roll-up does not pretend otherwise — seven
issues in the table above remain open. But #18's own text also says a regression "re-opens the
corresponding design issue," not "keeps #18 open," and that mechanism is what
this suite's own history shows working: #82 closed without waiting on
#83-#87; #67 (the layout decomposition) closed once its five sub-issues
landed rather than staying open through every follow-on layout defect; and
#189, filed by this exact re-run, has already gone from open to closed via a
normal decision-record cycle while #18 itself sat `loom:curated` waiting for
a Builder. Holding #18 open until every downstream regression clears would
make it a second, informal tracking mechanism duplicating what the issue
tracker and `sim/README.md`'s regression-routing convention already do, with
no added signal — a reader wanting the current state of any one regression
should read that regression's own issue, not this one.

What #18 close *does* certify, and only this: the parasitic-extracted netlist
exists for all five cells and the assembly (#82), every testbench in the
pre-layout suite that has a DUT in the layout at all has been re-run against
it at least once (#83-#87; the one exclusion and why it is correct is point 5),
every regression and gap found in doing so has an owning issue (table above),
and the three watch items #18's own body named explicitly have each been
reported rather than silently rounded to "clean" — the sensing core's
high-impedance-node loading (per-node ΣC/ΣR reported in `temp_core.md`'s
"Parasitic loading on the high-impedance nodes"; too small by two-to-six
orders of magnitude to move any spec row), the ~2 % reset-timing lengthening
this loading and `por_output_chain`'s own timing capacitors produce (point 2),
and cross-domain IR/coupling, which this repo's extraction model cannot show
at all (point 1).

What it explicitly does **not** certify: that the block is post-layout-*clean*
(it is not — see the routing table), that any ratified row's verdict has been
upgraded on post-layout evidence (none has; three rows carry a post-layout
citation and two of those carry it because something got worse), or that the
extraction model used here is a substitute for real PEX (point 1). The
maturity-ladder wording in [`README.md`](../README.md) § Status is written to
those limits.
