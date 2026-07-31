# DR-005: Temp sensor + POR architecture survey (topology selection)

- **Status**: proposed
- **Date**: 2026-07-30
- **Decided by**: Loom Builder agent, issue #3

## Context

This record is the topology-selection gate for the whole block. Five
downstream design issues (#8 schematic entry, #9 temp-sensing core, #10 POR
comparator, #11 shared bias/startup, #12 POR output chain) are blocked on its
outcome, and spec ratification (#1) consumes it. Getting a topology wrong
here is expensive precisely because it passes review and only surfaces weeks
later as a failed corner sim — so every recommendation below is argued
against a specific row of the README draft spec table (reproduced under
Consequences), not asserted from a literature list alone.

Two scope inputs this record depends on are themselves still open:

- **Supply flavor (#7, in flight).** This record assumes the **3.3 V**
  gf180mcu device flavor (`nfet_03v3`/`pfet_03v3`) throughout. The
  arithmetic: worst-case-high POR threshold 2.6 V × 1.05 = 2.73 V vs.
  worst-case-low 3.3 V rail × 0.90 = 2.97 V leaves ~240 mV of release margin;
  on a 5 V rail the same 2.6 V threshold sits at ~52 % of nominal (releases
  far too early relative to a sane brownout margin) and would force the
  05v0/06v0 device families throughout instead of 3.3 V devices. This
  assumption is stated explicitly here as an **input to #7**, not a silent
  bake-in — if #7 rules 5 V, the POR alternatives-rejected reasoning below
  (specifically the VBE-stack tempco argument and the native-divider
  rail-fraction argument) needs to be re-argued at 5 V numbers before this
  record can be treated as settled for that flavor.
- **Decision-record template (#6, in flight, PR #19 open).** This record
  mirrors the field set and section structure of #6's ported template
  (`spec/decision-records/TEMPLATE.md`, `DR-NNN-<slug>.md` naming) directly,
  since that template's shape was already visible in an open PR at authoring
  time. No reconciliation pass should be needed once #6 merges.

**Evidence status**: this survey precedes #4's device-characterization
sweeps and the #13/#14 testbench suites. Every quantitative number below
(currents, voltage margins, temperature coefficients, achievable accuracy)
is a **first-order estimate from PDK-documented device behavior and standard
bandgap/POR design practice for a 180 nm-class flavor** — not a simulated or
measured result. Per repo rule (CLAUDE.md: "no claim without a testbench"),
none of these numbers may be cited as verified until #4/#13/#14 produce
`sim/` evidence. Every candidate considered uses only gf180mcu-available
devices: vertical PNP, standard MOS flavors, poly/nwell resistors, and (where
available — to be confirmed by #4) a native/zero-Vt MOS option. No exotic
devices are proposed anywhere in this record.

## Decision

### Temp sensor: ΔVBE/VBE (PTAT/CTAT) bandgap-style core, plain (not chopped), single-point gain trim

Recommend a vertical-PNP-based temperature sensor built the same way a
bandgap reference is built, but left uncompensated for temperature on
purpose: combine a CTAT term (a single diode-connected vertical PNP's VBE,
~ −2 mV/°C) and a PTAT term (ΔVBE across two PNPs biased at an N:1 emitter-
area or current ratio, amplified by a resistor ratio to comparable slope)
without cancelling them into a flat bandgap voltage — instead output the
PTAT term directly (analog PTAT-out, matching the README draft's wave-1
interface) or a weighted PTAT+CTAT combination if a wider-range CTAT-flavored
output is later wanted. Bias network shared with the POR reference core (see
Shared Infrastructure below). No chopping in wave 1; a single-point (25 °C)
gain/offset trim on the PTAT amplification path.

### POR: bandgap-referenced comparator with hysteresis, gated by a native/subthreshold self-starting assist

Recommend a precision threshold engine built from a proper (curvature-
uncompensated is fine; full 2nd-order compensation is not needed for a 5 %
threshold budget) bandgap reference compared against a resistor-divided VDD
tap, through a comparator with resistor-network positive feedback for
hysteresis. This engine is **not** what asserts reset during power-up ramp —
see Shared Infrastructure for the startup-ordering split that resolves the
chicken-and-egg problem (#11).

### Shared infrastructure: one shared bias/reference core — yes, with a POR-only startup-assist leg that predates it

**Explicit answer: yes**, the temperature sensor and the POR precision
comparator share one bias/reference core (bandgap-style current + voltage
reference). Both consumers need a PVT-stable reference and bias currents;
sharing amortizes both Iq and area. **However**, POR additionally owns a
second, much simpler always-on leg — a native/subthreshold (or, if native
devices are unavailable in gf180mcu per #4, a minimally-biased standard-Vt)
resistive divider — that is *not* shared, is *not* precision, and exists
solely to hold reset asserted from the earliest moment VDD can support a
logic level, before the shared bias core has powered up and settled. This
two-tier structure is the resolution to #11's chicken-and-egg constraint:
POR must work before anything else is biased, so POR's *coarse* assertion
path cannot depend on the thing it is gating.

**Startup ordering** (earliest to latest):

1. VDD begins ramping from 0 V.
2. The POR startup-assist divider (self-biasing, no enable signal, no loop
   to settle) begins conducting almost immediately and holds the raw
   reset signal asserted as soon as there is enough voltage to define a
   logic level — well below the shared bias core's dropout. This is the
   circuit that is "up before anything else is biased."
3. Once VDD crosses the shared bias core's own minimum operating voltage
   (PDK-documented device data needed to pin this number — see Consequences
   → Open device questions for #4), the shared core's own startup kick
   (a small dedicated start-up leg, itself using only gf180mcu-available
   devices — e.g. a resistor- or native-device-referenced kick out of the
   bandgap loop's degenerate zero-current state) brings it up and it
   settles.
4. The precision bandgap-referenced comparator (Decision → POR) becomes the
   authoritative threshold decision only once the shared core reports valid
   (settle-time margin to be quantified by #11/#14 sim).
5. Reset deasserts only when **both** (a) the shared core is valid and
   (b) the precision comparator's hysteretic threshold decision says
   VDD ≥ 2.6 V (with the ≥100 mV hysteresis band satisfied), held for at
   least the reset-pulse width.
6. The temperature sensor's own enable is gated by POR's deasserted output —
   it is never required to be valid before POR, which removes it from the
   chicken-and-egg problem entirely (only POR itself needs a
   before-anything-is-biased path).

**Deglitch vs. hysteresis — explicit ownership split** (input to #10/#12):
hysteresis (the ≥100 mV static spec) is owned by the precision comparator
itself (the positive-feedback network in Decision → POR) — it prevents
chatter for a slowly-varying signal sitting near the threshold. Deglitching
(rejecting a narrow, fast transient dip that a hysteretic comparator would
still trip on instantaneously, since hysteresis is not a time-domain filter)
is a **separate, additional** block, owned downstream in #12's POR output
chain — e.g., an RC or counter-based minimum-dwell-time filter between the
raw comparator output and the reset pulse generator. These two mechanisms
are complementary, not substitutable; #10 should not attempt to satisfy
deglitch via hysteresis alone, and #12 should not attempt to satisfy
hysteresis via a time filter alone.

**Reset-pulse generation stance** (input to #7, not settled here): recommend
a simple RC/current-starved-capacitor one-shot referenced off the shared
bias core's existing bias current, sized for the ≥1 ms fixed target. A
programmable pulse width would require an oscillator + counter, which is a
materially higher Iq architecture class and is very unlikely to fit the
<1 µA budget (a free-running oscillator alone typically costs more than the
entire budget in a design of this class). This record recommends fixed-pulse
for wave 1 as the only option consistent with <1 µA, and flags
programmability as a stretch item #7 should keep out of wave 1 rather than
ruling on directly — final call belongs to #7's own decision record.

## Alternatives considered

### Temp sensor

- **Resistor-ratio-only (CTAT poly/nwell divider off a reference voltage,
  no VBE term)** — rejected. Without a VBE physics anchor, absolute accuracy
  is set entirely by resistor absolute tolerance and tempco (typically
  several hundred to low-thousands of ppm/°C untrimmed for poly/nwell
  flavors — estimate, pending #4), which does not credibly reach the ±3 °C
  untrimmed target across −40…125 °C the way a VBE-anchored approach does;
  a resistor-only design also has no natural single trim point that removes
  both gain and offset error the way a PTAT gain trim does on a VBE-based
  core, so it does not clear a credible path toward the ±1.5 °C stretch
  either.
- **MOSFET subthreshold-VGS-based PTAT (weak-inversion gate-source voltage
  differences instead of BJT VBE)** — rejected. Subthreshold VGS as a
  temperature proxy has a materially larger untrimmed process/mismatch
  spread than vertical-PNP VBE (MOS threshold-voltage mismatch dominates,
  vs. the tighter, physics-set VBE mismatch of a matched bipolar pair), and
  has a thinner track record in this device class than BJT-based sensors —
  the README's "Vidatronic-validated categories" selection rationale points
  toward the well-precedented BJT approach. Rejected primarily on accuracy-
  path credibility toward ±3 °C untrimmed, secondarily on precedent.
- **Chopped ΔVBE amplification (vs. plain)** — rejected for wave 1, not
  rejected outright. Chopping suppresses the dominant untrimmed error source
  (amplifier offset referred to the ΔVBE input, which the gain stage
  multiplies directly into temperature error) and would help push toward
  the ±1.5 °C stretch beyond what a single-point trim alone buys. It is
  rejected for **wave 1** because it adds a chopping clock, output ripple
  requiring settling/filtering, and incremental Iq (clock generation +
  switch drive) that works against the <20 µA target and materially works
  against the <5 µA Iq stretch — and because the untrimmed ±3 °C target
  and the 1-pt-trim ±1.5 °C stretch both look achievable with a plain
  architecture (estimates below), chopping is not needed to hit the stated
  spec. Revisit if #13 evidence shows plain amplifier offset alone consumes
  more than the ±1.5 °C stretch budget.

**What the 1-pt trim buys (estimate, pending #4/#13 evidence)**: for a
plain ΔVBE/VBE core, the dominant untrimmed error terms are (a) a
roughly-linear gain/offset error from resistor-ratio tolerance and amplifier
offset, correctable at a single reference temperature, and (b) a residual
curvature/nonlinearity term across the −40…125 °C span that a *single*-point
trim cannot remove (that requires 2-pt trim or higher-order compensation,
out of scope for wave 1). A single-point trim at 25 °C is estimated to
remove most of (a), taking a ±3 °C untrimmed budget down toward roughly
±1–1.5 °C, consistent with — but not by a wide margin — the stated ±1.5 °C
stretch target; the margin to that stretch depends on how large the
uncorrected curvature term turns out to be, which only #13 evidence can
settle.

**Iq budget (estimate)**: a ΔVBE/VBE core biased at low-µA branch currents
(order 1–5 µA per branch, shared with the POR bias core) plus a low-power
output buffer/amplifier (order a few µA) totals on the order of 5–15 µA,
comfortably inside the <20 µA target but not obviously inside the <5 µA
stretch without a dedicated low-power (e.g., subthreshold-biased) amplifier
redesign — flagged as an optimization target for #9, not resolved here.

### POR

- **VBE-stack threshold (N series diode-connected vertical PNPs, no
  bandgap loop)** — rejected on tempco. A stack sized near 2.6 V at room
  temperature (roughly N = 4 devices at ~0.65 V each) inherits each diode's
  ≈ −2 mV/°C coefficient un-cancelled: over the full −40…125 °C span (165 °C)
  the stack's effective threshold shifts by roughly 4 × (−2 mV/°C) ×
  165 °C ≈ −1.3 V — over an order of magnitude larger than the ±5 % (±130 mV)
  threshold budget. Compensating that tempco away requires cancelling it
  against a PTAT term, which is exactly what a bandgap loop already does —
  so a "simpler" VBE-stack that meets the accuracy spec collapses back into
  the bandgap-referenced comparator, with no simplicity or Iq win left to
  justify choosing it separately. Where a VBE-stack does win — Iq (no opamp
  loop, potentially <0.3 µA) and self-starting ramp behavior (diode stack
  conducts and defines a threshold-ish node almost as soon as VDD ramps,
  with no settle-time loop) — those properties are exactly what is captured
  instead in the recommended startup-assist leg, without inheriting the
  accuracy failure, because the assist leg is explicitly *not* the precision
  threshold decision.
- **Subthreshold/native-device VDD divider used as the precision threshold
  (not just a startup assist)** — rejected as the precision decision, for
  two independent reasons. First, a divider referenced only to VDD detects
  a fixed *fraction* of VDD, not an absolute 2.6 V — it cannot distinguish
  "VDD is 2.6 V" from "VDD is any other value that produces the same
  fraction," so it is not the right primitive for an absolute-voltage spec
  at all. Second, if instead referenced to a native/zero-Vt device's
  threshold voltage (an absolute-ish reference), untrimmed native-Vt process
  spread on this device class is typically on the order of ±100–200 mV
  (PDK-data estimate, to be confirmed by #4) — alone comparable to or larger
  than the entire ±130 mV threshold budget, before adding resistor-divider
  tolerance and comparator offset on top. Trimming it back into budget would
  erode the "simple, ultra-low-Iq, no bias-core dependency" advantage that
  motivated considering it in the first place. Where this candidate wins —
  Iq (potentially <0.1 µA, best-in-class toward the <0.3 µA stretch) and
  trivially self-starting ramp behavior (valid the instant VDD exceeds the
  divider's own headroom, no loop to settle) — those are exactly the
  properties recommended instead for the startup-assist role, not the
  precision-threshold role.

**Slow-ramp / below-operating-floor and brownout behavior, per candidate**
(estimates, pending #14 evidence):

| Candidate | Slow-ramp behavior | Below-floor / brownout behavior |
|---|---|---|
| Bandgap-referenced comparator (recommended, precision stage) | Needs the shared core's loop to settle before its decision is valid — by construction this candidate alone does *not* solve the "before anything is biased" requirement, which is exactly why it is paired with the startup-assist leg rather than used alone during ramp-in. | Once biased, catches brownout cleanly and immediately because it compares against an absolute reference, not a VDD-derived fraction — a genuine strength, provided the dip does not itself collapse the shared core below its own operating floor. |
| VBE-stack (rejected as precision stage) | Self-starts early (diode stack conducts near VDD ramp start) — good ramp behavior, but see accuracy rejection above. | Threshold value during a warm brownout is itself temperature/supply dependent enough (same tempco problem) to be unreliable at corners — a "clean-looking" but untrustworthy catch. |
| Native/subthreshold divider (rejected as precision stage; recommended as startup-assist) | Valid essentially instantly once VDD exceeds the divider's own small headroom — the best ramp behavior of the three, which is exactly why it is kept as the assist leg. | Fast to react to a dip, but the reacted-to value is not a trustworthy absolute threshold per the accuracy rejection above — acceptable for a coarse "hold reset" role, not acceptable as the qualified release decision. |

## Consequences

### Sizing against the README draft spec table

| README row | Target / Stretch | How this record's recommendation is sized against it (estimate, pending #4/#13/#14) |
|---|---|---|
| Temp range | −40…125 °C | Bandgap-style ΔVBE/VBE core is the standard choice across this full industrial-plus range for BJT-based sensors; no candidate considered here is range-limited within this window at a device level. |
| Temp accuracy (untrimmed) | ±3 °C target / ±1.5 °C stretch (1-pt trim) | Plain ΔVBE/VBE core estimated to reach ±3 °C untrimmed on gain/offset + curvature error; 1-pt gain trim estimated to remove most gain/offset error, landing near but not conclusively inside ±1.5 °C — residual curvature is the open risk, owned by #9/#13. |
| Temp interface | analog PTAT/CTAT out (digital-via-SAR stretch) | Recommendation outputs the PTAT signal directly (analog), matching wave-1 target; SAR pairing for the digital stretch is compatible with this core (it is a downstream ADC decision, not a core-topology change) and is left to #7/#9. |
| Temp Iq | <20 µA target / <5 µA stretch | Estimated 5–15 µA for the recommended plain core — inside target, stretch not yet clearly reachable without further low-power amplifier work (#9). |
| POR threshold | 2.6 V ±5 % | Bandgap-referenced comparator is the only candidate that provides an absolute-voltage reference at all (not a VDD fraction) — the other two candidates are rejected specifically because they cannot hit this row without reintroducing bandgap-level complexity or a trim mechanism. |
| POR hysteresis | ≥100 mV | Recommended comparator's positive-feedback resistor network is a standard, tunable mechanism for this row — not a differentiator between candidates; explicitly assigned as the comparator's job, distinct from deglitch (see Decision → ownership split). |
| POR Iq | <1 µA target / <0.3 µA stretch | Tight but estimated feasible (0.3–0.8 µA) for the shared-core-based precision comparator; the coarse startup-assist leg is estimated sub-0.1 µA and runs concurrently, not additively gating the target — final number is #11/#14's to verify. |
| POR reset pulse | ≥1 ms target / programmable stretch | Recommended fixed RC/current-starved one-shot meets the ≥1 ms target within the Iq budget; programmable stretch is flagged to #7 as very unlikely to fit <1 µA (oscillator+counter class) and recommended out of wave 1. |

### Downstream consumer decision points — settled or deferred

| Consumer | Decision point | Disposition here |
|---|---|---|
| #8 (schematic entry) | Hierarchy implications | Settled (recommendation): `bias_core` (shared) and `por_startup_assist` (POR-only) as earliest-instantiated leaves; `por_comparator`, `por_output_chain`, `temp_core`, `temp_buffer` layered on top, with `temp_*` gated by POR's output and never required to precede it. |
| #9 (temp-sensing core) | Trim node/mechanism | Settled (stance, not mechanism): single trim node on PTAT gain (or equivalently PTAT bias current), 1-pt trim at 25 °C. No POR trim node in wave 1. Trim *mechanism* (fuse/OTP/laser/etc.) is explicitly deferred to #9, including flagging it as a possible klayout-tools friction-protocol candidate if trim-cell layout support proves awkward. |
| #10 (POR comparator) | Slow-ramp / below-floor / brownout behavior; hysteresis ownership | Settled: behavior table above per candidate; hysteresis owned by the comparator's positive-feedback network. |
| #11 (shared bias/startup) | One core or two; startup-ordering / chicken-and-egg | Settled: one shared core (yes) plus a separate POR-only startup-assist leg; 6-step startup ordering given in Decision. |
| #12 (POR output chain) | Deglitch ownership; reset-pulse generation approach | Settled: deglitch owned by #12 (time-domain filter, distinct from hysteresis); reset-pulse generation recommended as fixed RC/current-starved one-shot, with programmability flagged as an input to #7 rather than ruled on here. |

### Open device questions recommended as inputs to #4's sweep plan

- Vertical PNP: β, absolute VBE and its tempco spread across process
  corners, ΔVBE mismatch for candidate emitter-area/current ratios (e.g.
  1:8), Early voltage.
- Poly and nwell resistor flavors: absolute tolerance, tempco (ppm/°C), and
  ratio-matching — needed to size the PTAT gain resistor ratio and the POR
  divider.
- 3.3 V MOS (`nfet_03v3`/`pfet_03v3`): threshold-voltage spread and tempco,
  needed for the comparator and any subthreshold-biased low-Iq amplifier
  option for the temp sensor's <5 µA stretch.
- **Native/zero-Vt device availability**: confirm whether gf180mcu offers a
  native or zero-Vt NMOS option usable in the startup-assist leg; if none is
  available, the fallback is a minimally-biased standard-Vt divider, which
  achieves a weaker (higher-Iq, later-valid) version of the same
  self-starting property — this changes the startup-ordering margins in
  step 2/3 above and should be re-argued once known.
- Minimum reliable operating voltage of the proposed startup-assist leg and
  of the shared bias core's own start-up kick — needed to pin the actual
  VDD crossing points in the 6-step startup ordering (currently stated only
  qualitatively).

### Risks / bad consequences

- The POR precision stage's <1 µA Iq estimate (0.3–0.8 µA) is tight against
  the target and could be blown by op-amp/comparator design realities not
  visible at this survey level — if #11/#14 evidence shows it doesn't fit,
  the fallback is very likely to loosen Iq at the cost of missing the
  <0.3 µA stretch, not a topology change.
- The 1-pt trim's reach toward the ±1.5 °C stretch is the least certain
  quantitative claim in this record (explicitly labeled as such above) —
  #13 evidence could show the untrimmed curvature term alone exceeds the
  stretch budget, in which case the stretch spec (not the topology) would
  need revisiting by #1.
- This record's 3.3 V assumption, if overturned by #7, invalidates the
  VBE-stack tempco arithmetic and the native-divider rail-fraction argument
  as stated (both scale differently at 5 V) and would require a follow-up
  decision record re-arguing the POR alternatives at 5 V numbers before this
  one could be treated as settled for that flavor.
