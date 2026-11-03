# DR-030: Keep new sim evidence bytes in the artifact store; git carries a manifest and the summary record

- **Status**: proposed
- **Date**: 2026-10-23
- **Decided by**: Loom Builder agent, issue #381

## Context

`sim/` is committed run output: tens of thousands of raw ngspice logs and
netlist snapshots, roughly 148 MB, and every new campaign grows the
repository. `sim/README.md` required each record to link to those raw logs
in git, and `.gitignore` exempts `sim/*/corners/**/*.log` from the blanket
`*.log` ignore for that reason. The fleet now runs a common artifact store
(`klt artifact put|get|verify`) that holds evidence bytes by sha256 and gives
git a small manifest to commit instead. Stored bytes are private; a manifest
names objects only by sha256 and `artifact:` URI, so it is safe in a public
repository.

## Decision

This changes **where raw run outputs live**. It does not change any spec row,
corner matrix, check, or pass/fail criterion.

1. For every record minted after this decision, the per-corner logs
   (`corners/<record-id>/*.log` / per-sample MC logs) and the netlist snapshot
   (`netlist-snapshots/<record-id>.spice`) are staged in the git-ignored
   `sim/.work/evidence-stage/`, put into the store with `klt artifact put`,
   and **not committed**.
2. Git gets `manifests/artifacts/<experiment>-<record-id>.manifest.json`
   (every `uri` starts with `artifact:`) and the Markdown summary record,
   which links the manifest in place of the raw-log and snapshot paths.
3. The writers fail closed: with `$KLT_ARTIFACT_BROKER` unset, a `klt` lacking
   `artifact put`, an unreachable broker, or a partial put, the run exits
   non-zero and records nothing. There is no fallback that commits the bytes.
   `--no-write` debugging runs are unaffected.
4. `scripts/check_artifact_manifests.py` runs in CI: manifest schema, only
   `artifact:` URIs, no `s3://` / `arn:aws:` strings, and no tracked file
   whose bytes match a stored object. `klt artifact verify <manifest>` is a
   fleet-worker check (public CI has no broker).

Manifest-forward only: existing committed evidence stays where it is, is not
migrated, and records already written are not edited (append-only rule). The
`.gitignore` exemptions for committed logs stay, since they cover that
history.

## Alternatives considered

- **Rewrite history / migrate the existing evidence** — destroys the
  append-only guarantee and rewrites every cited commit; not chosen.
- **Fall back to committing bytes when the store is unreachable** — silently
  reintroduces the growth this removes and makes a record's storage depend on
  the network; not chosen. A failed run can be re-run.
- **Run `klt artifact verify` in public CI** — needs the broker, which public
  CI does not have; verification stays a worker-side check.

## Consequences

- New records cannot be read from a plain clone: the raw logs are fetched with
  `klt artifact get` (access is limited to the fleet). The summary record,
  which holds every number a spec claim cites, stays in git.
- Writing a record now requires a fleet worker with the broker configured.
  Unit tests and `--no-write` runs do not.
- `sim/README.md`'s directory convention and "Links" field are updated to
  match; analysis scripts that read `corners/<record-id>/` logs (e.g.
  `runner.load_points`) must `klt artifact get` them first for post-DR-030
  records.
