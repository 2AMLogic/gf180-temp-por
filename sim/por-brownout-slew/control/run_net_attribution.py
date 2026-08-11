#!/usr/bin/env python3
"""Which extracted nets carry the post-layout falling-slew shift? (#214)

    python3 sim/por-brownout-slew/control/run_net_attribution.py
    python3 sim/por-brownout-slew/control/run_net_attribution.py --report-only

WHAT THIS ADDS

[DR-019](../../../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md)
re-cost `spec/target-spec.md#por-brownout` clause (c)'s `dVDD/dt|fall,max`
from 3.40 mV/us to 2.30 mV/us because the extracted netlist's own transition
edge sits between 2.45 and 2.50 mV/us where the schematic export's sits
between 3.44 and 3.46 -- a 28 % shift. `run_postlayout_margin.py`'s
`postlayout_margin_results.md` establishes the MECHANISM (DR-011's starved
loop: at 3.40 mV/us the extraction takes min `V_sg` on `bias_core`'s PMOS
mirror bank from -116.1 mV to -297.5 mV at 3.63 V, and `por_output_chain`'s
deglitch ramp never starts at all, peak `NDG`/VDD 0.706 -> 0.000).

What neither record says is WHICH NETS' parasitics carry it. DR-019's own
Consequences section says so explicitly: `PG`'s extracted 68.1 fF is ~5 % of
`design/bias_core.md`'s ~1.25 pF estimate for that node and cannot explain a
28 % shift alone, and the extraction loads 136 of 159 nets (SigmaC 5880.2 fF).

That distinction decides whether the lost envelope is ADDRESSABLE IN LAYOUT
(a few dominant nets that could be re-routed, widened or shielded) or
INTRINSIC to the starved loop at this bias level (in which case DR-019's
number is the number, and the only remaining lever is `bias_core`'s
architecture).

METHOD -- one variable: which nets' interconnect parasitics exist

`layout/postlayout.py` models each net's drawn interconnect as ONE lumped
series R from the net to a `<net>__par` stub node plus ONE lumped C from that
stub to `VSS`, and the stub node appears on those two cards and nowhere else
(checked against the netlist, not assumed). So a net's whole parasitic
contribution is exactly two cards, and "this net were ideal" is: comment both
out. Nothing else in the netlist moves -- same devices, same dimensions, same
topology, same card ordering, same line count -- so a variant's difference
from the `ext` arm is attributable to the named nets and to nothing else.
`diff` between a generated netlist under `netlists/` and its source shows
precisely the 2 x N commented cards.

#214's suggested spelling of "shorted out" was to keep both cards and set
R -> a negligible non-zero value with C -> 0 F, non-zero to avoid a singular
matrix. That was tried first, at 1 uOhm, and rejected on measured evidence:
it makes things WORSE, not better, because the stub node then hangs off a
1e6 S conductance with no capacitance to ground at all. ngspice reports
`Warning: singular matrix: check node xdut.xbias__nbg` six times per deck,
dynamic-gmin / true-gmin / source stepping all fail, and the `loop` deck at
3.63 V / 3.40 mV/us had not finished after 20 minutes where the untouched
`ext` deck takes 8 s. Removing the branch is both better conditioned and a
truer statement of the manipulation: the net carries no interconnect load,
and there is no stub node left to be ill-conditioned.

The R/C pair for a named net is located with `sim/postlayout_delta.py`'s own
`parasitics_by_net()` parser and its `_R_CARD` / `_C_CARD` / `PAR_SUFFIX`
constants, NOT with a second regex written here: the extraction renumbers its
`R_n` / `C_n` cards whenever the layout is regenerated, so a net has to be
found by name, and there must be exactly one parser in the repo that knows
how to do it.

Variants (see VARIANTS below for the exact net lists):

  * `sch`   the schematic export -- the upper anchor. Re-run here rather than
            quoted, so both anchors come from this host, ngspice build and
            PDK install.
  * `ext`   the extracted netlist, untouched -- the lower anchor.
  * `pg` / `nbg` / `nz` / `ibias`
            one `bias_core` loop net each, the four the issue names.
  * `loop`  all four of those together.
  * `bias`  every net `bias_core` owns, plus the two top-level nets it drives
            (`IBIAS`, `VREF`).
  * `por`   every net `por_output_chain` owns -- the deglitch ramp that
            `postlayout_margin_results.md` shows never starting.
  * `all`   every parasitic-carrying net in the extraction. This is the
            METHOD CONTROL: if shorting all 136 of them does not restore the
            schematic arm's behaviour, then the shift is not carried by
            interconnect parasitics at all and no per-net row below means
            what it appears to mean.

Each variant runs the binding family (`ss` / -40 C, all three supplies -- the
supply axis is kept for the reason #74 keeps it: the three points do not
agree with each other) at two rungs:

  * 2.50 mV/us -- the extracted netlist's own transition edge, the lowest
    rung #188 recorded a failure at (80/81), just above DR-019's ratified
    2.30 mV/us, and
  * 3.40 mV/us -- the pre-DR-019 bound, where the extracted arm fails all
    three supplies and the schematic arm passes all three.

Every deck is built by `run_band_mechanism.deck()` with the netlist as its
one parameter, exactly as `run_postlayout_margin.py` (#188) does, so no
variant can drift away from the measurement list the other two controls
share.

WHAT IT CANNOT DECIDE

DR-019's bound is ratified on the corner-grid records under `../records/` and
is not touched by this control either way: a one-corner-family sweep is not
evidence about the grid, so -- exactly as its two sibling controls do -- this
script does NOT go through sim/run_corners.py and does NOT mint a record
under `../records/`. What it decides is only whether a BETTER bound is
reachable by re-routing, which is a layout question, not a spec question.

Nor does it locate a boundary. Two rungs BRACKET one; locating where the
extracted transition edge would sit after a re-route needs a corner-grid
ladder, which is filed as #232 rather than done here.

Outputs, all regenerated on every run (a control is not a record):

    netlists/na-<variant>.spice          the exact DUT netlist as run
    decks/na-<variant>-<slew>mvus-<vdd>v.spice   the exact deck as run
    logs/na-<variant>-<slew>mvus-<vdd>v.log      raw ngspice output, verbatim
    net_attribution_results.md           the attribution tables

The `na-` prefix keeps these variants out of `run_band_mechanism.py`'s
`a-`/`b-` and `run_postlayout_margin.py`'s `pl-` namespaces, so none of the
three scripts can overwrite another's decks or logs.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, cliutil, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

# The extracted-netlist parser, imported rather than re-derived: `_R_CARD`,
# `_C_CARD` and `PAR_SUFFIX` are the private spelling of `layout/postlayout.py`'s
# own emission format, and a second copy of them here is exactly the drift
# this control cannot afford (the cards are renumbered on every layout
# regeneration, so the net name is the only stable handle).
from postlayout_delta import (  # noqa: E402
    _C_CARD,
    _R_CARD,
    PAR_SUFFIX,
    parasitics_by_net,
)

# run_band_mechanism.py lives beside this file rather than on sys.path as a
# package, so it is loaded by path -- the same way run_postlayout_margin.py
# loads it. Reuse rather than copy is the whole point: its deck() carries the
# measurement list every arm must share, and its internal() resolves the
# sub-cell node paths for the flat extraction.
_spec = importlib.util.spec_from_file_location(
    "run_band_mechanism", CONTROL_DIR / "run_band_mechanism.py"
)
band = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(band)

SCHEMATIC = REPO_ROOT / "design" / "netlist" / "temp_por_top.spice"
EXTRACTED = REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice"
NETLIST_DIR = CONTROL_DIR / "netlists"

#: How a shorted card is spelled in the generated netlist. Commented out
#: rather than deleted, so the generated netlist stays line-for-line
#: comparable with its source and a reader can see the value that was
#: removed. See the module docstring for why the branch is removed outright
#: instead of being given a negligible R and a zero C.
SHORT_PREFIX = "* SHORTED OUT by run_net_attribution.py: "

#: The two rungs. 3.40 is the pre-DR-019 bound the extracted arm fails at all
#: three supplies (`postlayout_margin_results.md`); 2.50 is the extracted
#: netlist's own transition edge, the lowest rung #188 recorded a failure at
#: (80/81 on the grid; 2.97 V only at this family).
SLEWS_MVUS = [2.50, 3.40]
BOUNDARY_SLEW_MVUS = 3.40

#: DR-019's ratified bound, quoted for orientation only -- nothing here
#: re-derives or changes it.
DR019_BOUND_MVUS = 2.30

#: `../testbench/tb.json`'s `resetn_ratio_min_in_dip` bound, the grid's own
#: checked discriminator. Read from the manifest at run time, not restated.
RESETN_RATIO_KEY = "resetn_ratio_min_in_dip"

#: Classification thresholds for the per-variant reading in section 5, in
#: fractions of the sch-vs-ext gap in min `V_sg` at BOUNDARY_SLEW_MVUS (the
#: one state variable that is defined for every run, including the ones where
#: `RESETn` never reaches valid-low and the margin is therefore undefined).
DOMINANT_FRACTION = 0.50
PARTIAL_FRACTION = 0.10


@dataclass(frozen=True)
class Variant:
    """One arm: a DUT netlist, optionally with named nets' parasitics shorted."""

    key: str
    base: Path
    #: Schematic net names whose R/C pair is shorted. Empty => the netlist is
    #: used exactly as it sits on disk (the two anchors).
    nets: tuple[str, ...] = ()
    #: How the net list was chosen, for the generated inventory table.
    note: str = ""

    @property
    def netlist(self) -> Path:
        if not self.nets:
            return self.base
        return NETLIST_DIR / f"na-{self.key}.spice"


def cell_nets(parasitics: dict[str, dict[str, float]], prefix: str) -> tuple[str, ...]:
    """Every parasitic-carrying net the flat extraction names for one cell.

    `layout/postlayout.py` renames a sub-cell's internal nets `<inst>__<NET>`
    when it flattens the assembly, so a cell's own nets are exactly the ones
    carrying its instance prefix. The top-level nets a cell DRIVES do not
    carry the prefix and are named explicitly by the caller.
    """
    return tuple(sorted(n for n in parasitics if n.startswith(prefix)))


def build_variants(parasitics: dict[str, dict[str, float]]) -> list[Variant]:
    """The arm list, with the group memberships resolved against the netlist
    actually on disk rather than hard-coded -- so a re-extraction that adds or
    drops a net changes the groups instead of silently mis-labelling them."""
    present = [n for n in ("IBIAS", "VREF") if n in parasitics]
    bias = cell_nets(parasitics, "xbias__") + tuple(present)
    por = cell_nets(parasitics, "xpor__")
    everything = tuple(sorted(parasitics))
    return [
        Variant("sch", SCHEMATIC, (), "the schematic export — upper anchor"),
        Variant("ext", EXTRACTED, (), "the extraction, untouched — lower anchor"),
        Variant("pg", EXTRACTED, ("xbias__PG",),
                "`bias_core`'s PMOS mirror gate — the node DR-011 measures "
                "the starved-loop collapse on"),
        Variant("nbg", EXTRACTED, ("xbias__NBG",),
                "`bias_core`'s NMOS mirror gate"),
        Variant("nz", EXTRACTED, ("xbias__NZ",),
                "`bias_core`'s compensation node (`XCC`/`XRZ`)"),
        Variant("ibias", EXTRACTED, ("IBIAS",),
                "the top-level bias current the other three cells run on"),
        Variant("loop", EXTRACTED,
                ("xbias__PG", "xbias__NBG", "xbias__NZ", "IBIAS"),
                "all four of the above together"),
        Variant("bias", EXTRACTED, bias,
                "every net `bias_core` owns (`xbias__*`), plus the top-level "
                "nets it drives"),
        Variant("por", EXTRACTED, por,
                "every net `por_output_chain` owns (`xpor__*`) — the deglitch "
                "ramp that never starts"),
        Variant("all", EXTRACTED, everything,
                "every parasitic-carrying net — the method control"),
    ]


def short_nets(netlist: Path, nets: tuple[str, ...]) -> tuple[str, dict[str, int]]:
    """``netlist``'s text with each named net's parasitic R/C pair shorted.

    Returns the text and a per-net count of cards shorted. Every other line
    -- devices, subcircuit header, comments, and the R/C cards of every net
    NOT named -- is passed through byte-for-byte, which is what makes a
    variant a one-variable manipulation rather than a re-extraction.

    Card identification is `sim/postlayout_delta.py`'s, not a second regex:
    the same `_R_CARD` / `_C_CARD` patterns and the same `PAR_SUFFIX`
    stub-node convention `parasitics_by_net()` buckets on, so a card this
    counts as net N's is exactly a card that function attributes to net N.
    """
    wanted = set(nets)
    shorted: dict[str, int] = {net: 0 for net in nets}
    out: list[str] = []
    for raw in netlist.read_text().splitlines():
        line = raw.strip()
        replacement = None
        if line and not line.startswith(("*", ".")):
            for pattern in (_R_CARD, _C_CARD):
                match = pattern.match(line)
                if not match:
                    continue
                a, b, _ = match.groups()
                stub = a if a.endswith(PAR_SUFFIX) else b
                net = stub[: -len(PAR_SUFFIX)] if stub.endswith(PAR_SUFFIX) else stub
                if net in wanted:
                    replacement = SHORT_PREFIX + raw
                    shorted[net] += 1
                break
        out.append(raw if replacement is None else replacement)
    return "\n".join(out) + "\n", shorted


def write_variant_netlist(variant: Variant) -> dict[str, int]:
    """Generate ``variant``'s DUT netlist on disk. Raises if a named net has
    no cards to short -- a silently-missed net would show up in the results
    as "shorting it changed nothing", which is the opposite conclusion."""
    text, shorted = short_nets(variant.base, variant.nets)
    empty = sorted(net for net, count in shorted.items() if count == 0)
    if empty:
        raise SystemExit(
            f"{variant.key}: no parasitic cards found for "
            f"{', '.join(empty)} in {variant.base.relative_to(REPO_ROOT)} -- "
            "the net names are stale (a re-extraction renames or drops nets); "
            "re-derive them from parasitics_by_net() before trusting any row "
            "of this control."
        )
    header = [
        f"* {variant.base.name} -- {len(variant.nets)} net(s) shorted out:",
        "*   " + ", ".join(variant.nets[:12])
        + (f", ... ({len(variant.nets)} total)" if len(variant.nets) > 12 else ""),
        f"* Their {sum(shorted.values())} interconnect R/C card(s) are commented "
        "out below, so those nets carry no interconnect load at all; every "
        "other line is byte-for-byte the source netlist's.",
        "* GENERATED by sim/por-brownout-slew/control/run_net_attribution.py "
        "-- do not edit.",
        f"* source sha256 {runner.sha256_file(variant.base)[:16]}...",
        "*",
    ]
    NETLIST_DIR.mkdir(exist_ok=True)
    variant.netlist.write_text("\n".join(header) + "\n" + text)
    return shorted


def variant_name(key: str, vdd: float, slew_mvus: float) -> str:
    return f"na-{key}-{slew_mvus:g}mvus-{vdd:.2f}v"


def read_logs() -> dict[str, dict[str, float]]:
    """Re-derive this control's variants from the logs already on disk.

    Scoped to the ``na-`` prefix so ``--report-only`` reads only this script's
    own runs and never its two siblings'.
    """
    log_dir = CONTROL_DIR / "logs"
    return {
        path.stem: runner.parse_bare_measurements(path.read_text())
        for path in sorted(log_dir.glob("na-*.log"))
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report_only = "--report-only" in argv

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    manifest = cliutil.load_manifest(band.MANIFEST)
    options = manifest["options"]
    parasitics = parasitics_by_net(EXTRACTED)
    variants = build_variants(parasitics)

    if report_only:
        results = read_logs()
        if not results:
            print("no na-* logs to report from -- run without --report-only first",
                  file=sys.stderr)
            return 1
    else:
        for variant in variants:
            if variant.nets:
                write_variant_netlist(variant)
        print(f"generated {sum(1 for v in variants if v.nets)} variant "
              f"netlist(s) in {NETLIST_DIR.relative_to(REPO_ROOT)}")

        jobs: list[tuple[str, str]] = []
        for variant in variants:
            for slew in SLEWS_MVUS:
                for vdd in band.SUPPLIES_V:
                    jobs.append(
                        (
                            variant_name(variant.key, vdd, slew),
                            band.deck(pdk, options, vdd, slew, None,
                                      variant.netlist),
                        )
                    )
        print(
            f"running {len(jobs)} decks ({len(variants)} arms x "
            f"{len(SLEWS_MVUS)} rungs x {len(band.SUPPLIES_V)} supplies) at "
            f"{band.CORNER} / {band.TEMP_C:g} C ..."
        )
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            results = dict(
                zip(
                    [name for name, _ in jobs],
                    pool.map(lambda job: runner.run_deck(*job, CONTROL_DIR), jobs),
                )
            )

    missing = probe_gaps(variants, results)
    if missing:
        print(f"  WARNING: {len(missing)} deck(s) lost an internal probe: "
              f"{', '.join(missing[:5])}")

    write_results(pdk, manifest, variants, parasitics, results)
    print(f"wrote {CONTROL_DIR / 'net_attribution_results.md'}")
    return 0


#: The measurements that come from a probe BELOW the cell boundary, which is
#: where `internal()`'s node-path resolution can silently fail: ngspice reports
#: "vector ... is not available", the derived `let` fails, and the row reads as
#: "the deglitch never started" rather than as "this arm never looked".
INTERNAL_PROBE_KEYS = ("vsg_pre", "vsg_min", "pgdg_r_min", "ndg_r_max")


def probe_gaps(variants: list[Variant], res: dict[str, dict[str, float]]) -> list[str]:
    """Deck names that ran but came back short an internal-probe measurement."""
    gaps: list[str] = []
    for variant in variants:
        for slew in SLEWS_MVUS:
            for vdd in band.SUPPLIES_V:
                name = variant_name(variant.key, vdd, slew)
                got = res.get(name)
                if got is None:
                    continue
                if any(key not in got for key in INTERNAL_PROBE_KEYS):
                    gaps.append(name)
    return gaps


def write_results(
    pdk,
    manifest,
    variants: list[Variant],
    parasitics: dict[str, dict[str, float]],
    res: dict[str, dict[str, float]],
) -> None:
    rst_bound = float(manifest["checks"][RESETN_RATIO_KEY]["max"])
    total_c = sum(v["c_f"] for v in parasitics.values()) or 1.0

    def g(name, key):
        return res.get(name, {}).get(key)

    def close_us(vdd: float, slew: float) -> float:
        return (band.edge_s(vdd, slew) + band.T_DWELL_S) * 1e6

    def margin_us(key: str, vdd: float, slew: float) -> float | None:
        t = g(variant_name(key, vdd, slew), "t_rst")
        if t is None:
            return None
        return close_us(vdd, slew) - (t - band.T_DIP_S) * 1e6

    def passes(key: str, slew: float) -> int:
        return sum(
            1
            for vdd in band.SUPPLIES_V
            if (lambda v: v is not None and v <= rst_bound)(
                g(variant_name(key, vdd, slew), "rst_r_min")
            )
        )

    def verdict(key: str, vdd: float, slew: float) -> str:
        v = g(variant_name(key, vdd, slew), "rst_r_min")
        if v is None:
            return "—"
        return "PASS" if v <= rst_bound else "**FAIL**"

    def recovered(key: str, vdd: float) -> float | None:
        """Fraction of the sch-vs-ext gap in min `V_sg` this arm gives back.

        `V_sg` rather than the margin because it is defined for every run:
        where `RESETn` never reaches valid-low the margin has no value at all,
        which is precisely the rows an attribution most needs to grade.
        """
        slew = BOUNDARY_SLEW_MVUS
        here = g(variant_name(key, vdd, slew), "vsg_min")
        lo = g(variant_name("ext", vdd, slew), "vsg_min")
        hi = g(variant_name("sch", vdd, slew), "vsg_min")
        if here is None or lo is None or hi is None or hi == lo:
            return None
        return (here - lo) / (hi - lo)

    def classify(key: str) -> tuple[str, float | None]:
        fractions = [f for f in (recovered(key, v) for v in band.SUPPLIES_V)
                     if f is not None]
        worst = min(fractions) if fractions else None
        if passes(key, BOUNDARY_SLEW_MVUS) == len(band.SUPPLIES_V):
            return "**restores the bound**", worst
        if worst is None:
            return "—", None
        if worst >= DOMINANT_FRACTION:
            return "dominant, not sufficient alone", worst
        if worst >= PARTIAL_FRACTION:
            return "contributes", worst
        return "not the carrier", worst

    lines: list[str] = []
    lines.append(
        "# Which extracted nets carry the post-layout falling-slew shift — results"
    )
    lines.append("")
    lines.append(
        "**Generated by `run_net_attribution.py`. Do not edit — re-run it.** "
        "Every number below is read out of `logs/na-*.log` by that script; "
        "nothing here is transcribed by hand."
    )
    lines.append("")
    lines.append(
        "[DR-019](../../../spec/decision-records/"
        "DR-019-brownout-falling-slew-postlayout-recost.md) re-cost "
        "`spec/target-spec.md#por-brownout` clause (c)'s `dVDD/dt|fall,max` "
        f"from {BOUNDARY_SLEW_MVUS:g} mV/µs to {DR019_BOUND_MVUS:g} mV/µs on "
        "the extracted netlist's measured transition edge, and left open "
        "which nets' parasitics carry the shift. This control answers that "
        "one question by making named nets' interconnect ideal, one group at "
        "a time, and re-running the binding family at the two rungs that "
        "bracket the disagreement. **It does not, and cannot, change DR-019's "
        "ratified bound** — that is settled on the corner-grid records under "
        "`../records/`; what is decided here is only whether a *better* bound "
        "is reachable by re-routing."
    )
    lines.append("")
    lines.append(
        f"- PVT points: `{band.CORNER}` / {band.TEMP_C:g} °C / "
        + ", ".join(f"{v:g} V" for v in band.SUPPLIES_V)
        + " (one corner family — a control is not corner evidence, see "
        "`sim/README.md`; the corner-grid evidence for the post-layout "
        "transition edge is the rung records under `../records/`)"
    )
    lines.append(f"- Rungs: " + ", ".join(f"{s:g} mV/µs" for s in SLEWS_MVUS))
    lines.append(f"- PDK: `{pdk.variant}` @ `{pdk.version}`")
    lines.append(f"- Harness version: `{HARNESS_VERSION}`")
    lines.append(
        "- Solver options (from `../testbench/tb.json`): "
        f"`{'`, `'.join(manifest['options'])}`"
    )
    lines.append(
        "- Anchor netlists: `sch` = `design/netlist/temp_por_top.spice` "
        f"(sha256 `{runner.sha256_file(SCHEMATIC)[:12]}…`); `ext` = "
        "`layout/postlayout/temp_por_top.spice` "
        f"(sha256 `{runner.sha256_file(EXTRACTED)[:12]}…`), which carries "
        "`layout/postlayout/AUDIT.md`'s `temp_por_top` caveats — 238 drawn "
        "devices, 1 ideal (`temp_core`'s undrawn `XCC`, #177, not on any node "
        "in this path), 136/159 nets carrying parasitics."
    )
    lines.append(
        f"- `PASS`/`FAIL` is `{RESETN_RATIO_KEY} ≤ {rst_bound:g}`, the grid's "
        "own checked discriminator, recomputed from this control's own trace "
        "over the same window `../testbench/tb.json` uses."
    )
    lines.append("")

    # ---- 1. what was shorted -------------------------------------------
    lines.append("## 1 — what each arm made ideal")
    lines.append("")
    lines.append(
        "`layout/postlayout.py` models a net's whole drawn interconnect as one "
        "lumped series R to a `<net>__par` stub plus one lumped C from that "
        "stub to `VSS`, and nothing else in the netlist references the stub. "
        "Each arm below comments out that pair for the named nets and changes "
        "nothing else — the generated netlists under `netlists/` diff against "
        "the source in exactly 2 × *nets* lines, so those nets carry no "
        "interconnect load and every other net keeps the extraction's."
    )
    lines.append("")
    lines.append(
        "| arm | nets made ideal | ΣC removed (fF) | ΣR removed (Ω) | "
        "share of cell ΣC | what it is |"
    )
    lines.append("|---|---:|---:|---:|---:|---|")
    for variant in variants:
        if not variant.nets:
            lines.append(
                f"| `{variant.key}` | — | — | — | — | {variant.note} |"
            )
            continue
        c = sum(parasitics[n]["c_f"] for n in variant.nets)
        r = sum(parasitics[n]["r_ohm"] for n in variant.nets)
        shown = (
            ", ".join(f"`{n}`" for n in variant.nets)
            if len(variant.nets) <= 4
            else f"{len(variant.nets)} nets"
        )
        lines.append(
            f"| `{variant.key}` | {shown} | {c * 1e15:.1f} | {r:.0f} | "
            f"{c / total_c * 100:.1f} % | {variant.note} |"
        )
    lines.append("")
    lines.append(
        f"Cell total for reference: {total_c * 1e15:.1f} fF of interconnect "
        f"capacitance over {len(parasitics)} nets."
    )
    lines.append("")

    # ---- 2. the verdict ------------------------------------------------
    lines.append("## 2 — does the boundary come back?")
    lines.append("")
    lines.append(
        "Supply points passing out of "
        f"{len(band.SUPPLIES_V)}, per arm per rung. The question the whole "
        f"control exists to answer is the {BOUNDARY_SLEW_MVUS:g} mV/µs column: "
        "`sch` passes all three there and `ext` fails all three, so an arm "
        "that passes all three has given the pre-DR-019 bound back, and an arm "
        "that still fails all three has not."
    )
    lines.append("")
    lines.append(
        "| arm | "
        + " | ".join(f"{s:g} mV/µs" for s in SLEWS_MVUS)
        + " | worst min `V_sg` at "
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs (mV) | reading at "
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs |"
    )
    lines.append("|---|" + "---:|" * (len(SLEWS_MVUS) + 1) + "---|")
    for variant in variants:
        cells = [f"{passes(variant.key, s)}/{len(band.SUPPLIES_V)}"
                 for s in SLEWS_MVUS]
        vsgs = [g(variant_name(variant.key, v, BOUNDARY_SLEW_MVUS), "vsg_min")
                for v in band.SUPPLIES_V]
        vsgs = [v for v in vsgs if v is not None]
        worst_vsg = f"{min(vsgs) * 1e3:+.1f}" if vsgs else "—"
        reading = (
            "the upper anchor" if variant.key == "sch"
            else "the lower anchor" if variant.key == "ext"
            else classify(variant.key)[0]
        )
        lines.append(
            f"| `{variant.key}` | " + " | ".join(cells)
            + f" | {worst_vsg} | {reading} |"
        )
    lines.append("")

    # ---- 3. the margin, per point --------------------------------------
    lines.append("## 3 — margin at each point")
    lines.append("")
    lines.append(
        "All times are µs after the dip starts. *window closes* is "
        "`edge + 50 µs dwell`, the end of the window "
        f"`../testbench/tb.json` measures `{RESETN_RATIO_KEY}` over, so a "
        "positive margin is a PASS at that point and a negative one — or a "
        "`RESETn` that never reaches valid-low — is the FAIL the grid records."
    )
    lines.append("")
    lines.append(
        "| rung (mV/µs) | supply | arm | window closes | `POR_RAW` asserts | "
        "`PGDG` falls | `RESETn` valid-low | margin | Δ vs `ext` | verdict |"
    )
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|---|")

    def us_after_dip(name, key):
        t = g(name, key)
        return None if t is None else (t - band.T_DIP_S) * 1e6

    def fmt_us(value):
        return "**never**" if value is None else f"{value:.1f}"

    for slew in SLEWS_MVUS:
        for vdd in band.SUPPLIES_V:
            base = margin_us("ext", vdd, slew)
            for variant in variants:
                name = variant_name(variant.key, vdd, slew)
                m = margin_us(variant.key, vdd, slew)
                delta = (
                    "—"
                    if (m is None or base is None or variant.key == "ext")
                    else f"{m - base:+.1f}"
                )
                lines.append(
                    f"| {slew:g} | {vdd:.2f} V | `{variant.key}` | "
                    f"{close_us(vdd, slew):.1f} | "
                    f"{fmt_us(us_after_dip(name, 't_praw'))} | "
                    f"{fmt_us(us_after_dip(name, 't_pgdg'))} | "
                    f"{fmt_us(us_after_dip(name, 't_rst'))} | "
                    + ("—" if m is None else f"{m:+.1f}")
                    + f" | {delta} | {verdict(variant.key, vdd, slew)} |"
                )
    lines.append("")

    # ---- 4. the state behind it ----------------------------------------
    lines.append(f"## 4 — the state behind it, at {BOUNDARY_SLEW_MVUS:g} mV/µs")
    lines.append("")
    lines.append(
        "`V_sg` (= VDD − `PG`) is the overdrive on `bias_core`'s PMOS mirror "
        "bank — the state variable [DR-011]"
        "(../../../spec/decision-records/DR-011-brownout-falling-slew-limit.md) "
        "measures the starved-loop collapse on, where a NEGATIVE value means "
        "the bank is driven fully off and every bias below it is dead. "
        "*recovered* is the fraction of the `sch`−`ext` gap in that number the "
        "arm gives back: 1.00 would be the schematic's own collapse, 0.00 the "
        "extraction's. It is computed on `V_sg` rather than on the margin "
        "because `V_sg` is defined for every run, including the ones where "
        "`RESETn` never reaches valid-low and the margin has no value at all. "
        "`ndg_r_max` is how far `por_output_chain`'s deglitch ramp got inside "
        "the window (≈0.6–0.7 is the level the PASS rows cross; 0.000 means it "
        "never moved)."
    )
    lines.append("")
    lines.append(
        "| arm | "
        + " | ".join(f"min `V_sg` (mV), {v:g} V" for v in band.SUPPLIES_V)
        + " | "
        + " | ".join(f"recovered, {v:g} V" for v in band.SUPPLIES_V)
        + " | "
        + " | ".join(f"peak `NDG`/VDD, {v:g} V" for v in band.SUPPLIES_V)
        + " |"
    )
    lines.append("|---" * (1 + 3 * len(band.SUPPLIES_V)) + "|")
    for variant in variants:
        cells: list[str] = []
        for vdd in band.SUPPLIES_V:
            v = g(variant_name(variant.key, vdd, BOUNDARY_SLEW_MVUS), "vsg_min")
            cells.append("—" if v is None else f"{v * 1e3:+.1f}")
        for vdd in band.SUPPLIES_V:
            f = recovered(variant.key, vdd)
            cells.append("—" if f is None else f"{f:+.2f}")
        for vdd in band.SUPPLIES_V:
            v = g(variant_name(variant.key, vdd, BOUNDARY_SLEW_MVUS), "ndg_r_max")
            cells.append("—" if v is None else f"{v:.3f}")
        lines.append(f"| `{variant.key}` | " + " | ".join(cells) + " |")
    lines.append("")

    # ---- 5. the reading ------------------------------------------------
    lines.append("## 5 — the reading, arm by arm")
    lines.append("")
    lines.append(
        "Each row states what shorting that arm's nets did to the "
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs boundary, classified from the two "
        "columns above and nothing else:"
    )
    lines.append("")
    lines.append(
        f"- **restores the bound** — passes all {len(band.SUPPLIES_V)} supply "
        f"points at {BOUNDARY_SLEW_MVUS:g} mV/µs. The loss is dominated by "
        "these nets and is a layout problem."
    )
    lines.append(
        f"- **dominant, not sufficient alone** — still fails, but gives back "
        f"≥ {DOMINANT_FRACTION:.0%} of the `V_sg` gap at every supply."
    )
    lines.append(
        f"- **contributes** — gives back ≥ {PARTIAL_FRACTION:.0%} of the gap "
        "at every supply, but not the bulk of it."
    )
    lines.append(
        f"- **not the carrier** — gives back < {PARTIAL_FRACTION:.0%} of the "
        "gap at one or more supplies. Removing this net's parasitics entirely "
        "does not move the boundary; the loss is elsewhere, or spread."
    )
    lines.append("")
    lines.append("| arm | nets | worst recovered | verdict at "
                 f"{BOUNDARY_SLEW_MVUS:g} mV/µs | reading |")
    lines.append("|---|---:|---:|---:|---|")
    for variant in variants:
        if not variant.nets:
            continue
        reading, worst = classify(variant.key)
        lines.append(
            f"| `{variant.key}` | {len(variant.nets)} | "
            + ("—" if worst is None else f"{worst:+.2f}")
            + f" | {passes(variant.key, BOUNDARY_SLEW_MVUS)}/"
            f"{len(band.SUPPLIES_V)} | {reading} |"
        )
    lines.append("")
    lines.append(
        "*worst recovered* is over the supply axis, because the binding point "
        "is the one that fails hardest, not the average: an arm that gives the "
        "collapse back at 2.97 V and nothing at 3.63 V has not moved the "
        "boundary, and the per-supply columns in section 4 are where that "
        "asymmetry is visible."
    )
    lines.append("")
    lines.append(
        "**Read `all` first.** It is the method control: it makes every one of "
        f"the {len(parasitics)} parasitic-carrying nets ideal at once, which is "
        "the most any amount of re-routing could ever recover. If `all` does "
        "not restore the bound, then no subset of it can, and the residue is "
        "not carried by interconnect parasitics at all — it is one of the other "
        "ways the extraction differs from the schematic export (per-device "
        "junction areas and perimeters taken from drawn geometry rather than "
        "from the schematic's formulas, plus `layout/postlayout/AUDIT.md`'s "
        "substitutions), which this control does not decompose further."
    )
    lines.append("")

    singles = [v.key for v in variants if len(v.nets) == 1]
    best = max(
        singles,
        key=lambda k: (lambda f: -2.0 if f is None else f)(classify(k)[1]),
        default=None,
    )
    all_pass = passes("all", BOUNDARY_SLEW_MVUS)
    lines.append(
        "**Bottom line, from the two tables above.** The method control `all` "
        f"passes {all_pass}/{len(band.SUPPLIES_V)} at "
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs against `sch`'s "
        f"{passes('sch', BOUNDARY_SLEW_MVUS)}/{len(band.SUPPLIES_V)}"
        + (
            ", so removing every parasitic in the extraction does not "
            "reproduce the schematic arm's behaviour at this rung and no "
            "subset of those nets can either"
            if all_pass < len(band.SUPPLIES_V)
            else ", so the shift is carried by interconnect parasitics and the "
            "rows above locate it"
        )
        + "."
        + (
            ""
            if best is None
            else (
                f" The best single net is `{best}` at "
                + (
                    "—"
                    if classify(best)[1] is None
                    else f"{classify(best)[1]:+.2f}"
                )
                + " worst recovered."
            )
        )
        + " Note that at this rung the block is inside the non-monotonic "
        "PASS/FAIL band `results.md` (#74) documents, so a partial pass count "
        "is a knife-edge, not a graded improvement — which is exactly why the "
        "`V_sg` column, and not the pass count, is what the classification "
        "above is computed from."
    )
    lines.append("")

    # ---- 5b. the other rung --------------------------------------------
    edge_slew = min(SLEWS_MVUS)
    lines.append(f"### The {edge_slew:g} mV/µs rung — a different question")
    lines.append("")
    lines.append(
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs asks whether the PRE-DR-019 bound is "
        f"recoverable. {edge_slew:g} mV/µs asks something else and more "
        "immediately useful: it is the extracted netlist's own transition edge "
        "— the lowest rung #188 recorded a failure at — so it is the rung that "
        f"put DR-019's bound at {DR019_BOUND_MVUS:g} mV/µs rather than higher. "
        "An arm that converts its failure is a lever on the ratified number "
        "even if it does nothing at "
        f"{BOUNDARY_SLEW_MVUS:g} mV/µs. Δ margin is against `ext` at the same "
        "point; only the supplies where `ext` does not already pass can move."
    )
    lines.append("")
    lines.append(
        "| arm | "
        + " | ".join(f"margin at {v:g} V (µs)" for v in band.SUPPLIES_V)
        + f" | passing | changes the {edge_slew:g} mV/µs edge? |"
    )
    lines.append("|---|" + "---:|" * (len(band.SUPPLIES_V) + 1) + "---|")
    ext_pass_at_edge = {
        vdd: (lambda v: v is not None and v <= rst_bound)(
            g(variant_name("ext", vdd, edge_slew), "rst_r_min")
        )
        for vdd in band.SUPPLIES_V
    }
    failing = [v for v, ok in ext_pass_at_edge.items() if not ok]
    for variant in variants:
        cells = []
        for vdd in band.SUPPLIES_V:
            m = margin_us(variant.key, vdd, edge_slew)
            base = margin_us("ext", vdd, edge_slew)
            cell = "—" if m is None else f"{m:+.1f}"
            if m is not None and base is not None and variant.key != "ext":
                cell += f" ({m - base:+.1f})"
            cells.append(cell)
        n_pass = passes(variant.key, edge_slew)
        if variant.key in ("sch", "ext"):
            note = "anchor"
        elif not failing:
            note = "—"
        elif n_pass == len(band.SUPPLIES_V):
            note = "**yes — converts every point `ext` fails**"
        else:
            note = "no"
        lines.append(
            f"| `{variant.key}` | " + " | ".join(cells)
            + f" | {n_pass}/{len(band.SUPPLIES_V)} | {note} |"
        )
    lines.append("")
    if failing:
        lines.append(
            "`ext` fails "
            + ", ".join(f"{v:g} V" for v in failing)
            + f" at {edge_slew:g} mV/µs; `sch` passes every point. An arm "
            "marked **yes** above removes the parasitics that carry that "
            "failure — which is a layout lever on where the extracted "
            "transition edge sits, and therefore on how much of the "
            f"{DR019_BOUND_MVUS:g} mV/µs bound is recoverable. Where the edge "
            "would land after such a re-route is not answered here: two rungs "
            "bracket a boundary, they do not locate it, and locating it is a "
            "corner-grid ladder's job (`../records/`), not a control's. That "
            "is filed as "
            "[#232](https://github.com/2AMLogic/gf180-temp-por/issues/232), "
            "which proposes re-laddering against this control's own "
            "`netlists/na-por.spice` first, before any layout is touched."
        )
        lines.append("")

    # ---- 6. probe integrity --------------------------------------------
    lines.append("## 6 — probe integrity")
    lines.append("")
    lines.append(
        "`run_band_mechanism.internal()` resolves the sub-cell node paths for "
        "either netlist flavour, and its docstring names the failure this "
        "section exists to rule out: if a probe below the cell boundary does "
        "not resolve, ngspice reports *vector … is not available*, the derived "
        "`let` fails, and the row reads as \"the deglitch never started\" "
        "rather than as \"this arm never looked\". Every generated netlist is "
        "a flat extraction with the same net names as its source, so the paths "
        "should resolve identically — this table is the check, not the claim."
    )
    lines.append("")
    lines.append(
        "| arm | decks with all of "
        + ", ".join(f"`{k}`" for k in INTERNAL_PROBE_KEYS)
        + " |"
    )
    lines.append("|---|---:|")
    for variant in variants:
        total = len(SLEWS_MVUS) * len(band.SUPPLIES_V)
        good = sum(
            1
            for slew in SLEWS_MVUS
            for vdd in band.SUPPLIES_V
            if all(
                key in res.get(variant_name(variant.key, vdd, slew), {})
                for key in INTERNAL_PROBE_KEYS
            )
        )
        flag = "" if good == total else " **← probe lost**"
        lines.append(f"| `{variant.key}` | {good}/{total}{flag} |")
    lines.append("")

    (CONTROL_DIR / "net_attribution_results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
