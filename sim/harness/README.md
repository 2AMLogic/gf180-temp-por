# sim/harness — the PVT corner runner

Reproducible ngspice simulation against the gf180mcu PDK. This document covers
**how to run** the harness and **how to write a testbench**.

The *output* of a run — directory layout, record-id format, the summary record
field set, and the append-only rule — is defined by
[`sim/README.md`](../README.md), not here. That convention is authoritative;
this harness exists to produce records that conform to it.

Ported from the `2AMLogic/gf180-bandgap` sister repo (their issue #2 / PR #23)
per CLAUDE.md's harness-bootstrap rule. Deliberate divergences are recorded in
[`spec/decision-records/DR-006-sim-harness-port.md`](../../spec/decision-records/DR-006-sim-harness-port.md)
— the notable one being that **`full` is this repo's default corner set**,
not `mos`.

```
sim/
  run_corners.py            CLI entry point (stdlib python3, no venv)
  run_mc.py                 Monte Carlo mismatch entry point (see "Monte Carlo" below)
  env.sh                    `source sim/env.sh` to export the same PDK to your shell
  selftest.sh               harness acceptance test (unit tests + end-to-end PVT run)
  pdk.json                  committed PDK defaults (variant, extra search roots)
  harness/                  the runner itself (this directory)
  tests/                    harness unit tests (no PDK, no ngspice required)
  .work/                    generated ngspice decks (git-ignored, disposable)

  <experiment-slug>/        one per claim under test -- see sim/README.md
    testbench/              tb.json + netlist fragment      <- you write these
    netlist-snapshots/      frozen netlist per record       <- the harness writes these
    corners/<record-id>/    raw <corner-id>.log per PVT point
    records/<record-id>.md  append-only summary record
```

## Quick start

```bash
python3 sim/run_corners.py --check-env     # is ngspice + the PDK present?
python3 sim/run_corners.py --list          # experiments, corners, corner sets
python3 sim/run_corners.py smoke-bias      # run the full PVT grid, mint a record
bash sim/selftest.sh                       # prove the harness works (writes nothing)

python3 sim/run_mc.py --list               # Monte Carlo experiments + binding points
python3 sim/run_mc.py temp-accuracy-mc     # N samples per binding point, mint a record
```

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| `ngspice` | simulation | `brew install ngspice` / `apt-get install ngspice` |
| gf180mcu PDK | device models | `pip install volare && volare enable --pdk gf180mcu <hash>` |
| `xschem` | schematic capture (optional for simulation) | `brew install xschem` / distro package |
| python3 ≥ 3.9 | the harness | stdlib only, no packages |

The harness never hardcodes a PDK path. It resolves one, in order:

1. `GF180_PDK_PATH` — the *variant* directory, e.g. `~/.volare/gf180mcuD`
   (the one containing `libs.tech/`).
2. `PDK_ROOT` (+ `PDK`, default `gf180mcuD`) — the open_pdks / OpenLane convention.
3. `sim/pdk.local.json` — machine-local, git-ignored.
4. `sim/pdk.json` — committed defaults.
5. Built-in search roots: `~/.volare`, `~/.ciel`, `/usr/share/pdk`,
   `/usr/local/share/pdk`, `~/share/pdk`, `/opt/pdk`.

If nothing is found the runner exits 3 with install instructions rather than
producing a misleading result. `sim/run_corners.py --print-env` emits the
resolved paths as shell exports; `source sim/env.sh` applies them so that an
interactive ngspice or xschem session uses the identical PDK.

## The PVT grid

`CLAUDE.md` requires PVT corners on every recorded result. The defaults are
baked into `corners.py` and are what a testbench gets unless its manifest says
otherwise:

- **Temperature**: −40, 27, 125 °C (the README spec table's rated range)
- **Voltage**: nominal ±10 % — 3.3 V flavor per DR-001, so 2.97 / 3.3 / 3.63 V
- **Process**: see below

gf180mcu has no single global corner switch — each device family carries its
own `.lib` section in `sm141064.ngspice`, so a named corner here is a bundle of
six sections (MOS, resistor, BJT, diode, MOS cap, MIM cap):

| Corner | Meaning |
|---|---|
| `tt` | everything typical |
| `ff` / `ss` | every device family fast / slow |
| `fs` / `sf` | fast-N/slow-P and slow-N/fast-P, passives typical |
| `res_ff` / `res_ss` | resistor sheet rho skewed, rest typical |
| `bjt_ff` / `bjt_ss` | BJT skewed, rest typical |

Corner sets: `tt` (1), `mos` (5), `full` (9 — **the default in this repo**).
`full` × 3 temperatures × 3 supplies = 81 operating points, about half a
minute at `-j 8`.

`full` is the default here because both circuits in this block ride on
passives, not just on the MOS skew: the sensing core is a vertical-PNP
VBE/ΔVBE pair scaled by a resistor ratio (so `bjt_ff`/`bjt_ss` and
`res_ff`/`res_ss` move the answer directly), and the POR threshold is a
resistor-divided VDD tap compared against that same reference. A `mos`-only
sweep would look green while never touching the devices that set the spec.
`--corner-set mos` remains available for a quick MOS-only iteration, but a
recorded claim should use the default.

Each point becomes one `<corner-id>` — `<process>_<temp>c_<supply>v`, the
naming `sim/README.md` ratifies — and one raw log under
`corners/<record-id>/`.

Override any axis from the command line:

```bash
python3 sim/run_corners.py smoke-bias --corner-set mos -j 8
python3 sim/run_corners.py smoke-bias --corners tt res_ss --temps -40 125
python3 sim/run_corners.py smoke-bias --supply 5.0 --supply-tol 0.10   # 5 V flavor
```

**Subsets need a reason.** `sim/README.md` requires every record's *Corner
matrix run* field to be the full mandated matrix "unless the record states why
a subset was used". The runner enforces that: if the grid you asked for is
missing a mandated temperature, a mandated supply, or has fewer than three
process corners, it refuses to write a record unless you supply
`--subset-reason '<why>'` (which is copied verbatim into the record), or pass
`--no-write` because you are only debugging.

```bash
# debugging: runs, records nothing
python3 sim/run_corners.py smoke-bias --corners tt --temps 27 --supply-tol 0 --no-write

# a deliberate, justified subset: runs and records, with the reason on the record
python3 sim/run_corners.py smoke-bias --corners tt --temps 27 \
    --subset-reason "nominal-only mismatch sweep; distribution claim, see Statistical convention"
```

## Writing a testbench

Create `sim/<experiment-slug>/testbench/` with a manifest and a netlist
fragment. The slug is the experiment directory from `sim/README.md`: one per
distinct claim under test, kebab-case.

`tb.json`:

```json
{
  "name": "my-experiment",
  "description": "one line, shows up in --list and in the record",
  "claim": "spec/target-spec.md#temp-accuracy-untrimmed",
  "netlist": "my_tb.spice",
  "nominal_supply_v": 3.3,
  "supply_tolerance": 0.1,
  "temperatures_c": [-40, 27, 125],
  "corners": ["full"],
  "analyses": ["op"],
  "params": {"ibias": "5u"},
  "options": ["reltol=1e-5"],
  "measure": {"vptat": "v(vptat)", "iq_ua": "-i(vsup)*1e6"},
  "checks": {"iq_ua": {"max": 20.0}}
}
```

`claim` is the default for the record's **Claim** field — the ratified spec
line this experiment substantiates. `--claim` overrides it per run.

`netlist_provenance` (optional, default `"schematic"`) and
`netlist_provenance_note` (required, non-empty, when `netlist_provenance` is
`"extracted"`) set the record's **Netlist provenance** field and its caveat —
see `sim/README.md`'s "Netlist provenance" for the convention and what the
note must say. A post-layout re-run of an existing testbench (issues #86,
#84) lives in a sibling `<experiment-slug>/testbench-postlayout/` directory
rather than editing `testbench/` in place — a `POSTLAYOUT_FRAGMENTS` entry in
`sim/build_tb.py` builds its fragment from `layout/postlayout/<cell>.spice`
(sharing the schematic sibling's `testbench/stimulus.spice`), and
`sim/run_corners.py sim/<slug>/testbench-postlayout` (a testbench *directory*
argument, not the bare slug, since `--list`/`discover()` only walk
`testbench/`) runs it.

The netlist is a **fragment**, not a complete deck. It must not contain
`.include`, `.lib`, `.temp`, `.control`, `.endc` or `.end` — the harness owns
all of those, which is what lets one netlist sweep the whole grid unedited.
The loader rejects fragments that break this rule instead of silently pinning
every corner to 27 °C. The harness hands the fragment:

| Parameter | Value |
|---|---|
| `vdd_val` | supply for this PVT point |
| `vdd_nom` | nominal supply, for ratio measurements |
| `temp_c` | temperature for this PVT point (also applied via `.temp`) |

Each `measure` entry becomes `let m_<name> = <expr>` followed by `print` inside
the control block, so the expression must reduce to a **scalar**: fine for
`op`; for `tran`/`ac` reduce with `maximum()`, `mean()`, `v(out)[0]`, etc.
POR work is inherently transient (ramp, brownout dip, reset pulse width), so
expect `"analyses": ["tran 10u 5m"]` plus reducing measure expressions there.

`checks` are evaluated after the sweep:

| Key | Applies to | Meaning |
|---|---|---|
| `min` / `max` | every point | hard limit; failure names the offending corner-id |
| `max_spread_pct` | the grid | `(max−min)/\|mean\|` must stay under the limit |
| `min_spread_pct` | the grid | must *exceed* it — asserts the sweep really moved |

`min_spread_pct` is a harness-integrity check: if `.temp` or a `.lib` section
silently failed to apply, a strongly PVT-sensitive measurement would come back
flat, and this catches that instead of reporting a suspiciously perfect result.
For a temperature sensor that check is doing real work — a PTAT output that
does not move with temperature is broken, not perfect.

## What a run writes

One run mints one `<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`) and
writes, under `sim/<experiment-slug>/`:

| Path | Contents |
|---|---|
| `records/<record-id>.md` | the append-only summary record (the nine fields from `sim/README.md`, plus an Environment section with PDK / ngspice / harness / git provenance and the per-corner model sections) |
| `netlist-snapshots/<record-id>.spice` | verbatim frozen copy of the testbench fragment, with its sha256 |
| `corners/<record-id>/<corner-id>.log` | raw ngspice output, one file per PVT point |

Nothing is ever overwritten: the runner refuses to write over an existing
record or snapshot, and mints a later record-id if one is somehow already
taken. Corrections and re-runs get a new record-id and reference the prior one
with `--supersedes <record-id>`. Do not edit or delete anything under
`records/`, `netlist-snapshots/` or `corners/` — see the append-only rule in
`sim/README.md`.

A run taken against a dirty working tree says so in the record's **Netlist
provenance** field and is not citable as a clean-tree result.

Exit codes: `0` pass · `1` a check failed · `2` a simulation failed or did not
converge · `3` environment problem (no ngspice, no PDK, bad manifest,
unjustified PVT subset).

Generated decks land in `sim/.work/<experiment-slug>/<record-id>/` and are
git-ignored, so a failing corner can be reproduced by hand with
`ngspice -b sim/.work/<slug>/<record-id>/<corner-id>.spice`.

## Monte Carlo mismatch (`sim/run_mc.py`)

Everything above sweeps a **deterministic** PVT grid with mismatch off
(`sw_stat_mismatch=0`, the default `design.ngspice` ships). That answers *how
far does the systematic/corner term move the answer*. `spec/target-spec.md` §2
additionally ratifies a **[3σ]** basis for the accuracy and threshold rows —
*process plus local mismatch, Monte Carlo, N ≥ 500, evaluated at the row's
binding corner* — which is a different question and gets a different entry
point:

```bash
python3 sim/run_mc.py --list                    # MC experiments + their binding points
python3 sim/run_mc.py temp-accuracy-mc -j 12    # N per binding point, mint a record
python3 sim/run_mc.py por-threshold-mc --n 20 --no-write   # fast deck iteration
```

| | `run_corners.py` | `run_mc.py` |
|---|---|---|
| grid | process × temperature × supply (81 points, `full`) | binding point × sample (N ≥ 500 each) |
| process | swept, mismatch off | **held** at each row's own named binding corner |
| mismatch | off | **on** (`sw_stat_mismatch=1`) + per-sample `.option seed=` |
| verdict | per-corner pass/fail | per-(binding point, measurement) distribution: mean, σ, empirical yield, parametric mean ± 3σ vs the ratified limits |
| record | `report.py` | `mc_report.py` — same nine `sim/README.md` fields, distribution-shaped Result |

`sw_stat_global` stays at `design.ngspice`'s default `0` on purpose: global
die-to-die spread is exactly what the deterministic corner sweep already
covers, so randomizing it too would double-count the same variation. The two
records compose — the corner sweep owns the process/temperature/rail axis, the
MC record adds the local-mismatch axis on top of it, at the same binding
points.

A testbench opts in by adding an `mc` block to its `tb.json`; `run_corners.py`
ignores the key entirely.

```json
"mc": {
  "n": 500,
  "seed_base": 20260802,
  "derive": "temp_trim",
  "binding_points": [
    {"label": "vth-rise-max", "corner": "ss", "temp_c": -40, "vdd": 3.63}
  ]
}
```

- **`binding_points`** — named, not a grid. Each entry is one row's own "binds
  at" text from `spec/target-spec.md` §4, resolved against the same `CORNERS`
  table `corners.py` defines. A row whose min and max edges bind at different
  corners contributes two entries.
- **`n`** — samples per binding point. A **recorded** run enforces the N ≥ 500
  floor §2 ratifies; `--no-write` lifts it so a deck can be iterated on
  quickly (the same split `run_corners.py --no-write` / `--subset-reason`
  uses).
- **`seed_base`** — seeds are `seed_base + binding_index*100000 + sample`, so
  the sample set is a pure function of the manifest and re-running reproduces
  it exactly.
- **`derive`** *(optional)* — a hook in `montecarlo.DERIVE_HOOKS` that adds
  per-sample computed quantities to each sample's measurements before
  summarization (e.g. `temp_trim`, which renormalizes each die against *its
  own* 25 °C reading to model a one-point production trim).
- `analyses` lines additionally accept Python `%(temp_c)g` / `%(vdd)g`
  placeholders, substituted before the line reaches ngspice — needed because
  ngspice's own `{expr}` substitution is netlist-elaboration-time and does not
  reach into `.control` commands like `dc temp <lo> <hi> <step>`.

One MC sample is one ngspice invocation with its own seed and its own log
under `corners/<record-id>/<label>_<corner>_<temp>c_<vdd>v_s<NNNN>.log`, so a
2000-sample distribution is reproducible from the repository rather than
transcribed into a summary table.

## smoke-bias

`sim/smoke-bias/` is the harness acceptance test, not a circuit deliverable and
not a spec claim. Three independent branches, each proving a different part of
the plumbing and each using a device family this block genuinely depends on:

1. an ideal resistor divider — must read exactly 0.5·vdd at all 81 points,
   proving parameter substitution and measurement parsing (and standing in for
   the POR threshold tap, which is a divider off VDD);
2. a PDK `ppolyf_u` resistor into a diode-connected `nfet_03v3` — proves the
   MOS and resistor `.lib` sections load and actually change between corners;
3. a diode-connected vertical `pnp_10p00x10p00` at 10 µA — V_EB is strongly
   CTAT (~ −2 mV/°C), so it proves `.temp` and the BJT corner take effect. This
   is the same device the sensing core's CTAT leg is built from (DR-005).

Run it end to end with `bash sim/selftest.sh` (no evidence written) or
`bash sim/selftest.sh --record` (mints a record under
`sim/smoke-bias/records/`).

## xschem

`source sim/env.sh` exports `PDK_ROOT`, `PDK`, `GF180_PDK_PATH`,
`GF180_MODELS` and an `XSCHEM_USER_LIBRARY_PATH` covering `design/` and every
`sim/<experiment-slug>/testbench/`, so an interactive xschem or ngspice
session resolves exactly the PDK the corner runner picked:

```bash
source sim/env.sh
cd design && xschem
```

Schematic entry (#8) owns `design/xschemrc` and the netlist-export flow; this
harness does not require xschem at all. To simulate a schematic, strip its
export to a fragment (or netlist a testbench schematic without its
`.control`/`.end` block) and point a `tb.json` at it — the corner runner is
agnostic about whether the fragment was typed or generated.

### `sim/build_tb.py` — inlining an exported cell into a fragment

A fragment may not `.include` anything, so simulating a `design/` cell means
inlining its `.subckt` export into the fragment. Doing that by hand lets the
evidence trail drift silently away from the schematic, so it is generated
instead:

```bash
python3 sim/build_tb.py           # regenerate every experiment's fragment
python3 sim/build_tb.py --check   # fail if any committed fragment is stale
```

Each participating experiment keeps a hand-written
`testbench/stimulus.spice` (sources, loads, probes) and a **generated**
`testbench/<name>.spice` = stimulus + a verbatim copy of one or more
`design/netlist/<cell>.spice`, with each source's sha256 in the header. Add an
experiment by adding a row to `FRAGMENTS` in `sim/build_tb.py`.

`build_tb.py --check` needs neither xschem nor the PDK, so it runs in the
headless CI job; `design/netlist.py --check` (which does need both) closes the
other half of the chain by proving the export reproduces from the `.sch`.
