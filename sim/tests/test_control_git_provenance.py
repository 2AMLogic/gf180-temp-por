#!/usr/bin/env python3
"""Fails when a control script emits an ngspice provenance block but no
``- git:`` line (#507).

Every control script that writes a provenance block into its ``results.md``
must also record ``runner.git_describe(REPO_ROOT, GENERATED)`` -- the line
that ties the recorded numbers to the commit that produced them and says
whether anything outside the script's own outputs was dirty at the time.
Before #507 the four scripts in ``sim/por-output-chain-deglitch/control/``
emitted the block but stopped one line short, and nothing in the tree
connected "emits a provenance block" to "wires ``git_describe``": the gap was
invisible unless someone remembered it (the one name that hinted at it,
``GENERATED``, had just been deleted as unread by #503). This test crosses
the two, so the next one fails CI here.

Scope is deliberately the provenance-emitting control scripts only. The
control scripts that emit no provenance block at all are a different (and
larger) question, not this check. ``GRANDFATHERED`` below carries scripts
with the gap whose fix is tracked separately; it is a ratchet -- entries may
be removed as each script is wired, and
``test_the_grandfather_list_has_no_stale_entries`` fails if a listed entry no
longer needs the exemption, so the list can only shrink.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent

# The literal that marks a provenance block, in every emitting script: an
# f-string like f"- ngspice: `{ngspice_version}`" or a template line
# "- ngspice: {ngspice_version}". test_the_detector_literals_still_match pins
# this against known-good scripts, so rewording the provenance lines fails
# loudly here instead of silently turning this whole check into a no-op.
PROVENANCE_MARKER = "- ngspice:"

# The emitted line itself, in the written provenance block. Two of the wired
# scripts carry it as a bare template line inside a multi-line f-string
# (run_gmin_control.py, run_mismatch_switch.py) rather than as an f-string
# list element, so this is matched as a bare literal, never a line-anchored
# regex. test_the_detector_literals_still_match_known_good_scripts pins it the
# same way as PROVENANCE_MARKER: rewording the emitted line fails loudly
# instead of quietly narrowing what "wired" means.
GIT_MARKER = "- git:"

# The wiring this check demands: a GENERATED tuple (the dirty-path allowlist
# runner.git_describe skips), the call to the helper, and the ``- git:`` line
# itself reaching the written block -- defining GENERATED and calling
# git_describe() without emitting the line leaves the recorded results with
# no commit hash, which is exactly the gap this check exists to catch.
GENERATED_DEF = re.compile(r"^GENERATED\s*=", re.MULTILINE)
GIT_DESCRIBE_CALL = "git_describe("

# The five scripts that already carry the ``- git:`` line. They exist so the
# positive direction of both detectors is exercised every run, not only when
# something breaks.
WIRED_PEERS = (
    "sim/bias-core-startup/control/run_gmin_control.py",
    "sim/por-glitch/control/run_depth_sweep.py",
    "sim/por-glitch/control/run_glitch_probe.py",
    "sim/por-ramp-rate/control/run_chatter_probe.py",
    "sim/temp-accuracy-mc/control/run_mismatch_switch.py",
)

# Scripts with the gap whose fix is tracked separately. Ratchet: shrink-only.
# Each value says what wiring it needs and where that is tracked.
GRANDFATHERED: dict[str, str] = {
    "sim/por-output-chain-deglitch/control/run_dwell_sweep.py": (
        "a 36-deck grid across variants and bias arms with -j/--jobs and a"
        " klt_batch backend; its re-run belongs on the batch fleet -- #508"
    ),
}


def _control_scripts() -> dict[str, str]:
    """Repo-relative path -> source, for every ``sim/*/control/*.py``."""
    return {
        path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SIM_DIR.glob("*/control/*.py"))
    }


def _emits_provenance(source: str) -> bool:
    return PROVENANCE_MARKER in source


def _wires_git(source: str) -> bool:
    return (
        GIT_DESCRIBE_CALL in source
        and GENERATED_DEF.search(source) is not None
        and GIT_MARKER in source
    )


class DetectorDriftTests(unittest.TestCase):
    """If the literals this check greps for drift, the check silently stops
    checking anything. These tests make that drift fail instead."""

    def test_the_detector_literals_still_match_known_good_scripts(self):
        for rel in WIRED_PEERS:
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertTrue(
                _emits_provenance(source),
                f"{rel} no longer contains {PROVENANCE_MARKER!r}. Update "
                "PROVENANCE_MARKER in this test to match -- otherwise the "
                "provenance-without-git check quietly passes on every script.",
            )
            self.assertTrue(
                GIT_MARKER in source,
                f"{rel} no longer contains {GIT_MARKER!r}. Update GIT_MARKER "
                "in this test to match -- otherwise the check passes on "
                "every script without demanding the emitted `- git:` line "
                "it exists to require.",
            )
            self.assertTrue(
                _wires_git(source),
                f"{rel} no longer defines GENERATED, calls "
                f"{GIT_DESCRIBE_CALL}, or emits {GIT_MARKER!r}. Update the "
                "wiring detectors in this test to match -- otherwise the "
                "check demands the wrong shape.",
            )

    def test_wires_git_rejects_wiring_that_never_emits_the_line(self):
        # Defines GENERATED, calls git_describe(), emits a provenance block
        # -- but stops one line short of the `- git:` line. The old detector
        # called this wired; the tightened one must not.
        wired_but_unemitted = (
            "import runner\n"
            'GENERATED = ("sim/foo/control/foo_results.md",)\n'
            "description = runner.git_describe(REPO_ROOT, GENERATED)\n"
            'lines.append(f"- ngspice: `{runner.ngspice_version()}`")\n'
        )
        self.assertFalse(
            _wires_git(wired_but_unemitted),
            "defining GENERATED and calling git_describe() without ever "
            "writing a `- git:` line must not count as wired: the recorded "
            "results would carry no commit hash. If this fails, the "
            "GIT_MARKER conjunct has been dropped from _wires_git().",
        )
        self.assertTrue(
            _wires_git(
                wired_but_unemitted + '-lines.append(f"- git: {description}")\n'
            ),
            "a source that wires git_describe AND emits the `- git:` line "
            "must count as wired -- the tightening above must not become a "
            "ban on wiring.",
        )

    def test_every_wired_peer_is_discoverable(self):
        missing = set(WIRED_PEERS) - _control_scripts().keys()
        self.assertFalse(
            missing,
            f"wired peer(s) no longer match any control script on disk: "
            f"{sorted(missing)}. That is either a rename or a sign this "
            "test's discovery glob has drifted from sim/*/control/*.py.",
        )


class ControlScriptProvenanceTests(unittest.TestCase):
    """Every provenance-emitting control script records its commit."""

    def test_no_control_script_emits_provenance_without_a_git_line(self):
        offenders = [
            rel
            for rel, source in _control_scripts().items()
            if _emits_provenance(source)
            and not _wires_git(source)
            and rel not in GRANDFATHERED
        ]
        if not offenders:
            return
        self.fail(
            "control script(s) emit an ngspice provenance block but no "
            f"`- git:` line:\n{chr(10).join(f'  {rel}' for rel in offenders)}\n\n"
            "Add a module-level GENERATED tuple naming every path a re-run is "
            "allowed to dirty (this script's own outputs plus its siblings' -- "
            "they share the control directory), and a "
            "`- git: `{runner.git_describe(REPO_ROOT, GENERATED)}`` line in "
            "the provenance block. Model: "
            "sim/por-glitch/control/run_depth_sweep.py. The committed "
            "results file must then be regenerated by running the script, "
            "never hand-edited.\n"
            "Do NOT add the script to GRANDFATHERED: that list is for scripts "
            "whose re-run is tracked separately, and it is shrink-only."
        )

    def test_the_grandfather_list_has_no_stale_entries(self):
        scripts = _control_scripts()
        stale = [
            rel
            for rel in GRANDFATHERED
            if rel not in scripts
            or _wires_git(scripts[rel])
            or not _emits_provenance(scripts[rel])
        ]
        self.assertEqual(
            [],
            stale,
            f"GRANDFATHERED lists script(s) that no longer need the "
            f"exemption: {stale}. Delete the entr(ies) -- the ratchet only "
            "tightens.",
        )


if __name__ == "__main__":
    unittest.main()
