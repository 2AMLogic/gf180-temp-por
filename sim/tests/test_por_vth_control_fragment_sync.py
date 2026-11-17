#!/usr/bin/env python3
"""Fails if the two named stimulus fragments under sim/por-vth/control/
drift apart card-wise (#509, #550).

``rate_ladder.spice`` and ``ramp_rate_probe.spice`` are separate files on
purpose -- sim/README.md ("One ``control/`` may hold more than one control.
When a second, distinct question arises about the same experiment, it gets
its own fragment ... beside the first rather than being folded into it")
keeps each control self-contained for reproduction. Do NOT merge them or
have one ``.include`` the other; the two files stay separate per
sim/README.md.

But separate files that are hand-copied can drift. ``run_rate_ladder.py``'s
docstring stakes its Arm C cross-check (215.655 mV there vs 215.660 mV here,
same corner, same rate) on the two controls "measuring the same thing", and
that identity holds only while the two stimuli agree: edit ``t_hold`` in one
fragment and not the other, and both ``results.md`` files still regenerate
while the published agreement quietly stops meaning anything. This test
converts that hand-maintained identity into a checked one, so the next
one-sided edit fails here instead of invalidating the cross-check.

The pair is named explicitly rather than discovered by a directory glob
(#550): card-identity is a property of these two files -- the ones the Arm C
cross-check depends on -- not of every ``*.spice`` in ``control/``.
sim/README.md ratifies a third fragment answering a different question
landing beside these two with deliberately different cards; such a fragment
is out of scope here, not a failure. The paths are direct children of
``control/`` (never ``decks/``), so the generated decks stay out of scope by
construction.

Comment (``*``) and blank lines are stripped before comparison: prose may
drift freely; cards may not.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
CONTROL_DIR = SIM_DIR / "por-vth" / "control"

# The two fragments whose shared stimulus run_rate_ladder.py's Arm C
# cross-check depends on, named explicitly: a card-identity claim over a
# named pair, not over whatever a directory glob happens to return.
PAIR = ("ramp_rate_probe.spice", "rate_ladder.spice")
PAIR_PATHS = [CONTROL_DIR / name for name in PAIR]


def _cards(fragment: Path) -> list[str]:
    """A fragment's netlist cards: its non-comment, non-blank lines, in order."""
    cards = []
    for line in fragment.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("*"):
            cards.append(stripped)
    return cards


class PorVthControlFragmentSyncTests(unittest.TestCase):
    """The two named fragments in PAIR must carry the same cards.

    The claim is two-file, not directory-wide: a distinct third control
    belongs beside these per sim/README.md and may carry deliberately
    different cards without failing this test.
    """

    def test_named_fragments_are_present(self):
        for path in PAIR_PATHS:
            self.assertTrue(
                path.is_file(),
                f"sim/por-vth/control/{path.name} is missing -- this test "
                f"checks that exact file by name (see PAIR); if it was "
                f"renamed or moved, update PAIR rather than weakening the "
                f"check",
            )

    def test_named_pair_carries_identical_cards(self):
        reference, other = PAIR_PATHS
        self.assertEqual(
            _cards(reference),
            _cards(other),
            f"{reference.name} and {other.name} have drifted apart: these "
            f"two fragments, and only these two, must stay card-identical "
            f"-- run_rate_ladder.py's Arm C cross-check depends on both "
            f"measuring the same stimulus. Edit both fragments together, "
            f"or, if the change answers a genuinely different question, "
            f"give it its own new fragment beside these per sim/README.md "
            f"and leave this pair alone.",
        )


if __name__ == "__main__":
    unittest.main()
