# `layout/floorplan.md` — floorplan sketch + matching plan

Issue #9's PNP array and PTAT resistor ratio, issue #10's comparator input
pair and sense divider, guard-ring/isolation between the always-on POR domain
and the temp-sensor domain, and pin placement per the ratified pinout — all
floorplanned to #15's Monte Carlo mismatch breakdown, per issue #17.

> **Status: this is a floorplan sketch and matching plan, not polygons.** It
> is a planning deliverable — the block's actual layout is drawn later,
> against the `klt`-driven flow #16 proved and #18's post-layout re-run
> checks. Nothing here has been through `klt drc` / `klt lvs`; correctness at
> this stage is judged by design review against #15's measured mismatch data
> and the schematics' own flagged matching notes, per this issue's Test Plan.

## Why this document is organized the way it is

#15's per-parameter attribution
([`sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md))
measured, in °C of σ against the ratified ±3 °C untrimmed window, which
mismatched device pair actually costs how much:

| Rank | Term | σ (worst binding point) | 3σ vs. its own budget | Removed by the 25 °C gain trim? |
| --- | --- | --- | --- | --- |
| 1 | Amplifier input pair + load mirror offset (`XMI1`/`XMI2`, `XML1`/`XML2`) | 5.71 °C | 3.07 mV vs. 0.46 mV budget — **6.7× over** | **No** — only its lever arm shortens |
| 2 | Gain/mirror ratio (`XR1` vs. `XR2*` ladder, plus `XMP1`/`XMP2`/`XMP3`) | 2.44 °C | 3σ = 7.32 °C | Yes |
| 3 | PNP pair Δ`V_BE` (`XQ1` vs. `XQ8A..H`) | 1.11 °C | 3σ = 3.32 °C | Yes |

The companion POR-side record
([`sim/por-threshold-mc/records/20260802-083749-3b9b414.md`](../sim/por-threshold-mc/records/20260802-083749-3b9b414.md))
measured the opposite outcome: `vth-rise`, `vth-fall`, `v_hys` all **PASS at
100 % empirical yield** with comfortable margin at every binding point, even
though the comparator's own input-referred offset (`comp_offs_rise_mv` /
`comp_offs_fall_mv`) runs σ ≈ 5.5–6.6 mV — informative-only in that record
because the ratio-feedback hysteresis scheme absorbs it (see
[`design/por_comparator.md` § "Why the hysteresis is a resistor ratio"](../design/por_comparator.md)).

Everything below floorplans to that ranking: highest layout effort on rank 1,
proportionately less on ranks 2–3, and an explicit, cited rationale — not
silence — for why the comparator side gets standard practice rather than
common-centroid treatment.

## Block-level floorplan sketch

Two domains, guard-ring separated, per `design/README.md`'s own framing of which
sub-circuits are always-on vs. gated:

- **Always-on POR domain** — `bias_core` (no enable pin, no off state —
  `design/bias_core.md` § "always-on"), `por_comparator`, `por_output_chain`.
  These three are live from the moment `VDD` ramps and make the precision
  threshold decision; `por_output_chain`'s ungated `XMBD` is what defines the
  shared `IBIAS` node's operating point per
  [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md),
  so nothing in this domain may be switched off by floorplanning either.
- **Temp-sensor domain** — `temp_core` alone. Gated by `EN` = `RESETn`
  (`design/temp_core.md` § "Enable: gated by POR"): disabled until POR
  releases, and its trim ladder (`XSW5..XSW0`) and startup-detector
  (`XMSU1..5`) switch internally once enabled. It is the one domain in the
  block that does digital-style switching next to analog precision circuitry,
  which is exactly the substrate-noise-injection case a guard ring exists
  for.

```
┌──────────────────────────────────────────────────────────────────────┐
│ VDD rail (top, spans full width)                                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  PTAT ●──┐ ┌────────────────────────────────────────────────────┐    │
│  CTAT ●──┤ │            TEMP-SENSOR DOMAIN  (temp_core)          │    │
│          │ │  ┌────────────┐  ┌─────────────┐  ┌──────────────┐ │    │
│          │ │  │ PNP array  │  │ R1 / R2      │  │ amplifier +  │ │    │
│          │ │  │ Q1 center, │  │ gain ladder  │  │ load mirror  │ │    │
│          │ │  │ Q8A..H ring│  │ (c.centroid/ │  │ (c.centroid  │ │    │
│          │ │  │ (c.centroid│  │  interdig.,  │  │  quad,       │ │    │
│          │ │  │  #3 below) │  │  #2 below)   │  │  #1 below)   │ │    │
│          │ │  └────────────┘  └─────────────┘  └──────────────┘ │    │
│          │ │  cascoded PMOS mirror (XMP1-3/XMPC1-3) — with #2    │    │
│          │ │  trim switches (XSW5..0), startup detector (XMSUx)  │    │
│          │ └────────────────────────────────────────────────────┘    │
│          │                                                            │
│  ════════╪══════ guard ring / moat, VSS-tied, continuous ═══════════ │
│          │                                                            │
│          │ ┌────────────────────────────────────────────────────┐    │
│          │ │            ALWAYS-ON POR DOMAIN                     │    │
│          │ │ ┌───────────┐  ┌────────────────┐  ┌──────────────┐│    │
│          │ │ │ bias_core │  │ por_comparator  │  │por_output_   ││    │
│          │ │ │ (VREF,    │  │ (RTOP/RBOT/RHYS │  │chain         ││    │
│          │ │ │  IBIAS    │  │  divider #4,    │  │(deglitch,    ││    │
│          │ │ │  gen)     │  │  MINA/MINB #4,  │  │ pulse, drive)││    │
│          │ │ │           │  │  std. matching) │  │              ││    │
│          │ │ └───────────┘  └────────────────┘  └──────────────┘│    │
│          │ └────────────────────────────────────────────────────┘    │
│          └──────────────────────────────────────────────── RESETn ●  │
├──────────────────────────────────────────────────────────────────────┤
│ VSS rail (bottom, spans full width; guard ring taps tie here)        │
└──────────────────────────────────────────────────────────────────────┘
```

Placement rationale:

- **`temp_core` sits nearest `PTAT`/`CTAT`**, `por_output_chain` nearest
  `RESETn` — both pad-adjacency choices shorten the run from the
  matching-critical internal nodes (`NA`/`NB`, the amplifier's summing nodes)
  and the digital output stage to their respective pads, rather than routing
  either across the other domain.
- **`bias_core` sits between the two domains**, adjacent to the guard ring,
  because it is the thing both domains consume (`IBIAS`, `VREF`) — this
  minimizes the total length of the two shared-net feedthroughs crossing the
  guard ring (one to `temp_core`, one to `por_comparator`/`por_output_chain`)
  rather than routing a shared net the long way around.
- **`VDD`/`VSS` run as full-width top/bottom rails** feeding both domains
  directly, so neither domain's supply is daisy-chained through the other —
  a switching `temp_core` transient on a shared rail segment is exactly the
  kind of coupling the guard ring elsewhere in this plan exists to block, and
  there is no reason to reintroduce it on the rail itself when a direct tap
  is free.

## Guard-ring / isolation plan

**Boundary**: one continuous VSS-tied guard ring/moat runs along the full
seam between the temp-sensor domain and the always-on POR domain (the
horizontal band in the sketch above), plus a second ring around the block's
outer perimeter (standard practice, protects both domains from whatever sits
outside this cell on the eventual shuttle die). Both rings are p+/Psub taps
strapped to `VSS` at regular intervals — no floating segments — because the
domain seam is precisely where a switching digital-style node (`temp_core`'s
trim switches, startup detector, `EN`/`ENB`) sits closest to the precision
analog decision (`por_comparator`'s comparator core and divider tap `SNS`)
that the whole block exists to get right.

**What this ring is for, concretely**: `temp_core`'s trim ladder
(`XSW5..XSW0`, each 32 µm/0.5 µm) and startup detector switch every time the
sensor is enabled/disabled and every time a code-dependent switching event
occurs; `por_comparator`'s regenerative transition (`MHSW` toggling `RHYS` in
and out) is a similarly abrupt edge on the other side of the seam. Neither
event should couple through the substrate into the other domain's precision
nodes — the guard ring is what stops that coupling, independent of anything
#15's mismatch data measured (mismatch is a *device-to-device* random
variable; substrate coupling is a *systematic* injected transient, a
different failure mode this floorplan still has to cover).

**What the automated flow will not check here.** Per
[`layout/README.md` § "Known deck limits"](README.md#known-deck-limits---what-a-clean-lvs-here-does-not-prove)
the extraction deck has no distinct tap/well-label layer, so a mis-tied or
untied well compares clean. This applies directly to the guard ring described
above — a ring drawn but left floating, or tied to the wrong net, would pass
`klt lvs` with a clean report, and a ring with a gap in one segment passes
`klt drc` too. **Guard-ring and well/substrate-tie correctness at this seam
must be caught by design review** when polygons are drawn (this issue's own
review, and again at #18's post-layout stage), or by the build-time geometry
checks #72 added for `temp_por_top` — it is not, and per the current deck
cannot be, a thing the automated DRC/LVS run in `layout/run_checks.sh`
verifies. The tool gap is filed generically as
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303).
(It is *not* covered by klayout-tools#281, which is **closed**: its curated
scope was narrowed to "shape (1) only" and it was resolved by #285's
`device.body_unverified` warning, which reports that bodies went uncompared
and says nothing about a ring.)

> **#72 update — measured, then partly answered.** Drawing the assembly
> confirmed the claim rather than assuming it: a `temp_por_top` whose seam moat
> is drawn but never tied to `VSS`, and one whose perimeter ring has a 10 µm
> gap in a segment, are each `klt drc` **clean** and `klt lvs` **match**. The
> deck's #285 follow-up *is* live now (every `lvs.json` carries two
> `device.body_unverified` warnings), but that reports only that *bodies* went
> uncompared — it says nothing about a ring, so it is not the missing signal,
> and #281 (which #285 closed) does not cover ring continuity or the tie. That
> gap is filed generically as
> [klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303),
> with both defect builds as its evidence.
> `layout/build_cells.py` therefore checks the drawn geometry itself before
> writing `temp_por_top.gds`: every net one connected group, every group one
> net, every guard ring an annulus (one polygon, one hole), every via covered
> on both levels — each negative-controlled by introducing the defect and
> confirming the check fires. What remains a design-review claim, and is the
> only part that does, is that `VSS` is the right net to tie the rings to.
> Cells drawn before #72 (`bias_core`, `por_comparator`, `por_output_chain`,
> `temp_core`) keep their own rings as a pure design-review claim.

**Shared-net feedthroughs.** `IBIAS`, `VREF`, and `BIAS_OK` all originate in
`bias_core` (inside the POR domain) and cross the seam only to reach
`temp_core`'s enable/bias network (`IBIAS` only — `VREF`/`BIAS_OK` are
POR-domain-internal per `design/README.md`'s net table). One feedthrough,
short and direct, routed through (not around) the guard ring at a single
crossing point rather than multiple, so the ring stays otherwise continuous.

(**#72, as built** — this is the part of the plan the metal stack changed, so
state it exactly. With Metal2/Metal3 available (see "Routing / metal-level
note" below) nothing has to be routed *through* the moat, so the plan's "one
feedthrough through a notch" becomes "cross over an unbroken ring", and the
count of crossings stops being the thing that matters. What crosses `y` at the
seam, as drawn: **four** left-margin Metal3 columns, all inside the moat's own
`x`-span — `IBIAS` and `RESETn`/`EN` (the two signals), plus the `VSS` riser
down to the bottom rail and the POR domain's `VDD` riser up to the top rail.
`temp_core`'s own `VDD` tap does not cross, the top rail being on its side of
the seam. None of the four is drawn on Metal1/COMP, the layers the moat is made
of, so the moat is continuous everywhere and has no notch anywhere. The
coupling claim this section is really making is unchanged and narrower than the
crossing count: `IBIAS` is the only *bias* net that crosses into the
temp-sensor domain, `VREF`/`BIAS_OK` staying POR-domain-internal.)
No special matching treatment applies to this net — it is a shared bias
reference, not a matched pair, and DR-010 already requires `temp_core` to
present high impedance to it when disabled, so nothing about crossing the
seam changes that contract.

## Matching plan, ranked to #15's data

### 1 (highest priority) — amplifier input pair + load mirror, `temp_core`

**Devices**: `XMI1`/`XMI2` (pfet 32 µm/4 µm, input pair, gates on `NA`/`NB`),
`XML1`/`XML2` (nfet 8 µm/8 µm, mirror load). Dominant term at every binding
point (σ up to 1.025 mV, 3σ = 3.07 mV against a 0.46 mV budget — 6.7×
over), and the one term a 25 °C gain trim cannot remove (it only shortens the
lever arm — `design/temp_core.md` § "Trim", confirmed empirically in the
breakdown record). **No downstream trim compensates for a layout-quality miss
here**, which is what makes this the floorplan's top priority rather than a
tie with rank 2.

**Layout strategy**:

- Split `XMI1`/`XMI2` into an even number of unit fingers and interleave them
  in a common-centroid pattern (A-B-B-A across both the row and column axis)
  around the shared axis of symmetry the input pair and its load mirror both
  sit on — so a first-order process gradient across the die cancels for the
  pair *and* the gradient direction relative to `XML1`/`XML2` is the same one
  the input pair sees, not an independent one.
- `XML1`/`XML2` get the identical treatment on their own shared axis, placed
  immediately adjacent to (not offset from) the input pair's centroid so the
  two matched structures share as much of the same local gradient as
  geometry allows.
- Same orientation, same finger width, same well/substrate context for every
  unit finger in both structures — no finger of `XMI1` may sit in a
  different local environment (edge-of-array, different neighbor type) than
  the corresponding finger of `XMI2`.
- **Dummy strategy**: one dummy finger of the same device (same `W`/`L`,
  same gate connection convention, tied off per standard practice) on each
  outward-facing edge of both the input-pair array and the load-mirror
  array, so no active finger of either pair is a boundary finger.
- `XMT` (pfet 20 µm/4 µm tail) is not itself named in the breakdown as a
  mismatch-critical *pair* (it has no matched partner — it is a single tail
  device), so it does not get common-centroid treatment; it is placed
  adjacent to the input pair to keep the tail-to-pair routing short, which
  matters for settling/noise but is not a #15-flagged accuracy term.
- `XMS2N`/`XMS2P` (second stage) and `XCC`/`XRZ` (compensation) are likewise
  not named in the breakdown — standard practice (short routing, consistent
  orientation) applies; no common-centroid budget is spent on them.

### 2 — gain/mirror ratio, `temp_core`

**Devices**: the resistor ratio `XR1` (21.6 kΩ) vs. the `R2` chain — `XR2F`
(479 kΩ fixed) plus the six binary-weighted trim segments `XR2T5..XR2T0`
(41.5…1.24 kΩ), all `ppolyf_u` — **and** the cascoded PMOS mirror
`XMP1`/`XMP2`/`XMP3` (pfet 8 µm/4 µm) with cascodes `XMPC1`/`XMPC2`/`XMPC3`
(pfet 8 µm/1 µm) on `PCAS`. The breakdown's "gain `A = R2/R1` × mirror ratio"
term bundles both — up to 2.44 °C of σ (3σ = 7.32 °C) — and both halves are
removed by the 25 °C gain trim, so this rank sits below rank 1 but still
needs an explicit plan rather than best-effort: at its own worst binding
point, alone with the other two terms at zero, it still misses the ±3 °C
window.

**Resistor-ratio layout strategy**:

- Build `R1` from a single unit-length `ppolyf_u` segment at the array's
  drawn width (matches `design/temp_core.md`'s existing `2 µm` convention).
  Build every `R2`-side segment (`XR2F` and each `XR2T*` trim segment) from
  an integer number of *the same* unit-length sub-resistor, tiled — not one
  long serpentine per segment — so `R1`'s unit and every `R2` sub-unit share
  identical width, orientation, and end-effect geometry.
- Arrange the tiled `R2` units in a common-centroid ring/cross around `R1`'s
  unit(s) rather than as a single contiguous block, so the ratio — not just
  the absolute values — is protected from a linear gradient across the
  array. This is the concrete form of what `design/temp_core.md` already
  states holds at the model level (same-flavor TC and sheet-rho cancel in
  the ratio); the common-centroid tiling is what makes that cancellation
  robust to a *spatial* gradient too, which the schematic-level argument does
  not by itself cover.
- Trim switches `XSW5..XSW0` (32 µm/0.5 µm) sit adjacent to their own
  segment, not centroid-critical individually (they are not named in the
  breakdown), but symmetric left/right placement relative to the ladder
  keeps their `Ron` contribution — already characterized at 0.229 % of a
  segment (`design/temp_core.md` § "Trim") — from adding an asymmetric term.
- **Dummy strategy**: guard/dummy resistor segments of the same flavor and
  width at both ends of the tiled array (standard poly-resistor practice —
  end segments see a different etch/implant environment than interior
  segments, and a dummy absorbs that rather than a live unit).
- **Area note, carried forward from `design/temp_core.md`**: this ladder is
  the smaller of the block's two large resistor structures (the POR
  divider, priority 4 below, is the area driver at ≈0.045 mm²); the
  common-centroid tiling above trades some area for the ratio protection
  #15's data says this term needs, consistent with the README's area
  posture ("matching quality wins over compactness only where the MC budget
  says it must") — which is exactly this case.

**Mirror layout strategy**:

- `XMP1`/`XMP2`/`XMP3` is a 3-way match (legs 1 and 2 must be exactly 1:1 for
  the ΔVBE construction to hold, per `design/temp_core.md`; leg 3 carries
  the gain output and is likewise part of the ratio). Split each leg into
  equal unit fingers and interleave in a common-centroid pattern
  (e.g. a repeating `1-2-3-3-2-1` finger sequence) rather than three
  contiguous blocks, so no leg is systematically closer to one edge of the
  array than another.
- Cascode devices `XMPC1`/`XMPC2`/`XMPC3` are stacked directly with their
  respective mirror-leg fingers (same finger ordering, same local
  neighborhood) rather than routed to a separately-placed cascode array —
  this keeps the two-device stack for each leg congruent with its
  partners' stacks, not just the mirror devices alone.
- **Dummy strategy**: one dummy finger of the same device on each outward
  edge of the interleaved array, mirroring the treatment in rank 1.

### 3 — vertical PNP pair, `temp_core`

**Devices**: `XQ1` (the 1× reference) vs. `XQ8A..XQ8H` (eight parallel
`pnp_10p00x10p00` unit instances forming the 8×). Smallest of the three
ranked terms (σ up to 0.19 mV of Δ`V_BE`, 1.11 °C of σ, 3σ = 3.32 °C), but —
per #15's own framing — each term alone with the other two at zero still
misses the ±3 °C window at its worst binding point, so this still needs an
explicit common-centroid plan rather than "best effort."

**Layout strategy**:

- Classic common-centroid ring: `XQ1` at the array's geometric center,
  the eight `XQ8A..XQ8H` unit devices placed in a symmetric ring around it
  (octagonal placement — one unit device roughly every 45°), each unit
  device equidistant from `XQ1`'s center and in the same orientation. This
  is exactly what `design/temp_core.md` flags as the reason the schematic
  instantiates eight discrete unit cells rather than one `par=8` device
  (which, per that document's own PDK finding, would not even give an 8:1
  ratio in this PDK's model — `par=` scales only the mismatch term, not
  `Is`).
- A shared, common base/collector ring construction around the whole array
  (rather than per-device rings) keeps every unit device's local well/tap
  environment identical.
- **Dummy strategy**: a ring of dummy `pnp_10p00x10p00` unit cells around
  the outside of the active 9-device array (1 center + 8 ring), so no active
  emitter sits at the array's true physical edge. This is the standard
  bipolar-array treatment and is what "eight discrete unit cells... so this
  is possible" in `design/temp_core.md` was written to enable.
- Current-source legs feeding the array (`MP1`/`MPC1` → `Q1`,
  `MP2`/`MPC2`/`MP3`/`MPC3` → the `Q8A..H` array) route symmetrically to the
  ring's center and perimeter respectively, so the current delivery itself
  does not reintroduce an asymmetry the device placement just removed.

### 4 (data-driven de-prioritization) — POR comparator input pair and sense divider

**Devices**: comparator input pair `MINA`/`MINB` (nfet 2 µm/1 µm, gates on
`SNS`/`VREF`); sense divider `RTOP`/`RBOT`/`RHYS` (`ppolyf_u_3k`, W = 2 µm,
same-flavor legs per `design/por_comparator.md` § "Sense divider").

**This is a documented de-prioritization, not an oversight.** #15's own
companion MC record measured the comparator's input-referred offset at
σ = 5.47–6.62 mV — an order of magnitude larger, in absolute terms, than the
temp-core amplifier's offset above — and yet `vth-rise`, `vth-fall`, and
`v_hys` still **PASS at 100 % empirical yield at every binding point** with
tens of mV of margin (see the table at the top of this document). The reason
is architectural, not a matching-quality accident:
`design/por_comparator.md` § "Why the hysteresis is a resistor ratio" shows
that feeding the release decision back into the **divider ratio** (rather
than injecting a bias-referenced current) makes the same comparator offset
appear on both the rise and fall thresholds and cancel in the difference —
measured σ(V_hys) collapsing from what an earlier current-injection variant
would have produced (order of magnitude tighter). The comparator's absolute
offset is large; what actually reaches the ratified spec rows is small,
*by construction of the topology*, independent of how tightly its input pair
is laid out.

**Layout strategy — standard practice, not common-centroid**:

- `MINA`/`MINB`: same orientation, short and symmetric routing from `SNS`
  and `VREF` to their respective gates, placed side-by-side rather than
  common-centroid-interleaved. No emitter/finger-splitting effort is spent
  here — #15's data says it would not move any ratified spec row.
- `RTOP`/`RBOT`/`RHYS`: same-flavor, same-width (`ppolyf_u_3k`, 2 µm) legs
  laid out with ordinary serpentine folding for area, not an
  interdigitated/common-centroid tile plan. The TC-in-ratio cancellation
  `design/por_comparator.md` relies on is a same-flavor property (the
  body-resistor model's temperature factor is a pure function of flavor,
  independent of geometry), not a spatial-matching one, so folding for area
  does not undermine it.
- **Dummy strategy**: standard end-of-string dummy segments for the divider
  (same reasoning as priority 2's resistor ladder — interior vs. boundary
  segment environment), and a token dummy device flanking `MINA`/`MINB` if
  it is free in the local floorplan — neither is required by #15's data, and
  neither should be allowed to grow the area budget below (this is the
  block's single largest area line item; see below).
- **Area is the actual constraint on this structure, not matching.** Per
  `design/por_comparator.md` § "Area — flagged for #17": the drawn divider
  is ≈30 883 µm² of poly at W = 2 µm, of order 0.045 mm² with realistic
  folding — essentially the whole block's ≤0.05 mm² wave-1 planning budget
  for this one sub-cell's divider, driven by the <1 µA Iq target (a
  20-plus-MΩ divider at 3 kΩ/sq is 7000 squares however it is folded).
  **This floorplan keeps `W = 2 µm`** (matching `temp_core`'s convention and
  the characterized geometry in `sim/devchar/SUMMARY.md`), consistent with
  that document's own conclusion that narrowing to `W = 1 µm` would trade
  the ~4× area saving for a larger relative width-bias mismatch term on a
  structure #15's data does not ask to be tightened. Folding pattern is
  chosen for area efficiency (serpentine, minimizing total die footprint)
  rather than for matching, per the README's area posture.

## Dummy strategy — summary

| Structure | Dummy treatment |
| --- | --- |
| Amplifier input pair (`XMI1`/`XMI2`) | edge dummy fingers, same device, both array edges |
| Load mirror (`XML1`/`XML2`) | edge dummy fingers, same device, both array edges |
| PTAT gain resistor ladder (`XR1`/`XR2*`) | dummy resistor segments, same flavor/width, both string ends |
| Cascoded PMOS mirror (`XMP1-3`/`XMPC1-3`) | edge dummy fingers, both array edges |
| PNP array (`XQ1`/`XQ8A..H`) | ring of dummy `pnp_10p00x10p00` unit cells around the 9-device array |
| Comparator input pair (`MINA`/`MINB`) | optional flanking dummy, not load-bearing |
| Sense divider (`RTOP`/`RBOT`/`RHYS`) | standard end-of-string dummy segments |

## Pin placement

Per the ratified pinout
([`spec/target-spec.md` § "Electrical interface"](../spec/target-spec.md#pinout),
asserted by `design/netlist.py --check`; 5 pads, no trim/config/programming
pins in wave 1):

| Pad | Dir | Placed on | Why |
| --- | --- | --- | --- |
| `VDD` | inout | top rail, full width | feeds both domains directly; see "Placement rationale" above |
| `VSS` | inout | bottom rail, full width; also the guard-ring tie net | feeds both domains directly and ties every guard-ring tap, so the isolation plan and the supply plan are the same net by construction |
| `PTAT` | out | left edge, adjacent to `temp_core` | shortest path from the sensing core's output node, avoids routing across the domain seam |
| `CTAT` | out | left edge, adjacent to `temp_core`, next to `PTAT` | same rationale; `CTAT` is buffered through `XRISO` inside `temp_core` per `design/temp_core.md`, so pad-side routing parasitics are already isolated from the loop node — no floorplan-level accuracy concern here |
| `RESETn` | out | right edge, adjacent to `por_output_chain` | shortest path from the push-pull output driver; `por_output_chain` is the domain-internal cell that owns this signal per `design/README.md`'s hierarchy table |

This exactly reproduces the 5-pad set (`VDD`, `VSS`, `PTAT`, `CTAT`,
`RESETn`) — no additional pad is introduced by this floorplan.

## Routing / metal-level note

`layout/README.md`'s known-limits list flags that `klt`'s `gf180mcu`
extraction deck may have been single-metal-only, with klayout-tools#220
listed as closed and a note to "re-check `klt`'s version before assuming the
limit still applies." Checked for this issue:

```
$ klt --version
klt 0.1.0
```

Inspecting the installed package directly
(`klayout_tools/decks/gf180mcu.py`, the `EXTRACTION_DECK` this `klt 0.1.0`
ships) showed `metals=((34, 0),)` — **Metal1 only**, still. klayout-tools#220
is closed upstream (merged via klayout-tools#238, which populates the full
Metal1–Metal5/Via1–Via4 stack), but that fix had not reached the `klt 0.1.0`
build installed in this environment. **This floorplan therefore assumed
Metal1-only routing**, consistent with #16's proven cell: matched structures'
internal interconnect and the domain-crossing feedthroughs above route on
Metal1, with poly used as the crossunder layer where two Metal1 runs must
cross, exactly as `layout/README.md` describes for the single-metal regime.
When the local `klt` install is upgraded past klayout-tools#238, this
constraint should be re-checked (`klt --version` / re-inspect the installed
deck) before assuming it still applies — this floorplan does not depend on
Metal1-only being permanent, only on it being the current, verified
capability.

No new `klayout-tools` friction issue is filed for this: the underlying gap
is already tracked and fixed upstream (klayout-tools#220 / #238); this is a
local-install version gap, not a new tool-capability gap.

### Re-checked for #72 (block-level assembly) — the constraint is lifted

The instruction above was carried out before drawing `temp_por_top`. Same
`klt --version` (`klt 0.1.0`), different deck:

```
>>> EXTRACTION_DECK.metals
((34, 0), (36, 0), (42, 0), (46, 0), (81, 0))
>>> EXTRACTION_DECK.vias
((35, 0), (38, 0), (40, 0), (41, 0))
```

klayout-tools#238's full stack **is** in the installed build, and the DRC
deck's `metal2`/`metal3` width and space rules are real (they previously
appeared under `rules_skipped` only because no stream in this repo drew those
layers; `temp_por_top`'s report shows them checked). So the single-metal
assumption above is historical, and this section is kept rather than deleted
because three cells were drawn under it and their geometry still reflects it.

What changes, and what does not:

- **The domain-seam guard ring needs no notch.** Under Metal1-only, the one
  `IBIAS` feedthrough this plan allows across the seam had to *break* the moat
  to cross it — a ring with a designed-in gap, which is exactly the structure
  whose correctness the plan then has to argue for. On Metal2/Metal3 every
  crossing — the two signal columns and the two supply risers listed under
  "Shared-net feedthroughs" — passes *over* an unbroken moat on Metal3, none of
  them on the Metal1/COMP the moat is drawn in. The isolation plan above is
  realised more literally than it was written.
- **`VDD`/`VSS` reach both domains without daisy-chaining.** The rails are
  Metal2; each domain taps them on its own riser rather than through the
  other's rail segment — the "Placement rationale" bullet above, satisfied by
  construction rather than by careful ordering.
- **The four sub-circuits are unchanged.** `bias_core`, `por_comparator`,
  `por_output_chain` and `temp_core` still route on Metal1 with poly
  crossunders and their committed GDS is byte-identical. The lifted limit is
  an opportunity for the assembly level, not an obligation to redraw proven
  cells.
  *(Superseded everywhere by #90/#91/#92/#93: `por_output_chain` now draws its
  two MiM caps, `temp_core` its PNP array and `R2` ladder, `por_comparator` its
  sense divider and `bias_core` its 10 vertical PNPs, 4 poly resistors and 2
  MiM caps, so no sub-cell's GDS is the #72 stream any more. They still keep
  **Metal1-only signal routing** with poly crossunders — the MiM stack, the
  resistor marker layers and the bipolar device mark are device geometry, not
  routing — except `temp_core`, the one cell that took the lifted limit up,
  routing its new passives' terminals on Metal2 risers. The assembly's own GDS
  is the #72 stream still, pending #97. See `layout/README.md`.)*
- **The matching plan is untouched, and #90 added to it where the plan was
  silent.** Nothing in ranks 1–4 depended on the metal count, and none of the
  four ranks covers `bias_core`. Drawing that cell's bipolars made one matched
  structure unavoidable, so it is recorded here rather than invented silently:
  the **8:1 emitter ratio is drawn as a 3×3 common centroid**, `XQ1` at the
  centre and `XQ8A`…`XQ8H` on the perimeter. `XQR` is not part of that ratio
  and takes a fourth column. A `layout/tests` case asserts the centroid.

No new `klayout-tools` friction issue *for the metal stack*: this is the *good*
outcome of an already-tracked, already-fixed upstream gap reaching the local
install. (The gap #72 *did* file is a different one — guard-ring continuity and
tie, [klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303),
see "Guard-ring / isolation plan" above.)

## Handoff

- **To #16's flow**: each matched structure above becomes one or more cells
  registered in `layout/build_cells.py` / `layout/lvs_reference.py` per
  [`layout/README.md` § "Adding a cell (for #17 / #18)"](README.md#adding-a-cell-for-17--18)
  once polygons are drawn.
- **To #18**: this floorplan's guard-ring/well-tie correctness claim is a
  design-review claim, not an automated one (see "Guard-ring / isolation
  plan" above) — #18's post-layout extracted re-run is where the matching
  plan's actual effectiveness gets measured against #15's mismatch budget on
  real, extracted parasitics, not where the guard-ring/tie correctness gets
  checked (the deck cannot check that; only review can).
