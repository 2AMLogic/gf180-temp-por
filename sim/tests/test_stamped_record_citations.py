#!/usr/bin/env python3
"""Fails when a `design/*.md` section cites a dirty-tree-stamped `sim/`
record without naming the caveat (#209).

`sim/harness/report.py` and `mc_report.py` stamp a record's **Netlist
provenance** field with "-- **taken against a dirty working tree** at commit
<sha>; not citable as a clean-tree result" when the run was collected against
uncommitted work. `sim/README.md` -> "Citing a 'taken against a dirty working
tree' record" states what such a record may be cited for, and requires a
design doc that cites one to either point at a clean-tree successor instead
or name the caveat where it cites it.

The root cause #209 found is that **nothing connected the stamp to its
consumers**: the stamp lives in the record, the citation lives in a design
doc, and no check crossed the two. Documenting the policy alone would not
have caught the recurrence that landed while #209 was open -- PR #222 minted
two more stamped records and cited them in `design/bias_core.md` uncaveated.
This test crosses them, so the next one fails CI here.

Scope is deliberately `design/*.md` only. `spec/target-spec.md` and the
ratified decision records under `spec/decision-records/` also cite stamped
records, but those are ratified documents that change through a decision
record rather than through a CI nudge (CLAUDE.md: "Spec changes go through
`spec/` with a decision record"), so this check does not demand edits to
them. `GRANDFATHERED` below carries the design-doc citations that predate the
policy; it is a ratchet -- entries may be removed as each site is caveated or
re-pointed, and `test_the_grandfather_list_has_no_stale_entries` fails if a
listed entry is no longer needed, so the list can only shrink.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
DESIGN_DIR = REPO_ROOT / "design"

# The literal the harness appends to a stamped record's Netlist provenance
# field. `test_the_stamp_text_still_matches_the_harness` pins this against
# the harness source, so rewording the stamp fails loudly here instead of
# silently turning this whole check into a no-op.
STAMP = "not citable as a clean-tree result"

# Phrases that count as "the caveat is named". A section containing any of
# these is telling the reader that clean-tree provenance is at issue; the
# policy asks for that acknowledgement, not for one exact wording.
CAVEAT_MARKERS = (
    "dirty working tree",
    "not citable",
    "dirty-tree",
    "clean-tree",
)

# (design doc, stamped record-id) citations that predate #209's policy.
# Ratchet: shrink-only. Each value says what a future fix would do.
GRANDFATHERED: dict[tuple[str, str], str] = {
    (
        "design/bias_core.md",
        "20260801-073555-8b7e57f",
    ): "schematic-level bias-core-ibias-sharing baseline; superseded in "
    "practice by the clean-tree 20260801-152327-b72c10c, so the two "
    "citation sites can be re-pointed",
    (
        "design/bias_core.md",
        "20260801-074334-8b7e57f",
    ): "schematic-level temp-por-top-release record, cited for the "
    "assembly-level Iq cross-check; needs a clean-tree re-run or a caveat",
    (
        "design/bias_core.md",
        "20260801-111049-bc599be",
    ): "superseded bias-core-startup record cited for the historical "
    "BIAS_OK quasi-static narrative; qualitative use, caveat still owed",
    (
        "design/bias_core.md",
        "20260802-000004-32fbaa0",
    ): "por-ramp-rate record cited for the chatter comparison; a "
    "full-assembly ramp sweep, so a re-run is not cheap",
    (
        "design/bias_core.md",
        "20260802-134958-dd0cd60",
    ): "por-brownout-slew schematic baseline; caveated in "
    "design/temp_por_top.md by #209 but not yet at this site",
    (
        "design/por_output_chain.md",
        "20260802-000004-32fbaa0",
    ): "same por-ramp-rate record as above, cited from this cell's "
    "assembly-level findings section",
    (
        "design/por_output_chain.md",
        "20260811-110752-d5b0168",
    ): "post-layout deglitch CDG-bound record minted by #201; a clean-tree "
    "re-run of that deck would clear it",
    (
        "design/temp_core.md",
        "20260801-073732-8b7e57f",
    ): "temp-core-designer-check schematic baseline; cited only for the "
    "qualitative 216/216-unchanged finding, which the policy permits, but "
    "the section does not say so",
    (
        "design/temp_core.md",
        "20260801-073944-8b7e57f",
    ): "temp-core-startup schematic record cited from the same summary "
    "block as the line above",
    (
        "design/temp_core.md",
        "20260801-074334-8b7e57f",
    ): "temp-por-top-release schematic record cited from the same summary "
    "block as the two lines above",
}


def _stamped_record_ids() -> dict[str, Path]:
    """Record-id -> path, for every `sim/*/records/*.md` carrying the stamp."""
    found: dict[str, Path] = {}
    for path in sorted(SIM_DIR.glob("*/records/*.md")):
        if STAMP in path.read_text(encoding="utf-8"):
            found[path.stem] = path
    return found


def _sections(lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) line-index spans, one per markdown ATX heading, plus a
    leading span for any preamble before the first heading."""
    heads = [i for i, line in enumerate(lines) if line.startswith("#")]
    if not heads:
        return [(0, len(lines))]
    if heads[0] != 0:
        heads = [0] + heads
    return [
        (start, heads[n + 1] if n + 1 < len(heads) else len(lines))
        for n, start in enumerate(heads)
    ]


def _uncaveated_citations() -> dict[tuple[str, str], list[int]]:
    """(design-doc path, stamped record-id) -> 1-based line numbers of the
    citations whose enclosing section never names the caveat."""
    stamped = _stamped_record_ids()
    offenders: dict[tuple[str, str], list[int]] = {}
    for doc in sorted(DESIGN_DIR.glob("*.md")):
        lines = doc.read_text(encoding="utf-8").splitlines()
        spans = _sections(lines)
        rel = doc.relative_to(REPO_ROOT).as_posix()
        for index, line in enumerate(lines):
            for record_id in stamped:
                if record_id not in line:
                    continue
                start, end = next(
                    span for span in spans if span[0] <= index < span[1]
                )
                body = "\n".join(lines[start:end])
                if any(marker in body for marker in CAVEAT_MARKERS):
                    continue
                offenders.setdefault((rel, record_id), []).append(index + 1)
    return offenders


class StampDiscoveryTests(unittest.TestCase):
    """If the stamp text or the record layout drifts, this check silently
    stops checking anything. These two tests make that drift fail instead."""

    def test_the_stamp_text_still_matches_the_harness(self):
        for module in ("report.py", "mc_report.py"):
            source = (SIM_DIR / "harness" / module).read_text(encoding="utf-8")
            self.assertIn(
                STAMP,
                source,
                f"sim/harness/{module} no longer emits the literal "
                f"{STAMP!r}. Update STAMP in this test to match -- otherwise "
                "the dirty-tree citation check quietly passes on every "
                "design doc.",
            )

    def test_at_least_one_stamped_record_is_discoverable(self):
        self.assertTrue(
            _stamped_record_ids(),
            "no record under sim/*/records/ carries the dirty-tree stamp. "
            "That is either very good news or a sign this test's discovery "
            "glob has drifted from the record layout.",
        )


class DesignDocCitationTests(unittest.TestCase):
    """sim/README.md's citation policy, enforced against design/*.md."""

    def test_no_new_uncaveated_citation_of_a_stamped_record(self):
        offenders = {
            pair: lines
            for pair, lines in _uncaveated_citations().items()
            if pair not in GRANDFATHERED
        }
        if not offenders:
            return
        detail = "\n".join(
            f"  {doc}:{','.join(str(n) for n in lines)} cites {record_id}"
            for (doc, record_id), lines in sorted(offenders.items())
        )
        self.fail(
            "design doc(s) cite a record the harness stamped "
            f"'{STAMP}' without naming the caveat in the citing section:\n"
            f"{detail}\n\n"
            "Per sim/README.md -> \"Citing a 'taken against a dirty working "
            'tree\' record", do one of:\n'
            "  (a) re-point the citation at a clean-tree successor record "
            "(no stamp, same numbers); or\n"
            "  (b) name the caveat in the citing section -- any of "
            f"{list(CAVEAT_MARKERS)} satisfies this check.\n"
            "Do NOT add the citation to GRANDFATHERED: that list is for "
            "sites predating the policy and is shrink-only."
        )

    def test_the_grandfather_list_has_no_stale_entries(self):
        stale = sorted(set(GRANDFATHERED) - set(_uncaveated_citations()))
        self.assertEqual(
            [],
            stale,
            "GRANDFATHERED lists citation(s) that are no longer uncaveated "
            f"(or no longer present): {stale}. Delete the entr(ies) -- the "
            "ratchet only tightens.",
        )


if __name__ == "__main__":
    unittest.main()
