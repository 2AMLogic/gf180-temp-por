#!/usr/bin/env python3
"""Fails if sim/por-iq/analyze_por_iq.py's hardcoded targets drift from
spec/target-spec.md's ratified `por-iq` / `iq-total` rows (#207).

The root cause #207 found: nothing connected `analyze_por_iq.py`'s
`TARGET_POR_IQ_UA` / `TARGET_IQ_TOTAL_UA` constants to the spec table they
publish against, so DR-018's re-cost of `por-iq` (<1 uA -> <3.0 uA) landed
in `spec/target-spec.md` without the publishing script following it. This
test reads the ratified ceiling straight out of the Target column of each
row's own table entry and compares it against the constants, so the next
re-cost fails CI here instead of silently drifting again.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR / "por-iq"))

import analyze_por_iq  # noqa: E402

SPEC_PATH = REPO_ROOT / "spec" / "target-spec.md"

# Matches the first "<<number> µA" (or "uA") token in a markdown table cell,
# e.g. "**<3.0 µA [DR-018]** (was <1 µA ...)" -> "3.0".
_CEILING_RE = re.compile(r"<\s*([\d.]+)\s*(?:µA|uA)")


def _target_column(spec_text: str, row_id: str) -> str:
    """The Target column (3rd `|`-delimited field) of `spec/target-spec.md`'s
    row anchored `<a id="row_id">`. Raises AssertionError with a clear
    message if the row cannot be found, so a renamed anchor fails loudly
    rather than silently skipping the check.
    """
    for line in spec_text.splitlines():
        if f'id="{row_id}"' in line:
            fields = line.split("|")
            # fields[0] is "" (line starts with "|"), fields[1] is the ID
            # column, fields[2] is Parameter, fields[3] is Target.
            if len(fields) < 4:
                raise AssertionError(
                    f"spec/target-spec.md row {row_id!r} has fewer than 4 "
                    f"'|'-delimited fields; table layout may have changed: "
                    f"{line!r}"
                )
            return fields[3]
    raise AssertionError(
        f'spec/target-spec.md has no row anchored id="{row_id}"'
    )


def _ceiling_ua(target_column: str) -> float:
    match = _CEILING_RE.search(target_column)
    if match is None:
        raise AssertionError(
            f"could not find a '<N uA'/'<N µA' ceiling in Target column: "
            f"{target_column!r}"
        )
    return float(match.group(1))


def _fake_rows(por_iq_ua: float, temp_iq_ua: float = 10.0) -> list[dict]:
    """One-row grid, enough to exercise render()'s PASS/FAIL branching."""
    return [
        {
            "corner_id": "ff_125c_3.63v",
            "process": "ff",
            "temp_c": 125.0,
            "supply": "3.63",
            "por_iq_ua": por_iq_ua,
            "iq_total_ua": por_iq_ua + temp_iq_ua,
            "temp_iq_ua": temp_iq_ua,
        }
    ]


class RenderRegressionTests(unittest.TestCase):
    """Guards the render() text against the specific #207 regression: a
    hardcoded "expected FAIL" narrative that goes stale once the target
    the row is checked against actually passes (post-DR-018).
    """

    def setUp(self):
        self._orig_source_provenance = analyze_por_iq.source_provenance
        analyze_por_iq.source_provenance = lambda *_a, **_kw: "schematic (fake)"
        self.addCleanup(
            setattr, analyze_por_iq, "source_provenance", self._orig_source_provenance
        )

    def test_a_passing_por_iq_result_says_pass_not_expected_fail(self):
        text = analyze_por_iq.render(
            "fake-id", _fake_rows(2.38), "2026-01-01T00:00:00+00:00", "test", []
        )
        self.assertIn("**Overall: PASS**", text)
        self.assertNotIn("EXPECTED. `design/bias_core.md`", text)

    def test_a_failing_por_iq_result_is_flagged_as_a_regression(self):
        text = analyze_por_iq.render(
            "fake-id", _fake_rows(9.0), "2026-01-01T00:00:00+00:00", "test", []
        )
        self.assertIn("**Overall: FAIL**", text)
        self.assertIn("REGRESSION", text)

    def test_first_record_does_not_claim_supersession(self):
        text = analyze_por_iq.render(
            "fake-id", _fake_rows(2.38), "2026-01-01T00:00:00+00:00", "test", []
        )
        self.assertIn(
            "(none -- first published record for these two rows", text
        )

    def test_a_later_record_names_the_prior_one_without_superseding_it(self):
        text = analyze_por_iq.render(
            "fake-id",
            _fake_rows(2.38),
            "2026-01-01T00:00:00+00:00",
            "test",
            ["some-prior-id-por-iq-derived"],
        )
        self.assertIn("`some-prior-id-por-iq-derived`", text)
        self.assertIn("does not chain-supersede", text)


class PorIqSpecSyncTests(unittest.TestCase):
    """DR-018 re-costed por-iq; TARGET_POR_IQ_UA must track it."""

    @classmethod
    def setUpClass(cls):
        cls.spec_text = SPEC_PATH.read_text(encoding="utf-8")

    def test_por_iq_ceiling_matches_the_ratified_spec_row(self):
        ceiling = _ceiling_ua(_target_column(self.spec_text, "por-iq"))
        self.assertEqual(
            ceiling,
            analyze_por_iq.TARGET_POR_IQ_UA,
            "analyze_por_iq.TARGET_POR_IQ_UA has drifted from "
            "spec/target-spec.md#por-iq's ratified Target column -- update "
            "the constant (citing the decision record that moved it) to "
            "match.",
        )

    def test_iq_total_ceiling_matches_the_ratified_spec_row(self):
        ceiling = _ceiling_ua(_target_column(self.spec_text, "iq-total"))
        self.assertEqual(
            ceiling,
            analyze_por_iq.TARGET_IQ_TOTAL_UA,
            "analyze_por_iq.TARGET_IQ_TOTAL_UA has drifted from "
            "spec/target-spec.md#iq-total's ratified Target column -- "
            "update the constant to match.",
        )


if __name__ == "__main__":
    unittest.main()
