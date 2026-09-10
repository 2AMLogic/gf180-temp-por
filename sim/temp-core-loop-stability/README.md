# temp-core-loop-stability

Small-signal `.ac` loop-gain testbench for `temp_core`'s error amplifier
loop (issue #274): unity-gain crossover, phase margin at that crossover, and
gain margin at the frequency the loop phase crosses zero. See
[`../../design/temp_core.md`](../../design/temp_core.md) → "Error amplifier"
for the topology this loop implements, and → "Loop stability" for the full
account of what each record here establishes.

## Break construction

The amplifier's own output node `PG` drives a cascoded PMOS mirror. Two of
that mirror's legs (the schematic's `XMP1`/`XMP2`) actually close the loop
back into the amplifier's own inputs (`NA`/`NB`); a third leg (`XMP3`) is a
dead-end replica that only reads `PG` out to the `PTAT` pad and does not feed
back. Both fragments below break the loop the same way:

- `PG` stays exactly as the source netlist has it — the amplifier's own
  output (`XMS2N`/`XMS2P` drains), the Miller compensation network
  (`XCC`/`XRZ`), the startup devices that terminate on that node, and
  (deliberately) `XMP3`'s gate, since it does not feed back and moving it
  would redistribute loading the real chip does not redistribute.
- A new port `PG_FB` carries only the two connections that close the loop —
  `XMP1`/`XMP2`'s gates. The testbench injects an AC test signal onto it and
  bridges it to `PG` with a `DC 0 / AC 1` voltage source, so the closed-loop
  DC operating point is unchanged (`dc_bias_delta_mv` in every record's
  `checks` is the self-test for that: it must read 0 at every corner) while
  the small-signal ratio `T(jw) = V(PG)/V(PG_FB)` is the closed-loop-equivalent
  open-loop gain around the whole loop, independent of the injection source's
  polarity or amplitude.

## Which fragment is which

| Directory | Netlist provenance | Source | Why hand-maintained |
| --- | --- | --- | --- |
| [`testbench/`](testbench/) | schematic | `design/netlist/temp_core.spice` | The break edits three lines *inside* the subcircuit body (rename + new port + two gate rewires). `sim/build_tb.py` only ever appends a cell **verbatim** after the stimulus, so it cannot produce this fragment — see the fragment's own header for the exact edits and provenance. |
| [`testbench-postlayout/`](testbench-postlayout/) | extracted | `layout/postlayout/temp_core.spice` | Same reason, applied to the extracted netlist (issue #298): in the layout, the schematic's `XMP1`/`XMP2`/`XMP3` are each split into two parallel unit devices (`X36`+`X47`, `X38`+`X45`, `X40`+`X43`); the first two pairs move to `PG_FB`, the third stays on `PG`. `PG`'s own extracted interconnect (`RPG`/`CPG`) stays on the `PG` side — that is where the amplifier's output metal physically is. |

Neither fragment is registered in `sim/build_tb.py`'s `FRAGMENTS` /
`POSTLAYOUT_FRAGMENTS` dicts, and `python3 sim/build_tb.py --check` does not
(and cannot) verify either one — both are deliberately outside that
mechanism. If the source netlist changes (a schematic edit re-exported, or a
new layout re-extracted), re-diff the affected fragment against its source
and re-apply the same edits by hand; each fragment's header documents
exactly what to do.

## Cold start

```bash
# schematic-level (design/netlist/temp_core.spice)
python3 sim/run_corners.py sim/temp-core-loop-stability/testbench

# post-layout / extracted (layout/postlayout/temp_core.spice)
python3 sim/run_corners.py sim/temp-core-loop-stability/testbench-postlayout \
    --supersedes <prior-schematic-or-extracted-record-id>
```

A post-layout re-run should also generate the schematic-vs-extracted delta
record (parasitic loading on the high-impedance loop nodes, plus a
per-measurement regression classification), computed from the two records'
raw logs rather than transcribed by hand:

```bash
python3 sim/postlayout_delta.py temp-core-loop-stability <extracted-record-id> \
    --against <schematic-record-id> --high-z PG,NZ,NA,NB --write
```

Records: [`records/`](records/). Raw per-corner logs: `corners/<record-id>/`.
Frozen netlist snapshots: `netlist-snapshots/<record-id>.spice`. See
[`../README.md`](../README.md) for the append-only and citation conventions
that apply to everything under this directory.
