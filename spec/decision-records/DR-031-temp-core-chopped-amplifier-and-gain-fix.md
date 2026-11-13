# DR-031: Chop the `temp_core` amplifier, fix the gain term, re-balance the trim ladder

- **Status**: proposed
- **Date**: 2026-11-13
- **Decided by**: Loom Builder agent, issue #451 (step 1 of 3 under #415)

## Context

DR-005 rejected chopping "for wave 1" and said to revisit it if plain
amplifier offset consumed the accuracy budget. DR-029 then measured exactly
that (`sim/temp-accuracy-mc/`, N = 500 per binding point, summarised in
`signoff/evidence/yield/temp-accuracy-mc.yield.json`), as a share of the
untrimmed ±3 °C **[3σ]** budget:

| Term | Share of the ±3 °C budget at 3σ |
|---|---|
| Amplifier input offset `V_os` (`XMI1`/`XMI2`, `XML1`/`XML2`) | 518–571 % |
| Gain `R2/R1` × mirror ratio (`XR1` vs `XR2*`, `XMP1`/`XMP2`/`XMP3`) | 216–244 % |
| PNP pair Δ`V_BE` (`XQ1` vs `XQ8A..H`) | 100–111 % |

DR-029 recorded both rows as measured-not-met, relaxed nothing, and left the
remedy open, listing chopping or auto-zero, a gain-term fix and a trim
re-balance. #415 settled the direction; this record picks the scheme and
specifies the fixes. It edits no schematic or netlist (child 2) and runs no
Monte Carlo (child 3).

## Decision

This record **supersedes DR-005's wave-1 rejection of chopping** (its
"Chopped ΔVBE amplification" alternative) and **closes DR-029's open remedy**.
No row of `spec/target-spec.md` changes value, the single 25 °C gain trim
stays, and the pair is not grown.

### 1. Amplifier: continuous-time chopper

Chop the `temp_core` error amplifier with input and output commutators
(ripple-reduction by a post-filter on the amplifier output, no separate
sampling phase). Rationale: `PTAT`/`CTAT` are analog pad outputs driven
continuously from inside the feedback loop. A chopper keeps the loop closed
and the output valid at all times, so it needs no hold capacitor and adds no
blanking window to a pad that integrators read asynchronously. It needs the
least new circuitry: eight small switches, a two-phase clock and a filter
capacitor, all inside `temp_core`. The cost is residual offset set by
charge injection and ripple at the chop frequency, both budgeted below.

Other schemes, one line each:

- **Auto-zero (sampled offset cancel)** — not chosen. It breaks the loop
  every cycle, so the pads need an output hold capacitor and show
  kT/C-limited sampled noise; it adds more analog area than a chopper.
- **Grow the input pair and load mirror** — not chosen. About 45× area per
  DR-029; not viable against [`area`](../target-spec.md#area).
- **Multi-point or per-part calibration** — not chosen. DR-003/DR-005 ratified
  a single 25 °C trim; this record does not reopen it.

**Clock**: a current-starved ring oscillator local to `temp_core`, nominal
chop frequency **≈100 kHz (estimate)**, above the 1/f corner but low enough
to keep switch-drive current small. It is biased from a **local mirror leg of
the existing `XMT` tail network** (the `XMSU4`-style 1:8 replica pattern), not
from a new tap on the shared `IBIAS` net. Where `IBIAS` is touched at all it
is a mirror-gate load with no DC draw, and the oscillator and switch drivers
are cut off by the existing `EN`-gated pass devices when disabled, so the
[DR-010](DR-010-shared-ibias-disabled-consumer-contract.md) high-impedance
contract holds and the sensor-disabled `por-iq` state sees no oscillator
current.

### 2. Expected cost

Every figure here is an **estimate, not a simulation**; child 2 builds the
netlist and child 3 measures it.

| Quantity | Estimate | Basis |
|---|---|---|
| Iq added by oscillator + non-overlap clock | 0.3–0.5 µA | current-starved ring at ~100 kHz, ~1–2 stages' worth of biased current plus buffering |
| Iq added by switch drive | ≈0.03 µA | 8 switch gates × ~10 fF × 3.63 V × 100 kHz |
| Total added `temp-iq` | **≈0.4–0.6 µA nominal, ≤1.2 µA if the clock runs 2× fast at FF/+125 °C** | the two rows above, with a 2× frequency guard band |
| `temp-iq` at FF / +125 °C / 3.63 V | 15.90 µA measured + ≤1.2 µA ≈ **≤17.1 µA** against the **<20 µA** target | measured figure from `sim/temp-accuracy-vt/` |
| `iq-total` at the same corner | 18.29 µA measured + ≤1.2 µA ≈ **≤19.5 µA** against **<21 µA** | measured figure from the `iq-total` row |
| `por-iq` | unchanged (0.66–2.38 µA measured, <3.0 µA) | sensor disabled ⇒ oscillator and switches off by construction |
| Output ripple at the pad | raw ripple ≈ residual of `V_os` × closed-loop gain, up to tens of mV before filtering; **requirement: ≤1 mV pk-pk at `PTAT`** (≈0.23 °C at 4.31 mV/K) after the on-chip filter | requirement, to be verified in child 3 |
| Residual offset after chopping | **requirement: ≤50 µV at 3σ** (≈0.28 °C at the published 5.57 °C/mV lever) | typical charge-injection-limited result; must be measured |
| Settling / latency | filter time constant of order 10 µs (estimate), one chop period of latency, small against the sensor's thermal time constant | `temp-interface` is analog out, so there is no conversion-time row to bind |

The stretch `temp-iq` <5 µA is already unmet (5.80 µA floor); chopping does
not change that and this record does not claim otherwise.

### 3. Gain-term fix

DR-029's breakdown attributes 0.54–1.05 % σ to `R2/R1` and the
`XMP1`/`XMP2`/`XMP3` mirror ratio together, without separating the two. This
record fixes both by area at constant current density, so overdrive, headroom
and the 265 mV worst-case cascode margin are unchanged:

- Mirror `XMP1`/`XMP2`/`XMP3` (and their `XMPC*` cascodes where the
  mismatch share warrants): 8/4 µm → **16/8 µm** (4× area, σ ≈ halved; W/L
  stays 2).
- Reference resistor `XR1`: 4× area at the same resistance (2 µm → **4 µm**
  wide, length scaled to hold 21.6 kΩ). The `XR2F`/`XR2T*` ladder segments
  take the **same 4 µm width** so the ratio is made of identically drawn
  squares. Common-centroid interdigitation remains #17's layout job.

Area cost estimate: roughly +0.4k µm² (mirror) and +0.7k µm² (`XR1`), plus
the matching ladder-width change; the `area` row is re-checked after child 2.
This is the least certain item in the record because the two gain
contributors were never separated; child 3's breakdown re-run is the check.

### 4. Trim-ladder re-balance

Keep six bits, the single 25 °C trim, the binary short-out topology and the
metal-strapped mechanism. **Halve the range and the LSB**: full range
±7.8 % → **about ±3.9 %**, LSB 0.23 % → **about 0.12 %** of `R2` (≈0.36 °C
per LSB at the 25 °C trim point, from 0.71 °C), obtained by shrinking the
shorted ladder segments against the fixed part `XR2F`. Quantisation falls from
±0.48 °C to roughly ±0.24 °C at 125 °C. The reduced range must still cover
the post-fix trim distribution (about ±2 % at 3σ from the gain and Δ`V_BE`
terms after §3, an estimate) plus the wave-1 code margin; child 3 reports the
trim-code distribution so a range that proves too tight is widened in a
follow-up rather than guessed here.

### 5. Acceptance check

Child 3 re-runs `sim/temp-accuracy-mc/` unchanged on the revised netlist
(N ≥ 500 per binding point, process at each row's binding corner, the
existing seed convention), regenerates the sample sets with
`signoff/yield_samples.py`, and grades them with `klt yield` into
`signoff/evidence/yield/temp-accuracy-mc.yield.json`. It also re-runs
`temp-iq` and `iq-total` over the PVT grid, since §2 is an estimate, and
reports the ripple and residual-offset requirements above.

**Per DR-029 finding 3, closing the trimmed ±1.5 °C row is not guaranteed.**
Removing `V_os` and halving the gain terms leaves ½-LSB quantisation and a
0.68–1.11 °C curvature term the linear attribution did not explain. If a row
still fails after this revision, it **returns to the operator with the
measured numbers**; neither row is relaxed to pass.

## Alternatives considered

See the one-line list under §1. The accuracy rows themselves are not
relaxed, re-defined to exclude mismatch, or re-quoted against multi-point
calibration, for the reasons DR-029 recorded.

## Consequences

- **`design/temp_core.sch` and the netlist change** in child 2: chopper
  switches, clock oscillator, output filter, larger mirror and resistors, and
  a re-ratioed trim ladder. Layout, DRC, LVS and PEX for the cell are redone
  only after child 3 shows the schematic passes.
- **New load on the sensor's own rail, not on `IBIAS`**, but it is the first
  clocked circuit in the block. The ripple at the pad and clock coupling into
  `VDD`/substrate are new things to measure; POR is unaffected only if the
  disabled-state cutoff holds, which child 3 re-verifies.
- **`temp-iq` margin shrinks** from 20 % to an estimated ≈14 % at the binding
  corner and `iq-total` from 13 % to ≈7 %. Both stay inside their ceilings
  on these estimates; if measurement disagrees, the Iq rows go through the
  usual measured-not-met path rather than being relaxed here.
- **DR-005 is superseded in part**: only its wave-1 rejection of chopping.
  A pointer is added to DR-005; its other decisions (PNP core, single
  25 °C trim, shared bias) stand.
- **DR-029's evidence stands** as the "before" measurement; nothing in it is
  edited.
- **Bad consequences**: more area, more Iq and a new clock to verify, for a
  fix that may still leave the trimmed ±1.5 °C stretch unmet.
