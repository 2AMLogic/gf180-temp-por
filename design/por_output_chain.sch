v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {por_output_chain -- deglitch, reset pulse, push-pull output stage} -300 -330 0 0 0.5 0.5 {}
T {Owner: issue #12 (POR output chain).
PLACEHOLDER: ports only, no internals yet -- see design/README.md.

Interface contract:
  VDD/VSS  3.3 V core-flavor supply pair (DR-001)
  IBIAS    bias-mirror node from bias_core; the nA-class charging
           current for the fixed >=1 ms pulse timer (DR-003)
  POR_RAW  raw threshold decision from por_comparator
  RESETn   active-low, push-pull reset output pad (DR-004)

This cell also owns the below-floor behaviour of DR-004: RESETn must be
actively held at a valid logic low for every VDD from 0 V up to the
comparator's own minimum operating voltage, by a mechanism that is not
gated by POR_RAW (which is undefined down there) -- i.e. the
startup-assist pull-down of DR-005 lives inside this cell, alongside
the deglitch filter and the pulse one-shot.} -300 -300 0 0 0.3 0.3 {}
N -300 -200 -240 -200 {lab=VDD}
N -300 -140 -240 -140 {lab=VSS}
N -300 -80 -240 -80 {lab=IBIAS}
N -300 -20 -240 -20 {lab=POR_RAW}
N 240 -200 300 -200 {lab=RESETn}
C {devices/iopin.sym} -300 -200 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -300 -140 0 1 {name=p_vss lab=VSS}
C {devices/ipin.sym} -300 -80 0 0 {name=p_ibias lab=IBIAS}
C {devices/ipin.sym} -300 -20 0 0 {name=p_por_raw lab=POR_RAW}
C {devices/opin.sym} 300 -200 0 0 {name=p_resetn lab=RESETn}
T {Placeholder termination: 1 Tohm to VSS on the output, so the stub is
ERC-clean and DC-solvable. Delete it when the real output stage lands --
note the real stage must actively hold RESETn low below the comparator
floor (DR-004), which a passive pull-down alone does not guarantee.} 400 60 0 0 0.3 0.3 {}
N 400 160 400 190 {lab=RESETn}
N 400 250 400 280 {lab=VSS}
C {devices/lab_pin.sym} 400 160 0 0 {name=l_ph_resetn sig_type=std_logic lab=RESETn}
C {devices/lab_pin.sym} 400 280 0 0 {name=l_ph_vss1 sig_type=std_logic lab=VSS}
C {devices/res.sym} 400 220 0 0 {name=Rplaceholder_resetn
value=1T
footprint=1206
device=resistor
m=1}
C {devices/code_shown.sym} -300 120 0 0 {name=STUB only_toplevel=false value="* PLACEHOLDER: por_output_chain has no internals yet -- they land with issue #12.
* The Rplaceholder_* devices in this cell are 1 Tohm terminations, not
* design content: they exist only so this stub is ERC-clean and DC-solvable.
* Nothing in this cell may be cited as simulation evidence."}
