#!/usr/bin/env python3
"""Every post-layout testbench fragment still matches the netlist it cites (#316).

No PDK, no ngspice: this is a hash comparison.

`sim/build_tb.py --check` already guards the fragments build_tb.py *generates*
-- it regenerates them and diffs. It cannot guard the ones it does not manage:
a fragment that edits ports *inside* a subcircuit body (the #274/#298
loop-break testbenches) is hand-forked from `layout/postlayout/<cell>.spice`
and deliberately absent from `POSTLAYOUT_FRAGMENTS`, because registering it
there would make `--check` overwrite the hand edits.

That gap is not hypothetical: #314 regenerated every
`layout/postlayout/*.spice` against a newer `klt` whose parasitic model is a
different shape, PR #317 rebuilt all twenty managed fragments, and
`sim/temp-core-loop-stability/testbench-postlayout/` -- the one hand-forked
fragment -- was left inlining the retired model with nothing in CI to say so
(#316 re-forked it). This test closes that hole generically rather than for
that one file: a fragment that cites a source netlist's sha256 must match it,
and a fragment outside `POSTLAYOUT_FRAGMENTS` must cite one.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from build_tb import POSTLAYOUT_FRAGMENTS  # noqa: E402
from postlayout_delta import POSTLAYOUT_TESTBENCH_DIRNAME  # noqa: E402

#: ``layout/postlayout/<cell>.spice  (sha256 <64 hex>)``, in either of the two
#: spellings in use: ``build_tb.py``'s generated "Sources:" block and a
#: hand-maintained fork's "Forked from" line. Matched against the comment
#: block flattened onto one line first, so a digest wrapped across a ``*``
#: continuation still matches.
CITATION = re.compile(
    r"layout/postlayout/(?P<cell>\S+?\.spice)[^\S\n]*\(sha256\s+(?P<digest>[0-9a-f]{64})"
)


def fragments() -> list[Path]:
    return sorted(REPO_ROOT.glob(f"sim/*/{POSTLAYOUT_TESTBENCH_DIRNAME}/*.spice"))


def flattened(path: Path) -> str:
    """``path``'s text with ``*`` comment continuations joined onto one line."""
    return re.sub(r"\n\*\s*", " ", path.read_text())


class PostlayoutFragmentProvenanceTests(unittest.TestCase):
    def test_there_are_fragments_to_check(self):
        # Guards against this whole file silently becoming a no-op if the
        # directory convention changes.
        self.assertGreater(len(fragments()), 0)

    def test_every_cited_source_netlist_digest_is_current(self):
        """A regenerated `layout/postlayout/<cell>.spice` fails here, by name.

        Covers the hand-maintained forks `build_tb.py --check` cannot see, and
        (harmlessly, as defence in depth) the generated fragments it can.
        """
        stale = []
        checked = 0
        for fragment in fragments():
            for match in CITATION.finditer(flattened(fragment)):
                source = REPO_ROOT / "layout" / "postlayout" / match.group("cell")
                self.assertTrue(source.is_file(), f"{fragment}: cites missing {source}")
                current = hashlib.sha256(source.read_bytes()).hexdigest()
                checked += 1
                if current != match.group("digest"):
                    stale.append(
                        f"{fragment.relative_to(REPO_ROOT)} cites "
                        f"{match.group('cell')} @ {match.group('digest')[:12]}…, "
                        f"but it is now {current[:12]}…"
                    )
        self.assertGreater(checked, 0, "no fragment cites a source digest at all")
        self.assertEqual(
            stale,
            [],
            "stale post-layout fragment(s) -- re-generate with "
            "`python3 sim/build_tb.py` if build_tb.py manages it, or re-fork "
            "it by hand (re-applying its edits and updating its digest) if it "
            "does not:\n  " + "\n  ".join(stale),
        )

    def test_a_hand_maintained_fork_cites_the_netlist_it_was_forked_from(self):
        """The provenance line is what makes the check above possible.

        A fragment outside `POSTLAYOUT_FRAGMENTS` is hand-maintained by
        definition, so nothing else in the repo knows what it was built from.
        `sim/postlayout_delta.py` reads the same line to find the netlist whose
        parasitics belong in a delta record's table.
        """
        missing = []
        for fragment in fragments():
            experiment = fragment.parent.parent.name
            if experiment in POSTLAYOUT_FRAGMENTS:
                continue
            if not CITATION.search(flattened(fragment)):
                missing.append(str(fragment.relative_to(REPO_ROOT)))
        self.assertEqual(
            missing,
            [],
            "hand-maintained fragment(s) with no 'Forked from "
            "layout/postlayout/<cell>.spice (sha256 …)' provenance line, so "
            "neither this test nor sim/postlayout_delta.py can tell what they "
            "were forked from:\n  " + "\n  ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
