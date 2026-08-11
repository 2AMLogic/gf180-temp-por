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
  That table is **RATIFIED** ([DR-008](../spec/decision-records/DR-008-target-spec-ratification.md),
  2026-07-31), but individual rows can still carry their own `pending #1` /
  `TBD-#n` / `conditional #n` status tags per the table's own tagging scheme —
  a claim against a tagged row is a claim against that row's still-open
  status, not against the table as a whole.
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`). Required so post-layout re-runs are
  distinguishable from the original schematic-level record.
  An `extracted` record's netlist is `layout/postlayout/<cell>.spice`
  (`layout/postlayout.py`, from `klt extract --parasitics` plus `klt lvs`'s
  net correspondence) and the record **must** carry the caveat that netlist's
  own header carries — that a small, enumerated set of body/well/plate nets is
  tied where the *schematic* says rather than where the extraction found them
  (the deck's connectivity stack does not reach them), and which devices, if
  any, are still ideal because the layout does not draw them. The per-cell
  list is `layout/postlayout/AUDIT.md`; quoting its row for the cell under
  test is enough. A record that says `extracted` without that caveat overstates
  what the netlist proves.

  **Mechanism** (issues #86, #84): add the experiment to
  `sim/build_tb.py`'s `POSTLAYOUT_FRAGMENTS` dict (the post-layout sibling of
  `FRAGMENTS`). `python3 sim/build_tb.py` then builds that entry's fragment
  from `layout/postlayout/<cell>.spice` instead of
  `design/netlist/<cell>.spice`, into a sibling
  `<experiment-slug>/testbench-postlayout/` directory rather than
  `testbench/` — so a post-layout re-run's evidence sits beside the original
  schematic-level testbench and record rather than replacing them, and the
  schematic-level `testbench/tb.json` / fragment stay untouched. (The
  stimulus is *shared*, read from the schematic sibling's
  `testbench/stimulus.spice`: same DUT ports, so the same stimulus drives
  either netlist unedited.) That directory's own hand-authored `tb.json` sets
  `"netlist_provenance": "extracted"` and a non-empty
  `"netlist_provenance_note"` (the caveat above — `sim/harness/testbench.py`
  refuses to load `"extracted"` without one); `sim/run_corners.py
  <path-to-testbench-postlayout-dir>` runs it and the harness renders both
  fields into the record automatically (`sim/harness/README.md` "Writing a
  testbench" has the full manifest shape).
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

## Control experiments (`sim/<experiment-slug>/control/`)

Occasionally what an experiment needs is not another result but a
**diagnosis**: a small one-variable experiment explaining *why* an earlier
record measured what it did. Those live in an optional `control/`
sub-directory of the experiment they belong to:

```
sim/
  <experiment-slug>/
    control/
      <name>.spice             # stimulus fragment, hand-written
      run_<name>.py            # composes and runs every variant, one process
      decks/<variant>.spice    # the exact deck as run, generated
      logs/<variant>.log       # raw ngspice output, verbatim
      results.md               # the comparison table, generated from the logs
```

Rules, so this never becomes a back door around the record convention:

- **A control is not a record and never substantiates a spec row.** It does
  not go under `records/`, it carries no Claim, and it is not evidence about
  the corner grid — by construction it runs at one or two points. The
  corner-grid evidence for the surrounding experiment is still its records,
  and the closing rule of this document ("anything that substantiates a spec
  row uses this convention and the corner runner") is untouched.
- **Its numbers are generated, never transcribed twice.** `results.md` is
  written by the script from the raw logs of the same run. Prose that quotes
  a control — a design document, a testbench comment — transcribes from
  `results.md` and cites it, so each number has exactly one source.
- **Everything except the one variable is fixed by construction**: the
  variants are composed from the same fragment in the same process, and the
  script reads corner sections and solver options from the harness and from
  the experiment's own `testbench/tb.json` rather than restating them.
- **One `control/` may hold more than one control.** When a second, distinct
  question arises about the same experiment, it gets its own fragment, its own
  `run_*.py` and its own `*_results.md` beside the first rather than being
  folded into it — otherwise the "one variable per run" property is lost and
  the earlier control's numbers stop being reproducible on their own.
  `sim/por-glitch/control/` is the first instance: `run_glitch_probe.py`
  (*why* does the block respond to this glitch — DR-014) and
  `run_depth_sweep.py` (*which* glitches does it respond to at all — DR-017).
- **Re-running a control overwrites its outputs.** That is the opposite of
  the append-only rule and is precisely why a control is not a record: it
  makes no claim, so there is nothing to preserve, and it is cheap enough to
  reproduce on demand. `records/`, `netlist-snapshots/` and `corners/` — the
  things the append-only rule protects — are never touched by a control.

First instance: [`sim/bias-core-startup/control/`](bias-core-startup/control/),
the `gmin` control that diagnoses record `20260801-111049-bc599be`. Second:
[`sim/temp-accuracy-mc/control/`](temp-accuracy-mc/control/), the
mismatch-switch control that demonstrates the three ngspice/PDK mechanisms
`sim/harness/montecarlo.py` rests on (the `sw_stat_mismatch` switch engages
the statistical models; `.option seed` both reproduces and varies the draw;
the override must follow the `.include` to survive). That one diagnoses no
record — it substantiates a *mechanism* every MC record depends on, which is
the same "make the reasoning reproducible rather than asserted" job.

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
illustrates the **Statistical convention** field: `N = 500` samples per
binding point and the distribution reported at ±3σ. It is a distinct claim
from the corner-matrix record above, not a correction of it, so it does
**not** use Supersedes.

**As actually built** (#15), such a record lives in its own experiment
directory — `sim/temp-accuracy-mc/`, `sim/por-threshold-mc/` — and is written
by `sim/run_mc.py` rather than `sim/run_corners.py`. It carries the same nine
fields, but its **Corner matrix run** field names the row's own spec-ratified
binding points instead of the 81-point grid (with the justification inline,
which is the role `--subset-reason` plays for a deterministic subset), and its
**Result** is a per-(binding point, measurement) distribution table rather
than one row per PVT point. See `sim/harness/README.md` § "Monte Carlo
mismatch" for the mechanism and why the two record shapes are deliberately
different.

A **derived** record may reduce an existing record's raw logs without running
a simulation — `sim/temp-accuracy-vt/analyze_derived.py`,
`sim/temp-accuracy-mc/analyze_breakdown.py` and `sim/postlayout_delta.py`
all do this, minting `<record-id>-derived` / `<record-id>-breakdown` /
`<record-id>-postlayout-delta`. A derived record cites its source record(s),
makes no measurement of its own, and does not supersede the record it reads.
Its own **Netlist provenance** field quotes what its *source record* says
about itself (`sim/harness/report.py`'s `source_provenance()`) rather than
restating a manifest: since #86 an experiment has two manifests, and a record
is append-only while a manifest is not, so the record is the only stable
answer.

A post-layout extracted re-run (#18) of the original corner-matrix claim
lives under the same experiment directory with its own `<record-id>`,
`Netlist provenance: extracted`, and a `Supersedes` field naming the
schematic-level record it re-runs. The **schematic-vs-extracted delta
summary** is `sim/postlayout_delta.py`'s derived
`<record-id>-postlayout-delta` beside it, not free text edited into either
record's Result section: the corner runner writes one record from one run and
never reads a second, and the append-only rule forbids going back and
inserting the comparison afterwards. That derived record joins the two grids
on corner-id, re-evaluates the experiment's own `tb.json` checks against
both with the harness's own evaluator, and classifies every checked
measurement:

| transition | meaning |
|---|---|
| `ok -> ok` | no regression |
| `ok -> MISS` | **a regression** — it passed on the schematic and fails post-layout |
| `MISS -> MISS` | a miss the schematic-level record already carried |
| `MISS -> ok` | an improvement |

Per CLAUDE.md an `ok -> MISS` row goes back to its owning design issue; the
target is not relaxed to absorb it, and the tool exits non-zero so the row
cannot be scrolled past. Distinguishing it from `MISS -> MISS` is the whole
point — without that, re-running an already-failing row would manufacture a
false regression and a real one would be lost in the noise. The same record
also tabulates the extracted netlist's per-net interconnect ΣR/ΣC on the
nodes the caller names as high-impedance, which is what #18's acceptance
criteria mean by reporting parasitic loading "explicitly, not just
pass/fail".

**The index of which experiments have an extracted record, and what the
whole set does and does not establish, is
[`design/temp_por_top.md`](../design/temp_por_top.md) § "Closing roll-up for
issue #18".** Read it before citing any single post-layout record: it names
the one experiment with no post-layout re-run (and why that is correct), the
one device still schematic-ideal in every extracted netlist, the records
stamped "not citable as a clean-tree result", and the two effects — rail IR
drop and net-to-net coupling — that **no** record in this directory is
capable of evidencing today, whatever it appears to show.

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
