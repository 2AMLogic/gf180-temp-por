# DR-001: Supply flavor (gf180mcu 3.3 V vs. 5 V)

- **Date:** 2026-07-30
- **Decided by:** Builder agent, issue #7
- **Status:** proposed (ratification is issue #1's call — this record does not
  edit the README spec table)

## Context

The draft spec (README "Target specification") pins a POR threshold of
**2.6 V ±5%** but never states which gf180mcu supply/device flavor the block
runs on. gf180mcu offers, among others, `nfet_03v3`/`pfet_03v3` (3.3 V core),
and `05v0`/`06v0` thick-oxide families (5 V / 6 V I/O-class). The temp sensor
+ POR pair is a single-supply canary block (no separate core/IO domain
split described anywhere in the repo), so "supply flavor" here means the one
rail the whole block is designed against.

Template note: `spec/decision-records/TEMPLATE.md` (issue #6) has not landed
on `origin/main` as of this writing (only `spec/.gitkeep` exists) — this
record bootstraps the field set instead (title/date/decided-by, status,
context, decision, alternatives rejected, consequences), per the issue's
Coordination section. Filenames follow the `DR-NNN-<slug>.md` convention
issue #6 is expected to specify; reconcile numbering while records remain
`proposed` if #6 lands with different guidance.

Landed-artifact check: neither #3 (architecture survey) nor #4 (device
characterization) has landed artifacts in `spec/` or `sim/` as of this
writing (both dirs contain only `.gitkeep`). Per issue #7's Coordination
section this does not block the decision — the margin arithmetic below
stands on the draft spec's own numbers. If #3's memo or #4's sweep data land
later, a follow-up record (or an amendment while this one is still
`proposed`) should reconcile against them.

## Decision

**Pin the 3.3 V gf180mcu flavor as the block's supply.** VDD nominal = 3.3 V;
primary active devices are the 3.3 V core family (`nfet_03v3`/`pfet_03v3` or
the gf180mcu-equivalent naming). 5 V/6 V devices are not used in the signal
path unless a specific downstream issue (e.g. #8's pad-ring/ESD design)
requires them for I/O purposes — that is #8's call, not this record's.

**Threshold-to-rail margin arithmetic (the reason for 3.3 V):**

- Worst-case-**high** POR threshold: 2.6 V × 1.05 = **2.73 V**
- Worst-case-**low** 3.3 V rail (±10% supply tolerance): 3.3 V × 0.90 =
  **2.97 V**
- Release margin at worst case: 2.97 V − 2.73 V = **240 mV** — the rail is
  guaranteed to sit comfortably above the highest possible threshold even at
  the lowest allowed steady-state supply, which is the behavior a POR release
  decision needs (reset must not be marginal at rated low-rail conditions).

**In-spec-during-ramp / accuracy window (feeds #13's supply-sensitivity
sweep):** the temp-sensor accuracy target (±3 °C untrimmed / ±1.5 °C
1-pt-trim stretch, per the README table) is valid across **±10 % of the
pinned 3.3 V nominal rail evaluated at steady state** — i.e. **2.97 V to
3.63 V**, post-POR-release, with the rail settled (not slewing). Accuracy is
**not** specified while the rail is ramping or below POR release — behavior
in that regime is a POR/reset question, not a temp-sensor-accuracy question,
and is governed by DR-004 (reset polarity/drive, below-floor requirement)
and DR-003 (pulse timing), which #10/#12/#14 test against instead. This is
an explicit, intentional narrowing (not a deferral): #13's accuracy
testbench sweeps VDD only across 2.97–3.63 V, always post-release.

## Alternatives Rejected

**5 V gf180mcu flavor — rejected.**

- The 2.6 V threshold sits at only ~52 % of a 5 V nominal rail (2.6 / 5.0),
  which means POR would release far too early relative to the rail range a
  5 V-rated design is meant to operate across — defeating the purpose of a
  POR gate (ensuring internal circuits see enough headroom before running).
- 3.3 V-flavor devices (`nfet_03v3`/`pfet_03v3`) cannot sit directly on a 5 V
  rail (Vgs/Vds overstress), so a 5 V choice would force the `05v0`/`06v0`
  thick-oxide families throughout the signal path, not just at I/O. Those
  devices are larger and change the characterization/area profile of every
  sub-block.
- This directly contradicts the README's stated selection rationale ("tiny
  area rides along on any shuttle seat") — thick-oxide-throughout is a
  meaningfully larger design than a 3.3 V core implementation for the same
  function.

No other flavor (e.g. a mixed 3.3 V-core/5 V-IO split) was considered viable
for this record's scope: this is a single-pad-count canary block with no
described core/IO domain separation, so a split flavor is a design-topology
question for #8, not a supply-flavor decision for #7.

## Consequences (README spec-table rows touched)

- **New row needed:** the ratified table (#1) should add an explicit
  **"Supply voltage"** row — `3.3 V nominal, ±10 %` — since the draft table
  currently has no row for it at all; #1 should add this alongside
  ratifying the existing rows below.
- **POR threshold** row (`2.6 V ±5%`): unchanged in value, but its
  interpretation is now anchored — the 2.6 V ±5 % number is meaningful
  specifically against a 3.3 V ±10 % rail (see margin arithmetic above).
- **Temp accuracy (untrimmed)** row (`±3 °C`): consequence is the explicit
  measurement window this record adds — ±10 % of 3.3 V, steady-state only —
  which #13 must encode as its supply-sweep bounds.
- Downstream: #13's supply-sensitivity sweep bounds are fully specified by
  this record (2.97–3.63 V, steady state); no deferral needed.
