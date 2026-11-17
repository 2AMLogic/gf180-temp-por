# DR-032: `open_pdks` `f6eeac7d` is the authoritative revision for `sim/` evidence

- **Status**: proposed
- **Date**: 2026-11-17
- **Decided by**: operator (rjwalters), `/fleet:decide` round 20261116-r15, q87

## Context

Reviewing PR #601 (which reorders the harness's builtin PDK search roots so
`~/.ciel` precedes `~/.volare`) surfaced a dual-install divergence
([#602](https://github.com/2AMLogic/gf180-temp-por/issues/602)): on a host
with both stores present, `~/.ciel` holds an `open_pdks` `f6eeac7d` build
and `~/.volare` holds `c6d73a35`. The dispatch fleet and the `klt` client
resolve the `~/.ciel` install, so new evidence there is taken against
`f6eeac7d` — while this repository's `README.md` and
`.github/workflows/ci.yml` declared `c6d73a35`, and CI kept provisioning
`c6d73a35`. Records are self-describing (each names its build from the
install's `SOURCES` file), so no committed record was falsified — but the
declared pin had drifted from the revision new evidence is actually taken
against, and CI graded different device models than the fleet.

## Decision

`open_pdks` commit `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` is
authoritative for this repository's `sim/` evidence going forward:

1. New evidence is minted against `f6eeac7d`. The `README.md` pin and the
   CI provisioning step name that revision.
2. Existing records minted against
   `c6d73a35f524070e85faff4a6a9eef49553ebc2b` stay valid as history. They
   are not re-minted and not edited (append-only rule); each names its own
   build in its provenance.
3. A `c6d73a35` record and an `f6eeac7d` record must not be compared
   number-for-number — e.g. a spec-row pass/fail call across the two
   builds — without the comparison saying so explicitly. A like-for-like
   cross-build comparison of any spec row is filed as its own issue.

## Alternatives considered

- **Keep `c6d73a35` pinned and repoint the fleet / harness defaults at it** —
  declined: the fleet and the `klt` client already resolve the `f6eeac7d`
  build on dual-install hosts, so the repository would permanently fight
  its own tooling.
- **Document both revisions as a standing two-build situation** — declined:
  two live pins invite exactly the silent cross-build comparison this
  record forbids.

## Consequences

- CI's `pdk-checks` job provisions `f6eeac7d` via `ciel` and grades the
  same device models the dispatch fleet and `klt` resolve, so a corner run
  passing locally on the fleet no longer meets different models in CI.
- The committed `c6d73a35` evidence corpus stays in place. A reader
  reproducing an older record must provision `c6d73a35` and point the
  harness at it (`GF180_PDK_PATH` / `PDK_ROOT` / `sim/pdk.local.json`).
- Any claim that mixes the two builds in one comparison must name both
  builds explicitly, per the decision above.
