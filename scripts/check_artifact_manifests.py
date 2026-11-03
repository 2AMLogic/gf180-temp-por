#!/usr/bin/env python3
"""Validate ``manifests/artifacts/*.manifest.json`` (DR-030).

Run from anywhere: ``python3 scripts/check_artifact_manifests.py [--root DIR]``.
Exits 0 when clean, 1 with one line per problem otherwise.

Checks, per manifest:

* schema: ``schema_version`` 1 and a non-empty ``entries`` list whose entries
  each carry a 64-hex ``sha256``, an integer ``size`` >= 0, a ``name`` and a
  ``uri``;
* every ``uri`` starts with ``artifact:`` (no URLs, no bucket paths);
* the manifest names no storage location: no ``s3://`` and no ``arn:aws:``;

and across the repository:

* no tracked file outside ``manifests/`` has the bytes of a stored object
  (matched by size and sha256) -- the bytes live in the store, not in git.

It needs neither the broker nor ``klt``: ``klt artifact verify`` is a
fleet-worker check, public CI has no broker. Stdlib only (Python 3.9+).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_DIR = Path("manifests") / "artifacts"
URI_PREFIX = "artifact:"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_RE = re.compile(r"s3://|arn:aws:")


def _load(path: Path, rel: str, errors: list[str]) -> list[dict]:
    text = path.read_text()
    if FORBIDDEN_RE.search(text):
        errors.append(f"{rel}: names a storage location (s3:// or arn:aws:)")
    try:
        doc = json.loads(text)
    except ValueError as exc:
        errors.append(f"{rel}: not valid JSON ({exc})")
        return []
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
        return []
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append(f"{rel}: entries must be a non-empty list")
        return []
    good = []
    for i, entry in enumerate(entries):
        where = f"{rel}: entries[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: not an object")
            continue
        ok = True
        if not (isinstance(entry.get("sha256"), str) and SHA256_RE.match(entry["sha256"])):
            errors.append(f"{where}: sha256 must be 64 lowercase hex characters")
            ok = False
        size = entry.get("size")
        if not (isinstance(size, int) and not isinstance(size, bool) and size >= 0):
            errors.append(f"{where}: size must be an integer >= 0")
            ok = False
        if not (isinstance(entry.get("name"), str) and entry["name"]):
            errors.append(f"{where}: name must be a non-empty string")
            ok = False
        uri = entry.get("uri")
        if not (isinstance(uri, str) and uri.startswith(URI_PREFIX) and "://" not in uri):
            errors.append(f"{where}: uri must start with {URI_PREFIX!r} (got {uri!r})")
            ok = False
        if ok:
            good.append(entry)
    return good


def _tracked_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
        ).stdout
        return [root / p for p in out.decode().split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return [
            p for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts
        ]


def check(root: Path) -> list[str]:
    """Return a list of problems under ``root`` (empty means clean)."""
    errors: list[str] = []
    stored: dict[int, dict[str, str]] = {}  # size -> {sha256: uri}
    manifest_dir = root / MANIFEST_DIR
    for path in sorted(manifest_dir.glob("*.manifest.json")):
        rel = path.relative_to(root).as_posix()
        for entry in _load(path, rel, errors):
            if entry["size"] > 0:  # empty bytes are not evidence
                stored.setdefault(entry["size"], {})[entry["sha256"]] = entry["uri"]
    if not stored:
        return errors

    skip = (root / "manifests").resolve()
    for path in _tracked_files(root):
        if not path.is_file() or skip in path.resolve().parents:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size not in stored:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in stored[size]:
            errors.append(
                f"{path.relative_to(root).as_posix()}: bytes of a stored object "
                f"({stored[size][digest]}) are committed; keep them out of git"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent,
        help="repository root (default: this script's repository)",
    )
    args = parser.parse_args(argv)
    errors = check(args.root.resolve())
    for line in errors:
        print(f"error: {line}", file=sys.stderr)
    if not errors:
        n = len(list((args.root / MANIFEST_DIR).glob("*.manifest.json")))
        print(f"artifact manifests: ok ({n} manifest(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
