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
| [`temp-por-top-release`](../sim/temp-por-top-release/) | [`20260811-064427-564950b`](../sim/temp-por-top-release/records/20260811-064427-564950b.md) | `20260802-205904-bdc077d` | 27/81 PASS → 27/81 PASS (identical failure set) |

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

### What "extracted" means for this assembly

Per [`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md)'s
`temp_por_top` row: **238 drawn devices, 1 ideal.** The single ideal device is
`temp_core`'s `XCC` MiM cap (here instance `xtemp`'s, on `xtemp__PG` /
`xtemp__NZ`), which that cell's layout does not draw yet — reserved floor
area, tracked as #177. Every other device in the assembly, including all 19
bipolars, all 77 resistors and the other 7 MiM caps, is drawn and extracted.
136 of 159 nets carry first-order interconnect R/C across 272 parasitic cards
(ΣR 280 923 Ω, ΣC 5880.2 fF); the 23 without are isolated well/plate nets and
the substrate global, and those are tied where the *schematic* puts them
because the extraction deck's connectivity stack does not reach them. Two deck
substitutions are undone on the way out (27 `ppolyf_u_1k` → `ppolyf_u_3k`,
klayout-tools#323; 7 `cap_mim_2f0_m4m5_noshield` →
`cap_mim_2f0_m3m4_noshield`, klayout-tools#315) — the drawn geometry is the
schematic's in both cases, only the deck's name for it differs.

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
| Falling-slew brownout response degrades: the 3.46 mV/µs rung goes 1/81 → 6/81 failures (all `SS`/`res_ss` at −40 °C), and `por-brownout`'s `ss_-40c_2.97v` stops re-asserting `RESETn` at all inside the 55 ms run (schematic: 51.58 µs) | `por-brownout-slew`, `por-brownout` | [#188](https://github.com/2AMLogic/gf180-temp-por/issues/188) |
| `spec/target-spec.md#por-iq` missed at 54/81 corners, unchanged post-layout — previously untracked by any issue | `temp-por-top-release` | [#189](https://github.com/2AMLogic/gf180-temp-por/issues/189) |

Everything else that fails in these records failed identically before the
re-run — `por-glitch` at 0/81 (DR-014 / DR-017's known 300 ns glitch
response, byte-for-byte the same failure set) and `por-brownout` at 0/81
(DR-011's falling-slew root cause) — and is not re-routed here.


### `sim/por-iq/` is not re-derived here

`sim/por-iq/analyze_por_iq.py` publishes `spec/target-spec.md#por-iq` and
`#iq-total` by reducing **`sim/temp-accuracy-vt/`'s** raw per-point logs, not
this suite's. That experiment belongs to the temp-sensing domain re-run
(#83), which has no post-layout record yet, so the `por-iq` derivation stays
on the schematic-level source record until #83 lands. The `iq_por_ua` column
of `sim/temp-por-top-release/`'s own extracted record above is the
post-layout number for that row in the meantime; it is measured in the same
state (target-spec.md §5 rule 1) on the same assembled path.
