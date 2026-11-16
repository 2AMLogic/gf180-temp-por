# Work Log

Merged PRs and closed issues from the initial 30-day snapshot (2026-09-07 onward).

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-16

- **PR #561**: fix: run the deglitch controls on the star extraction — CDG regex, citations, design-doc reconciliation
- **PR #571**: test: require the emitted - git: literal in the provenance wiring detector
- **PR #564**: refactor(layout-tests): one golden-netlist accessor and one MiM-cap mixin instead of per-class copies
- **Issue #533** (closed): Regenerate the three deglitch control files against the star extraction: one script is broken, two files' numbers (and one verdict) moved
- **Issue #537** (closed): test_control_git_provenance.py checks that git_describe is wired, not that a `- git:` line reaches the provenance block
- **Issue #500** (closed): Dedupe the golden-netlist read and the MiM-cap test block in layout/tests/test_lvs_reference.py
- **PR #535**: layout: grow resistor SAB markers past Poly2 so SB.10 has no coincident edge
- **PR #559**: docs: correct the via comments' false "no deck rule" claim to the deck's real via rules
- **PR #567**: docs: refresh roadmap Now section to the 2026-11-16 anchor
- **PR #566**: refactor(layout): draw all Via1 landing pads through _cap_via/_cap_pad
- **PR #554**: refactor: drop four dead arguments from control deck composers and job tuples
- **PR #498**: feat(signoff): forbid hand-written T1 verdict counts in prose
- **PR #556**: feat(layout): draw the missing Nplus/Pplus implants on every COMP site
- **PR #539**: refactor(sim): drop dead report.py imports from mc_report and correct its reuse docstring
- **PR #541**: refactor(layout): delegate _m2_h/_m2_v to _cap_wire, the one fixed-width-wire primitive
- **Issue #517** (closed): Poly resistors draw SAB coincident with Poly2: zero extension where SB.10 requires 0.22 um
- **Issue #531** (closed): Via3/Via4 are drawn at VIA_SIDE_UM, a constant whose own comment cites only DRM V1.1/V2.1
- **Issue #548** (closed): docs/ROADMAP.md: refresh the Now section — item 3 is already complete, and the sub-cell count disagrees with itself
- **Issue #505** (closed): Three independent implementations of one Via1-with-landing-pads primitive in layout/build_cells.py
- **Issue #495** (closed): README and signoff/README.md say 9 of 11 T1 items met; the committed tier report says 8
- **Issue #502** (closed): Remove four dead arguments threaded into control-script deck composers and job tuples
- **Issue #491** (closed): README's T1 verdict count drifts from signoff/tier-report.json, and the docs-PR path cannot carry the fix
- **Issue #516** (closed): MOS source/drain and guard-ring COMP are drawn with no Nplus/Pplus implant (DF.12, all six cells)
- **Issue #525** (closed): Remove three dead report.py imports from sim/harness/mc_report.py, and the docstring claim they fossilise
- **Issue #506** (closed): _m2_h/_m2_v re-derive _cap_wire's straight-wire branches — the wire counterpart to #505's via drift

### 2026-11-15

- **PR #544**: control scripts: drop arguments their workers never read
- **Issue #522** (closed): Remove the dead name and log_dir/deck_dir arguments three control scripts thread into their workers
- **PR #549**: test(sim): assert por-vth control fragments stay card-identical; drop two dead .params
- **PR #547**: test: assert temp_core's drawn track nets equal its manifest ports
- **PR #542**: layout: snap generator coordinates to the 0.005 um manufacturing grid (31,928 *.ongrid.1 violations)
- **PR #540**: fix(sim): reject unrecognized argv in every control entry point before its sweep
- **PR #534**: feat(sim): record the commit behind deglitch control results via a - git: provenance line
- **PR #524**: refactor: derive the DRM via square once in _via_square
- **PR #504**: feat: build klt sim requests with per-row spec limits, without submitting
- **PR #494**: docs: roadmap as of 2026-11-13
- **PR #529**: refactor(lvs_reference): one declared-net guard, now covering cap plates too
- **PR #526**: refactor(layout): inline cell_failed() and drop three dead branches in run_checks.sh
- **PR #520**: docs: classify every DRC rule the committed cells violate under klt 0.8.0
- **PR #501**: refactor(sim): give three duplicated control helpers one definition per directory
- **Issue #515** (closed): Snap generator-derived coordinates to the 0.005 um manufacturing grid (31,928 *.ongrid.1 violations)
- **Issue #512** (closed): Control scripts ignore unrecognized argv and run the full local sweep (overwriting committed evidence)
- **Issue #511** (closed): Remove _TopRoutes.via1/via2's inline via-square arithmetic: the only via drawer that bypasses CellBuilder.via
- **Issue #509** (closed): Remove ramp_rate_probe.spice's two dead .params, and assert the por-vth control fragments' cards agree
- **Issue #507** (closed): run_deglitch_asym_probe.py's results.md carries no `- git:` provenance line, unlike its five peers
- **Issue #499** (closed): Assert temp_core's drawn track list equals its manifest ports — the one leaf cell missing the sibling guard
- **Issue #496** (closed): sim harness: build a klt sim request with per-row spec limits for one experiment (dry-run half of #388)
- **Issue #523** (closed): Collapse four leftovers in layout/run_checks.sh from the cell-freeze removal and --regen-all
- **Issue #514** (closed): Collapse lvs_reference.py's three copies of the undeclared-net guard into one helper — and give the MiM cap builder the call site #269 never wrote
- **Issue #497** (closed): Classify the DRC violations the committed cells show under klt 0.8.0 and later (unblocks #400)
- **Issue #493** (closed): Three control-script helpers are duplicated within one experiment directory; consolidate per the _rung_record.py precedent

### 2026-11-14

- **PR #503**: refactor: delete five unread constants from four control scripts and selftest.sh
- **Issue #492** (closed): Remove four unread constants the #487 sweep missed (one is a stale copy of DR-019's bound)

### 2026-11-13

- **PR #489**: refactor(sim): drop selftest.sh --quick, whose single point always fails the grid checks
- **PR #488**: refactor(sim): drop five unread constants from three sim control scripts
- **Issue #485** (closed): Remove sim/selftest.sh --quick: the single-point mode always fails the harness's own min_spread_pct checks
- **Issue #487** (closed): Remove five unread constants from three sim control scripts (the decks hardcode the same literals)
- **PR #484**: refactor(sim): drop the unreachable commit-the-bytes write path from the harness
- **PR #483**: docs: describe the drawn divider in the SNS/SNSB track comment
- **Issue #481** (closed): Remove the unreachable pre-DR-030 commit-the-bytes write path from the sim harness (stage=False, reserve=True)
- **Issue #480** (closed): Stale comment in layout/build_cells.py still calls the sense divider undrawn
- **PR #479**: refactor: drop unused RESERVED layer, add_cell and RESISTOR_MODEL
- **PR #478**: test(layout): drop the retired #97 drift fallback from the temp_por_top assembly check
- **Issue #477** (closed): Remove retired reservation-layer and sibling-top-cell leftovers from layout/build_cells.py (RESERVED, add_cell) and dead RESISTOR_MODEL
- **Issue #465** (closed): Remove the retired #97 drift fallback from TempPorTopAssemblyTest.test_reference_matches_the_committed_file
- **PR #473**: feat(sim): refuse a batch result whose runner read a different PDK build
- **PR #472**: fix(sim): pass --wait-for-capacity on the single-request batch submit path
- **PR #471**: fix(pex): refuse a swept supply axis under either klt request key
- **PR #466**: fix(sim): sweep the lifted vdd_val on klt's parameter axis, not its supply axis
- **PR #463**: refactor(sim): add runner.run_decks and call it from the seven control-script pools
- **PR #461**: docs: name the ratification keys as the Publication rule's one exception
- **Issue #475** (closed): Batch backend: the inlined design.ngspice is not covered by the runner-PDK gate or the evidence record
- **Issue #469** (closed): sim/pex/build_requests.py: the 'unexpected supply axis' guard still reads corners.supply_v, which the harness no longer emits
- **Issue #468** (closed): sim evidence: batch results record the submitting host's PDK, not the build the fleet runner actually simulated
- **Issue #467** (closed): sim harness: the single-request batch path never passes --wait-for-capacity, so a full fleet fails the run outright
- **Issue #464** (closed): sim harness batch backend: klt refuses the lifted vdd_val supply axis, and requests do not pin the PDK root the harness resolved
- **Issue #462** (closed): Dedupe the seven copies of the control scripts' thread-pool run_deck loop into runner.run_decks
- **Issue #435** (closed): Scrub or remove ratification/market-key before public visibility flip
- **PR #454**: docs(spec): DR-031 chopped temp_core amplifier, gain-term fix, trim re-balance
- **Issue #451** (closed): temp_core: decision record superseding DR-005's no-chopping rejection (#415 step 1/3)

### 2026-11-12

- **PR #449**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-10

- **PR #445**: refactor(sim): route Monte Carlo samples through run_point via compose=
- **Issue #443** (closed): Remove run_mc_point: near-verbatim duplicate of runner.run_point

### 2026-11-07

- **PR #441**: sim: submit Monte Carlo samples via one klt --batch-set; run multi-solve decks
- **Issue #440** (closed): sim: submit Monte Carlo samples via klt --batch-set and let the two-solve temp deck run on the batch backend
- **PR #436**: Bump Repo Skills 0.25.1 -> 0.25.10

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

