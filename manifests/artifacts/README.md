# manifests/artifacts/

One `<experiment-slug>-<record-id>.manifest.json` per recorded run made after
DR-030, written by `sim/run_corners.py` / `sim/run_mc.py` through
`sim/harness/evidence_store.py`. Each entry names a stored object (the
per-corner or per-sample ngspice logs and the frozen netlist snapshot) by
name, size, sha256 and `artifact:` URI. The bytes are not in this repository;
the summary record under `sim/<experiment>/records/` links the manifest.

- Check a run's bytes (from a fleet worker): `klt artifact verify <manifest>`
- Fetch one object: `klt artifact get` (see `klt artifact get --help`)
- CI (`scripts/check_artifact_manifests.py`) validates every manifest and
  fails if a stored object's bytes are tracked in git.

Manifests are append-only. Do not hand-edit them, and do not put a storage
location (bucket, account id, URL) in one.
