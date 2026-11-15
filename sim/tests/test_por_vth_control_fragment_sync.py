#!/usr/bin/env python3
"""Fails if the stimulus fragments under sim/por-vth/control/ drift apart
card-wise (#509).

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

Comment (``*``) and blank lines are stripped before comparison: prose may
drift freely; cards may not.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
CONTROL_DIR = SIM_DIR / "por-vth" / "control"


def _cards(fragment: Path) -> list[str]:
    """A fragment's netlist cards: its non-comment, non-blank lines, in order."""
    cards = []
    for line in fragment.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("*"):
            cards.append(stripped)
    return cards


class PorVthControlFragmentSyncTests(unittest.TestCase):
    """Every fragment in sim/por-vth/control/ must carry the same cards."""

    def test_both_fragments_are_present(self):
        fragments = sorted(CONTROL_DIR.glob("*.spice"))
        self.assertGreaterEqual(
            len(fragments),
            2,
            f"expected both stimulus fragments in {CONTROL_DIR}, found "
            f"{[f.name for f in fragments]} -- if a fragment was renamed, "
            f"update this test's directory, not the invariant",
        )

    def test_all_fragments_carry_identical_cards(self):
        fragments = sorted(CONTROL_DIR.glob("*.spice"))
        reference = fragments[0]
        for other in fragments[1:]:
            self.assertEqual(
                _cards(reference),
                _cards(other),
                f"{reference.name} and {other.name} have drifted apart: the "
                f"controls under {CONTROL_DIR} must stay card-identical -- "
                f"run_rate_ladder.py's Arm C cross-check depends on both "
                f"measuring the same stimulus. Edit both fragments together, "
                f"or move a genuinely different control to its own directory.",
            )


if __name__ == "__main__":
    unittest.main()
