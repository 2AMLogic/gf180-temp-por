# DR-015: `por-ramp-rate` release-edge chatter is root-caused to `por_output_chain`'s trip detector, not the starved-loop window — recorded, not fixed

- **Status**: superseded by [DR-016](DR-016-por-ramp-rate-chatter-release-latch.md)
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #56

> **Superseded (same issue, next increment).** This record's negative results
> stand — the chatter is *not* `design/bias_core.md`'s starved-loop window, it
> is ramp-rate independent and temperature-dependent, and `bias_core` /
> `por_comparator` are settled before the window opens. Its **positive**
> claim does not: the chatter does not "originate entirely inside
> `por_output_chain`'s trip detector". A loop-break control
> (`sim/por-ramp-rate/control/`, arms `nokeeper_en_vdd` / `nokeeper_en_vss`)
> shows the oscillation closes through `RESETn` → `temp_core`'s `EN` → the
> **shared `IBIAS` node** → this cell's starve bias, and disappears when that
> path is cut without any device in `por_output_chain` changing. DR-016
> records the corrected mechanism and the one-device fix. Read this record
> for what was excluded; read DR-016 for what it is.

## Context

`sim/por-ramp-rate/records/20260802-000004-32fbaa0.md` (81-point PVT grid,
full four-cell assembly, all four ratified test rates) measures `RESETn`
chattering — crossing its 1.0 V release threshold more than once — at up to
60 of 81 points per rate, up to 109.6 µs against a ≤1 ns bound. 21/81 PASS.
Chatter is worst at 27 °C/125 °C, near-zero at −40 °C, and — the detail that opened
issue #56 — occurs at **all four tested rates**, including the two slow
ones (1 V/s, 10 V/s) where `design/bias_core.md`'s already-tracked
"starved-loop window" (a slew-rate-limited effect specific to the fast
1 V/µs ratified limit) does not apply.

Issue #56 asked whether this is the starved-loop mechanism operating at
smaller scale on slow ramps, or a distinct effect. `sim/por-ramp-rate/
control/run_chatter_probe.py` (a committed, re-runnable control experiment,
`sim/README.md` §"Control experiments") traces `POR_RAW`, `PGDG`, `VREF`,
`BIAS_OK`, `TIM`, `TRIP`, `RSTB` and `RESETn` at three PVT + rate points
chosen to isolate rate from temperature, and answers it:

- **`bias_core` and `por_comparator` are firmly settled before the chatter
  window opens.** `VREF`, `BIAS_OK` and `POR_RAW` each cross their threshold
  exactly once, well before `RESETn` starts toggling, at every point traced
  — including the chattering ones.
- **`TRIP` and `RSTB` (both `por_output_chain`'s own nodes) chatter in
  lock-step with `RESETn`** — same crossing count, same ~37 µs window — at
  the chattering points, and settle in one clean transition at the
  non-chattering one. The chatter therefore originates entirely inside
  `por_output_chain`'s trip detector (`XMDAPI`/`XMDANT`/`XMDBNI`/`XMDBPT` →
  `TRIP`), the release NAND, and the `XMAST` keeper loop on `RSTB`.
- **It is ramp-rate independent**: `tt`/27 °C chatters with a near-identical
  ~37 µs window at both 10 V/s and 1 V/s, a decade apart — the opposite
  signature from the starved-loop window, which is a slew-rate-limited
  effect that would scale with the ramp rate. `TIM`'s approach to the trip
  detector's decision point is set by its own `~2.5 nA / 6.27 pF` time
  constant once `PGDG` has already asserted, independent of how fast `VDD`
  is still moving.
- **It is temperature-dependent**: `tt`/−40 °C settles cleanly at the same
  rate and `VDD` that chatters at `tt`/27 °C — consistent with the trip
  detector being, by design, "two nA-limited current comparators"
  (`design/por_output_chain.md`), a weak-inversion stage whose margin is
  exponentially temperature-sensitive.

Full root-cause writeup: `design/por_output_chain.md`, "The release-edge
chatter — a marginal transition in the trip detector, not the starved-loop
window". Full evidence: `sim/por-ramp-rate/control/results.md`.

## Decision

**This is recorded as a design/sizing defect in `por_output_chain`'s trip
detector, release-NAND and `XMAST` keeper loop — most likely a stability
margin the deliberately weak, nA-class devices in that loop do not carry at
every corner — not an architecture-level tension between two ratified spec
rows the way `design/bias_core.md`'s starved-loop window is.** Unlike that
window (where the fix competes directly against `por-iq`'s already-missed
budget), nothing about this mechanism implies a necessary trade against
another ratified row: it is a local stability property of one node's decision
circuit, in principle fixable by re-sizing or re-biasing that circuit alone.

**No fix is attempted in this record or by this issue's PR.** Root-causing a
regenerative, marginal analog transition — and then sizing a fix that both
resolves it at all 81 points × 4 rates and does not disturb this cell's other
already-passing checks (the ≥1 ms pulse floor, the valid-low floor, the
below-floor startup-assist behaviour) — is design and verification work of a
different scope and risk profile than a root-cause pass, and CLAUDE.md's "no
claim without a testbench" rule means a fix cannot be claimed without a fresh
81-point re-run across all four rates backing it. Issue #56's own PR defers
that work rather than risk landing an unverified analog fix.

`spec/target-spec.md`'s `por-ramp-rate` row is updated to cite this record
and `design/por_output_chain.md`'s new section, and its `pending #1` status
is **unchanged** — the row still needs both this defect fixed *and*
`design/bias_core.md`'s starved-loop window resolved (a separate,
architecture-level question already assigned to #1) before it can be
ratified. No target-spec value is added, removed, or relaxed by this record.

## Alternatives considered

- **Attempt a sizing fix inside this issue** (wider/faster `XMDAPI`/
  `XMDANT`/`XMDBNI`/`XMDBPT`, more decisive `RSTB` drive, or decoupling
  `XMAST`'s gate-`RESETn`/drain-`RSTB` feedback path). **Rejected for this
  record**, not because it is wrong in principle — it is the recommended
  next step — but because sizing an nA-class regenerative loop's stability
  margin correctly, and proving it across all 81 points × 4 rates without
  regressing the ≥1 ms pulse floor or the valid-low floor, is real analog
  design work that deserves its own scoped issue and its own full-grid
  verification, not a same-PR addendum to a root-cause pass.
- **Fold this into `design/bias_core.md`'s starved-loop window as "the same
  finding, smaller scale".** Rejected — the traced evidence (ramp-rate
  independence, `bias_core` settled throughout the chatter window,
  temperature rather than rate as the controlling variable) directly
  contradicts that framing. Conflating them would misdirect any future fix
  at `bias_core`'s amplifier drive, which cannot touch a defect that lives
  entirely inside `por_output_chain`.
- **Leave the finding undocumented pending a fix.** Rejected — CLAUDE.md
  commits this repo to recording measured findings as they are found;
  `target-spec.md`'s own convention (DR-009) is to record a root-cause or
  correction as its own decision record even when no spec value changes.

## Consequences

- **No design or testbench change lands with this record.** Every device in
  `design/por_output_chain.sch` is untouched; `design/netlist/
  por_output_chain.spice` is byte-identical.
- **`sim/por-ramp-rate/`'s 21/81 result stands as the open evidence** for a
  real, fixable defect — not an architecture-level tension needing a spec
  re-cost, and not a testbench artefact.
- **`design/bias_core.md`'s starved-loop window section is corrected** to
  explicitly disclaim ownership of this finding, with a cross-reference to
  `design/por_output_chain.md`'s new section, so the two `pending #1`
  `por-ramp-rate` sub-issues are not conflated in future reading.
- **What becomes possible.** A follow-on fix issue now has a precise target
  (the trip-detector/release-NAND/`XMAST` loop's stability margin,
  temperature-dependent, ramp-rate-independent) instead of an open question
  spanning two cells, and a committed control experiment
  (`sim/por-ramp-rate/control/`) to re-check the mechanism against cheaply
  before committing to a full 81-point × 4-rate re-run.
