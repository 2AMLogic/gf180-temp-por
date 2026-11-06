# Work Log

Merged PRs and closed issues from the initial 30-day snapshot (2026-09-07 onward).

### 2026-11-06

- **PR #432**: refactor(sim): share one local grid loop, drop single-call batch wrappers
- **PR #430**: ci(sim): fail PRs that edit, delete or move existing sim evidence
- **Issue #431** (closed): Simplify sim harness: share the local grid loop and drop the one-line batch wrappers
- **Issue #353** (closed): CI: mechanically enforce the append-only rule for sim/ evidence records
- **PR #428**: refactor(sim): share one record renderer and writer between PVT and Monte Carlo
- **PR #426**: refactor(sim): share one batch-grid runner between PVT and Monte Carlo
- **Issue #427** (closed): Dedupe render_record/render_mc_record and write_record/write_mc_record in sim harness
- **Issue #424** (closed): Dedupe run_mc_grid_batch onto run_grid_batch (~85-line copy)
- **PR #423**: feat(sim): define seeded known-bad variants of the two yield campaigns
- **PR #421**: feat(sim): add klt sim batch backend to run_mc.py
- **PR #419**: layout: remove one-point postlayout smoke script, re-point citations to grid records
- **PR #418**: feat(signoff): klt yield reports for the [3σ] rows (T1 item 6)
- **Issue #420** (closed): sim/run_mc.py: add a klt sim batch backend for large Monte Carlo campaigns
- **Issue #409** (closed): Remove layout/postlayout_smoke.py and SMOKE.md: superseded by full-PVT post-layout re-runs
- **Issue #384** (closed): T1 item 6 (Monte Carlo): klt yield reports for temp-accuracy-mc and por-threshold-mc
- **PR #413**: refactor(layout): remove the unused cell-freeze mechanism
- **Issue #411** (closed): Remove the unused cell-freeze mechanism (FROZEN_CELLS is empty; its tests skip)

### 2026-11-01

- **PR #408**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-29

- **PR #407**: feat(pex): klt pex evidence for the temp_core and por_output_chain cells
- **PR #406**: docs(por-brownout): root-cause the schematic leg's missing re-assert at 8 corners
- **PR #404**: feat(pex): klt pex evidence for brownout, ramp-rate and temp-accuracy-vt
- **Issue #405** (closed): Investigate por-brownout post-layout errors: schematic leg yields no reset re-assert at low-supply dips
- **Issue #393** (closed): T1 item 7: klt pex coverage for cell-level post-layout benches (temp_core, por_output_chain)
- **Issue #391** (closed): T1 item 7: extend the klt pex report to the remaining post-layout benches

### 2026-10-28

- **PR #403**: fix(pex): stage three more temp_por_top experiments and harden the PEX driver
- **PR #402**: fix(signoff): refresh stale item-10 hash, fail on stale citation hashes, correct README verdict
- **Issue #401** (closed): T1 grading: refresh tier-report.json (item 10 cites a superseded inventory hash) and correct README's 8/11 verdict

### 2026-10-27

- **PR #399**: ci: quote manifest-check step name so ci.yml parses
- **PR #397**: refactor(design): netlist cells through klt netlist instead of raw xschem
- **PR #395**: chore: remove truncated .loom/manifest.json.tmp install leftover
- **PR #392**: feat(signoff): cite a klt pex report for T1 item 7 (por-vth, 81 corners)
- **PR #390**: chore(signoff): pin grader to klt 0.8.0 and declare item 5 spec_rows as gaps
- **Issue #398** (closed): ci: .github/workflows/ci.yml is invalid YAML on main, so no CI job runs
- **Issue #396** (closed): Replace hand-rolled xschem call in design/netlist.py with klt netlist
- **Issue #394** (closed): Remove .loom/manifest.json.tmp: truncated install leftover
- **Issue #387** (closed): T1 item 5 phase 1: bump the grader pin and declare spec_rows."5" with every measured row as a gap
- **Issue #385** (closed): T1 item 7 (post-layout verification): klt pex delta report for temp_por_top

### 2026-10-24

- **PR #382**: feat: store new sim evidence bytes in the artifact store, commit manifests
- **Issue #381** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-10-21

- **PR #380**: ci: pin checks job to ubuntu-24.04 for the Python 3.9 leg
- **Issue #379** (closed): CI: python 3.9 matrix leg fails — setup-python has no 3.9 build for ubuntu-latest (Ubuntu 26.04)
- **PR #377**: Bump Repo Skills 0.24.3 -> 0.24.7

### 2026-10-17

- **PR #372**: refactor(sim): share toolchain-locating preamble across control scripts
- **Issue #371** (closed): Dedupe the PDK/ngspice environment preamble across the 20 sim control scripts (and unify its exit code)
- **PR #368**: refactor(sim): share read_bare_logs() across the por-brownout-slew controls
- **Issue #367** (closed): Dedupe four read_logs() copies in por-brownout-slew controls into sim/harness

### 2026-10-16

- **PR #365**: Bump Repo Skills 0.24.1 -> 0.24.3

### 2026-10-15

- **PR #363**: feat(sim): add --klt-pin to pin the batch client to the runner's klt version
- **PR #361**: feat(signoff): cite audited hash-bound evidence for T1 items 1, 2, 9, 10
- **PR #359**: Bump Repo Skills 0.19.5 -> 0.24.1
- **PR #351**: signoff: move the T1 grader pin to klt 0.6.0 so the verdict of record includes item 11

- **Issue #346** (closed): Auditor: sim/selftest.sh PVT smoke fails when klt client and batch runner versions differ
- **Issue #348** (closed): T1 items 1, 2, 9, 10: cite artifact-anchored evidence now that klt signoff can bind it
- **Issue #342** (closed): signoff: move the T1 grader pin to klt 0.6.0 so the verdict of record includes item 11

### 2026-10-08

- **PR #355**: ci: test the documented Python 3.9 floor
- **PR #352**: Add make test as single source of truth for unit-test suites
- **PR #332**: sim/harness: fail-closed klt sim batch backend (#331)
- **PR #337**: fix(sim/harness): close fail-open klt batch paths found on the live fleet (#331)
- **PR #340**: characterize: return failure when an experiment is killed by a signal
- **PR #341**: signoff: verify supply ERC evidence hashes against current GDS and spec
- **PR #343**: sim harness: reserve evidence record IDs before runs
- **PR #344**: fix: reject contradictory or malformed klt batch corner results

- **Issue #354** (closed): CI: test the documented Python 3.9 floor (or raise the documented floor)
- **Issue #345** (closed): Test entry points disagree: make check and npm test skip the signoff suite; add one make test source of truth
- **Issue #339** (closed): sim harness: reserve evidence record IDs before runs to prevent log collisions
- **Issue #335** (closed): batch results: reject contradictory success labels and malformed measurement values
- **Issue #334** (closed): signoff: verify supply ERC evidence hashes against the current GDS and spec
- **Issue #333** (closed): characterize: return failure when an experiment subprocess is killed by a signal

### 2026-10-07

- **PR #329**: docs: align README with current extraction and ERC evidence

### 2026-10-03

- **PR #327**: sim: finish consolidating control-script ngspice invocations onto run_deck_raw
- **Issue #326** (closed): Finish consolidating control-script ngspice invocations onto runner.run_deck_raw

### 2026-10-02

- **PR #325**: Restate post-layout por_output_chain claims from full-grid re-runs on the star extraction
- **PR #323**: Re-measure the XMBD/IBIAS watch item under the star parasitic model; name the two grid gaps it leaves
- **PR #320**: fix: re-derive the net-shorting manipulation for the star parasitic model
- **PR #318**: layout: declare ties[] in temp_por_top's erc supply spec (T1 item 11)
- **PR #317**: layout: regenerate postlayout evidence against the pinned klt 0.6.0 (star parasitic model, bare capacitor cards, assembly body-tie join)
- **Issue #322** (closed): Post-layout por_output_chain grid claims are still published from the retired extraction; a 9-point probe shows the one-shot moved ~2 %
- **Issue #319** (closed): Re-run the two post-layout claims the #314 parasitic-model change left resting on a retired model
- **Issue #316** (closed): sim/ parasitic readers and design/*.md still assume the retired `<net>__par` stub model, so they silently misread the star-model post-layout netlists
- **Issue #314** (closed): layout/postlayout.py's own evidence predates klt 0.6.0: parser gaps block --extract regeneration, MiM law pin now stale
- **Issue #311** (closed): Bump layout/toolchain.json's klt pin to >=0.6.0 and regenerate all evidence (needed for T1 item 11 ties[], #310)
- **Issue #310** (closed): T1 item 11: declare ties[] in the klt erc supply spec so erc.missing_tie is actually computed (bronze grant paused on this)

### 2026-10-01

- **PR #315**: layout: re-transcribe lvs_reference.py for klt 0.6.0's gf180mcu deck
- **Issue #313** (closed): Curator applied issue-lifecycle labels (loom:curating/loom:curated) to PR #306
- **Issue #312** (closed): klt 0.6.0's gf180mcu deck obsoletes layout/lvs_reference.py's deck-imposed rewrites and MiM capacitance law (blocks the #311 pin bump)

### 2026-09-24

- **PR #305**: chore: resync installed Loom surfaces

### 2026-09-23

- **PR #308**: docs: embed fleet burndown chart in README
- **Issue #309** (closed): loom-wake live verification — throwaway, safe to close
- **Issue #307** (closed): README: embed the fleet burndown chart (one line)

### 2026-09-21

- **PR #304**: layout(temp_por_top): clear the T1 item-11 ERC supply verdict with devices[]
- **Issue #300** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo

### 2026-09-20

- **PR #303**: layout(temp_por_top): add T1 item 11 klt erc supply spec + report
- **PR #302**: signoff: commit a klt signoff block manifest as the T1 verdict of record
- **Issue #301** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read

### 2026-09-10

- **PR #299**: sim: post-layout re-run of temp_core's loop-stability testbench (#298)
- **Issue #298** (closed): sim: post-layout re-run of temp_core's .ac loop-stability testbench against layout/postlayout/temp_core.spice (closes the one temp_core testbench without an extracted sibling)

### 2026-09-09

- **Issue #297** (closed): Champion: Merge-Risk Hold Digest
- **Issue #145** (closed): Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)
