# DR-028: Draw `temp_core`'s MiM cap `XCC` — both recorded reasons for leaving it out have expired, but the drawing is sequenced behind a klt deck migration

- **Status**: **in effect** — ratified by the operator's approval of the pull
  request that landed this record (per the 2026-08-19 standing policy for this
  repo's spec/DR ratification-via-PR), and **executed** on 2026-08-19: the
  sequencing precondition landed as #258 (published `klt 0.2.0` pin) and #264
  (the four already-drawn MiM cards routed onto their schematic nets), and
  [#259](https://github.com/2AMLogic/gf180-temp-por/issues/259) drew `XCC`
  itself. See "Execution" below.
- **Date**: 2026-08-19
- **Decided by**: Loom Builder, on the measurements in "Context" below, dispatched
  onto [#177](https://github.com/2AMLogic/gf180-temp-por/issues/177) — whose own
  acceptance criteria ask for exactly this decision.
- **Relates to**: #82 / PR #94 (the composite post-layout netlist this decision
  finally retires the last use for), #176 (that PR's parse failure), #180 (the
  direct-extraction post-layout netlist that ships the ideal splice this record
  aims to delete), `layout/README.md` → "One device stays out", klayout-tools
  #314 / #315.

## Context

`design/netlist/temp_core.spice:38` instantiates one MiM capacitor:

```
XCC PG NZ cap_mim_2f0_m3m4_noshield c_width=12u c_length=12u m=1
```

It is the **only** golden device anywhere in this block that the layout does not
draw. Every other non-MOS device — 19 vertical PNPs, 14 poly resistors, and four
golden MiM cards (seven drawn units: `bias_core`'s `XCC`/`XCOK`,
`por_output_chain`'s `XCDG` and `XCTIM`'s 2×2 array) — is drawn, extracted and
LVS-compared. The consequence is carried in every post-layout artifact:
`layout/postlayout/temp_core.spice` and `temp_por_top.spice` splice `XCC` in
**ideal**, so any recorded result that turns on the amplifier's compensation pole
is a schematic claim, not a post-layout one (see the netlist headers,
`layout/postlayout/AUDIT.md`, and the provenance line of
`sim/temp-core-designer-check/records/20260811-075055-b06af8e.md`).

`layout/README.md` and `layout/build_cells.py`'s `_temp_core_passives()` both
record **two independent blockers, either sufficient**, for that omission. Both
were re-measured on 2026-08-19 against `main` (`0a6a023d`) and the toolchain
installed on this host, and **neither survives**:

1. **"The deck models only the `m4m5` MiM flavour, the schematic names `m3m4`"**
   (klayout-tools#315). Still true — klt 0.2.0's `gf180mcu` deck declares exactly
   one `CapacitorDevice`, `cap_mim_2f0_m4m5_noshield`. But it is **not a
   differentiator**: `lvs_reference.CAP_CLASS` makes that exact substitution
   today for all four drawn golden MiM cards in `bias_core` and
   `por_output_chain`. Applying it to `XCC` accepts a class of fidelity loss this
   block has already accepted, in writing, twice.

2. **"A recognised MiM's plate regions sit outside the deck's connectivity
   stack, so a drawn `XCC` would compare as a capacitor floating between two
   anonymous nets"** (klayout-tools#314). **This is now false at the tool.**
   klayout-tools#314 is **closed**, and the installed klt 0.2.0 deck carries the
   fix directly in its `gf180mcu` `CapacitorDevice`:

   ```
   # Top-plate connectivity (issue #314): `main.drc`'s own
   # `top_via = via4` / `top_metal = metal5` confirms Via4 lands
   # directly on FuseTop and connects up to Metal5 for this 5LM stack
   top_plate_via=(41, 0),        # Via4
   top_plate_via_metal=(81, 0),  # Metal5
   ```

   A drawn MiM's top plate now reaches the routing graph through Via4/Metal5, so
   a *routed* MiM cap can be LVS'd against its real schematic nets. The stronger
   of the two recorded blockers — the one the README leans on when it says
   drawing `XCC` "says less than leaving it out and recording why" — no longer
   describes the tool.

So the premise the omission rests on has expired. Nothing about `XCC` is
special any more; it is a scope deferral from #93 that outlived its reason.

**A second measurement, made while verifying the first, constrains *when* it can
be executed.** The committed evidence under `layout/reports/` was produced by
`klt 0.1.0` against deck content hash
`sha256:be1a89e0…872b1d`. The only klt obtainable today is **0.2.0**, and klt's
own resolver reports that the committed deck **never shipped in a release**:

```
$ klt deck resolve --deck gf180mcu \
    --content-hash sha256:be1a89e0f899a68c60baeeedffe1b4d76b965bd763e1b16beed1c85937872b1d
no known release for deck 'gf180mcu' ships deck content hash '…' (not found in
known deck history, which covers v0.1.0..v0.2.0 -- the hash may predate the
table's start, be from an unreleased build, or never have shipped)
```

(PyPI's published `klayout-tools==0.1.0` is not a substitute: it self-reports
`klt 0.0.1` and has no `extract` or `lvs` subcommand at all.)

Re-running `bash layout/run_checks.sh` on **unmodified committed geometry** under
klt 0.2.0 therefore fails in three places, none of them caused by any layout edit:

| cell | result under klt 0.2.0 | cause |
| --- | --- | --- |
| `bias_core` | **LVS mismatch** (14: 4 `device.unmatched`, 8 `net.unmatched`) | its two MiM caps are drawn *connected to nothing*; with #314 fixed their plates are on the connectivity graph, so they no longer pair with the reference's synthesized isolated plate nets (`XCC.PG`, `XCC.NZ` — `lvs_reference.cap_plate_nets`) |
| `por_output_chain` | **DRC 11 ×** `metal1.enclosing.contact.1` | a rule klt 0.2.0 adds (0.005 µm, re-derived from the PDK's own `contact.drc` CO.6); the violations are 0.22 × 0.01 µm slivers on existing contact landings |
| `temp_por_top` | **DRC 11 ×** (the same, via its `por_output_chain` instance) | as above |

and `run_checks.sh`'s deck-hash gate rejects regenerating any *single* cell,
because that would leave `layout/reports/` split across two decks. There is
consequently **no way to produce consistent, committable evidence for a changed
`temp_core` today** without first migrating the whole repo's layout evidence onto
a published klt release.

## Decision

**Draw `temp_core`'s `XCC`.** Option 3 of #177 is adopted; options 1 and 2 are
recorded as moot (see "Alternatives considered"). Specifically:

1. `temp_core`'s manifest in `layout/lvs_reference.py` gains `"caps": ["XCC"]`,
   the same field `bias_core` and `por_output_chain` already carry.
2. `layout/build_cells.py` draws the 12 × 12 µm plate through the existing
   `_mim_block()` / `_mim_cap()` helpers and the existing `CAP_CLASS`
   `m3m4` → `m4m5` substitution. No new mechanism is invented for this cap.
3. Because klayout-tools#314 is fixed, the plate is **routed to its schematic
   nodes** (`PG`, `NZ`) through Via4/Metal5 rather than drawn floating, so LVS
   checks the cap's *connectivity* and not only its capacitance. The same
   applies to the four already-drawn golden MiM cards, which are floating today
   for a reason that no longer holds.
4. `layout/README.md`'s "One device stays out" passage is retired: it currently
   asserts, as settled fact, a tool limitation that has since been fixed.

**Sequencing (binding):** step 1–3 land *after* the layout evidence base is
migrated onto a published klt release. This is not a soft preference — the
migration is a precondition for producing any committable evidence at all, and
it also changes the correct implementation (it is what makes routed plates
checkable and what re-derives the MiM capacitance model, which klt 0.2.0 extends
with a perimeter/fringe term, `perim_cap_f_um=2.383e-16`, that
`lvs_reference.MIM_AREA_CAP_F_UM2`'s area-only model does not carry). Drawing
`XCC` against klt 0.1.0 semantics now would produce a floating cap that would
have to be redrawn immediately afterwards.

**This record therefore lands the decision and the documentation correction; the
geometry lands in the follow-up issues filed alongside it.** No claim is made
here that `XCC` is drawn — `layout/postlayout/AUDIT.md` and the netlist headers
continue to disclose it as ideal until it is, and remain correct.

## Execution

*Added 2026-08-19, when the decision above was carried out. Everything before
this section is the record as ratified and is left unedited.*

The binding sequencing held: #258 migrated the evidence base onto the published
`klt 0.2.0` release and pinned it in `layout/toolchain.json`; #264 routed the
four already-drawn golden MiM cards' plates onto their schematic nets through
the Via4/Metal5 stack (decision item 3, applied to them first); #259 then drew
`temp_core`'s `XCC` as the fifth card through that same pattern — decision
items 1, 2 and 4, plus item 3 for this cap: a 12 × 12 µm plate from
`_mim_block()`/`_mim_cap()`, bottom plate routed onto `PG` and top plate onto
`NZ`, not floating.

Measured on the result (`klt 0.2.0`, deck
`sha256:1256c45b…d14a3913`):

| claim | measured |
| --- | --- |
| `temp_core` DRC | clean, 0 violations |
| `temp_core` LVS | match — 115/115 devices, 73/73 nets, 30/30 pins; all three negative controls detected |
| `temp_por_top` DRC | clean, 0 violations |
| `temp_por_top` LVS | match — **239**/239 devices (was 238), 145/145 nets, 6/6 pins; all three negative controls detected |
| ideal devices | **none, in any cell** — `layout/postlayout/AUDIT.md`'s "ideal (not drawn)" column is 0 across the board and every netlist header reads "No ideal device: every golden device is drawn" |
| drawn area (`klt stats`) | `temp_core` 77 689.5 → 78 352.9 µm², `temp_por_top` 372 409.9 → 373 073.3 µm² — **+663.4 µm²**, not the ≈144 µm² this record predicted, because `klt stats`' total sums every drawn layer: the 12 × 12 µm plate is counted once each on `FuseTop`, `CAP_MK` and `MIM_L_MK` (3 × 144), the `Metal4` bottom plate adds 13.4² = 179.6, and the Via3/Via4/Metal2–Metal5 escape adds the rest |
| footprint | **unchanged** — `temp_por_top`'s bounding box is still 1334 × 794 µm (1.059 mm²) and `temp_core`'s still 569.25 × 211.355 µm; the plate sits inside both. `spec/target-spec.md#area` re-stamped from `klt stats` accordingly (its parenthetical drawn-polygon figure moves 0.372 → 0.373 mm²) |

What this record predicted and did **not** get is worth stating too: the
`m3m4` → `m4m5` substitution stays (klayout-tools#315 is closed without the
`m3m4` variant being modelled), and re-running the campaigns whose provenance
lines say a compensation-pole claim "is a schematic claim, not a post-layout
one" is deliberately **not** part of #259 — those records stay valid for the
netlists they name, per this repo's append-only convention, and re-recording
them is separate work, filed as
[#270](https://github.com/2AMLogic/gf180-temp-por/issues/270).

## Alternatives considered

- **Option 1 of #177 — re-scope #82 to "extract + splice only `XCC`"** — moot.
  #180 (merged 2026-08-11) already builds a post-layout netlist per cell by
  direct extraction, commits the parasitic artifacts, and splices `XCC` in ideal
  with the caveat disclosed in three places. There is nothing left of option 1
  to do.
- **Option 2 of #177 — keep `composite_netlist.py` and pay for a
  net-correspondence solver redesign** — moot, and the file no longer exists on
  `main`. klayout-tools#311 closed; `klt lvs` reports `net_correspondence`
  directly for every net of all five cells, so #180 reads the tool's answer and
  there is no solver to redesign. PR #94 was closed by the operator on
  2026-08-11.
- **Leave `XCC` undrawn permanently and re-word the README to say so** —
  rejected. It would freeze a "the deck can't do this" justification that the
  deck demonstrably can now do, in a repository whose stated product is its
  verification evidence. The honest end state for a block that draws 100 % of its
  golden devices minus one is to draw the one.
- **Draw `XCC` in this same change** — rejected on evidence, not on effort: with
  only klt 0.2.0 available and the committed deck unreleased, no consistent
  `layout/reports/` state exists that a changed `temp_core` could be committed
  against, and `run_checks.sh` fails on unmodified geometry before the edit is
  even made.
- **Migrate the whole evidence base to klt 0.2.0 inside this change** — rejected
  as scope. It requires fixing 11 DRC violations in a proven cell, adding a
  Metal4/Via4/Metal5 routing path to four already-drawn caps in a block whose
  signal routing is deliberately Metal1-only, re-deriving the MiM capacitance
  model with a fringe term, and regenerating every cell's reports, every
  post-layout netlist and every `testbench-postlayout/` fragment. That is its own
  body of work, filed separately.

## Consequences

**Good.**

- Once executed, `temp_core` and `temp_por_top` carry **zero** ideal devices, and
  `layout/postlayout/AUDIT.md` reports "No ideal device: every golden device is
  drawn." `postlayout.undrawn_capacitors()` is manifest-derived, so that change
  is automatic once the manifest gains `"XCC"`.
- Every existing recorded result whose provenance line says a claim resting on
  the compensation pole "is a schematic claim, not a post-layout one" can be
  re-run and re-recorded as a genuine post-layout claim.
- Routing the plates converts the block's MiM caps from "capacitance proven,
  connectivity unproven" to fully compared devices — a strictly larger fraction
  of the drawn block under check.

**Bad, and stated plainly.**

- The block's layout evidence is currently **not reproducible** by anyone who
  installs klt from PyPI. That was true before this record and is unchanged by
  it; this record is the first place it is written down.
- The `m3m4` → `m4m5` substitution stays. `XCC` will be drawn on a metal stack the
  schematic does not name, exactly as the four existing MiM cards already are.
  klayout-tools#315 is closed without the `m3m4` variant being modelled, so this
  is now a permanent, recorded property of this block's layout, not a temporary
  one.
- Executing the decision invalidates and re-runs a large amount of committed
  evidence: `layout/reports/*` for every cell, `layout/postlayout/*`, and every
  `sim/*/testbench-postlayout/` fragment that inlines `temp_core` or
  `temp_por_top` (11 experiments). Per this repo's append-only convention those
  are new records, not edits to old ones — the existing records stay valid for
  the geometry and toolchain they name.
- `temp_core`'s drawn area grows by the plate and its 0.7 µm enclosure
  (≈ 144 µm² of plate, against 77 690 µm² of drawn area today), and `klt stats`
  re-stamps `spec/target-spec.md#area`. The change is a rounding error at block
  level, but it is a change, and it is in the direction of the area row being
  *more* honest: nothing is reserved for `XCC` in the stream today — the
  `RESERVED` layer `build_cells.py` defines is used by no cell — so the recorded
  area currently understates the cell by that plate.
- Until the follow-ups land, `layout/README.md` describes a device that is
  decided-but-not-drawn. That state is disclosed in the README text this record
  lands, so no artifact overstates what the layout proves.
