#!/usr/bin/env python3
"""Fail a change that edits, deletes, or moves existing `sim/` evidence (#353).

`sim/README.md` -> "Append-only rule": evidence is never edited or deleted
after creation, not even for a typo fix; a correction is a new record that
names the old one under **Supersedes**. This script turns that rule into a
mechanical check on the diff between a base ref and HEAD.

    python3 sim/check_append_only.py [--base origin/main] [--repo PATH]

It diffs `<merge-base of --base and HEAD>..HEAD` with `--no-renames`, so a
rename or move appears as a delete plus an add and fails on the delete.
Additions always pass. There is deliberately no allowlist, flag, or
environment bypass: the only way to correct evidence is a superseding record.

Exit codes: 0 pass, 1 protected evidence was modified/deleted/retyped,
2 the base ref (or a merge-base with it) could not be resolved -- never a
silent pass.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Single source of truth for the protected evidence paths. Mirrored in
# sim/README.md § "Append-only rule". `control/`, `devchar/results/` and
# `testbench/` are intentionally absent: the README documents them as
# overwritable or separately governed.
PROTECTED_DIRS = ("records", "corners", "netlist-snapshots")
PROTECTED = re.compile(r"^sim/[^/]+/(?:%s)/" % "|".join(PROTECTED_DIRS))

README_POINTER = (
    'sim/README.md § "Append-only rule" -- supersede with a new record instead'
)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )


def violations(repo, base):
    """Return (violations, error). `violations` is [(status, path)]."""
    mb = _git(repo, "merge-base", base, "HEAD")
    if mb.returncode != 0 or not mb.stdout.strip():
        return None, (
            "cannot resolve a merge-base between %r and HEAD (is the base ref "
            "fetched? a shallow checkout needs fetch-depth: 0): %s"
            % (base, mb.stderr.strip() or "no common ancestor")
        )
    diff = _git(
        repo, "diff", "--name-status", "--no-renames", "-z",
        "%s..HEAD" % mb.stdout.strip(),
    )
    if diff.returncode != 0:
        return None, "git diff failed: %s" % diff.stderr.strip()
    fields = diff.stdout.split("\0")
    found = []
    # With --no-renames and -z the stream is: STATUS \0 PATH \0 ...
    for status, path in zip(fields[0::2], fields[1::2]):
        if status != "A" and PROTECTED.match(path):
            found.append((status, path))
    return found, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="origin/main",
                    help="base ref to compare against (default: origin/main)")
    ap.add_argument("--repo", default=".", help="repository path (default: .)")
    args = ap.parse_args(argv)

    found, err = violations(args.repo, args.base)
    if err:
        print("check_append_only: ERROR: %s" % err, file=sys.stderr)
        return 2
    if not found:
        print("check_append_only: OK (no protected evidence modified or deleted)")
        return 0
    print("check_append_only: FAIL: protected evidence was changed:",
          file=sys.stderr)
    names = {"M": "modified", "D": "deleted", "T": "type-changed"}
    for status, path in found:
        print("  %s: %s\n      %s" % (names.get(status, status), path,
                                      README_POINTER), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
