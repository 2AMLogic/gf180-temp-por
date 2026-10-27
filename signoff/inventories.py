#!/usr/bin/env python3
"""Audited inventories behind T1 items 1, 2, 9 and 10.

`klt signoff` (>= 0.7.0) accepts a `kind: generic` envelope for these four
items when it is bound to an audited artifact: the envelope declares
`"t1_item": <n>`, names the artifact in `provenance.input.path`, and the
manifest pins the same `content_hash`. That binding proves the artifact's
*bytes* are fresh. It proves nothing about whether the artifact is *true*, or
whether a file the inventory is about has moved underneath it.

So the artifacts bound here are inventories that carry the sha256 of every
member file, and this module is both their only writer and their verifier:

* `build_*` derives an inventory from the tree and **raises** when the audit
  fails (a spec row that claims a measurement but names no committed
  testbench, a schematic with no derived netlist, an experiment directory
  nobody classified, ...). `--regen` therefore cannot write a `pass`
  envelope over a claim the tree does not support.
* `verify_item` rebuilds the same inventory from the live tree and compares
  it with the committed one, member by member, so a changed, deleted or newly
  added file fails with its name -- even though the inventory's own bytes did
  not change.

Pure stdlib; no klt, PDK, xschem or ngspice. Nothing here runs a simulation
or touches `sim/` evidence: `sim/` is only read.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC = "spec/target-spec.md"
CI_WORKFLOW = ".github/workflows/ci.yml"
HARNESS_README = "sim/harness/README.md"
GDS_TOP = "layout/cells/temp_por_top.gds"

ITEM_ARTIFACTS = {
    1: "signoff/evidence/inventory-design-sources.json",
    2: GDS_TOP,
    9: "signoff/evidence/inventory-testbenches.json",
    10: "signoff/evidence/inventory-repo-hygiene.json",
}
ITEM_ENVELOPES = {
    1: "signoff/evidence/t1-item-1-design-sources.json",
    2: "signoff/evidence/t1-item-2-layout.json",
    9: "signoff/evidence/t1-item-9-testbenches.json",
    10: "signoff/evidence/t1-item-10-repo-hygiene.json",
}
ITEM_TITLES = {
    1: "Design sources",
    2: "Layout",
    9: "Testbenches shipped",
    10: "Repo hygiene",
}

# Every spec row (an `<a id=...>` anchor in spec/target-spec.md) must be
# classified here. `measured`/`derived` rows claim a number that a testbench
# produced, so each must name experiments that ship a committed testbench;
# every other kind claims no simulated number and says what it rests on.
# A row added to the spec without an entry here fails the audit.
MEASURED, DERIVED = "measured", "derived"
ROW_BASIS: dict[str, dict] = {
    "supply-voltage": {"kind": "condition"},
    "operating-temperature": {"kind": "condition"},
    "corner-grid": {"kind": "condition"},
    "accuracy-window": {"kind": "condition"},
    "temp-range": {"kind": "condition"},
    "pinout": {
        "kind": "design-gate",
        "gate": "python3 design/netlist.py --check",
    },
    "temp-accuracy-untrimmed": {
        "kind": MEASURED,
        "experiments": ["temp-accuracy-vt", "temp-accuracy-mc"],
    },
    "temp-accuracy-trimmed": {
        "kind": DERIVED,
        "experiments": ["temp-accuracy-vt", "temp-accuracy-mc"],
        "derivation": "sim/temp-accuracy-vt/analyze_derived.py",
    },
    "temp-trim-strategy": {
        "kind": MEASURED,
        "experiments": ["temp-core-designer-check"],
    },
    "temp-vt-transfer": {
        "kind": MEASURED,
        "experiments": ["temp-accuracy-vt", "temp-core-designer-check"],
    },
    "temp-supply-sensitivity": {
        "kind": MEASURED,
        "experiments": ["temp-accuracy-vt"],
    },
    "temp-iq": {"kind": MEASURED, "experiments": ["temp-accuracy-vt"]},
    "temp-interface": {"kind": "decision", "basis": "DR-002"},
    "temp-resolution-rate": {"kind": "decision", "basis": "continuous analog output"},
    "temp-self-heating": {"kind": "analytic", "basis": "iq-total x 3.63 V power budget"},
    "self-heating": {"kind": "analytic", "basis": "alias of temp-self-heating"},
    "por-vth-rise": {
        "kind": MEASURED,
        "experiments": ["por-vth", "por-threshold-mc"],
    },
    "por-vth-fall": {
        "kind": MEASURED,
        "experiments": ["por-vth", "por-threshold-mc"],
    },
    "por-hysteresis": {
        "kind": MEASURED,
        "experiments": ["por-vth", "por-threshold-mc"],
    },
    "por-digital-min-vdd": {"kind": "tbd", "basis": "integrator-supplied; no value claimed"},
    "por-ramp-rate": {"kind": MEASURED, "experiments": ["por-ramp-rate"]},
    "por-brownout": {
        "kind": MEASURED,
        "experiments": [
            "por-brownout",
            "por-brownout-slew",
            "por-brownout-spurious",
            "por-glitch",
            "por-output-chain-deglitch",
        ],
    },
    "por-reset-pulse": {
        "kind": MEASURED,
        "experiments": ["por-brownout", "por-output-chain-pulse"],
    },
    "por-polarity": {"kind": "decision", "basis": "DR-004"},
    "por-drive": {"kind": "decision", "basis": "DR-004"},
    "por-reset-valid-floor": {
        "kind": MEASURED,
        "experiments": ["por-brownout", "por-output-chain-floor"],
    },
    "por-iq": {
        "kind": DERIVED,
        "experiments": ["temp-accuracy-vt", "temp-por-top-release"],
        "derivation": "sim/por-iq/analyze_por_iq.py",
    },
    "iq-total": {
        "kind": DERIVED,
        "experiments": ["temp-accuracy-vt"],
        "derivation": "sim/por-iq/analyze_por_iq.py",
    },
    "area": {
        "kind": "layout-stat",
        "evidence_file": "layout/reports/temp_por_top/stats.json",
    },
}

# `sim/` directories that ship no `testbench*/` directory of their own. Each
# must be classified; a new one is unclassified and fails the audit.
NO_TESTBENCH_DIRS = {
    "devchar": "device characterization decks and results; cited by the spec only "
    "as an informative physics anchor, no spec row's number is measured here",
    "harness": "shared corner-runner support code, not an experiment",
    "por-iq": "derivation only (analyze_por_iq.py) over the temp-accuracy-vt "
    "testbench's raw logs; por-iq and iq-total list that testbench as their basis",
    "pex": "klt pex staging and measure-command driver (T1 item 7); it re-expresses "
    "the por-vth testbench rather than adding an experiment of its own",
    "tests": "harness unit tests, not an experiment",
}

# Commands a reader needs to reproduce a record from a cold checkout, each
# with the committed file that documents it. The audit requires the text to be
# present in that file, so the inventory cannot name a command nobody wrote down.
COLD_START = [
    ("python3 sim/run_corners.py --check-env", HARNESS_README),
    ("python3 sim/run_corners.py <experiment>", HARNESS_README),
    ("python3 sim/run_mc.py", HARNESS_README),
    ("bash sim/selftest.sh --require-pdk", CI_WORKFLOW),
]
_COLD_START_NEEDLE = {"<experiment>": "smoke-bias"}

HYGIENE_FILES = ["README.md", "LICENSE", SPEC, CI_WORKFLOW]


class AuditError(Exception):
    """The tree does not support the claim an inventory would make."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def dump_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def _member(root: Path, rel: str) -> dict:
    path = root / rel
    if not path.is_file():
        raise AuditError(f"{rel}: listed in an inventory but missing")
    return {"path": rel, "sha256": sha256_file(path)}


def _members(root: Path, rels) -> list[dict]:
    return [_member(root, rel) for rel in sorted(rels)]


def _glob(root: Path, pattern: str) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.glob(pattern) if p.is_file())


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text()
    except OSError as exc:
        raise AuditError(f"{rel}: unreadable ({exc})") from exc


def spec_row_ids(root: Path = REPO_ROOT) -> list[str]:
    return sorted(set(re.findall(r'<a id="([a-z0-9-]+)"></a>`', _read(root, SPEC))))


def build_design_inventory(root: Path = REPO_ROOT) -> dict:
    schematics = _glob(root, "design/*.sch")
    netlists = _glob(root, "design/netlist/*.spice")
    if not schematics:
        raise AuditError("design/*.sch: no schematics found")
    sch_cells = {Path(p).stem for p in schematics}
    net_cells = {Path(p).stem for p in netlists}
    if sch_cells != net_cells:
        raise AuditError(
            "design/ schematics and design/netlist/ netlists disagree: "
            f"schematic only {sorted(sch_cells - net_cells)}, "
            f"netlist only {sorted(net_cells - sch_cells)}"
        )
    gate = "python3 design/netlist.py --check"
    if '"--check"' not in _read(root, "design/netlist.py"):
        raise AuditError("design/netlist.py has no --check mode; the gate named is not real")
    if gate not in _read(root, CI_WORKFLOW):
        raise AuditError(f"{CI_WORKFLOW} does not run {gate!r}")
    return {
        "inventory": "design-sources",
        "t1_item": 1,
        "regeneration_gate": {
            "command": gate,
            "runs_in": f"{CI_WORKFLOW} (pdk-checks; needs xschem + the PDK, so "
            "it is not re-run by signoff/check.py)",
        },
        "schematics": _members(root, schematics),
        "netlists": _members(root, netlists),
    }


def _ci_pdk_pin(root: Path) -> str:
    match = re.search(r"volare enable --pdk gf180mcu ([0-9a-f]{40})", _read(root, CI_WORKFLOW))
    if not match:
        raise AuditError(f"{CI_WORKFLOW}: no `volare enable --pdk gf180mcu <commit>` pin")
    return match.group(1)


def _experiment_pvt(root: Path, slug: str) -> dict:
    path = root / "sim" / slug / "testbench" / "tb.json"
    if not path.is_file():
        return {}
    try:
        tb = json.loads(path.read_text())
    except ValueError as exc:
        raise AuditError(f"{path.relative_to(root)}: not valid JSON ({exc})") from exc
    return {
        key: tb[key]
        for key in ("corners", "temperatures_c", "nominal_supply_v", "supply_tolerance")
        if key in tb
    }


def build_testbench_inventory(root: Path = REPO_ROOT) -> dict:
    experiments: dict[str, dict] = {}
    without: dict[str, str] = {}
    for sim_dir in sorted(p for p in (root / "sim").iterdir() if p.is_dir()):
        slug = sim_dir.name
        if slug.startswith((".", "__")):
            continue
        tb_dirs = [d for d in ("testbench", "testbench-postlayout") if (sim_dir / d).is_dir()]
        files = [
            f"sim/{slug}/{d}/{f.relative_to(sim_dir / d).as_posix()}"
            for d in tb_dirs
            for f in (sim_dir / d).rglob("*")
            if f.is_file() and "__pycache__" not in f.parts
        ]
        if not files:
            if slug not in NO_TESTBENCH_DIRS:
                raise AuditError(
                    f"sim/{slug}/ ships no testbench*/ files and is not classified in "
                    "NO_TESTBENCH_DIRS"
                )
            without[slug] = NO_TESTBENCH_DIRS[slug]
            continue
        experiments[slug] = {
            "testbench_dirs": tb_dirs,
            "pvt": _experiment_pvt(root, slug),
            "files": _members(root, files),
        }

    spec_rows, classified = set(spec_row_ids(root)), set(ROW_BASIS)
    if spec_rows != classified:
        raise AuditError(
            f"{SPEC} rows and ROW_BASIS disagree: spec only {sorted(spec_rows - classified)}, "
            f"classified only {sorted(classified - spec_rows)}"
        )
    rows: dict[str, dict] = {}
    for row_id in sorted(ROW_BASIS):
        basis = dict(ROW_BASIS[row_id])
        for slug in basis.get("experiments", []):
            if slug not in experiments:
                raise AuditError(
                    f"spec row {row_id!r} claims a measurement from sim/{slug}/, which "
                    "ships no committed testbench"
                )
        evidence_file = basis.get("evidence_file")
        if evidence_file and not (root / evidence_file).is_file():
            raise AuditError(f"spec row {row_id!r}: {evidence_file} is missing")
        derivation = basis.get("derivation")
        if derivation and not (root / derivation).is_file():
            raise AuditError(f"spec row {row_id!r}: {derivation} is missing")
        rows[row_id] = basis

    cold_start = []
    for command, source in COLD_START:
        needle = command
        for placeholder, value in _COLD_START_NEEDLE.items():
            needle = needle.replace(placeholder, value)
        if needle not in _read(root, source):
            raise AuditError(f"{source} does not document {needle!r}")
        cold_start.append({"command": command, "documented_in": source})

    try:
        variant = json.loads(_read(root, "sim/pdk.json"))["variant"]
    except (ValueError, KeyError) as exc:
        raise AuditError(f"sim/pdk.json: no readable variant ({exc})") from exc
    return {
        "inventory": "testbenches",
        "t1_item": 9,
        "pdk": {
            "variant": variant,
            "variant_file": _member(root, "sim/pdk.json"),
            "volare_pdk": "gf180mcu",
            "volare_commit": _ci_pdk_pin(root),
            "pinned_in": CI_WORKFLOW,
        },
        "pvt_grid": f"{SPEC}#corner-grid",
        "cold_start": cold_start,
        "cold_start_docs": [_member(root, HARNESS_README)],
        "rows": rows,
        "experiments": experiments,
        "dirs_without_testbench": without,
    }


def build_hygiene_inventory(root: Path = REPO_ROOT) -> dict:
    license_text = _read(root, "LICENSE")
    if "Apache License" not in license_text:
        raise AuditError("LICENSE: not the Apache-2.0 text CLAUDE.md declares")
    readme = _read(root, "README.md")
    for needle in ("## What this is", "spec/target-spec.md", "## Simulation", "## License"):
        if needle not in readme:
            raise AuditError(f"README.md: no {needle!r} (what the block is / spec / how to reproduce / license)")
    if not spec_row_ids(root):
        raise AuditError(f"{SPEC}: no anchored spec rows")
    if "signoff/check.py" not in _read(root, CI_WORKFLOW):
        raise AuditError(f"{CI_WORKFLOW}: does not run signoff/check.py")
    return {
        "inventory": "repo-hygiene",
        "t1_item": 10,
        "assertions": [
            "LICENSE contains the Apache License text",
            "README.md states what the block is, links the spec, documents how to reproduce "
            "results (## Simulation) and has a License section",
            f"{SPEC} carries anchored spec rows",
            f"{CI_WORKFLOW} runs signoff/check.py",
        ],
        "files": _members(root, HYGIENE_FILES),
    }


INVENTORY_BUILDERS = {
    1: build_design_inventory,
    9: build_testbench_inventory,
    10: build_hygiene_inventory,
}


def build_envelope(root: Path, item: int) -> dict:
    """The generic envelope for `item`, derived from the bound artifact on disk."""
    artifact = ITEM_ARTIFACTS[item]
    if item == 2:
        cells = _glob(root, "layout/cells/*.gds")
        if GDS_TOP not in cells:
            raise AuditError(f"{GDS_TOP} is missing")
        if "--check" not in _read(root, "layout/build_cells.py"):
            raise AuditError("layout/build_cells.py has no --check mode")
        summary = (
            f"Layout for gf180-temp-por: the assembled top cell {GDS_TOP} (bound by hash; "
            "the same hash T1 items 3, 4 and 11 pin) plus the other cell layouts "
            + ", ".join(c for c in cells if c != GDS_TOP)
            + ". Reproducibility gate: python3 layout/build_cells.py --check. This asserts "
            "the layout artifact exists and is the one the DRC, LVS and supply-ERC reports "
            "describe; it does not assert that the layout meets the area budget."
        )
    else:
        inventory = json.loads(_read(root, artifact))
        if item == 1:
            what = (
                f"{len(inventory['schematics'])} xschem schematics and "
                f"{len(inventory['netlists'])} derived netlists, regeneration gate "
                f"{inventory['regeneration_gate']['command']!r}"
            )
        elif item == 9:
            what = (
                f"the committed testbench files of {len(inventory['experiments'])} sim/ "
                f"experiments mapped to all {len(inventory['rows'])} spec rows, the "
                "cold-start invocation and the pinned PDK revision"
            )
        else:
            what = ", ".join(m["path"] for m in inventory["files"]) + " with the stated assertions"
        summary = (
            f"Audited inventory for T1 item {item} ({ITEM_TITLES[item]}): {what}. Every "
            "member file is listed with its sha256 and signoff/check.py re-derives the "
            "inventory from the live tree, so the bound hash proves the inventory is current "
            "and the member hashes prove the files it describes are. It does not run a "
            "simulation or re-derive any measured value."
        )
    return {
        "schema_version": 1,
        "kind": "generic",
        "t1_item": item,
        "status": "pass",
        "summary": summary,
        "source": artifact,
        "provenance": {
            "klt_version": None,
            "klayout_version": None,
            "pdk": None,
            "deck": None,
            "input": {
                "path": {"path": artifact, "scope": "repo"},
                "content_hash": sha256_file(root / artifact),
            },
        },
    }


def write_all(root: Path = REPO_ROOT) -> dict[int, str]:
    """Rebuild every inventory and envelope; returns {item: pinned content_hash}."""
    # Build everything before writing anything, so a failed audit leaves the
    # previous (honest) files untouched.
    inventories = {item: builder(root) for item, builder in INVENTORY_BUILDERS.items()}
    build_envelope(root, 2)
    for item, inventory in inventories.items():
        (root / ITEM_ARTIFACTS[item]).write_text(dump_json(inventory))
    pins = {}
    for item in ITEM_ENVELOPES:
        envelope = build_envelope(root, item)
        (root / ITEM_ENVELOPES[item]).write_text(dump_json(envelope))
        pins[item] = envelope["provenance"]["input"]["content_hash"]
    return pins


def _member_map(node, prefix: str = "") -> tuple[dict[str, str], object]:
    """Flatten {path,sha256} members to {section/path: hash}; return the rest."""
    members: dict[str, str] = {}

    def walk(value, where: str):
        if isinstance(value, dict):
            if set(value) == {"path", "sha256"}:
                members[f"{where}:{value['path']}"] = value["sha256"]
                return "<member>"
            return {k: walk(v, f"{where}/{k}") for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, where) for v in value]
        return value

    return members, walk(node, prefix)


def diff_inventory(committed: dict, rebuilt: dict) -> list[str]:
    old, old_rest = _member_map(committed)
    new, new_rest = _member_map(rebuilt)
    problems = []
    for key in sorted(old.keys() | new.keys()):
        where, _, path = key.partition(":")
        if key not in new:
            problems.append(f"{path}: listed in the inventory but no longer in the tree")
        elif key not in old:
            problems.append(f"{path}: in the tree but absent from the inventory")
        elif old[key] != new[key]:
            problems.append(f"{path}: changed since it was inventoried")
    if not problems and old_rest != new_rest:
        problems.append("inventory metadata (rows, pvt, pdk, commands) differs from the tree")
    return problems


def verify_item(root: Path, item: int, manifest: dict) -> list[str]:
    """Every reason item `item`'s citation no longer describes the tree."""
    problems: list[str] = []
    entry = (manifest.get("evidence") or {}).get(str(item))
    if not isinstance(entry, dict) or not entry.get("file") or not entry.get("content_hash"):
        return [f"manifest item {item}: needs one {{file, content_hash}} citation"]
    envelope_rel = ITEM_ENVELOPES[item]
    if entry["file"] != envelope_rel:
        problems.append(f"manifest item {item}: cites {entry['file']!r}, expected {envelope_rel!r}")
    try:
        committed_env = json.loads(_read(root, entry["file"]))
    except (AuditError, ValueError) as exc:
        return problems + [f"{entry['file']}: unreadable ({exc})"]

    artifact = ITEM_ARTIFACTS[item]
    if not (root / artifact).is_file():
        return problems + [f"{artifact}: bound artifact is missing"]
    actual = sha256_file(root / artifact)
    if entry["content_hash"] != actual:
        problems.append(
            f"manifest item {item}: pins {entry['content_hash']} but {artifact} hashes to {actual}"
        )
    if committed_env.get("kind") != "generic":
        problems.append(f"{entry['file']}: kind must be 'generic' (no native envelope backs item {item})")
    if committed_env.get("t1_item") != item or isinstance(committed_env.get("t1_item"), bool):
        problems.append(f"{entry['file']}: t1_item is {committed_env.get('t1_item')!r}, expected {item}")
    prov_input = (committed_env.get("provenance") or {}).get("input") or {}
    if committed_env.get("source") != artifact or prov_input.get("path") != {
        "path": artifact,
        "scope": "repo",
    }:
        problems.append(
            f"{entry['file']}: `source` and provenance.input.path must both name {artifact} "
            "(repo scope), so the grader and check.py read the same artifact"
        )
    if prov_input.get("content_hash") != actual:
        problems.append(f"{entry['file']}: provenance.input.content_hash is stale vs {artifact}")

    builder = INVENTORY_BUILDERS.get(item)
    try:
        if builder is not None:
            rebuilt = builder(root)
            committed = json.loads(_read(root, artifact))
            problems += [f"{artifact}: {p}" for p in diff_inventory(committed, rebuilt)]
        expected_env = build_envelope(root, item)
    except (AuditError, ValueError) as exc:
        return problems + [f"item {item}: audit failed: {exc}"]
    if not problems and committed_env != expected_env:
        problems.append(
            f"{entry['file']}: differs from the envelope derived from the tree "
            "(summary or provenance edited by hand, or a layout cell was added/removed)"
        )
    return problems
