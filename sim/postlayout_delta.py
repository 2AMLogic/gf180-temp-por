#!/usr/bin/env python3
"""Schematic-vs-extracted delta for a post-layout corner-sweep re-run (#83).

    python3 sim/postlayout_delta.py <experiment-slug> <extracted-record-id> \
        --against <schematic-record-id> [--high-z NET,NET,...] [--write]

WHY THIS EXISTS

``sim/README.md`` says a post-layout extracted re-run carries "a
schematic-vs-extracted delta summary" against the schematic-level record it
supersedes. The corner runner cannot produce that: it writes one record from
one run and never reads a second record. And the append-only rule forbids
going back and editing the delta into either record afterwards.

So the delta is a **derived record**, the idiom ``sim/README.md`` already
ratifies for ``analyze_derived.py`` / ``analyze_breakdown.py``: it cites its
two source records, makes no measurement of its own, supersedes nothing, and
re-running it against the same pair reproduces the identical table. Its
numbers are computed from the two records' own raw per-corner logs, so no
number in it is transcribed by hand -- the evidence-hygiene rule
``sim/README.md`` states for controls, applied to the same job here.

WHAT IT COMPUTES

1. **Parasitic loading on the high-impedance nodes.** Issue #18's acceptance
   criteria ask for this explicitly, "not just pass/fail". Read straight out
   of the extracted netlist(s) ``sim/build_tb.py``'s ``POSTLAYOUT_FRAGMENTS``
   entry for this experiment names -- the same single source of truth that
   assembled the fragment, so the table cannot describe a different netlist
   than the one that ran. For an experiment with no ``POSTLAYOUT_FRAGMENTS``
   entry (a hand-maintained fragment that edits ports *inside* a subcircuit
   body, e.g. #274/#298's loop-break testbenches -- ``build_tb.py``'s
   verbatim-copy mechanism cannot produce those, so registering one there
   would make ``build_tb.py --check`` overwrite the hand edits), the source
   list is instead recovered from the fragment's own "Forked from
   ``layout/postlayout/<cell>.spice``" header line. ``layout/postlayout.py``
   models each net's interconnect as one resistive **star** -- the net's own
   name is the hub, each device terminal on it is a ``<net>__t<k>`` node, and
   the net's single lumped series resistance is split across the arms joining
   them, with the net's lumped C on the hub -- so per-net ΣC and ΣR are
   directly recoverable, and the loading a named high-impedance node actually
   sees is its own row of that table. ``--high-z`` names the nodes
   to call out (they are a property of the *design* -- e.g.
   ``design/temp_core.md``'s ``PTAT`` at R_src ≈ 516 kΩ -- not of the
   extraction, so the tool is told rather than guessing).

2. **Per-measurement delta.** Both records' grids, joined on corner-id: the
   schematic and extracted min/max/mean of every shared measurement, and the
   single worst per-corner delta with the corner it happened at.

3. **The regression verdict.** Each measurement's checks (from the
   experiment's own ``tb.json``) are evaluated against BOTH records' points
   using the harness's own ``report.evaluate_checks`` -- not a
   re-implementation of it -- and classified:

   | transition | meaning |
   |---|---|
   | `ok -> ok` | no regression |
   | `ok -> MISS` | **REGRESSION**: passes on the schematic, fails post-layout |
   | `MISS -> MISS` | a miss the schematic-level record already carried |
   | `MISS -> ok` | improvement (report it; do not celebrate it) |

   ``ok -> MISS`` is the row that matters: per CLAUDE.md the spec is not
   relaxed to make it pass, so it routes back to the owning design issue.

This is generic across experiments on purpose. #83 runs it on the
temp-sensing domain; #87's POR-domain re-runs need the identical comparison,
and neither should own a private copy of it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

SIM_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIM_DIR.parent

sys.path.insert(0, str(SIM_DIR))

from build_tb import POSTLAYOUT_DIR, POSTLAYOUT_FRAGMENTS  # noqa: E402
from harness import report  # noqa: E402
from harness.cliutil import add_author_arg, fmt, now_iso, write_derived_record  # noqa: E402
from harness.corners import CORNERS, PvtPoint, parse_corner_id  # noqa: E402
from harness.runner import PointResult, load_points  # noqa: E402
from harness.testbench import TESTBENCH_DIRNAME  # noqa: E402
from harness.testbench import load as load_testbench  # noqa: E402

#: Where ``sim/build_tb.py`` writes a post-layout fragment and where its
#: hand-authored manifest lives (issues #86/#84): a sibling of ``testbench/``,
#: never ``testbench/`` itself.
POSTLAYOUT_TESTBENCH_DIRNAME = f"{TESTBENCH_DIRNAME}-postlayout"

#: ``layout/postlayout.py``'s star-model terminal-node suffix. A net ``N`` that
#: carries drawn interconnect becomes a hub node ``N`` plus one ``N__t<k>``
#: node per device terminal on it; see that module's ``TERMINAL_SUFFIX`` and
#: ``layout/postlayout/AUDIT.md`` -> "The parasitic model".
TERMINAL_RE = re.compile(r"^(?P<net>.+)__t\d+$")

#: ``klt``'s own name prefix for a net-to-net coupling capacitor, passed
#: through verbatim by ``layout/postlayout.py``. It is the only thing that
#: separates a coupling card from a net's own ground capacitance card, which
#: have the identical shape -- so :func:`parasitics_by_net`'s own totals are
#: asserted against ``layout/postlayout/audit.json``'s in
#: ``sim/tests/test_postlayout_delta.py``: if klt ever renames these, that test
#: fails rather than the attribution quietly moving.
COUPLING_PREFIX = "CCC"

#: ``klt``'s 1 Tohm substrate DC tie (``Rvsubs_dctie <ground> 0 1e+12``). Not
#: interconnect on any net -- it exists only to give the substrate node a DC
#: path -- and large enough to swamp a cell's whole ΣR if it were summed in.
DCTIE_SUFFIX = "_DCTIE"

_R_CARD = re.compile(r"^(R\S*)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)
_C_CARD = re.compile(r"^(C\S*)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)


class ParasiticCardError(Exception):
    """A parasitic card whose shape this reader does not recognise.

    Never downgraded to a skip. The failure this exists to prevent is a model
    change upstream (#314 moved ``layout/postlayout.py`` from a dangling
    ``<net>__par`` leg to a per-net star) silently re-attributing a cell's whole
    capacitance to its ground rail while every number still looked plausible.
    """


def _number(token: str) -> float | None:
    """SPICE value token -> float, or None if it is not a bare number."""
    try:
        return float(token)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 1. parasitic loading, read out of the extracted netlist
# --------------------------------------------------------------------------


class ParasiticCard(NamedTuple):
    """One parasitic card of a post-layout netlist, and whose load it is."""

    line: str                 # the raw line, unmodified
    kind: str                 # resistance | capacitance | coupling | substrate_tie
    nets: tuple[str, ...]     # the schematic net(s) it loads; () for the tie
    value: float              # ohms or farads


def parasitic_cards(netlist: Path) -> list[ParasiticCard]:
    """Every parasitic card of ``netlist``, attributed to its net(s).

    The one parser for ``layout/postlayout.py``'s emitted parasitic network, so
    a consumer that *sums* a net's load (:func:`parasitics_by_net`) and one that
    *suppresses* it (``run_net_attribution.py``'s ``short_nets``) can never
    disagree about which cards are that net's. Four shapes, all of them klt's
    own naming passed through unchanged:

    ======================================  ====================================
    ``R<net>_t<k> <net>__t<k> <net> <ohms>``  one arm of the net's star
    ``C<net> <net> <ground> <farads>``        the net's lumped ground C
    ``Ccc__<a>__<b> <a> <b> <farads>``        net-to-net coupling: loads both
    ``R<subs>_dctie <ground> 0 1e+12``        the substrate DC tie: loads none
    ======================================  ====================================

    Raises :class:`ParasiticCardError` on anything else rather than skipping it.
    """
    cards: list[ParasiticCard] = []
    for raw in netlist.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith(("*", ".")):
            continue
        for pattern, kind in ((_R_CARD, "resistance"), (_C_CARD, "capacitance")):
            match = pattern.match(line)
            if not match:
                continue
            name, a, b, token = match.groups()
            value = _number(token)
            if value is None:
                # Not a parasitic: a device card whose third field happens to
                # be a node (the emitted devices are all X cards, so this is
                # only reachable for a hand-edited fragment).
                break
            if kind == "resistance" and name.upper().endswith(DCTIE_SUFFIX):
                cards.append(ParasiticCard(raw, "substrate_tie", (), value))
                break
            if kind == "resistance":
                # Both nodes are the same net: one is the hub, the other its
                # own terminal node.
                hub = _star_hub(name, a, b)
                cards.append(ParasiticCard(raw, "resistance", (hub,), value))
                break
            if name.upper().startswith(COUPLING_PREFIX):
                cards.append(ParasiticCard(raw, "coupling", (a, b), value))
                break
            # The net's own lumped capacitance; the far node is the ground it
            # returns to, which is not this net's load.
            cards.append(ParasiticCard(raw, "capacitance", (a,), value))
            break
    return cards


def _star_hub(name: str, a: str, b: str) -> str:
    """The net a star arm belongs to: the hub of ``<net>`` / ``<net>__t<k>``."""
    for terminal, hub in ((a, b), (b, a)):
        match = TERMINAL_RE.match(terminal)
        if match and match.group("net") == hub:
            return hub
    raise ParasiticCardError(
        f"{name}: {a!r} and {b!r} are not a star terminal and its own hub, so "
        "this resistor cannot be attributed to one net -- the parasitic model "
        "layout/postlayout.py emits has changed shape"
    )


def parasitics_by_net(netlist: Path) -> dict[str, dict[str, float]]:
    """Per-net interconnect ΣR / ΣC from an extracted netlist.

    Keyed on the *schematic* net name, because that is the name the design
    documents and the measure expressions use. Per net:

    * ``r_ohm`` -- its star's arms. Summing them gives the net's one lumped
      series resistance, which is the quantity klt reports per net.
    * ``c_f`` -- its own lumped capacitance to ground. Summing over nets
      reproduces the extraction's ``total_capacitance_ff`` exactly.
    * ``c_coupling_f`` -- coupling capacitance to *other* nets. A coupling
      capacitor loads both of its nets, so it is counted on each: summing over
      nets gives twice the extraction's ``total_coupling_capacitance_ff``.

    The substrate DC tie is excluded from ``r_ohm``: it is a 1 Tohm leak giving
    the substrate node a DC path, not interconnect on any net.
    """
    nets: dict[str, dict[str, float]] = {}

    def bucket(name: str) -> dict[str, float]:
        return nets.setdefault(
            name, {"r_ohm": 0.0, "c_f": 0.0, "c_coupling_f": 0.0}
        )

    key = {
        "resistance": "r_ohm",
        "capacitance": "c_f",
        "coupling": "c_coupling_f",
    }
    for card in parasitic_cards(netlist):
        if card.kind == "substrate_tie":
            continue
        for net in card.nets:
            bucket(net)[key[card.kind]] += card.value
    return nets


# --------------------------------------------------------------------------
# 2/3. the two records, joined and re-checked
# --------------------------------------------------------------------------


def as_results(points: dict[str, dict[str, float]]) -> list[PointResult]:
    """Raw per-corner measurements -> the harness's own PointResult objects.

    Reconstructed from the ratified corner-id naming so the check evaluation
    below can be `report.evaluate_checks` itself rather than a second
    implementation of the same limits that could drift away from it.
    """
    results: list[PointResult] = []
    for index, (corner_id, measurements) in enumerate(sorted(points.items())):
        fields = parse_corner_id(corner_id)
        if fields is None:
            continue
        process, temp_c, supply = fields
        corner = CORNERS.get(process)
        if corner is None:
            continue
        results.append(
            PointResult(
                point=PvtPoint(corner=corner, temp_c=temp_c, vdd=float(supply), index=index),
                status="ok",
                measurements=dict(measurements),
            )
        )
    return results


def verdicts(checks: dict[str, dict], results: list[PointResult]) -> dict[str, list[dict]]:
    """measurement -> its check failures, using the harness's own evaluator."""
    summary = report.summarize(results, sorted({n for r in results for n in r.measurements}))
    failures = report.evaluate_checks(checks, results, summary)
    by_measurement: dict[str, list[dict]] = {name: [] for name in checks}
    for failure in failures:
        by_measurement.setdefault(failure["measurement"], []).append(failure)
    return by_measurement


def classify(schematic: list[dict], extracted: list[dict]) -> str:
    if not schematic and not extracted:
        return "ok -> ok"
    if not schematic and extracted:
        return "ok -> MISS"
    if schematic and not extracted:
        return "MISS -> ok"
    return "MISS -> MISS"


def compare(
    schematic_points: dict[str, dict[str, float]],
    extracted_points: dict[str, dict[str, float]],
    checks: dict[str, dict],
) -> dict:
    schematic_results = as_results(schematic_points)
    extracted_results = as_results(extracted_points)
    names = sorted(
        {n for m in schematic_points.values() for n in m}
        & {n for m in extracted_points.values() for n in m}
    )
    shared_corners = sorted(set(schematic_points) & set(extracted_points))

    schematic_summary = report.summarize(schematic_results, names)
    extracted_summary = report.summarize(extracted_results, names)
    schematic_verdicts = verdicts(checks, schematic_results)
    extracted_verdicts = verdicts(checks, extracted_results)

    rows = []
    for name in names:
        worst_abs, worst_at, worst_rel = 0.0, None, None
        for corner_id in shared_corners:
            before = schematic_points[corner_id].get(name)
            after = extracted_points[corner_id].get(name)
            if before is None or after is None:
                continue
            delta = after - before
            if abs(delta) >= abs(worst_abs):
                worst_abs, worst_at = delta, corner_id
                worst_rel = (delta / before * 100.0) if before else None
        rows.append(
            {
                "measurement": name,
                "schematic": schematic_summary.get(name, {}),
                "extracted": extracted_summary.get(name, {}),
                "worst_delta": worst_abs,
                "worst_delta_at": worst_at,
                "worst_delta_pct": worst_rel,
                "checked": name in checks,
                "transition": classify(
                    schematic_verdicts.get(name, []), extracted_verdicts.get(name, [])
                ),
                "extracted_failures": extracted_verdicts.get(name, []),
                "schematic_failures": schematic_verdicts.get(name, []),
            }
        )
    return {
        "rows": rows,
        "shared_corners": shared_corners,
        "schematic_only": sorted(set(schematic_points) - set(extracted_points)),
        "extracted_only": sorted(set(extracted_points) - set(schematic_points)),
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _fmt_f(value: float | None) -> str:
    return "n/a" if value is None else fmt(value)


def render(
    experiment: str,
    extracted_id: str,
    schematic_id: str,
    delta: dict,
    parasitics: dict[str, dict[str, float]],
    high_z: list[str],
    sources: list[str],
    when: str,
    author: str,
    argv: list[str],
) -> str:
    regressions = [r for r in delta["rows"] if r["transition"] == "ok -> MISS"]
    carried = [r for r in delta["rows"] if r["transition"] == "MISS -> MISS"]
    improved = [r for r in delta["rows"] if r["transition"] == "MISS -> ok"]

    lines = [
        f"# Record {extracted_id}-postlayout-delta",
        "",
        f"- **Record ID**: `{extracted_id}-postlayout-delta`",
        f"- **Claim**: none of its own. This is a **derived** record in the sense "
        f"`sim/README.md` defines: it reduces two existing records' raw per-corner "
        f"logs, runs no simulation, and substantiates no spec row by itself. It is "
        f"the schematic-vs-extracted delta summary `sim/README.md` asks a post-layout "
        f"extracted re-run to carry against the schematic-level record it supersedes. "
        f"The claims stay with the source records: `{schematic_id}` (schematic) and "
        f"`{extracted_id}` (extracted).",
        f"- **Netlist provenance**: derived — no netlist of its own. Compares "
        f"`{schematic_id}` (schematic, `design/netlist/...`) against `{extracted_id}` "
        f"(extracted, "
        + ", ".join(f"`{s}`" for s in sources)
        + "). Each source record states its own provenance and, for the extracted "
        "one, the caveat `layout/postlayout/AUDIT.md` puts on it.",
        f"- **Corner matrix run**: none run here. {len(delta['shared_corners'])} "
        f"corner-ids are present in both records and are the ones compared below"
        + (
            ""
            if not (delta["schematic_only"] or delta["extracted_only"])
            else f"; {len(delta['schematic_only'])} only in `{schematic_id}` "
            f"({', '.join('`' + c + '`' for c in delta['schematic_only'][:8])}"
            + (", …" if len(delta["schematic_only"]) > 8 else "")
            + f"), {len(delta['extracted_only'])} only in `{extracted_id}` "
            f"({', '.join('`' + c + '`' for c in delta['extracted_only'][:8])}"
            + (", …" if len(delta["extracted_only"]) > 8 else "")
            + ")"
        )
        + ".",
        "- **Statistical convention**: N/A (a difference of two deterministic "
        "corner-matrix records, not a distribution claim).",
        "",
        "## 1. Parasitic loading on the high-impedance nodes",
        "",
        "`layout/postlayout.py` models each net's drawn interconnect as one",
        "resistive star -- the net is the hub, each device terminal on it a",
        "`<net>__t<k>` node, the net's lumped series R split across the arms",
        "joining them and its lumped C on the hub -- so the loading a node sees is",
        "its own row here. `coupling C` is capacitance charged between this net and",
        "a *different* net rather than to ground, and is counted on both of them.",
        "Read out of the extracted netlist, not measured:",
        "",
    ]

    if high_z:
        lines += [
            "| net | ΣC (fF) | coupling C (fF) | ΣR (Ω) | share of cell ΣC |",
            "|---|---|---|---|---|",
        ]
        total_c = sum(v["c_f"] for v in parasitics.values()) or 1.0
        for net in high_z:
            entry = parasitics.get(net)
            if entry is None:
                lines.append(
                    f"| `{net}` | **no drawn interconnect of its own** | — | — | — |"
                )
                continue
            lines.append(
                f"| `{net}` | {entry['c_f'] * 1e15:.2f} | "
                f"{entry['c_coupling_f'] * 1e15:.3f} | {entry['r_ohm']:.1f} | "
                f"{entry['c_f'] / total_c * 100:.1f} % |"
            )
        lines.append("")

    ranked = sorted(parasitics.items(), key=lambda kv: kv[1]["c_f"], reverse=True)[:10]
    lines += [
        "Ten most heavily loaded nets in the same netlist, for scale:",
        "",
        "| net | ΣC (fF) | coupling C (fF) | ΣR (Ω) |",
        "|---|---|---|---|",
    ]
    for net, entry in ranked:
        lines.append(
            f"| `{net}` | {entry['c_f'] * 1e15:.2f} | "
            f"{entry['c_coupling_f'] * 1e15:.3f} | {entry['r_ohm']:.1f} |"
        )
    lines += [
        "",
        f"Cell total: {sum(v['c_f'] for v in parasitics.values()) * 1e15:.1f} fF of "
        f"interconnect capacitance over {len(parasitics)} nets.",
        "",
        "## 2. Verdict transitions",
        "",
        "Each checked measurement's `tb.json` limits evaluated against both records'",
        "points, by the harness's own `report.evaluate_checks`:",
        "",
        "| measurement | transition | worst extracted violation |",
        "|---|---|---|",
    ]
    for row in delta["rows"]:
        if not row["checked"]:
            continue
        worst = ""
        if row["extracted_failures"]:
            f0 = max(
                row["extracted_failures"],
                key=lambda f: abs((f["value"] or 0) - (f["limit"] or 0)),
            )
            worst = (
                f"`{f0['measurement']}` {f0['kind']}={_fmt_f(f0['limit'])}, "
                f"got {_fmt_f(f0['value'])} at `{f0['at']}` "
                f"({len(row['extracted_failures'])} point(s))"
            )
        marker = "**REGRESSION**" if row["transition"] == "ok -> MISS" else row["transition"]
        lines.append(f"| `{row['measurement']}` | {marker} | {worst or '—'} |")

    lines += [
        "",
        f"- **Regressions (`ok -> MISS`): {len(regressions)}**"
        + (
            " — none. Every check the schematic-level record passed, the "
            "extracted one passes too."
            if not regressions
            else " — "
            + ", ".join(f"`{r['measurement']}`" for r in regressions)
            + ". Per CLAUDE.md the spec is not relaxed to make these pass; each "
            "routes back to its owning design issue."
        ),
        f"- Misses the schematic record already carried (`MISS -> MISS`): "
        f"{len(carried)}"
        + (
            "."
            if not carried
            else " — " + ", ".join(f"`{r['measurement']}`" for r in carried) + "."
        ),
        f"- Improvements (`MISS -> ok`): {len(improved)}"
        + (
            "."
            if not improved
            else " — " + ", ".join(f"`{r['measurement']}`" for r in improved) + "."
        ),
        "",
        "## 3. Per-measurement delta",
        "",
        "| measurement | schematic min…max | extracted min…max | worst per-corner Δ | at |",
        "|---|---|---|---|---|",
    ]
    for row in delta["rows"]:
        s, e = row["schematic"], row["extracted"]
        pct = (
            ""
            if row["worst_delta_pct"] is None
            else f" ({row['worst_delta_pct']:+.3g} %)"
        )
        lines.append(
            f"| `{row['measurement']}` | {_fmt_f(s.get('min'))}…{_fmt_f(s.get('max'))} "
            f"| {_fmt_f(e.get('min'))}…{_fmt_f(e.get('max'))} "
            f"| {row['worst_delta']:+.6g}{pct} | `{row['worst_delta_at']}` |"
        )

    lines += [
        "",
        "- **Links**:",
        f"  - Schematic-level source record: "
        f"`sim/{experiment}/records/{schematic_id}.md` "
        f"(raw logs `sim/{experiment}/corners/{schematic_id}/`)",
        f"  - Extracted source record: `sim/{experiment}/records/{extracted_id}.md` "
        f"(raw logs `sim/{experiment}/corners/{extracted_id}/`)",
        "  - Extracted netlist: " + ", ".join(f"`{s}`" for s in sources),
        f"  - Testbench manifest (the checks re-evaluated above): "
        f"`sim/{experiment}/testbench/tb.json`",
        f"- **Timestamp / author**: {when}, {author}",
        "- **Supersedes**: (none — a derived record supersedes nothing; it cites "
        "the two records it reduces)",
        "",
        "---",
        "",
        "Written by `sim/postlayout_delta.py`. Reproduce with:",
        "",
        "```bash",
        "python3 " + " ".join(argv),
        "```",
        "",
        "Append-only: never edit or delete this file — re-deriving it against a",
        "different pair of records mints a new derived record (see `sim/README.md`).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("experiment", help="experiment slug under sim/")
    parser.add_argument("record_id", help="the post-layout (extracted) <record-id>")
    parser.add_argument(
        "--against",
        required=True,
        metavar="RECORD_ID",
        help="the schematic-level <record-id> it supersedes",
    )
    parser.add_argument(
        "--high-z",
        default="",
        metavar="NET,NET,...",
        help="nets to call out as high-impedance (a design property, so it is "
        "declared here rather than guessed from the extraction)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write records/<record-id>-postlayout-delta.md (default: stdout only)",
    )
    add_author_arg(parser)
    args = parser.parse_args(argv)

    tb_path = SIM_DIR / args.experiment / POSTLAYOUT_TESTBENCH_DIRNAME
    if not (tb_path / "tb.json").is_file():
        print(
            f"no {tb_path.relative_to(REPO_ROOT)}/tb.json -- "
            f"{args.experiment} has no post-layout sibling testbench. Add it to "
            "sim/build_tb.py's POSTLAYOUT_FRAGMENTS and hand-author that "
            "directory's manifest first (sim/README.md, 'Netlist provenance').",
            file=sys.stderr,
        )
        return 2
    tb = load_testbench(tb_path)
    experiment_dir = tb.experiment_dir
    corners_dir = experiment_dir / report.CORNERS_DIR

    if tb.mc:
        # A Monte Carlo record's points are per-sample draws
        # (`mc_<corner>_<temp>c_<vdd>v_s<n>`), not PVT grid points: there is
        # no corner-for-corner correspondence to difference, and its checks
        # are `[3 sigma]` bounds on a distribution rather than per-point
        # limits. Differencing them here would silently produce a table with
        # no meaning, so refuse instead. `sim/run_mc.py --supersedes` already
        # ties the post-layout MC record to the schematic-level one, and
        # `analyze_breakdown.py` is where its per-term attribution lives.
        print(
            f"{tb_path}: {tb.experiment} is a Monte Carlo experiment. Its "
            "records are per-sample distributions, not a PVT grid, so a "
            "corner-for-corner delta is not defined. Compare the two records' "
            "own distribution tables (each MC record's Result section), and "
            "use sim/temp-accuracy-mc/analyze_breakdown.py for the per-term "
            "attribution.",
            file=sys.stderr,
        )
        return 2

    extracted_points = load_points(corners_dir, args.record_id)
    schematic_points = load_points(corners_dir, args.against)

    if tb.netlist_provenance != "extracted":
        print(
            f"{tb_path}/tb.json: netlist_provenance is "
            f"{tb.netlist_provenance!r}, not 'extracted' -- this tool compares "
            "a post-layout record against a schematic-level one",
            file=sys.stderr,
        )
        return 2

    # The netlist(s) under the extracted record come from the one place that
    # assembled its fragment, so the parasitic table below cannot end up
    # describing a netlist other than the one that ran.
    if args.experiment in POSTLAYOUT_FRAGMENTS:
        _, cells = POSTLAYOUT_FRAGMENTS[args.experiment]
        sources = [
            str((POSTLAYOUT_DIR / f"{cell}.spice").relative_to(REPO_ROOT)) for cell in cells
        ]
    else:
        # Hand-maintained fragment outside sim/build_tb.py's mechanism (#274/
        # #298: a loop-break testbench edits ports *inside* the subcircuit
        # body, which build_tb.py's verbatim-copy can't do, so it is
        # deliberately not a POSTLAYOUT_FRAGMENTS entry -- registering it
        # there would make `build_tb.py --check` overwrite the hand edits).
        # Its own header names the extracted netlist(s) it was forked from
        # ("Forked from layout/postlayout/<cell>.spice"), the same
        # provenance convention every hand-maintained fragment carries, so
        # recover the source list from there instead.
        header = tb.netlist.read_text()
        found = sorted(set(re.findall(r"layout/postlayout/(\S+?\.spice)", header)))
        if not found:
            print(
                f"{tb.netlist}: {args.experiment!r} is not in POSTLAYOUT_FRAGMENTS "
                "and its header does not cite a 'layout/postlayout/<cell>.spice' "
                "source to fall back to -- add a 'Forked from "
                "layout/postlayout/<cell>.spice' provenance line to the fragment's "
                "header",
                file=sys.stderr,
            )
            return 2
        sources = [f"layout/postlayout/{name}" for name in found]

    parasitics: dict[str, dict[str, float]] = {}
    for source in sources:
        for net, entry in parasitics_by_net(REPO_ROOT / source).items():
            got = parasitics.setdefault(
                net, {"r_ohm": 0.0, "c_f": 0.0, "c_coupling_f": 0.0}
            )
            for key, value in entry.items():
                got[key] += value

    high_z = [n.strip() for n in args.high_z.split(",") if n.strip()]
    delta = compare(schematic_points, extracted_points, tb.checks)

    text = render(
        experiment=tb.experiment,
        extracted_id=args.record_id,
        schematic_id=args.against,
        delta=delta,
        parasitics=parasitics,
        high_z=high_z,
        sources=sources,
        when=now_iso(),
        author=args.author,
        argv=["sim/postlayout_delta.py", args.experiment, args.record_id,
              "--against", args.against]
        + (["--high-z", args.high_z] if args.high_z else [])
        + ["--write"],
    )
    print(text)

    if args.write:
        try:
            out = write_derived_record(
                text,
                experiment_dir / report.RECORDS_DIR,
                f"{args.record_id}-postlayout-delta.md",
            )
        except report.RecordExists as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"\nwrote {out.relative_to(REPO_ROOT)}", file=sys.stderr)

    regressions = [r for r in delta["rows"] if r["transition"] == "ok -> MISS"]
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
