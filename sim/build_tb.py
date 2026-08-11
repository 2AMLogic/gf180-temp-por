#!/usr/bin/env python3
"""Assemble testbench netlist fragments from committed sources.

    python3 sim/build_tb.py            # (re)generate every fragment
    python3 sim/build_tb.py --check    # verify each is current; write nothing

A generated fragment is ``<experiment>/testbench/stimulus.spice`` followed by a
verbatim copy of one or more ``design/netlist/<cell>.spice`` exports.

Why generate instead of ``.include``: the corner runner rejects ``.include``
inside a fragment (``sim/harness/README.md``), so the device under test has to
be *inlined*. Inlining by hand would let the evidence trail drift silently away
from the schematic -- exactly the failure the append-only convention exists to
prevent. So the fragment is generated, carries each source's sha256 in its
header, and ``--check`` fails if it is stale.

``design/netlist.py --check`` already guarantees the exported netlist matches
the schematic, so the two checks together tie a record back to its ``.sch``.
Unlike ``netlist.py``, this script needs neither xschem nor the PDK, so it is
safe to run in the headless CI job.

Some experiments also have a POSTLAYOUT_FRAGMENTS entry (#86): a second,
extracted-netlist fragment generated into ``<experiment>/testbench-postlayout/``
from ``layout/postlayout/<cell>.spice`` instead of the schematic export, for a
post-layout re-run against the same stimulus. Both kinds are (re)generated and
``--check``'d by the same invocation above; see POSTLAYOUT_FRAGMENTS' own
docstring for the manifest half of that pairing.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIM = REPO_ROOT / "sim"
NETLIST_DIR = REPO_ROOT / "design" / "netlist"
POSTLAYOUT_DIR = REPO_ROOT / "layout" / "postlayout"

#: experiment slug -> (generated fragment name, DUT cells inlined after the stimulus)
FRAGMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "temp-core-designer-check": ("tb_temp_core.spice", ("temp_core",)),
    "temp-core-startup": ("tb_temp_core_startup.spice", ("temp_core",)),
    "por-comparator-designer-check": ("tb_por_comparator.spice", ("por_comparator",)),
    "por-output-chain-pulse": ("tb_por_pulse.spice", ("por_output_chain",)),
    "por-output-chain-deglitch": ("tb_por_deglitch.spice", ("por_output_chain",)),
    "por-output-chain-floor": ("tb_por_floor.spice", ("por_output_chain",)),
    "bias-core-designer-check": ("tb_bias_core.spice", ("bias_core",)),
    "bias-core-startup": ("tb_bias_core_startup.spice", ("bias_core",)),
    "bias-core-ibias-sharing": (
        "tb_ibias_sharing.spice",
        ("bias_core", "temp_core", "por_comparator"),
    ),
    # temp_por_top.spice already carries every sub-circuit definition the top
    # level instantiates, so one cell here is the whole four-cell assembly.
    "temp-por-top-release": ("tb_temp_por_top.spice", ("temp_por_top",)),
    "temp-accuracy-vt": ("tb_temp_accuracy_vt.spice", ("temp_por_top",)),
    # #14's full-assembly POR testbench suite -- all against the same
    # four-cell assembly, nothing idealised.
    "por-vth": ("tb_por_vth.spice", ("temp_por_top",)),
    "por-ramp-rate": ("tb_por_ramp_rate.spice", ("temp_por_top",)),
    "por-brownout": ("tb_por_brownout.spice", ("temp_por_top",)),
    "por-brownout-spurious": ("tb_por_brownout_spurious.spice", ("temp_por_top",)),
    "por-glitch": ("tb_por_glitch.spice", ("temp_por_top",)),
    # #60's falling-slew boundary characterization: same 1.0 V / 50 us
    # qualifying dip as por-brownout, with the falling EDGE duration as the
    # one variable. testbench/stimulus.spice is regenerated per rung by
    # testbench/gen_rung.py (see sim/por-brownout-slew/testbench/README.md);
    # each rung's netlist snapshot freezes the exact fragment that ran.
    "por-brownout-slew": ("tb_por_brownout_slew.spice", ("temp_por_top",)),
    # #15's Monte Carlo local-mismatch testbenches -- cell-level idealised-bias
    # DUTs (same cells temp-core-designer-check / por-comparator-designer-check
    # use), not the full four-cell assembly: mismatch is a property of these
    # cells' own devices, not of bias_core's startup dynamics, and the
    # idealised-bias level is cheap enough to run N=500+ ngspice invocations
    # per binding point at.
    "temp-accuracy-mc": ("tb_temp_accuracy_mc.spice", ("temp_core",)),
    "por-threshold-mc": ("tb_por_threshold_mc.spice", ("por_comparator",)),
    # NOTE: sim/por-iq/ is deliberately absent here -- it has no netlist
    # fragment of its own. It PUBLISHES spec/target-spec.md#por-iq/#iq-total
    # as a derivation from sim/temp-accuracy-vt/'s already-run raw logs (see
    # sim/por-iq/analyze_por_iq.py), the same "derivation, not a fresh
    # simulation" idiom sim/temp-accuracy-vt/analyze_derived.py established.
}

#: experiment slug -> (generated fragment name, DUT cells inlined after the
#: stimulus) for the POST-LAYOUT (extracted, #86) sibling of a FRAGMENTS
#: entry. Written to a separate ``testbench-postlayout/`` subdirectory of
#: the same experiment (never ``testbench/``, which stays the schematic
#: fragment FRAGMENTS builds) so a schematic-level re-run and an
#: extracted-level re-run can both be re-generated and --check'd without
#: either overwriting the other -- see sim/README.md's "Netlist provenance"
#: field and issue #86. Each entry here also needs a hand-written
#: ``testbench-postlayout/tb.json`` (this script only assembles the netlist
#: fragment, not the manifest): set ``"netlist_provenance": "extracted"``,
#: a ``"netlist_provenance_note"`` quoting the cell's row in
#: layout/postlayout/AUDIT.md, and ``"netlist"`` naming the fragment below.
#: The stimulus is shared with the schematic sibling (same DUT ports), read
#: from FRAGMENTS' own ``testbench/stimulus.spice`` rather than duplicated.
POSTLAYOUT_FRAGMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "por-output-chain-pulse": ("tb_por_pulse_postlayout.spice", ("por_output_chain",)),
    "por-output-chain-deglitch": ("tb_por_deglitch_postlayout.spice", ("por_output_chain",)),
    "por-output-chain-floor": ("tb_por_floor_postlayout.spice", ("por_output_chain",)),
    # #84's bias_core-domain post-layout re-runs. These three fragment names
    # deliberately do NOT carry the ``_postlayout`` suffix the por-output-chain
    # rows above use: their records under sim/bias-core-*/records/ (and the
    # frozen sim/bias-core-*/netlist-snapshots/*.spice those records cite) were
    # written against these exact paths, and a record is append-only evidence
    # -- renaming the fragment would leave a committed record pointing at a
    # file that does not exist. The ``testbench-postlayout/`` directory is
    # what distinguishes the two fragments, not the file name; the suffix on
    # the #86 rows is belt-and-braces, not a load-bearing convention.
    "bias-core-designer-check": ("tb_bias_core.spice", ("bias_core",)),
    "bias-core-startup": ("tb_bias_core_startup.spice", ("bias_core",)),
    "bias-core-ibias-sharing": (
        "tb_ibias_sharing.spice",
        ("bias_core", "temp_core", "por_comparator"),
    ),
}


def build(slug: str) -> str:
    fragment_name, cells = FRAGMENTS[slug]
    stimulus = SIM / slug / "testbench" / "stimulus.spice"
    header = [
        f"* {fragment_name.removesuffix('.spice')} -- GENERATED by sim/build_tb.py",
        "* Do not edit. Sources:",
        f"*   sim/{slug}/testbench/stimulus.spice",
    ]
    bodies = []
    for cell in cells:
        text = (NETLIST_DIR / f"{cell}.spice").read_text()
        digest = hashlib.sha256(text.encode()).hexdigest()
        header.append(f"*   design/netlist/{cell}.spice  (sha256 {digest})")
        bodies.append(text)
    header += ["* Regenerate with:", "*   python3 sim/build_tb.py", "", ""]
    return "\n".join(header) + stimulus.read_text() + "\n" + "\n".join(bodies)


def build_postlayout(slug: str) -> str:
    """Like :func:`build`, but inlines ``layout/postlayout/<cell>.spice``
    (the klt-extracted netlist, #82) instead of ``design/netlist/<cell>.spice``.
    The stimulus is the schematic sibling's -- same DUT port list, so the
    same stimulus fragment drives either DUT unchanged.
    """
    fragment_name, cells = POSTLAYOUT_FRAGMENTS[slug]
    stimulus = SIM / slug / "testbench" / "stimulus.spice"
    header = [
        f"* {fragment_name.removesuffix('.spice')} -- GENERATED by sim/build_tb.py",
        "* Do not edit. Sources:",
        f"*   sim/{slug}/testbench/stimulus.spice",
    ]
    bodies = []
    for cell in cells:
        text = (POSTLAYOUT_DIR / f"{cell}.spice").read_text()
        digest = hashlib.sha256(text.encode()).hexdigest()
        header.append(f"*   layout/postlayout/{cell}.spice  (sha256 {digest})")
        bodies.append(text)
    header += ["* Regenerate with:", "*   python3 sim/build_tb.py", "", ""]
    return "\n".join(header) + stimulus.read_text() + "\n" + "\n".join(bodies)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed fragments match their sources; do not write",
    )
    parser.add_argument(
        "experiments",
        nargs="*",
        default=None,
        help="experiment slugs to build (default: all of "
        f"{', '.join(sorted(set(FRAGMENTS) | set(POSTLAYOUT_FRAGMENTS)))})",
    )
    args = parser.parse_args(argv)

    all_slugs = sorted(set(FRAGMENTS) | set(POSTLAYOUT_FRAGMENTS))
    slugs = args.experiments or all_slugs
    unknown = [s for s in slugs if s not in FRAGMENTS and s not in POSTLAYOUT_FRAGMENTS]
    if unknown:
        print(f"unknown experiment(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    jobs: list[tuple[Path, str]] = []
    for slug in slugs:
        if slug in FRAGMENTS:
            fragment_name, _ = FRAGMENTS[slug]
            jobs.append((SIM / slug / "testbench" / fragment_name, build(slug)))
        if slug in POSTLAYOUT_FRAGMENTS:
            fragment_name, _ = POSTLAYOUT_FRAGMENTS[slug]
            jobs.append(
                (SIM / slug / "testbench-postlayout" / fragment_name, build_postlayout(slug))
            )

    failures = 0
    for path, text in jobs:
        rel = path.relative_to(REPO_ROOT)
        if args.check:
            if not path.is_file():
                print(f"FAIL {rel}: missing", file=sys.stderr)
                failures += 1
            elif path.read_text() != text:
                print(
                    f"FAIL {rel}: stale -- re-run 'python3 sim/build_tb.py' "
                    "(the stimulus or the exported DUT netlist changed)",
                    file=sys.stderr,
                )
                failures += 1
            else:
                print(f"OK   {rel}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {rel}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
