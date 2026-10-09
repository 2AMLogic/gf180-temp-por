# Work Log

Merged PRs and closed issues from the initial 30-day snapshot (2026-09-07 onward).

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
