# DR-006: Sim harness ported from gf180-bandgap — divergences

- **Status**: proposed
- **Date**: 2026-07-31
- **Decided by**: Loom Builder agent, issue #2

## Context

CLAUDE.md pins the harness bootstrap: "copy the sim-harness pattern from
`2AMLogic/gf180-bandgap` once it lands there rather than reinventing." That
pattern landed on 2026-07-31 (their issue #2, PR #23) and is now ported here:
`sim/harness/`, `sim/run_corners.py`, `sim/env.sh`, `sim/selftest.sh`,
`sim/pdk.json`, `sim/tests/`, `sim/README.md`, `sim/harness/README.md`, and a
`sim/smoke-bias/` acceptance testbench.

The port is deliberately near-verbatim — `pdk.py`, `runner.py`, `report.py`
and `cli.py` are copied unchanged apart from repo-name strings. Issue #2 is
explicit that a fork of the sister repo's harness is the failure mode to
avoid: divergence is allowed only where the *block* differs, and only if it
is written down. This record is that writing-down. Anything not listed below
is upstream behavior and should stay upstream behavior; the correct way to
change shared behavior is to change it upstream and re-port.

Two block facts drive the divergences: DR-001 pins a 3.3 V ±10 % rail, and
DR-005 builds both circuits out of vertical PNPs and resistors — a
VBE/ΔVBE sensing core scaled by a resistor ratio, and a POR threshold taken
as a resistor-divided VDD tap compared against that reference.

## Decision

Adopt the upstream harness as-is, with exactly these four divergences.

**1. `DEFAULT_CORNER_SET` is `full` (9 process corners), not upstream's
`mos` (5).** Upstream leaves the passive corners opt-in and relies on each
`tb.json` requesting `"corners": ["full"]`. Here the passive corners are not
optional for *any* claim: `res_ff`/`res_ss` move the resistor ratio that sets
PTAT slope and the divider that sets the POR trip point, and
`bjt_ff`/`bjt_ss` move the Is/beta that set V_EB. A MOS-only sweep reports
green while never touching the devices that set the spec. Making `full` the
default means the safe grid is what you get by forgetting to think about it,
and `--corner-set mos` remains available for quick iteration. Cost: 81 points
per run instead of 45.

A unit test asserts the default *and* asserts that every experiment
discovered under `sim/` resolves to a corner list containing all four passive
corners, so a future `tb.json` cannot quietly opt back down to MOS-only.

**2. `sim/smoke-bias/`'s third branch is a diode-connected vertical
`pnp_10p00x10p00`, where upstream uses `npn_10p00x10p00`.** The branch's job
is identical — prove `.temp` and the BJT `.lib` section take effect via a
strongly CTAT junction voltage — but it should exercise the device this
block's CTAT leg is actually built from (DR-005). Same 10 µA forced bias,
same check band, base and collector both to substrate.

**3. Upstream's `sim/smoke_test/` (their issue #24, an *install* smoke test
driven from `docs/environment-setup.md`) is not ported.** This repo has no
`docs/environment-setup.md` and no issue that owns one. `sim/run_corners.py
--check-env` already reports ngspice and PDK status and exits 3 with install
instructions, which covers the same ground for this repo's purposes.
Consequence: there is no pre-harness "is my install correct?" check here — a
broken install surfaces as a `--check-env` failure instead. If a fresh-machine
onboarding doc is ever written, port `smoke_test/` at that point rather than
inventing something new.

**4. `design/xschemrc` is not ported.** Upstream ships one; schematic entry
here is issue #8's scope and no `design/` content exists yet. `source
sim/env.sh` still exports the PDK and `XSCHEM_USER_LIBRARY_PATH`, so #8 can
add an `xschemrc` on top without touching the harness.

Additionally — not a divergence, but a stated position: **issue #4's
pre-harness `sim/devchar/` evidence is left as-is**, not migrated onto the
runner. Rewriting it into `records/<record-id>.md` form would mean rewriting
existing evidence, which the append-only rule forbids. The reasoning and the
"no new exceptions" boundary are in `sim/README.md` § *Pre-harness evidence*.

## Alternatives considered

- **Keep `mos` as the default and require every `tb.json` to say
  `"corners": ["full"]`** — rejected. It is upstream-identical, but it makes
  the correct grid an act of remembering on every new testbench, in a repo
  where the correct grid is *always* `full`. The failure mode is silent: a
  MOS-only run produces a clean-looking record that passes the matrix
  conformance check (which only requires ≥3 process corners) while never
  skewing a resistor or a BJT.
- **Fork harder — restructure corner handling around this block's
  topologies** — rejected outright. Issue #2's whole point is that the sister
  repos share one harness so a fix in either flows to the other. Divergence
  is a liability to be minimized, not a design freedom.
- **Port `sim/smoke_test/` anyway, for parity** — rejected. It is the
  acceptance step of a document this repo does not have; porting it would
  leave a test whose stated purpose points at a missing file, which is worse
  than its absence.
- **Migrate `sim/devchar/` onto the runner** — rejected. It would rewrite
  append-only evidence, and those runs characterize devices rather than
  substantiate a spec row, so no coverage map depends on them.

## Consequences

- Every recorded run in this repo is 81 points (9 × 3 × 3) by default,
  ~30 s wall time for a trivial `op` testbench at `-j 8`. Transient POR
  testbenches (#14) will be substantially slower; budget for it, and use
  `--corner-set mos --no-write` while iterating.
- #13/#14 inherit a runner whose default grid already satisfies "PVT corners
  on every recorded result" with no per-testbench opt-in, and inherit the
  `sim/<experiment-slug>/` structure their spec-row completeness check maps
  onto.
- The four divergences above are the complete diff surface against upstream.
  When gf180-bandgap's harness changes, re-porting is a matter of copying
  `harness/*.py` again and re-applying exactly these; if that stops being
  true, this record is stale and must be superseded rather than quietly
  outgrown.
- Divergence 1 costs simulator time on every run and will be felt most by the
  transient POR suite. If that becomes painful, the fix is a per-testbench
  `"corners"` override with a stated reason on the record — not lowering the
  default back to `mos`.
- No spec table row changes. This record touches tooling only; it does not
  ratify, relax, or reinterpret any parameter, and #1 remains the sole
  ratification gate.
