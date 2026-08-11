"""Append-only evidence records for Monte Carlo mismatch runs (issue #15).

Same *schema* as ``sim/harness/report.py`` -- the nine ratified fields from
``sim/README.md`` (Record ID, Claim, Netlist provenance, Corner matrix run,
Statistical convention, Result, Links, Timestamp / author, Supersedes), same
``records/<record-id>.md`` / ``netlist-snapshots/<record-id>.spice`` /
``corners/<record-id>/<corner-id>.log`` directory convention, same
append-only guarantee -- but a different *shape* of content, because an MC
run is not a PVT-grid claim:

- **Corner matrix run** names the row's own spec-ratified binding points
  (a handful of named (process corner, temperature, rail) triples, not the
  81-point grid) with an explicit justification, exactly the pattern
  ``sim/README.md``'s own worked example previews for a Monte Carlo record:
  "nominal PVT only, with ``--subset-reason`` naming why ... It is a distinct
  claim from the corner-matrix record above, not a correction of it".
- **Result** is a per-(binding point, measurement) distribution table (n,
  mean, sigma, empirical yield, parametric mean +/- 3 sigma bound) rather
  than one row per PVT point -- a run with 2000+ samples cannot be one row
  per sample and stay readable, and the distribution IS the claim.
- Every sample's raw ngspice log is still written under
  ``corners/<record-id>/``, so the distribution is reproducible from the
  repository, not hand-transcribed (the evidence-hygiene lesson #50 flagged,
  named explicitly in issue #15).

This module reuses ``report.py``'s git/environment provenance, record-id
allocation and the append-only netlist-snapshot writer directly -- those are
genuinely generic. It does not reuse ``report.py``'s ``build_record`` /
``render_record`` / ``matrix_conformance``, which are shaped around the
deterministic PVT grid.
"""

from __future__ import annotations

from pathlib import Path

from .cliutil import fmt as _fmt
from .montecarlo import BindingPoint, McPoint
from .pdk import Pdk
from .report import (
    CORNERS_DIR,
    RECORDS_DIR,
    SNAPSHOT_DIR,
    TESTBENCH_DIR,
    RecordExists,
    environment,
)
from .runner import PointResult
from .testbench import Testbench


def build_mc_record(
    tb: Testbench,
    pdk: Pdk,
    binding_points: list[BindingPoint],
    points: list[McPoint],
    results: list[PointResult],
    summary: dict[str, dict[str, dict]],
    ngspice: str,
    repo_root: Path,
    record_id: str,
    started_utc: str,
    wall_seconds: float,
    n_per_point: int,
    seed_base: int,
    derived_measures: list[str],
    claim: str = "",
    supersedes: str = "",
    statistical_convention: str = "",
    git: dict | None = None,
) -> dict:
    n_ok = sum(1 for r in results if r.status == "ok")

    # A binding point "fails" if the parametric [3sigma] bound of ANY of its
    # measurements with a spec limit crosses that limit. The record's overall
    # verdict is the worst binding point, mirroring the deterministic
    # harness's "any failing point fails the record" convention.
    failures: list[dict] = []
    for label, by_measure in summary.items():
        for name, stats in by_measure.items():
            if stats.get("n", 0) < 2:
                continue
            if not stats.get("parametric_3sigma_pass", True):
                failures.append(
                    {
                        "label": label,
                        "measurement": name,
                        "mean": stats["mean"],
                        "sigma3_lo": stats["sigma3_lo"],
                        "sigma3_hi": stats["sigma3_hi"],
                        "spec_min": stats["spec_min"],
                        "spec_max": stats["spec_max"],
                    }
                )

    if n_ok != len(results):
        status = "error"
    elif failures:
        status = "fail"
    else:
        status = "pass"

    return {
        "record_id": record_id,
        "experiment": tb.experiment,
        "status": status,
        "started_utc": started_utc,
        "wall_seconds": round(wall_seconds, 2),
        "claim": claim or tb.claim,
        "supersedes": supersedes,
        "statistical_convention": statistical_convention,
        "testbench": tb.provenance(),
        "environment": environment(pdk, ngspice, repo_root, git),
        "binding_points": [
            {
                "label": bp.label,
                "corner": bp.corner.name,
                "corner_sections": list(bp.corner.sections),
                "corner_description": bp.corner.description,
                "temp_c": bp.temp_c,
                "vdd": bp.vdd,
            }
            for bp in binding_points
        ],
        "n_per_point": n_per_point,
        "seed_base": seed_base,
        "total_points": len(points),
        "points_ok": n_ok,
        "measure": {**dict(tb.measure), **{name: "(derived)" for name in derived_measures}},
        "summary": summary,
        "checks": {"spec": tb.checks, "passed": not failures, "failures": failures},
    }


def _binding_points_lines(record: dict) -> list[str]:
    lines = [
        "- **Corner matrix run**:",
        "  - **Monte Carlo distribution claim at spec-ratified binding points, "
        "not the full 81-point deterministic grid** (per "
        "`spec/target-spec.md` section 2's own `[3σ]` definition: process is "
        "held at each row's own named binding corner, only local mismatch is "
        "randomized -- see `sim/harness/montecarlo.py`'s module docstring). "
        "The process/temperature/rail axis is already covered by the "
        "deterministic corner-sweep records this run's Claim cites; this "
        "record adds the local-mismatch axis on top, at those same records' "
        "own named binding points.",
    ]
    for bp in record["binding_points"]:
        lines.append(
            f"  - `{bp['label']}`: corner `{bp['corner']}` "
            f"({bp['corner_description']}), {bp['temp_c']:g} °C, {bp['vdd']:.2f} V "
            f"-- sections: {' '.join(bp['corner_sections'])}"
        )
    lines.append(
        f"  - {record['n_per_point']} samples per binding point x "
        f"{len(record['binding_points'])} binding points = {record['total_points']} "
        f"ngspice invocations, {record['points_ok']} completed."
    )
    return lines


def _result_lines(record: dict) -> list[str]:
    lines = ["- **Result**:", ""]
    lines.append(
        "  | binding point | measurement | n | mean | σ | mean−3σ | mean+3σ | "
        "spec limits | empirical yield | [3σ] verdict |"
    )
    lines.append("  |---|---|---|---|---|---|---|---|---|---|")
    failures_index = {
        (f["label"], f["measurement"]) for f in record["checks"]["failures"]
    }
    for label, by_measure in record["summary"].items():
        for name, stats in by_measure.items():
            if stats.get("n", 0) < 2:
                lines.append(f"  | `{label}` | `{name}` | {stats.get('n', 0)} | no data | | | | | | |")
                continue
            spec_bits = []
            if stats["spec_min"] is not None:
                spec_bits.append(f"min={_fmt(stats['spec_min'])}")
            if stats["spec_max"] is not None:
                spec_bits.append(f"max={_fmt(stats['spec_max'])}")
            limits = ", ".join(spec_bits) or "—"
            verdict = "n/a (informative)" if not spec_bits else (
                "FAIL" if (label, name) in failures_index else "PASS"
            )
            lines.append(
                f"  | `{label}` | `{name}` | {stats['n']} | {_fmt(stats['mean'])} | "
                f"{_fmt(stats['stdev'])} | {_fmt(stats['sigma3_lo'])} | "
                f"{_fmt(stats['sigma3_hi'])} | {limits} | "
                f"{stats['empirical_yield'] * 100:.2f}% | {verdict} |"
            )

    lines.append("")
    if record["checks"]["failures"]:
        lines.append("  [3σ] budget misses:")
        for f in record["checks"]["failures"]:
            lines.append(
                f"  - `{f['label']}` / `{f['measurement']}`: mean {_fmt(f['mean'])}, "
                f"mean±3σ = [{_fmt(f['sigma3_lo'])}, {_fmt(f['sigma3_hi'])}] against "
                f"spec [{_fmt(f['spec_min'])}, {_fmt(f['spec_max'])}]"
            )
        lines.append("")

    verdict = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[record["status"]]
    lines.append(f"  - **Overall: {verdict}**")
    return lines


def render_mc_record(record: dict, experiment: str) -> str:
    record_id = record["record_id"]
    env = record["environment"]
    tb = record["testbench"]
    git = env["git"]
    pdk = env["pdk"]

    # Manifest-driven, exactly as report.py's render_record() does it (#86):
    # tb["directory"] is the actual testbench subdirectory name (usually
    # "testbench"; "testbench-postlayout" for an extracted-provenance sibling
    # directory), and the provenance kind plus its mandatory caveat note come
    # from the testbench manifest rather than being assumed. Hardcoding
    # "schematic" here mislabelled the first post-layout Monte Carlo record
    # (#194) -- an extracted run has to say so, and has to carry the
    # layout/postlayout/AUDIT.md caveat sim/README.md requires of it. Falls
    # back to the ratified defaults for records built before these fields
    # existed.
    testbench_dir = tb.get("directory") or TESTBENCH_DIR
    provenance_kind = tb.get("netlist_provenance") or "schematic"
    provenance = f"{provenance_kind} (`sim/{experiment}/{testbench_dir}/{tb['netlist']}`)"
    note = tb.get("netlist_provenance_note") or ""
    if note:
        provenance += f" — {note}"

    # `run_mc.py <slug>` resolves to the experiment's schematic `testbench/`
    # directory (cliutil.resolve_tb_path), so a record taken against any other
    # testbench directory has to spell that directory out or its Reproduce
    # line re-runs a different netlist (#194).
    reproduce_arg = (
        experiment
        if testbench_dir == TESTBENCH_DIR
        else f"sim/{experiment}/{testbench_dir}"
    )

    if git["dirty"]:
        provenance += (
            f" — **taken against a dirty working tree** at commit `{git['commit']}`; "
            "not citable as a clean-tree result"
        )

    lines = [
        f"# Record {record_id}",
        "",
        f"- **Record ID**: {record_id}",
        f"- **Claim**: {record['claim'] or 'harness self-verification — no spec claim'}",
        f"- **Netlist provenance**: {provenance}",
    ]
    lines += _binding_points_lines(record)
    lines.append(
        "- **Statistical convention**: "
        + (
            record["statistical_convention"]
            or (
                f"Process plus local mismatch (spec/target-spec.md §2's `[3σ]`): "
                f"process held at each binding point's own named deterministic "
                f"corner (see above), local mismatch on "
                f"(`sw_stat_mismatch=1`, `sw_stat_global=0`), N={record['n_per_point']} "
                f"independent samples per binding point (>= the N>=500 floor), "
                f"each sample reproducible via `.option seed=<{record['seed_base']}"
                f" + binding_index*100000 + sample>` (see the raw per-sample logs "
                f"linked below). Reported per (binding point, measurement): "
                f"empirical mean/σ, the empirical yield (fraction of the N "
                f"samples inside the ratified spec limits), and the parametric "
                f"mean ± 3σ bound spec/target-spec.md §2 defines a `[3σ]` claim "
                f"against."
            )
        )
    )
    lines += _result_lines(record)
    lines += [
        "- **Links**:",
        f"  - Testbench: `sim/{experiment}/{testbench_dir}/{tb['netlist']}`, "
        f"`sim/{experiment}/{testbench_dir}/tb.json`",
        f"  - Netlist snapshot: `sim/{experiment}/{SNAPSHOT_DIR}/{record_id}.spice`",
        f"  - Raw per-sample logs (one file per (binding point, sample), "
        f"{record['total_points']} files): `sim/{experiment}/{CORNERS_DIR}/{record_id}/`",
        f"- **Timestamp / author**: {record['started_utc']}, {env['user']}",
        f"- **Supersedes**: {record['supersedes'] or '(none)'}",
        "",
        "## Environment",
        "",
        "Everything needed to re-run this record:",
        "",
        f"- PDK: {pdk.get('variant')} @ open_pdks `{pdk.get('open_pdks_version')}`"
        f" ({pdk.get('path')}, found via {pdk.get('discovered_via')})",
        f"- ngspice: {env['ngspice']}",
        f"- Harness: sim/harness {env['harness_version']}, python {env['python']}",
        f"- git: `{git['commit']}` on `{git['branch']}`"
        + (" (dirty)" if git["dirty"] else " (clean)"),
        f"- Testbench netlist sha256: `{tb['netlist_sha256']}`",
        f"- Manifest sha256: `{tb['manifest_sha256']}`",
        f"- Wall time: {record['wall_seconds']} s",
        f"- Reproduce: `python3 sim/run_mc.py {reproduce_arg}` "
        f"(same `mc.seed_base` in the manifest reproduces the identical sample set)",
        "",
        "---",
        "",
        "Written by `sim/run_mc.py`. Append-only: never edit or delete this",
        "file — a re-run or correction mints a new record-id and points back here",
        "via **Supersedes** (see `sim/README.md`).",
        "",
    ]
    return "\n".join(lines)


def write_mc_record(record: dict, experiment_dir: Path) -> Path:
    """Write ``records/<record-id>.md``; never overwrite an existing record."""
    out_dir = experiment_dir / RECORDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{record['record_id']}.md"
    if path.exists():
        raise RecordExists(
            f"{path} already exists; records are append-only -- mint a new record-id"
        )
    path.write_text(render_mc_record(record, experiment_dir.name))
    return path
