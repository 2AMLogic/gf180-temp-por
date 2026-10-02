#!/usr/bin/env python3
"""Unit tests for run_net_attribution.py's net-shorting manipulation (#316).

No PDK, no ngspice: these exercise the text transform only.

The property under test is the one a wrong answer would hide. This control
reports "making net N's interconnect ideal moved the boundary by X"; that
sentence is only true if the generated variant differs from its source in
exactly one way -- N carries no interconnect load -- and in no other way. Under
`layout/postlayout.py`'s star model a net's series resistance sits on the arms
joining its hub to each device terminal, so the obvious manipulation
(commenting the arms out) would also DISCONNECT every device terminal on N from
the rest of the net. That variant still parses, still simulates, and still
produces a plausible-looking row; it just answers a different question. So the
tests below assert both halves: the load is gone, AND no device terminal was
opened.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

CONTROL = SIM_DIR / "por-brownout-slew" / "control" / "run_net_attribution.py"
EXTRACTED = REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice"


def _load_control():
    """Import the control by path -- it is a script, not an importable module.

    Registered in ``sys.modules`` before execution because its ``@dataclass``
    decorator resolves the defining module out of there.
    """
    spec = importlib.util.spec_from_file_location("run_net_attribution", CONTROL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_net_attribution"] = module
    spec.loader.exec_module(module)
    return module


rna = _load_control()


# --------------------------------------------------------------------------
# helpers: read a netlist's connectivity back out of its text
# --------------------------------------------------------------------------

def active_cards(text: str) -> list[list[str]]:
    """Every uncommented element card of ``text``, tokenised."""
    cards = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("*", ".")):
            continue
        cards.append(line.split())
    return cards


def card_nodes(tokens: list[str]) -> list[str]:
    """The node tokens of one element card.

    Two shapes only, which is all these netlists contain: an ``X`` card is
    ``X<n> <nodes…> <model> [param=value…]``, and an ``R``/``C`` card is
    ``<name> <node> <node> <value>``.
    """
    if tokens[0].upper().startswith("X"):
        fields = [t for t in tokens[1:] if "=" not in t]
        return fields[:-1]          # drop the model name
    return tokens[1:3]


def node_degree(text: str) -> Counter:
    """How many element cards each node appears on.

    Its job is to catch a node that LOST connections -- an opened device
    terminal is a node left on exactly one card -- so what matters is the
    before/after comparison, not the absolute count.
    """
    degree: Counter = Counter()
    for tokens in active_cards(text):
        for node in card_nodes(tokens):
            degree[node] += 1
    return degree


STAR_NETLIST = """\
* a post-layout netlist in layout/postlayout.py's star model
.subckt cell VDD VSS OUT
X1 OUT__t0 NG__t0 VSS VSS nfet_03v3 L=1u W=1u
X2 OUT__t1 NG__t1 VSS VSS nfet_03v3 L=1u W=1u
X3 OUT__t2 NG__t2 VDD VDD pfet_03v3 L=1u W=1u
ROUT_t0 OUT__t0 OUT 120.5
ROUT_t1 OUT__t1 OUT 79.5
ROUT_t2 OUT__t2 OUT 60.0
COUT OUT VSS 10e-15
RNG_t0 NG__t0 NG 10
RNG_t1 NG__t1 NG 20
RNG_t2 NG__t2 NG 30
CNG NG VSS 1e-15
Ccc__OUT__NG OUT NG 2e-16
Rvsubs_dctie VSS 0 1e+12
.ends
"""


class ShortNetsStarModelTests(unittest.TestCase):
    """`short_nets` on a star-model netlist: load gone, no terminal opened."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "cell.spice"
        self.path.write_text(STAR_NETLIST)

    def test_terminal_nodes_collapse_onto_the_hub_on_the_device_cards(self):
        text, _ = rna.short_nets(self.path, ("OUT",))
        cards = {tokens[0]: tokens for tokens in active_cards(text)}
        # Each device that had a terminal on OUT now sits on OUT itself.
        self.assertEqual(cards["X1"][1], "OUT")
        self.assertEqual(cards["X2"][1], "OUT")
        self.assertEqual(cards["X3"][1], "OUT")
        # ... and nothing else on those cards moved.
        self.assertEqual(cards["X1"][2], "NG__t0")
        self.assertEqual(cards["X3"][3:5], ["VDD", "VDD"])

    def test_the_whole_interconnect_load_of_the_named_net_is_gone(self):
        text, _ = rna.short_nets(self.path, ("OUT",))
        names = {tokens[0] for tokens in active_cards(text)}
        # its arms (series R), its lumped C and its coupling to NG
        self.assertNotIn("ROUT_t0", names)
        self.assertNotIn("ROUT_t1", names)
        self.assertNotIn("ROUT_t2", names)
        self.assertNotIn("COUT", names)
        self.assertNotIn("Ccc__OUT__NG", names)

    def test_no_device_terminal_is_left_floating(self):
        """The failure mode the #314 refusal existed to prevent.

        Commenting an arm out would leave its `OUT__t<k>` node on one card --
        the device's -- and nothing else: an open terminal, not an ideal net.
        """
        text, _ = rna.short_nets(self.path, ("OUT",))
        self.assertNotIn("OUT__t", "\n".join(" ".join(c) for c in active_cards(text)))
        before = node_degree(STAR_NETLIST)
        after = node_degree(text)
        # No node that had company before is left alone on one card now.
        # (`0`, the SPICE ground the substrate tie leaks to, is on one card
        # before and after -- it is not a node anything can open.)
        for node, count in after.items():
            if before.get(node, 0) < 2:
                continue
            self.assertGreaterEqual(
                count, 2, f"{node} is left on a single card -- an open terminal"
            )
        # No node gained connections either, and no node was invented: the
        # transform only ever merges a terminal into its own hub.
        self.assertTrue(set(after) <= set(before) | {"OUT"})
        self.assertEqual(after["OUT"], before["OUT__t0"] + before["OUT__t1"]
                         + before["OUT__t2"] - 3)

    def test_nets_that_were_not_named_keep_their_parasitics_byte_for_byte(self):
        text, _ = rna.short_nets(self.path, ("OUT",))
        for card in ("RNG_t0 NG__t0 NG 10", "RNG_t1 NG__t1 NG 20",
                     "CNG NG VSS 1e-15", "Rvsubs_dctie VSS 0 1e+12"):
            self.assertIn("\n" + card + "\n", text)

    def test_only_the_named_nets_cards_and_terminals_differ_from_the_source(self):
        """A one-variable manipulation: every other line is passed through."""
        text, _ = rna.short_nets(self.path, ("OUT",))
        source = STAR_NETLIST.splitlines()
        got = text.splitlines()
        self.assertEqual(len(source), len(got), "line count must not change")
        changed = [(a, b) for a, b in zip(source, got) if a != b]
        # 3 arms + 1 lumped C + 1 coupling commented, 3 device cards renamed
        self.assertEqual(len(changed), 8)
        for before, after in changed:
            self.assertTrue(
                after.startswith(rna.SHORT_PREFIX) or "OUT__t" in before,
                f"unexpected edit: {before!r} -> {after!r}",
            )

    def test_the_counts_are_per_net_and_name_what_was_removed(self):
        _, shorted = rna.short_nets(self.path, ("OUT",))
        self.assertEqual(set(shorted), {"OUT"})
        self.assertEqual(shorted["OUT"].arms, 3)
        self.assertEqual(shorted["OUT"].terminals, 3)
        self.assertEqual(shorted["OUT"].capacitors, 1)
        self.assertEqual(shorted["OUT"].couplings, 1)
        self.assertEqual(shorted["OUT"].cards, 5)

    def test_shorting_two_nets_at_once_counts_the_shared_coupling_on_both(self):
        text, shorted = rna.short_nets(self.path, ("OUT", "NG"))
        self.assertEqual(shorted["OUT"].couplings, 1)
        self.assertEqual(shorted["NG"].couplings, 1)
        names = {tokens[0] for tokens in active_cards(text)}
        self.assertEqual(names, {"X1", "X2", "X3", "Rvsubs_dctie"})

    def test_a_terminal_node_with_no_arm_to_its_hub_is_refused(self):
        """The model's shape is asserted, not assumed.

        A `<net>__t<k>` node with no `R<net>_t<k>` arm card is a model this
        manipulation has not been derived against; collapsing it would silently
        delete a series element that is there for some other reason.
        """
        broken = STAR_NETLIST.replace("ROUT_t2 OUT__t2 OUT 60.0\n", "")
        self.path.write_text(broken)
        with self.assertRaises(SystemExit) as caught:
            rna.short_nets(self.path, ("OUT",))
        self.assertIn("OUT__t2", str(caught.exception))

    def test_a_net_with_no_parasitics_at_all_reports_zero_rather_than_guessing(self):
        _, shorted = rna.short_nets(self.path, ("VDD",))
        self.assertEqual(shorted["VDD"].cards, 0)
        self.assertEqual(shorted["VDD"].terminals, 0)


@unittest.skipUnless(EXTRACTED.exists(), "no committed extraction to read")
class ShortNetsAgainstTheCommittedExtractionTests(unittest.TestCase):
    """The same properties against the netlist the control actually runs on.

    Expected counts are re-derived from the netlist's own text on every run
    rather than pinned, so a re-extraction that renumbers or re-partitions the
    cards changes the expectation with it -- what is pinned is the *agreement*
    between the two readings, which is the thing a model change would break.
    """

    NET = "IBIAS"

    def test_counts_agree_with_a_plain_text_reading_of_the_same_netlist(self):
        _, shorted = rna.short_nets(EXTRACTED, (self.NET,))
        text = EXTRACTED.read_text()
        arms = re.findall(rf"(?m)^R{self.NET}_t\d+\s+{self.NET}__t\d+\s+{self.NET}\s",
                          text)
        caps = re.findall(rf"(?m)^C{self.NET}\s+{self.NET}\s", text)
        couplings = re.findall(rf"(?m)^Ccc_\S*\s+(?:{self.NET}\s+\S+|\S+\s+{self.NET})\s",
                               text)
        self.assertTrue(arms, "fixture assumption: IBIAS carries a star")
        self.assertEqual(shorted[self.NET].arms, len(arms))
        self.assertEqual(shorted[self.NET].terminals, len(arms))
        self.assertEqual(shorted[self.NET].capacitors, len(caps))
        self.assertEqual(shorted[self.NET].couplings, len(couplings))

    def test_no_terminal_of_the_shorted_net_survives_and_none_is_opened(self):
        text, shorted = rna.short_nets(EXTRACTED, (self.NET,))
        flat = "\n".join(" ".join(c) for c in active_cards(text))
        self.assertNotIn(f"{self.NET}__t", flat)
        before = node_degree(EXTRACTED.read_text())
        after = node_degree(text)
        singletons = sorted(n for n, c in after.items()
                            if c < 2 and before.get(n, 0) >= 2)
        self.assertEqual(singletons, [], "these nodes lost their other connection")
        self.assertEqual(len(text.splitlines()),
                         len(EXTRACTED.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
