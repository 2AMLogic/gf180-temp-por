#!/usr/bin/env python3
"""Re-grade this block against the klayout-tools T1 checklist, and fail on rot.

    python3 signoff/check.py            # the gate CI runs
    python3 signoff/check.py --regen    # rewrite signoff/tier-report.json

`signoff/block-manifest.json` is this block's machine-readable T1 claim and
`signoff/tier-report.json` is the verdict `klt signoff --manifest` rendered
against it at commit time. Neither is worth anything if nobody re-runs it: a
manifest that cites `layout/reports/temp_por_top/drc.json` is a claim about
*that* report against *that* GDS, and the moment either moves without the
claim moving with it, the committed verdict is a statement about a tree that
no longer exists.

This script is what stops that. It re-runs the grader and refuses to pass on
any drift between what is committed and what the current tree actually
grades to. Four distinct checks, because `klt signoff` alone cannot cover all
four (see signoff/README.md, "What the grader cannot check"):

1. **Hand-rolled evidence is self-consistent.** A generic evidence envelope
   (`"kind": "generic"`) is written by hand, and so is the `content_hash`
   inside it. `klt signoff` compares the manifest's pin against *the
   envelope's own recorded hash* -- it never opens the underlying artifact,
   so two hand-written hashes agreeing with each other proves nothing. This
   re-hashes the file the envelope's `source` names and requires it to match.
2. **Committed DRC/LVS reports still describe the committed GDS.** Delegated
   to `layout/lvs_reference.py --check-gds-hash`, which already does exactly
   this. It matters most for item 4: `klt lvs` (through 0.5.0, the latest
   release) populates no `provenance.input` block, so item 4's citation
   cannot carry a `content_hash` pin at all and `klt signoff` has no
   freshness gate for it. This check is that gate.
3. **The grader itself runs clean.** Exit 0 (`tier: "T1"`) or 3 (`tier:
   null`, at least one item unmet) are both fine -- an all-`unmet` report is
   a correct result. Exit 1/2 mean the manifest or the tiers doc is
   malformed, which is a real failure.
4. **The committed report still matches the rendered one.** Compared on a
   normalized projection (per-item `status`/`reason`, counts, tier), so a
   `klt` release that merely adds a field does not trip it -- but a citation
   going stale, a check starting to fail, or the T1 checklist itself growing
   an item all do.

Pure stdlib; no PDK, no xschem, no ngspice. Only `klt` on PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGNOFF_DIR = REPO_ROOT / "signoff"
MANIFEST = SIGNOFF_DIR / "block-manifest.json"
REPORT = SIGNOFF_DIR / "tier-report.json"
TOOLCHAIN = SIGNOFF_DIR / "toolchain.json"
EVIDENCE_DIR = SIGNOFF_DIR / "evidence"

# `klt signoff --manifest` exit codes that mean "the grader ran": 0 is
# tier T1, 3 is "ran fine, at least one item unmet". Anything else is a
# malformed manifest / unparsable tiers doc / usage error.
RAN_CLEAN = (0, 3)


def fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def check_generic_envelopes() -> bool:
    """Every hand-rolled generic envelope's pinned hash matches its source."""
    ok = True
    if not EVIDENCE_DIR.is_dir():
        return ok
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        try:
            envelope = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            fail(f"{path.relative_to(REPO_ROOT)}: unreadable ({exc})")
            ok = False
            continue
        if not isinstance(envelope, dict) or envelope.get("kind") != "generic":
            continue
        source = envelope.get("source")
        pinned = (envelope.get("provenance") or {}).get("input", {}).get(
            "content_hash"
        )
        rel = path.relative_to(REPO_ROOT)
        if not source:
            fail(
                f"{rel}: a generic envelope must name the artifact it wraps in "
                '"source", so its freshness can be re-derived'
            )
            ok = False
            continue
        if not pinned:
            fail(
                f"{rel}: no provenance.input.content_hash -- an unpinned generic "
                "envelope's freshness cannot be verified at all"
            )
            ok = False
            continue
        source_path = REPO_ROOT / source
        if not source_path.is_file():
            fail(f"{rel}: source {source!r} does not exist")
            ok = False
            continue
        actual = sha256_file(source_path)
        if actual != pinned:
            fail(
                f"{rel}: pinned {pinned} but {source} now hashes to {actual}.\n"
                f"     {source} changed since this characterization claim was "
                "made. Re-read it, update the envelope's summary if the\n"
                "     disclosed exceptions moved, then re-pin the hash here "
                "and in signoff/block-manifest.json and run --regen."
            )
            ok = False
            continue
        print(f"ok   {rel}: pinned hash matches {source}")
    return ok


def check_committed_report_hashes() -> bool:
    """layout/reports/ still describe the GDS actually committed."""
    script = REPO_ROOT / "layout" / "lvs_reference.py"
    if not script.is_file():
        fail("layout/lvs_reference.py is missing; cannot verify report freshness")
        return False
    proc = subprocess.run(
        [sys.executable, str(script), "--check-gds-hash"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        fail(
            "layout/lvs_reference.py --check-gds-hash: a committed report no "
            "longer describes its committed .gds"
        )
        return False
    return True


def check_toolchain_pin() -> None:
    """Warn -- never fail -- when the grader on PATH is not the pinned one."""
    try:
        pinned = json.loads(TOOLCHAIN.read_text())["klt"]["version"]
    except (OSError, ValueError, KeyError):
        print(f"warn {TOOLCHAIN.name}: no readable klt version pin", file=sys.stderr)
        return
    proc = subprocess.run(["klt", "--version"], capture_output=True, text=True)
    actual = proc.stdout.strip() or proc.stderr.strip()
    if actual != pinned:
        print(
            f"warn grader is {actual!r}, signoff/toolchain.json pins {pinned!r}.\n"
            "     Not a failure: a newer grader is how a newly-added T1 item "
            "reaches this repo.\n"
            "     The report-drift check below is what turns that into an "
            "actionable failure.",
            file=sys.stderr,
        )
    else:
        print(f"ok   grader is the pinned {actual}")


def run_grader() -> tuple[dict, bool]:
    proc = subprocess.run(
        [
            "klt",
            "signoff",
            "--manifest",
            str(MANIFEST.relative_to(REPO_ROOT)),
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in RAN_CLEAN:
        fail(
            f"klt signoff --manifest exited {proc.returncode} (expected 0 or 3). "
            "The manifest or the tiers doc is malformed:"
        )
        sys.stderr.write(proc.stderr)
        return {}, False
    try:
        return json.loads(proc.stdout), True
    except ValueError as exc:
        fail(f"klt signoff produced output that is not valid JSON: {exc}")
        return {}, False


def projection(report: dict) -> dict:
    """The part of a tier report whose drift is a real, actionable change.

    Deliberately excludes `citation` detail and `schema_version`: a klt
    release that adds a citation field (e.g. issue #2002's DRC `coverage`
    block) is not rot, and should not fail this gate. Per-item
    `status`/`reason`, the item set itself, and the counts are what a reader
    of signoff/tier-report.json is relying on.
    """
    return {
        "block": report.get("block"),
        "kind": report.get("kind"),
        "tier": report.get("tier"),
        "t1_item_count": report.get("t1_item_count"),
        "t1_met_count": report.get("t1_met_count"),
        "items": [
            {
                "tier": item.get("tier"),
                "id": item.get("id"),
                "partition": item.get("partition"),
                "status": item.get("status"),
                "reason": item.get("reason"),
            }
            for item in report.get("items", [])
        ],
    }


def check_no_stale(report: dict) -> bool:
    stale = [
        item
        for item in report.get("items", [])
        if item.get("reason") == "stale_evidence"
    ]
    if not stale:
        return True
    for item in stale:
        fail(
            f"T1 item {item.get('id')} ({item.get('title')}): stale_evidence -- "
            "the cited check ran against a different input revision than the "
            "manifest pins."
        )
    return False


def check_drift(report: dict) -> bool:
    if not REPORT.is_file():
        fail(
            f"{REPORT.relative_to(REPO_ROOT)} is missing. "
            "Run: python3 signoff/check.py --regen"
        )
        return False
    try:
        committed = json.loads(REPORT.read_text())
    except ValueError as exc:
        fail(f"{REPORT.relative_to(REPO_ROOT)} is not valid JSON: {exc}")
        return False
    want, got = projection(committed), projection(report)
    if want == got:
        print(
            f"ok   {REPORT.relative_to(REPO_ROOT)} matches what the current "
            "tree grades to"
        )
        return True
    fail(
        f"{REPORT.relative_to(REPO_ROOT)} no longer matches what the current "
        "tree grades to."
    )
    by_id = {(i["tier"], i["id"], i["partition"]): i for i in want["items"]}
    for item in got["items"]:
        key = (item["tier"], item["id"], item["partition"])
        old = by_id.pop(key, None)
        if old is None:
            print(
                f"     + new checklist row {key}: {item['status']}"
                f" ({item['reason']})",
                file=sys.stderr,
            )
        elif old != item:
            print(
                f"     ~ {key}: committed {old['status']}/{old['reason']}"
                f" -> now {item['status']}/{item['reason']}",
                file=sys.stderr,
            )
    for key in by_id:
        print(f"     - checklist row {key} no longer rendered", file=sys.stderr)
    for field in ("block", "kind", "tier", "t1_item_count", "t1_met_count"):
        if want[field] != got[field]:
            print(
                f"     ~ {field}: committed {want[field]!r} -> now {got[field]!r}",
                file=sys.stderr,
            )
    print(
        "     If the new verdict is the correct one, regenerate the evidence "
        "record and commit it:\n"
        "       python3 signoff/check.py --regen\n"
        "     and update signoff/README.md's claim to match -- the prose and "
        "the report are one artifact, not two.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--regen",
        action="store_true",
        help=(
            "rewrite signoff/tier-report.json from the current tree instead of "
            "comparing against it"
        ),
    )
    args = parser.parse_args(argv)

    if shutil.which("klt") is None:
        fail(
            "klt is not on PATH. Install the pinned grader:\n"
            "       uv tool install --force klayout-tools==0.5.0\n"
            "     (see signoff/toolchain.json for why this pin is separate "
            "from layout/toolchain.json's)"
        )
        return 1

    check_toolchain_pin()

    ok = check_generic_envelopes()
    ok = check_committed_report_hashes() and ok

    report, ran = run_grader()
    if not ran:
        return 1

    if args.regen:
        REPORT.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {REPORT.relative_to(REPO_ROOT)}")
        print(
            f"     tier={report.get('tier')} "
            f"met={report.get('t1_met_count')}/{report.get('t1_item_count')}"
        )
        return 0 if ok else 1

    ok = check_no_stale(report) and ok
    ok = check_drift(report) and ok

    print(
        f"     tier={report.get('tier')} "
        f"met={report.get('t1_met_count')}/{report.get('t1_item_count')} "
        f"(source_doc={report.get('source_doc')})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
