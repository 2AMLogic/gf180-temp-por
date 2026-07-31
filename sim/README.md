# sim/ — evidence record format

This directory holds simulation testbenches and their results. Results are
**append-only evidence**: once a record is written, it is never edited or
deleted. A re-run — even one that corrects a mistake — mints a new record
with a new ID; a correction references the record it supersedes rather than
overwriting it in place.

This convention exists because CLAUDE.md commits this repo to two rules that
need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench. Every
  recorded result carries the full PVT corner matrix (−40/27/125 °C, ±10%
  supply, process corners) unless the record explicitly states why a subset
  was used.
- **`sim/` is append-only evidence.** Re-runs get new records; records are
  never edited or deleted.

**This file is the authoritative convention.** The corner runner that produces
records in this format — how to run it, how to write a testbench, PDK
resolution, corner definitions — is documented in
[`sim/harness/README.md`](harness/README.md). If the harness and this document
ever disagree, this document wins and the harness is the thing that gets fixed.

This convention and the harness beneath it are **ported from the
`2AMLogic/gf180-bandgap` sister repo** (their issue #2 / PR #23), as CLAUDE.md
mandates, rather than invented here. The deliberate divergences — and only
those — are recorded in
[`spec/decision-records/DR-006-sim-harness-port.md`](../spec/decision-records/DR-006-sim-harness-port.md).

## Directory / naming convention

Each testbench topic gets its own experiment directory:

```
sim/
  <experiment-slug>/                 # e.g. temp-accuracy, por-threshold, por-pulse, mc-untrimmed
    testbench/                       # testbench netlist(s) / xschem export used
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.log              # raw ngspice output per PVT point
                                      # e.g. ss_-40c_2.97v.log
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short, descriptive, kebab-case name for what is
  being verified (`temp-accuracy`, `temp-iq`, `por-threshold`,
  `por-hysteresis`, `por-pulse`, `mc-untrimmed`, ...). One directory per
  distinct claim being tested, not per run. This is the unit that #13 and
  #14 map ratified spec rows onto: **every ratified spec row maps to a named
  experiment slug**, so a spec row with no `sim/<slug>/` directory is a
  visible coverage hole rather than a silent one.
- **`<record-id>`** — unique and traceable:
  `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (e.g. `20260729-153000-1a7ef75`).
  Re-runs simply mint a new `<record-id>`; nothing under `records/` is ever
  edited in place. The same `<record-id>` ties together the netlist snapshot,
  the raw per-corner logs, and the summary record for one run.
- **`<corner-id>`** — `<process-corner>_<temp>c_<supply>v.log`, e.g.
  `ss_-40c_2.97v.log`, `tt_27c_3.30v.log`, `ff_125c_3.63v.log`.
- **`testbench/`** is not versioned per record — it holds the current
  testbench netlist(s)/xschem export(s) used to generate records. If the
  testbench itself changes in a way that could affect comparability across
  records, note that in the new record's summary (e.g. under Claim or a
  free-text note).

## Summary record format

Each run produces one `records/<record-id>.md` file with the following
fields:

- **Record ID** — the `<record-id>` for this run (matches the filename and
  the corresponding `netlist-snapshots/` / `corners/` subdirectory).
- **Claim** — which spec parameter/line this record substantiates, referenced
  by its row anchor in the target-spec table:
  `spec/target-spec.md#<row-id>` (e.g. `spec/target-spec.md#por-vth-rise`).
  That table is still DRAFT until #1 ratifies it, so a claim against it is a
  claim against a proposed target until then.
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`). Required so post-layout re-runs are
  distinguishable from the original schematic-level record.
- **Corner matrix run** — explicit list of (process corner, temperature,
  supply) points actually executed. Must be the full PVT matrix from
  CLAUDE.md (−40/27/125 °C, ±10% supply, process corners) unless the record
  states why a subset was used.
- **Statistical convention** (when applicable, e.g. Monte Carlo mismatch
  analysis) — N samples and sigma level reported. Used for distribution
  claims that are not a per-corner pass/fail (e.g. #15's untrimmed
  temperature-accuracy and POR-threshold spreads).
- **Result** — per-corner pass/fail, plus an overall pass/fail against the
  ratified spec value.
- **Links** — paths to the testbench file(s), the frozen netlist snapshot,
  and the raw per-corner logs used to produce this record.
- **Timestamp / author** — when the record was created and who (human or
  agent) created it.
- **Supersedes** (optional) — the prior `<record-id>` this record supersedes,
  for corrections or for a post-layout extracted re-run that reports a
  schematic-vs-extracted delta against the schematic-level record. Mirrors
  the status/supersession language of `spec/decision-records/TEMPLATE.md`,
  so both conventions read as one house style.

## Append-only rule

`records/*.md` files are never edited or deleted after creation. A re-run or
a correction always creates a new record with a new `<record-id>`. If it
corrects or replaces a prior result, it references that prior record via
**Supersedes** rather than overwriting it. This applies even to typo fixes —
the append-only guarantee is what makes `sim/` usable as an evidence trail;
"fixing" an existing record in place would defeat that.

## Worked example

Directory layout for an untrimmed temperature-accuracy claim, followed by a
Monte Carlo re-check of the same claim, followed by a post-layout extracted
re-run:

```
sim/
  temp-accuracy/
    testbench/
      tb.json
      tb_temp_accuracy.spice
    netlist-snapshots/
      20260729-153000-1a7ef75.spice
      20260805-091200-7c2f9de.spice
    corners/
      20260729-153000-1a7ef75/
        tt_27c_3.30v.log
        ss_-40c_2.97v.log
        ff_125c_3.63v.log
        ...
      20260805-091200-7c2f9de/
        ...
    records/
      20260729-153000-1a7ef75.md
      20260805-091200-7c2f9de.md
```

`records/20260729-153000-1a7ef75.md` (placeholder values — no ratified spec
values exist yet, see #1):

```markdown
# Record 20260729-153000-1a7ef75

- **Record ID**: 20260729-153000-1a7ef75
- **Claim**: `spec/target-spec.md#temp-accuracy-untrimmed` — untrimmed
  temperature error over −40…125 °C, ±3 °C target (draft target; ratification
  pending #1)
- **Netlist provenance**: schematic (`design/temp_sensor.sch`)
- **Corner matrix run**:
  - Process: tt, ff, ss, fs, sf, res_ff, res_ss, bjt_ff, bjt_ss
  - Temperature: −40 °C, 27 °C, 125 °C
  - Supply: 2.97 V, 3.30 V, 3.63 V (±10% of 3.3 V, per DR-001)
  - (81 point full-factorial grid — process × temperature × supply)
  - Full PVT matrix per CLAUDE.md.
- **Statistical convention**: N/A (corner-matrix claim, not a distribution
  claim)
- **Result**:
  - tt/27C/3.30V: PASS (placeholder value)
  - ss/-40C/2.97V: PASS (placeholder value)
  - ... (remaining corners: PASS, placeholder values)
  - **Overall: PASS** (placeholder — pending ratified spec, #1)
- **Links**:
  - Testbench: `sim/temp-accuracy/testbench/tb_temp_accuracy.spice`
  - Netlist snapshot: `sim/temp-accuracy/netlist-snapshots/20260729-153000-1a7ef75.spice`
  - Raw logs: `sim/temp-accuracy/corners/20260729-153000-1a7ef75/`
- **Timestamp / author**: 2026-07-29T15:30:00Z, agent-builder
- **Supersedes**: (none — first record for this claim)
```

A later Monte Carlo mismatch check of the same untrimmed claim (#15)
illustrates the **Statistical convention** field: nominal PVT only, with
`--subset-reason` naming why, `N = 500` samples and the distribution reported
at ±3σ. It is a distinct claim from the corner-matrix record above, not a
correction of it, so it does **not** use Supersedes.

A later post-layout extracted re-run (#18) of the original corner-matrix
claim would live under the same `temp-accuracy/` experiment directory with
its own `<record-id>`, `Netlist provenance: extracted (layout/... ->
extracted netlist)`, and a `Supersedes: 20260729-153000-1a7ef75` field
carrying a schematic-vs-extracted delta summary in its Result section.

## Pre-harness evidence (`sim/devchar/`, issue #4)

Issue #4's device-characterization sweeps were written before this harness
existed and use their own orchestration layer (`sim/devchar/run_devchar.py`,
appending CSV under `sim/devchar/results/`). They are **explicitly left
as-is** — not rewritten, not renamed, not re-run through the corner runner:

- `sim/` evidence is append-only. Retrofitting those results into the
  `records/<record-id>.md` schema would mean rewriting existing evidence,
  which the rule above forbids outright. A migration would have to be a
  *fresh run* minting *new* record-ids, and there is no reason to spend
  simulator time re-deriving device curves that are already recorded.
- They are device characterization, not spec claims. No ratified spec row
  depends on them, so they are not part of the #13/#14 spec-row coverage
  map. Their job is to inform design choices, and they do that as they are.
- `sim/devchar/` has no `testbench/tb.json`, so the runner's experiment
  discovery ignores it. The two conventions coexist without collision.

**Going forward**, anything that substantiates a spec row — including any
re-characterization whose result is cited in a claim — uses this convention
and the corner runner. `sim/devchar/` is the one grandfathered exception, and
it does not grow.
