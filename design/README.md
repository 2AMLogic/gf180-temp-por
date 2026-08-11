# design/ — xschem sources and netlist export

Schematic entry for the temperature-sensor + power-on-reset block, in xschem,
against the gf180mcu PDK. This directory is the **source of truth for the
block's electrical interface**: `sim/` testbenches and (later) `layout/` LVS
both consume the netlists exported from here.

> **Status: hierarchy and pinout are real; all four sub-circuits are designed.**
> The top level, the four sub-circuit cells, their symbols, and the netlist
> export pipeline are complete and verified. `temp_core` is **designed and
> characterized** (#9) — see [`temp_core.md`](temp_core.md) for its sizing
> rationale, error budget and Iq budget, and `sim/temp-core-designer-check/`
> + `sim/temp-core-startup/` for the PVT evidence behind them. `por_comparator`
> is **designed and characterized** (#10) — see
> [`por_comparator.md`](por_comparator.md) and
> `sim/por-comparator-designer-check/`. `por_output_chain` is **designed and
> characterized** (#12) — see [`por_output_chain.md`](por_output_chain.md) and
> `sim/por-output-chain-pulse/` + `sim/por-output-chain-deglitch/` +
> `sim/por-output-chain-floor/`. `bias_core` is **designed and characterized**
> (#11) — see [`bias_core.md`](bias_core.md), `sim/bias-core-designer-check/`,
> `sim/bias-core-ibias-sharing/` and `sim/bias-core-startup/`, and read that
> document's opening section first: it landed with three measured, owned
> conflicts (`por-iq` missed by 2.3×, a starved-loop window inside the
> ratified `por-ramp-rate` envelope, and a bias-vs-POR lockup on the shared
> `IBIAS` net) plus a fourth reported later by issue #43's branch-tracking
> sweep (`BIAS_OK` failing to assert, or asserting non-monotonically, on a
> quasi-static rising rail at all 27 corner/temperature combinations).
> **The `IBIAS` lockup is fixed** —
> [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)
> via #41, evidenced by `sim/temp-por-top-release/`. **The `BIAS_OK` report
> was not a defect in the cell** — issue #46 root-caused it to the reporting
> testbench's own `gmin = 1 nS` convergence aid, which injected **0.563 nA**
> of differential error into a settle comparator whose whole signal is
> **0.247 nA** (the one-variable control that measures both is committed and
> re-runnable at `sim/bias-core-startup/control/`); re-founded on a
> quasi-static *transient* ramp at ngspice's default `gmin`,
> `sim/bias-core-startup/` passes at all 81 points and no schematic change
> was needed. `por-iq` and the starved-loop window remain open pending their
> own re-cost record through #1. All four sub-circuits are designed; nothing
> in this hierarchy is a placeholder. See
> [Placeholder status](#placeholder-status).

## Top-level pinout (ratified)

`temp_por_top`, in netlist port order:

| Pin      | Dir   | Meaning                                              | Source |
| -------- | ----- | ---------------------------------------------------- | ------ |
| `VDD`    | inout | Supply, 3.3 V nominal ±10 % (2.97–3.63 V steady state) | [DR-001](../spec/decision-records/DR-001-supply-flavor.md) |
| `VSS`    | inout | Ground                                                | DR-001 |
| `PTAT`   | out   | Analog PTAT output                                    | [DR-002](../spec/decision-records/DR-002-temp-interface.md) |
| `CTAT`   | out   | Analog CTAT output                                    | DR-002 |
| `RESETn` | out   | Reset, **active low**, **push-pull**                  | [DR-004](../spec/decision-records/DR-004-reset-polarity-drive.md) |

Consequences of the ratified decisions that are visible as *absences* in this
pinout, and are therefore easy to erode by accident:

- **No trim/config/programming pins.** The reset pulse is fixed at ≥ 1 ms and
  programmability is de-scoped for wave 1
  ([DR-003](../spec/decision-records/DR-003-por-reset-pulse.md)); the 1-point
  temperature trim of DR-005 is an internal node, not a pad, in wave 1.
- **No digital temperature interface.** Wave 1 is analog-only — both pads, no
  SAR/ADC pairing (DR-002).
- **Devices are the 3.3 V core flavor** (`nfet_03v3` / `pfet_03v3`); no 5 V/6 V
  devices in the signal path (DR-001).

`python3 netlist.py --check` asserts this exact port list, so a schematic edit
that drifts from the ratified interface fails loudly instead of quietly
shipping. Changing the pinout means changing a decision record first.

## Hierarchy

One cell per design sub-issue, per
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md):

```
temp_por_top                     top level, the ratified pad interface
├── xbias  bias_core             shared bias / reference core     issue #11
├── xtemp  temp_core             PTAT/CTAT sensing core           issue #9
├── xcmp   por_comparator        threshold comparator + hysteresis issue #10
└── xpor   por_output_chain      deglitch, pulse, output stage    issue #12
```

Internal nets:

| Net       | Driver           | Consumers                        | Why |
| --------- | ---------------- | -------------------------------- | --- |
| `IBIAS`   | `bias_core`      | `temp_core`, `por_comparator`, `por_output_chain` | one shared bias core, amortizing Iq and area (DR-005). **Contract, per [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md): a consumer presents high impedance to this net whenever it is disabled** — it may gate its own fan-out off the node, never clamp it. The node's operating point is defined by `por_output_chain`'s always-on diode-connected `XMBD`, and at least one such always-on element must remain on the net. A disabled `temp_core` used to clamp it to `VSS`, which starved `por_comparator` in exactly the reset-asserted state POR has to work in and locked the block up; `sim/bias-core-ibias-sharing/` measured it and `sim/temp-por-top-release/` now witnesses its absence on the full assembly. **Sharing this net has a measured magnitude cost as well as the liveness contract**: `sim/por-output-chain-ibias-sharing/` (#221, [DR-024](../spec/decision-records/DR-024-por-output-chain-real-ibias-delivery.md)) meters each consumer leg individually and finds `por_output_chain` receives only 0.344×–1.155× the 0.5 µA convention with `RESETn` asserted and 0.182×–0.608× with it released — under the ≥0.44× its own deglitch ceiling needs, at 61 of 81 PVT points. Open, routed to #235 / #236. |
| `VREF`    | `bias_core`      | `por_comparator`                 | absolute reference; the threshold is a voltage, not a rail fraction |
| `BIAS_OK` | `bias_core`      | `por_comparator`                 | gates the authoritative release decision (DR-005 startup ordering, step 5) |
| `POR_RAW` | `por_comparator` | `por_output_chain`               | hysteresis is the comparator's job; deglitch/pulse/drive are the output chain's (DR-005 ownership split) |
| `RESETn`  | `por_output_chain` | top-level pad, `temp_core.EN`  | the sensor is enabled only after POR releases (DR-005 step 6), which keeps it out of the startup chicken-and-egg problem |

The assembly itself has a document too — [`temp_por_top.md`](temp_por_top.md).
It carries only what is true of the *loop between* the cells rather than of any
one of them, which today is the post-layout re-run of the full-assembly
testbench suite (#87).

Two DR-005 leaves are deliberately *not* separate cells: the shared core's
startup kick lives inside `bias_core`, and the POR startup-assist pull-down
lives inside `por_output_chain` — the cell DR-004 makes responsible for holding
`RESETn` low below the comparator's operating floor. Keeping the cell list 1:1
with the design issues is what lets each issue land as one schematic.

## Exporting the netlist

```bash
python3 design/netlist.py            # regenerate design/netlist/*.spice
python3 design/netlist.py --check    # verify committed netlists are current
python3 design/netlist.py --cell bias_core -v
```

Requirements: **`xschem` >= 3.4.7** on `PATH`, plus the gf180mcu PDK installed.
PDK discovery is delegated to `sim/harness/pdk.py` — the same resolver the
corner runner uses — so `python3 sim/run_corners.py --check-env` diagnoses a
missing PDK for both. No PDK path is ever baked into a netlist or into this
directory.

> **Why the version floor:** Ubuntu 24.04's apt package (xschem 3.4.4-1) has a
> `top_is_subckt` regression — it fails to wrap the top-of-invocation cell as
> an active `.subckt`, instead emitting a double-comment-prefixed
> `**.subckt`/`**.ends` pair, even though `design/xschemrc` sets
> `top_is_subckt 1`. Every cell hits this when netlisted on its own (each is
> the "top of invocation" for its own xschem run), which is exactly what
> `netlist.py` does per cell — so `--check` fails on an unaffected schematic
> with `.subckt <cell> not found in its own netlist` (issue #89). xschem 3.4.7
> does not have this defect and reproduces `design/netlist/*.spice`
> byte-for-byte; there is no known-good newer apt/PPA package as of this
> writing, so CI (`.github/workflows/ci.yml`'s `pdk-checks` job) builds 3.4.7
> from source rather than relying on the distro package. If your local
> `xschem --version` is older than 3.4.7, do the same: download a
> [3.4.7+ release tarball](https://github.com/StefanSchippers/xschem/releases),
> then `./configure && make && sudo make install`.

Under the hood, per cell:

```bash
xschem -x -q -n -s -r --rcfile design/xschemrc -o <outdir> design/<cell>.sch
```

`-x` batch (no X11), `-q` quit when done, `-n -s` netlist as SPICE, `-r` no
readline. `design/xschemrc` sets the library path (xschem devices → PDK symbols
→ `design/`) and, critically, `top_is_subckt 1`: **every** cell — including the
top — netlists as a `.subckt`, never as a flat simulation deck. Cells here are
blocks that testbenches instantiate; the deck belongs to the testbench.

`netlist.py` then rewrites the absolute paths xschem records in its `sch_path` /
`sym_path` comments to repo-relative form and prepends a provenance header. That
is what makes the export **deterministic**: the same sources produce
byte-identical netlists on any machine, so a netlist diff means a design change
and nothing else.

### What `--check` verifies

1. **Committed netlists are current** — regenerating into a temp directory
   reproduces `design/netlist/*.spice` byte-for-byte. This is simultaneously the
   staleness check and the reproducibility check.
2. **The top-level pinout matches the ratified interface** — exact port list and
   order (see the table above).
3. **Symbol pins match schematic ports**, per cell, in order. xschem takes the
   `.subckt` port list from the *symbol* when one exists, so a symbol that has
   drifted from its schematic silently drops or miswires a port on every
   instantiation. (xschem's own ERC catches the count mismatch and exits
   non-zero; this check also catches order/name drift.)
4. **Every sub-circuit is instantiated in the top level** with the right number
   of nets.

`--check` exits non-zero on any failure and prints the offending diff, so it is
usable as a pre-commit or CI gate once a runner exists.

## Using the netlists from a testbench

`design/netlist/` holds one file per cell:

- `temp_por_top.spice` — the whole hierarchy: `temp_por_top` plus every
  sub-circuit definition it instantiates. Include this to simulate the block.
- `bias_core.spice`, `temp_core.spice`, `por_comparator.spice`,
  `por_output_chain.spice` — a single `.subckt` each, so a testbench can target
  one sub-circuit on its own (#13/#14 need exactly this).

```spice
.include design/netlist/temp_por_top.spice
xdut VDD VSS PTAT CTAT RESETn temp_por_top
```

> **Include exactly one of these files per deck.** `temp_por_top.spice` already
> contains the sub-circuit definitions; including it *and* a sub-circuit file
> redefines the same `.subckt` twice.

Port order is positional in SPICE — take it from the `.subckt` line of the file
you include, or from the symbol pin list, which the check above keeps in sync.

## Working in the GUI

```bash
source sim/env.sh                                   # exports GF180_PDK_PATH etc.
xschem --rcfile design/xschemrc design/temp_por_top.sch
```

Conventions for the sub-circuit issues that fill these cells in:

- **PDK devices are referenced as `symbols/<device>.sym`** (e.g.
  `symbols/nfet_03v3.sym`, `symbols/pnp_10p00x10p00.sym`,
  `symbols/ppolyf_u_1k.sym`) — resolved against
  `$GF180_PDK_PATH/libs.tech/xschem`. Never write an absolute PDK path into a
  schematic.
- **Project cells are referenced by bare name** (`bias_core.sym`), resolved
  against `design/`.
- **Do not hand-edit `design/netlist/*.spice`.** Edit the schematic and re-run
  the export; `--check` will catch it if you forget.
- **Keep symbol pins and schematic ports in the same order.** When you add a
  port, add it to both the `.sch` and the `.sym`.
- Re-run `python3 design/netlist.py` and commit the regenerated netlists with
  the schematic change, so the netlist in the tree always matches the sources.

## Placeholder status

A placeholder cell contains only its ports, a comment block that reaches the
netlist, and 1 TΩ `Rplaceholder_*` terminations from each output to `VSS`. The
terminations exist so the stubs are ERC-clean and DC-solvable (the export
requires xschem to exit 0, and the hierarchy loads and solves in ngspice);
they are **not** design content.

| Cell               | Internals land with | Status | Also owns, per the decision records |
| ------------------ | ------------------- | ------ | ----------------------------------- |
| `bias_core`        | #11                 | **designed** — [`bias_core.md`](bias_core.md) | the shared core's own startup kick (DR-005 step 3) |
| `temp_core`        | #9                  | **designed** — [`temp_core.md`](temp_core.md) | the 1-point PTAT gain trim node (DR-005) |
| `por_comparator`   | #10                 | **designed** — [`por_comparator.md`](por_comparator.md) | hysteresis 100–250 mV; must state its own operating floor (DR-004) |
| `por_output_chain` | #12                 | **designed** — [`por_output_chain.md`](por_output_chain.md) | deglitch filter (4.58 µs worst-case dwell), fixed ≥ 1 ms one-shot (DR-003), push-pull driver, and the below-floor pull-down that holds `RESETn` low from 0 V (DR-004) |

> All four sub-circuits are designed, and since #41 / DR-010 `temp_por_top`
> **has** its own full-assembly corner record:
> [`sim/temp-por-top-release/`](../sim/temp-por-top-release/). It exists
> because the shared-`IBIAS` lockup `bias_core.md` documents could not be
> caught by any single-cell testbench — a two-cell integration testbench found
> it, and only the full four-cell loop can witness that it is gone, since the
> defect *was* the loop. That record is liveness and startup ordering only;
> the ramp-rate / brownout envelope on the assembled block is still #14's.
> Each designed cell's evidence is additionally recorded against its own
> `design/netlist/<cell>.spice` — the single-`.subckt` export — which is
> exactly why that per-cell export exists.

When a sub-circuit lands: delete that cell's `Rplaceholder_*` devices and the
placeholder comment block, draw the internals, keep the port list unchanged
unless a decision record changes with it, re-run `python3 design/netlist.py`,
and commit the netlists alongside the schematic.
