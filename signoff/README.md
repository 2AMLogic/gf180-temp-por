# T1 signoff — the verdict of record

This directory is **this block's machine-readable claim about its own
evidence**, graded mechanically rather than read by hand.

| File | What it is |
|---|---|
| [`block-manifest.json`](block-manifest.json) | The claim. Declares the block's `kind` and, per T1 checklist item, the evidence envelope that backs it. This is the file the fleet roll-up (`klt signoff --fleet`) consumes. |
| [`tier-report.json`](tier-report.json) | The verdict. `klt signoff --manifest block-manifest.json --format json` output, committed as an append-only evidence record. |
| [`evidence/`](evidence/) | Hand-rolled *generic* evidence envelopes — the opt-in wrapper for a record no `klt` verb produces. T1 item 8 accepts one; items 1, 2, 9 and 10 accept one only when it is bound to an audited artifact. Also holds the three audited inventories those envelopes bind to. |
| [`inventories.py`](inventories.py) | Builds and verifies those inventories (member-file hashes, spec-row to testbench audit). Imported by `check.py`. |
| [`toolchain.json`](toolchain.json) | The `klt` build that **grades** this block, pinned separately from `layout/toolchain.json`'s pin on the build that **produced** the DRC/LVS evidence. |
| [`check.py`](check.py) | The gate CI runs. Re-grades the tree and fails on any drift from the committed verdict. |

Checklist: [`klayout-tools/docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md).
Grader contract: [`klayout-tools/docs/cli/signoff.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/signoff.md).

## Why this replaced a prose checklist

Issue [#145](https://github.com/2AMLogic/gf180-temp-por/issues/145) tracked
the gap to T1 as a hand-maintained checkbox list, re-read by hand on
2026-08-09, 2026-08-15 and 2026-08-21, and closing at **10/10 pass**. A
hand-read goes stale the moment either the evidence or the checklist moves,
and both have: the checklist grew an eleventh item on 2026-09-17
([klayout-tools#2025](https://github.com/2AMLogic/klayout-tools/issues/2025)),
which invalidated every prior hand-read in the fleet at a stroke.

**`tier-report.json` is now this repo's verdict of record.** Where it and any
prose disagree — including #145's checkboxes — the report wins, and the prose
is the thing that is wrong.

## The current verdict: `tier: null`, 9 of 11 items met

Rendered by `klt 0.8.0` against its bundled `docs/design-evidence-tiers.md`.
Block `kind` is **`analog`**: a single analog partition with no synthesized
or placed-and-routed digital sub-block. The POR output chain is logic, but it
is hand-captured as schematics and hand-drawn as layout — no RTL, no
synthesis, no P&R — so nothing in this repo produces a Digital-column
artifact, and there is no partition boundary to declare.

| # | Item | Verdict | What actually backs it |
|---|---|---|---|
| 1 | Design sources | **`met`** | `evidence/t1-item-1-design-sources.json`, a generic envelope bound (`artifact_binding.input_verified: true`) to `evidence/inventory-design-sources.json`: the 5 xschem schematics under `design/` and the 5 derived `design/netlist/*.spice`, each with its sha256, plus the regeneration gate `design/netlist.py --check`. **Binding limits below.** |
| 2 | Layout | **`met`** | `evidence/t1-item-2-layout.json`, a generic envelope bound directly to `layout/cells/temp_por_top.gds` (`sha256:a119a12b…`, the hash items 3, 4 and 11 pin). Its summary names the other 5 GDS under `layout/cells/` and the gate `layout/build_cells.py --check`. **Binding limits below.** |
| 3 | DRC clean | **`met`** | `layout/reports/temp_por_top/drc.json` — `status: clean`, deck `gf180mcu`, pinned to `sha256:a119a12b…` which is the sha256 of the committed `layout/cells/temp_por_top.gds`. **Coverage gaps disclosed below.** |
| 4 | LVS clean | **`met`** | `layout/reports/temp_por_top/lvs.json` — `status: match`, engine `klayout` 0.30.10, 145/145 nets, 239/239 devices, 6/6 pins. **Warnings-only mismatches and a freshness caveat disclosed below.** |
| 5 | Full corner verification vs a ratified spec | `unmet` / `no_evidence` | The 81-point PVT matrix exists under `sim/*/records/`, but as this repo's own Markdown evidence records — there is no `klt sim` JSON envelope to cite. The manifest already declares `spec_rows."5"` (every `measured`/`derived` row in `evidence/inventory-testbenches.json`, each a gap naming the issue that will cover it: [#388](https://github.com/2AMLogic/gf180-temp-por/issues/388), [#389](https://github.com/2AMLogic/gf180-temp-por/issues/389)); `klt 0.8.0` accepts it but only surfaces it (`partial_coverage` + `declared_gaps`) once a first envelope is cited, so the verdict stays `no_evidence` until then. |
| 6 | Statistical claims carry Monte Carlo evidence | `unmet` / `no_evidence` | N=500 MC records exist (`sim/temp-accuracy-mc`, `sim/por-threshold-mc`) with a reproducible seed formula and a deterministic negative control, but there is no `klt yield` report. |
| 7 | Post-layout verification | **`met`** | `layout/reports/temp_por_top/pex.json`, a `klt pex` report (`--measure-command` mode) on `layout/cells/temp_por_top.gds` against `design/netlist/temp_por_top.spice`: the `sim/por-vth` full-assembly bench over all 81 PVT corners, 23 measurements per corner, 1863 `delta[]` rows, none errored. Covers `por-vth-rise`, `por-vth-fall`, `por-hysteresis` only; every other row with a post-layout bench is a declared gap (`spec_rows."7"`, [#391](https://github.com/2AMLogic/gf180-temp-por/issues/391)). **`body_bias.status` is `unbiased`** (64 PMOS bodies); see the item 7 section below. |
| 8 | Characterization report | **`met`** | `evidence/characterization-report.json`, a generic envelope wrapping `spec/target-spec.md`, pinned to `sha256:d78561ee…`. **Disclosed exceptions below.** |
| 9 | Testbenches shipped | **`met`** | `evidence/t1-item-9-testbenches.json`, bound to `evidence/inventory-testbenches.json`: all 29 spec rows classified, every measured row mapped to the committed `testbench/` and `testbench-postlayout/` files of 22 `sim/` experiments (each file hashed, with the testbench's own PVT settings from its `tb.json`), the cold-start invocations from `sim/harness/README.md`, and the PDK pin from `.github/workflows/ci.yml`. **Binding limits below.** |
| 10 | Repo hygiene | **`met`** | `evidence/t1-item-10-repo-hygiene.json`, bound to `evidence/inventory-repo-hygiene.json`: `README.md`, `LICENSE`, `spec/target-spec.md` and `.github/workflows/ci.yml`, each hashed, with four stated assertions re-checked on every run. **Binding limits below.** |
| 11 | Power delivery (structural) | **`met`** | `layout/reports/temp_por_top/erc_supply.json` (a `klt erc` supply-spec run) plus `layout/reports/temp_por_top/lvs.json`, whose `net_correspondence` carries both supplies ([#300](https://github.com/2AMLogic/gf180-temp-por/issues/300), `ties[]` added by [#310](https://github.com/2AMLogic/gf180-temp-por/issues/310)). The report has `erc_finding_count: 0` — zero `erc.supply_short`, zero `erc.unconnected_net`, and zero `erc.missing_tie`, with all four declared `ties[]` entries graded `checked` (none `skipped`/degenerate) — pinned to `sha256:a119a12b…` (the committed GDS) and `sha256:773047b1…` (the committed spec). The grader reports all four ties as caller-asserted (`ties_checked_by_assertion`), three of them resting on an asserted well (`ties_checked_by_well_assertion`) — this is provenance, not a weaker bar; see `layout/README.md`'s "Item 11" section. **Produced with the released `klt 0.7.0`** (PR #351's operator ruling declined to grade item 11 on an earlier unreleased-build run; the report was regenerated on the released tool and the caveat retired — see below), with the spec's own declared coverage disclosed below. |

**9 of 11 is a lower number than #145's 10/10, and both are honest reads of
different questions.** #145 asked "does this repo contain the artifact the
item describes?" and largely, it does. This report asks "is there a passing,
fresh, machine-readable envelope of the kind this item accepts?" and for 3
items (5, 6) there is not. Nothing regressed between the two reads; the second
question is simply stricter, and it is the one a downstream consumer of this
block can actually verify without taking our word for it.

## Disclosures that travel with the `met` verdicts

A `met` verdict is not a statement that the check had no blind spots. The
checklist requires the blind spots to be enumerated in the claim, and `klt
0.7.0`'s report quotes the DRC envelope's `coverage` block into item 3's
citation (klayout-tools#2002), but quoting is not grading — `klt signoff`
grades item 3 on `status: "clean"` alone. So they are stated here, and must
agree with that quoted block.

### Item 3 — DRC coverage gaps

From `layout/reports/temp_por_top/drc.json`'s own `coverage` block:

- **`rules_skipped`**: `comp.space.mv.1`, `comp.width.mv.1`,
  `metaltop.space.1`, `metaltop.width.1`, `pad.enclosing.metal5.1`. MV
  comp spacing/width, top-metal spacing/width and pad-to-metal5 enclosure are
  **not checked** by this deck run.
- **3 deck layers drawn but unchecked**: `37/0`, `53/0` and `55/0` are in
  `deck_layers` but not in `layers_checked`.
- **9 layers present in the stream with no rules at all**
  (`layers_in_stream_without_rules`): `31/0`, `32/0`, `34/10`, `36/10`,
  `49/0`, `62/0`, `110/5`, `117/5`, `117/10`.
- **`deck_scope`** (the only DRM chapters the deck transcribes): 7.4 Nwell,
  7.5 Comp, 7.7 Poly2, 7.12 Contact, 7.13 Metaln, 7.14 Vian, 7.15 MetalTop,
  9.1 Bond Pad, 10.4.2 MIM Option B, 10.7 DRC_BJT Mark Layer.

`status: clean` means "no violation of the rules this deck actually ran".
It does not mean the geometry on those unchecked layers, or under those skipped rules, is correct.

### Item 4 — warnings-only mismatches, and a freshness gap the grader cannot close

- `mismatch_count: 2`, both severity `warning`, both category
  `device.body_unverified`: 71 NMOS body terminals compared against the
  deck-synthesized `vsubs` net rather than a real schematic net, and 64 PMOS
  body terminals compared against an anonymous deck-synthesized well net.
  The gf180mcu deck draws no distinct NMOS substrate/tap layer and no
  distinct well-tap layer, so body connectivity is **not independently
  verified** by this compare.
- Single engine only. No second independent engine's concurring verdict
  (which the checklist marks as strengthening, not required).
- **The citation now carries a `content_hash` pin.** Through `klt 0.5.0`,
  `klt lvs` populated no `provenance.input` block, so item 4 could not be
  pinned and the layout hash lived only in `environment.layout_sha256`, which
  the grader's staleness gate does not read
  ([klayout-tools#1969](https://github.com/2AMLogic/klayout-tools/issues/1969)).
  The committed `lvs.json` was produced by `klt 0.6.0`, whose
  `provenance.input.content_hash` is `a119a12b…` — byte-identical to the
  committed `layout/cells/temp_por_top.gds` — and the grader now
  quotes it in item 4's citation. The grader still reports
  `input_verified: null` for it, so it does not itself re-hash the GDS;
  `check.py` keeps the repo-side gate
  (`layout/lvs_reference.py --check-gds-hash`) that re-hashes the committed
  GDS against every committed report on every CI run.

### Item 8 — what the generic envelope does and does not assert

`evidence/characterization-report.json` asserts that the aggregated,
current per-spec-row characterization artifact T1 item 8 asks for **exists**
— `spec/target-spec.md`, 29 anchored rows, each with a measured value, a
binding PVT corner, a status tag, and a link to the `sim/` record the verdict
rests on. It does **not** assert that every row passes, and two do not:

- `temp-accuracy-untrimmed` / `temp-accuracy-trimmed` are recorded
  **measured-and-not-met** under
  [DR-029](../spec/decision-records/DR-029-temp-accuracy-mismatch-not-met.md)
  — Monte Carlo mean ±3σ of −19.23…+19.63 °C against a ±3 °C target, roughly
  6.5× over budget. The target was deliberately **not** relaxed.
- Rows tagged `pending #1` are measured and recorded but await the operator's
  ratification sweep.

A generic envelope is a hand-written assertion; `klt signoff` reads its
`status` and nothing else. The one thing that makes it checkable is the
pinned hash, and `check.py` re-derives that hash from `spec/target-spec.md`
itself on every run — so editing the spec table without re-reading this claim
fails CI rather than silently invalidating item 8.

## Items 1, 2, 9, 10 — bound to audited artifacts

Items 1, 2, 9 and 10 are claims about what a repository *contains*, and no
`klt` verb backs them. Until `klt 0.7.0` the grader's rule for them was blunt:
**any** passing native envelope rendered them `met`, regardless of topical
relevance, so this manifest left all four uncited rather than have a DRC
report say something it never checked. That gap was closed upstream
([klayout-tools#2718](https://github.com/2AMLogic/klayout-tools/issues/2718),
resolved by klayout-tools#2843, in the released `klt 0.7.0`): a `kind:
generic` envelope is accepted for these four items when it declares
`"t1_item": <n>`, names the audited artifact in `provenance.input.path`
(here always `{"path": ..., "scope": "repo"}`) with its `content_hash`, the
manifest pins the same hash, and the grader re-hashes the artifact. Each
`met` citation then carries `artifact_binding` with `input_verified: true`.

| Item | Envelope | Bound artifact |
|---|---|---|
| 1 | `evidence/t1-item-1-design-sources.json` | `evidence/inventory-design-sources.json` |
| 2 | `evidence/t1-item-2-layout.json` | `layout/cells/temp_por_top.gds` |
| 9 | `evidence/t1-item-9-testbenches.json` | `evidence/inventory-testbenches.json` |
| 10 | `evidence/t1-item-10-repo-hygiene.json` | `evidence/inventory-repo-hygiene.json` |

No native (`drc`, `lvs`, `erc`) envelope is cited for any of the four.

### What the binding does and does not prove

**Binding proves the artifact's bytes are the ones the envelope audited. It
does not prove the artifact is complete or that the files it describes are
unchanged** — a modified schematic leaves the inventory's own bytes alone. So
the inventories list **every member file with its sha256**, and
`signoff/inventories.py` rebuilds each from the live tree on every
`check.py` run and fails, naming the file, on a changed member, a deleted
one, or a relevant file the inventory does not list. The envelopes
themselves are generated, not written: `check.py` fails on a hand-edited
summary or provenance. `check.py --regen` rebuilds the inventories,
envelopes and manifest pins together, and **refuses to write anything when
the audit fails**, so a `pass` is never recorded over a claim the tree does
not support.

The audits behind each `pass`:

- **Item 1.** Every `design/*.sch` has a `design/netlist/*.spice` of the same
  name and vice versa. The regeneration gate (`design/netlist.py --check`)
  needs xschem and the PDK, so it runs in the `pdk-checks` CI job, **not**
  here: this item attests the netlists are committed alongside their
  schematics and unchanged, not that they were re-derived today.
- **Item 2.** Bound to the assembled top cell only; the other five GDS are
  named in the envelope's summary, and `check.py` fails if a `.gds` is added
  to or removed from `layout/cells/` without the summary moving.
  `layout/build_cells.py --check` is named, not re-run (it needs the PDK).
- **Item 9.** Every spec row (an `<a id>` anchor in `spec/target-spec.md`)
  must be classified. A row that claims a measurement must name `sim/`
  experiments that ship a committed `testbench/` — all 15 `measured`/`derived`
  rows do. Two rows' evidence directories ship no testbench of their own and
  the inventory says so rather than hiding it: `sim/por-iq/` is a derivation
  over `temp-accuracy-vt`'s raw logs (`por-iq` and `iq-total` list that
  testbench), and `sim/devchar/` is cited only as an informative physics
  anchor. Rows that claim no simulated number (conditions, interface
  decisions, the analytic self-heating bound, `area` from
  `layout/reports/temp_por_top/stats.json`, and the
  `[TBD]` `por-digital-min-vdd`) are listed as such, not as measurements.
  **It does not re-run a testbench or re-derive any measured value**, and it
  does not assert any row passes — the disclosed exceptions under item 8
  still apply.
- **Item 10.** `LICENSE` contains the Apache License text; `README.md` states
  what the block is, links the spec, has a reproduction section and a
  license section; the spec has anchored rows; CI runs `signoff/check.py`.
  Because `ci.yml` and the spec are hashed members, editing either requires
  `--regen` and a look at the diff.

Consequence for the fleet roll-up
([2AMLogic/2am#956](https://github.com/2AMLogic/2am/issues/956)): the first
unmet item is now 5, so `blocking_item` reports a real blocker rather than
item 1. Items 5 and 6 are what stand between this block and T1.

## Item 7 — `klt pex` evidence, its `body_bias` status, and what was patched

`layout/reports/temp_por_top/pex.json` is `klt pex 0.8.0` run with
`--measure-command` (`sim/pex/run_pex.sh` reproduces it; the staged requests are
committed under `layout/reports/temp_por_top/pex-requests/`). The grader quotes
the report's `body_bias` on the citation and does not grade on it, so the
claim states it:

- **`body_bias.status: "unbiased"`**, `unbiased_device_count: 64`, on six
  deck-synthesized well nets (`$50`, `$51`, `$53`, `$65`, `$100`, `$101`):
  every PMOS body in the extraction sits on an Nwell island the gf180mcu
  deck found no tie for. That is the same condition `klt lvs` reports as
  `device.body_unverified` (item 4). It is a property of the deck, not
  evidence that the drawn wells are untied.

The comparison would be physically wrong if those wells floated, so the
extracted leg is **patched before it is simulated**; `sim/pex/measure.py`
prints each patch on stderr and keeps `extracted-patched.spice`:

1. Each of the 19 extracted `Q… bjt` cards becomes `XQ… pnp_10p00x10p00` (the
   deck has one generic bipolar class), after checking `AE=100P`.
2. The six unbiased well nets get a 0 V source to the net the schematic puts
   that well on (`layout/postlayout.py:body_ties()`, found through a
   `klt lvs 0.8.0` net correspondence): five go to `VDD`, `xtemp.NW2` to
   `xtemp.NT`; the bipolar base well `xbias.NWQ` goes to `VSS`.
3. The `.SUBCKT` header lists the same pins in the schematic's order.

`klt pex` therefore reports `body_bias` for the *unpatched* extraction, and
the numbers were measured on the patched one.

Settings that decide the numbers, all in `sim/pex/run_pex.sh`:
`--deck-option poly_res=3k` (the schematic's resistor flavour; the default `1k`
shifts the divider) and `--substrate-tie-ohms 0` (the default leaves the
synthesized substrate floating at 1e12 ohm, so every ground capacitance hangs
off a floating node and couples nets to each other: with it, VREF's 127.5 fF
to `vsubs` removed the comparator's hysteresis entirely. Dropping that single
capacitor, or tying the substrate, restores 190 mV).

Measured result: thresholds agree within 0.24 % (`vpor_rise_v`, `vpor_fall_v`),
`v_hys_mv` within 4.3 % (190.3 mV extracted against 183.6 mV on the schematic
at the typical corner, in line with the repo's own post-layout record), and the
large relative deltas are on near-zero rows (`vref_settle_drift_mv`,
`por_raw_hi_droop_mv`, `v_hys_rate_guard_delta_mv`), where the absolute values
are millivolts or less.

Toolchain split: the batch fleet runs `klt 0.7.0` and refuses any other
`klt sim` client (`batch_runner_version_mismatch`), so the legs' `klt sim`
runs at 0.7.0 while `klt pex` and `klt lvs` run at 0.8.0 (the grader's pin).
0.7.0's `klt sim` silently drops `corners.params`, so the supply is one literal
`.param vdd_val` per request rather than an axis; `measure.py` fails if a
report's corner count differs from the request's.

## Item 11 — graded `met` on released-tool evidence (`klt 0.7.0`)

[klayout-tools#2025/#2057](https://github.com/2AMLogic/klayout-tools/issues/2025)
added T1 item 11, "Power delivery (structural)", on 2026-09-19. It first
shipped in a published release in `klt 0.6.0`. Until [#342](https://github.com/2AMLogic/gf180-temp-por/issues/342)
moved the grader pin there, the pinned `klt 0.5.0` bundled a tiers doc that
stopped at item 10, so `tier-report.json` rendered `t1_item_count: 10` and
this item had no row at all. Moving the pin re-graded existing evidence and
produced none: `block-manifest.json` is unchanged, and items 3, 4 and 8 stay
`met` (item 3's citation now also quotes the DRC `coverage` block, which
changes no verdict).

The pin has since moved again, to `klt 0.7.0`. The operator ruling on
[PR #351](https://github.com/2AMLogic/gf180-temp-por/pull/351) declined to
accept item 11 as `met` on evidence produced by an unreleased build — the
one report under `layout/reports/` that answered to a `main` build rather
than a release — so the report was regenerated with the released `klt 0.7.0`
(which carries every `klt erc` capability the spec's `ties[]` declarations
need; see below) and the verdict re-graded: unchanged. `block-manifest.json`
is still unchanged, and items 3, 4 and 8 still grade `met`.

For an analog block, item 11 wants a `klt erc` supply-spec run (every declared
supply resolving to exactly one electrical island, zero `erc.missing_tie`)
plus an LVS report whose reference carried the supply nets.

**#300 produced both, and both are now clean.**

- `layout/reports/temp_por_top/lvs.json` is a SPICE-reference compare
  (`status: match`) with `VDD`/`VSS` both present in `net_correspondence`,
  which is what item 11's analog column asks for by construction.
- `layout/reports/temp_por_top/erc_supply.json` (regenerated with the
  released `klt 0.7.0`) reports
  `erc_finding_count: 0` — zero `erc.supply_short` and zero
  `erc.unconnected_net`, so each declared supply resolves to exactly one
  electrical island — with `provenance.input.content_hash` matching the
  committed GDS and `provenance.spec.content_hash` matching the committed
  spec.

**Freshness is gated repo-side.** The grader reports
`input_verified: true` for the GDS, but does not check the supply spec's hash
against the report, so `signoff/check.py` (`check_erc_supply_freshness`) re-hashes the GDS and
the supply spec the report names and requires them to equal
`provenance.input.content_hash` / `provenance.spec.content_hash`. A missing or
unreadable report, input or recorded hash is a failure, not a skip. It needs no
PDK and runs no `klt erc`; on failure, re-run the ERC and commit the
regenerated report rather than editing hashes. Unit tests:
`python3 -m unittest discover -s signoff/tests -t signoff/tests`.

It took two passes to get there, and the first one is the more useful
record. #300's first pass (PR #303) reported one `erc.supply_short` naming
`VDD`/`VSS`, root-caused to `klt erc`'s connectivity model registering no
device extraction, so this block's real poly-resistor bias/reference network
and its supply-sensing sense divider read as plain wires bridging the two
rails. Rather than tune the spec until it passed — every spec-side
workaround tried (dropping the `Contact` via, downgrading the nets to `kind:
"signal"`, omitting `Poly2` from the stackup) was strictly worse than the
finding itself — it was filed upstream, generically, as
[klayout-tools#2183](https://github.com/2AMLogic/klayout-tools/issues/2183)
and the honest `unmet` was committed. Upstream then fixed it
([klayout-tools#2205](https://github.com/2AMLogic/klayout-tools/pull/2205),
commit `ddf47e78`) by adding a `devices[]` spec array that subtracts a
declared device-body marker layer from a conductor role before connectivity
is registered. The spec now declares one such entry (`RES_MK` `110/5` on
the `poly2` role) and the finding is gone. `layout/README.md`'s "Item 11"
section has the full account, including why `RES_MK` and not the `Resistor`
`62/0` ID layer, and the measured over-coverage cross-check showing the
carve-out removes no gate region.

**The unreleased-build caveat is retired; the spec-declaration gap it hid
behind is now disclosed in its place.** The #310 caveat — that the report
was produced by a `main` build (`klt 0.6.0+gaf8d6c54312e`) because the
released `v0.6.0` lacked `well_requires`/`well_excludes`
([klayout-tools#2339](https://github.com/2AMLogic/klayout-tools/issues/2339))
and `well_requires_boxes`/`well_excludes_boxes`
([klayout-tools#2540](https://github.com/2AMLogic/klayout-tools/issues/2540))
— no longer applies: `klt 0.7.0` ships both, and the committed report names
`provenance.klt_version: "0.7.0"` with no build suffix. Per PR #351's
operator ruling, item 11 counts as `met` only on this released-tool
evidence, and it passes on it: same zero findings, same four `checked` ties,
same `input`/`spec` hash pins as the run it replaces (the grader's rendered
verdict is byte-for-byte the same verdict modulo the checklist text and
`build` block).

Two things did change with the regeneration, both recorded here rather than
papered over:

- **The spec file lost its inline `_comment` block.** `klt 0.7.0` enforces
  strict spec-key validation
  ([klayout-tools#2243](https://github.com/2AMLogic/klayout-tools/issues/2243)):
  any key outside the erc spec schema is a hard error, and the schema has no
  comment convention, so the 291-line justification block that used to travel
  inside the spec as a top-level `_comment` key moved verbatim to
  [`layout/cells/temp_por_top.erc-supply-spec-NOTES.md`](../layout/cells/temp_por_top.erc-supply-spec-NOTES.md).
  The spec's content hash moved with it — `provenance.spec.content_hash` is
  now `sha256:773047b1…` (was `sha256:88b908db…`) — and `check.py`'s
  freshness gate re-derives the pair on every run.
- **The spec declares seven layers the stream draws and it declares
  nowhere** — `erc_coverage.layers_in_stream_without_declaration` is
  non-empty, and the tiers doc `klt 0.7.0` bundles
  ([klayout-tools#2389](https://github.com/2AMLogic/klayout-tools/issues/2389))
  makes quoting it part of the claim: `31/0`, `32/0`, `49/0`, `62/0`, `75/0`,
  `117/5`, `117/10`. Named from the curated `gf180mcu` deck's own layer
  table (which cites the PDK's LVS deck): Pplus (31/0), Nplus (32/0), SAB
  salicide block (49/0), the `Resistor` high-sheet-rho poly mark (62/0),
  FuseTop (75/0), CAP_MK (117/5) and MIM_L_MK (117/10) — every one an
  implant, marker or ID layer. None is a conductor level the supply could
  route on: this block's entire drawn interconnect stack (Poly2, Comp,
  Metal1–Metal5, Contact, Via1–Via4) plus both label layers is declared in
  the spec's `stackup`/`label_layer`, so a rail that moved or grew on any
  routable level would still be inside the model the clean read ran on.

**`erc.missing_tie` is now computed, resolved by #310.** The spec declared no
`ties[]` until then, because on every `klt` build this repo could reach at
the time, declaring one collapsed a real design into a single island and
reported a *different* false `erc.supply_short`
([klayout-tools#2169](https://github.com/2AMLogic/klayout-tools/issues/2169)).
That bug is fixed upstream (the fix predates even `v0.6.0`), so the spec now
declares four `ties[]` entries covering every substrate/well tie in the
design, and the committed report shows zero `erc.missing_tie` findings with
all four graded `checked` — see `layout/README.md`'s "`erc.missing_tie`: now
computed" section for the full per-entry account and the falsifiability
checks run against this GDS before any of it was committed.

A third, smaller tool gap surfaced while verifying the carve-out and was
filed generically as
[klayout-tools#2226](https://github.com/2AMLogic/klayout-tools/issues/2226):
`provenance.devices[].body_area_um2` reports the marker layer's own area
rather than the area actually subtracted from the declared role, so the
report cannot by itself distinguish a carve-out that bit from one declared
on the wrong role. It does not affect this verdict — the areas were measured
independently — but it is why they had to be.

## Running it

```bash
# Install the pinned grader (separate from layout/toolchain.json's pin --
# see toolchain.json for why)
uv tool install --force klayout-tools==0.8.0

# The gate CI runs: re-grade the tree, fail on any drift from the committed verdict
python3 signoff/check.py

# Rebuild the item 1/2/9/10 inventories + envelopes + manifest pins and rewrite
# tier-report.json, after evidence or the checklist legitimately moves.
# Refuses (writes nothing) if the inventory audit fails.
python3 signoff/check.py --regen
```

No PDK, no xschem, no ngspice — `klt signoff --manifest` only reads committed
JSON envelopes, so this runs in the headless `checks` CI job on every push and
PR.

**`--regen` is not a way to make a failure go away.** It rewrites the verdict
of record. If it changes a `met` row to `unmet`, the claim genuinely got
weaker and the table above has to be corrected in the same commit.
