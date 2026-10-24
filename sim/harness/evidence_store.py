"""Route a new run's raw evidence bytes to the common artifact store.

``sim/README.md`` (as amended by DR-030) keeps a run's *summary* record in git
but sends its bulky raw outputs -- the per-corner ngspice logs and the frozen
netlist snapshot -- to the fleet's artifact store via ``klt artifact put``.
Git keeps only a manifest, ``manifests/artifacts/<experiment>-<record-id>.manifest.json``,
naming every stored object by sha256 and ``artifact:`` URI.

The flow for one run:

1. ``preflight()`` before anything is simulated: the broker is configured and
   ``klt`` can ``artifact put``. Refuses (``EvidenceStoreError``) otherwise.
2. The harness writes the run's raw outputs into a git-ignored staging
   directory (``stage_dir_for()``), never into the tracked ``sim/`` tree.
3. ``publish()`` puts every staged file, validates the resulting manifest and
   only then installs it under ``manifests/artifacts/``.

Fail closed: no broker, no ``artifact put``, an unreachable broker, or a
partial put raises and installs nothing. There is no fallback that commits the
bytes instead. Stdlib only. The broker URL is read by ``klt`` from
``$KLT_ARTIFACT_BROKER`` and is never written anywhere by this module.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping

#: Environment variable ``klt artifact`` reads the broker location from.
BROKER_ENV = "KLT_ARTIFACT_BROKER"

#: Git-ignored staging area (``sim/.work/`` is ignored wholesale).
STAGE_DIRNAME = "evidence-stage"

#: Where manifests live, relative to the repository root.
MANIFEST_DIR = Path("manifests") / "artifacts"

#: Subdirectories of a staged run.
STAGE_CORNERS = "corners"
STAGE_SNAPSHOTS = "netlist-snapshots"

URI_PREFIX = "artifact:"


class EvidenceStoreError(RuntimeError):
    """The artifact store could not be used; nothing was recorded."""


def stage_dir_for(work_dir: Path, experiment: str, record_id: str) -> Path:
    """Staging directory of one run: ``<work_dir>/evidence-stage/<exp>/<id>``."""
    return work_dir / STAGE_DIRNAME / experiment / record_id


def manifest_relpath(experiment: str, record_id: str) -> Path:
    return MANIFEST_DIR / f"{experiment}-{record_id}.manifest.json"


def preflight(
    klt: str = "klt",
    env: Mapping[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Raise ``EvidenceStoreError`` unless an artifact put can be attempted."""
    env = os.environ if env is None else env
    if not env.get(BROKER_ENV):
        raise EvidenceStoreError(
            f"${BROKER_ENV} is not set: new evidence bytes go to the artifact store "
            "and there is no fallback that commits them. Run from a fleet worker "
            "(or use --no-write for a debugging run)."
        )
    if shutil.which(klt) is None and not Path(klt).is_file():
        raise EvidenceStoreError(f"{klt!r} not found: `klt artifact put` is required")
    try:
        probe = run([klt, "artifact", "put", "--help"], capture_output=True, text=True)
    except OSError as exc:
        raise EvidenceStoreError(f"cannot run {klt!r}: {exc}") from None
    if probe.returncode != 0:
        raise EvidenceStoreError(
            f"{klt!r} has no usable `artifact put` (need klayout-tools >= 7e3561f)"
        )


def staged_files(stage_dir: Path) -> list[Path]:
    return sorted(p for p in stage_dir.rglob("*") if p.is_file())


def publish(
    stage_dir: Path,
    repo_root: Path,
    experiment: str,
    record_id: str,
    klt: str = "klt",
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    """Put every staged file and install the manifest; return its path.

    Raises ``EvidenceStoreError`` (installing nothing under ``manifests/``) if
    there is nothing staged, any put fails, or the manifest is not made purely
    of ``artifact:`` URIs.
    """
    files = staged_files(stage_dir)
    if not files:
        raise EvidenceStoreError(f"nothing staged under {stage_dir}")
    dest = repo_root / manifest_relpath(experiment, record_id)
    if dest.exists():
        raise EvidenceStoreError(f"{dest} already exists; manifests are append-only")

    tmp = stage_dir.parent / f".{record_id}.manifest.tmp"
    if tmp.exists():
        tmp.unlink()
    for path in files:
        name = f"{experiment}/{record_id}/{path.relative_to(stage_dir).as_posix()}"
        cmd = [
            klt, "artifact", "put", "--manifest", str(tmp), "--name", name,
            "--media-type", "text/plain", str(path),
        ]
        try:
            proc = run(cmd, capture_output=True, text=True, cwd=repo_root)
        except OSError as exc:
            raise EvidenceStoreError(f"cannot run {klt!r}: {exc}") from None
        if proc.returncode != 0:
            raise EvidenceStoreError(
                f"`klt artifact put` failed for {name} (exit {proc.returncode}); "
                f"nothing recorded: {(proc.stderr or proc.stdout).strip()}"
            )

    try:
        text = tmp.read_text()
        manifest = json.loads(text)
    except (OSError, ValueError) as exc:
        raise EvidenceStoreError(f"klt wrote no usable manifest: {exc}") from None
    entries = manifest.get("entries") or []
    if not entries or not all(
        isinstance(e.get("uri"), str) and e["uri"].startswith(URI_PREFIX) for e in entries
    ):
        raise EvidenceStoreError("manifest has no entries or a non-`artifact:` uri; not installed")

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "x") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    except FileExistsError:
        raise EvidenceStoreError(f"{dest} already exists; manifests are append-only") from None
    tmp.unlink()
    return dest
