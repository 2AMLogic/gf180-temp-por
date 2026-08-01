v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {bias_core -- shared bias / reference core (issue #11)} -1100 -1560 0 0 0.6 0.6 {}
T {Topology per DR-005 'Shared infrastructure': ONE shared bandgap-style bias/reference core for the\ntemperature sensor and the POR precision comparator, plus the dedicated startup kick that resolves the\ncore's own degenerate zero-current state (DR-005 startup ordering, step 3). The separate below-floor POR\npull-down is NOT here -- it lives in por_output_chain (#12).\n\nSizing, startup analysis and the Iq apportionment: design/bias_core.md.\nEvidence: sim/bias-core-designer-check/records/, sim/bias-core-startup/records/.\n\nInterface contract (unchanged from the #8 stub -- ports are fixed, only the internals land here):\n  VDD/VSS  3.3 V core-flavour supply pair (DR-001). NOTE: this cell has no EN pin, so every branch in it\n           is always-on and, under target-spec.md section 5 rule 1, is charged to por-iq.\n  IBIAS    shared bias-mirror node. Convention (from #9/#10): bias_core SOURCES the reference current INTO\n           this pin; each consumer puts a diode-connected nfet on it. MP4 is an 8:1 mirror leg, so\n           IBIAS ~ 8 * I(loop) ~ 0.5 uA at tt/27 C -- the value temp_core and por_comparator were each\n           characterised against. The node is SHARED by three consumers at the top level, so each sees\n           roughly a third of it; see design/bias_core.md, 'IBIAS fan-out'.\n  VREF     absolute bandgap-style reference, ~1.20 V. Consumed by por_comparator only, as a gate voltage --\n           no DC load, which is why MP3's leg can be a plain 60 nA mirror leg.\n  BIAS_OK  'shared core is up and settled' flag; the POR release decision is gated on it (DR-005 step 4).\n           Held LOW from 0 V of rail upward by XMOKZ/XMOKD -- driven low, not merely undriven.} -1100 -1500 0 0 0.3 0.3 {}
N -1300 -1000 -1240 -1000 {}
C {devices/iopin.sym} -1300 -1000 0 0 {name=p_vdd lab=VDD}
N -1300 -940 -1240 -940 {}
C {devices/iopin.sym} -1300 -940 0 0 {name=p_vss lab=VSS}
N -1300 -880 -1240 -880 {}
C {devices/opin.sym} -1300 -880 0 0 {name=p_ibias lab=IBIAS}
N -1300 -820 -1240 -820 {}
C {devices/opin.sym} -1300 -820 0 0 {name=p_vref lab=VREF}
N -1300 -760 -1240 -760 {}
C {devices/opin.sym} -1300 -760 0 0 {name=p_bias_ok lab=BIAS_OK}
T {CASCODE-FREE PMOS MIRROR  --  four legs off PG. MP1/MP2 are the 1:1 pair whose equal VGS *and* equal\nVDS (the amplifier forces V(NA)=V(NB), and both drains sit at the same VBE) make the ratio that defines\nDVBE exact by construction, so no cascode is needed for it. L=8u keeps leg 3 (drain at VREF ~1.2 V, i.e.\n0.64 V above legs 1/2) on ratio to ~1 % by Early voltage alone -- a deliberate trade of that 1 % against\nthe ~0.4 V of extra dropout a cascode stack would cost, because this cell has to be valid well below the\nPOR release threshold (DR-005 startup step 3).} -1100 -390 0 0 0.4 0.4 {}
N -980 -170 -980 -130 {}
C {devices/lab_pin.sym} -980 -130 0 0 {name=l1 lab=NA}
N -1020 -200 -1080 -200 {}
C {devices/lab_pin.sym} -1080 -200 0 0 {name=l2 lab=PG}
N -980 -230 -980 -270 {}
C {devices/lab_pin.sym} -980 -270 0 0 {name=l3 lab=VDD}
N -980 -200 -930 -200 {}
C {devices/lab_pin.sym} -930 -200 0 0 {name=l4 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 -200 0 0 {name=MP1
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 -170 -740 -130 {}
C {devices/lab_pin.sym} -740 -130 0 0 {name=l5 lab=NB}
N -780 -200 -840 -200 {}
C {devices/lab_pin.sym} -840 -200 0 0 {name=l6 lab=PG}
N -740 -230 -740 -270 {}
C {devices/lab_pin.sym} -740 -270 0 0 {name=l7 lab=VDD}
N -740 -200 -690 -200 {}
C {devices/lab_pin.sym} -690 -200 0 0 {name=l8 lab=VDD}
C {symbols/pfet_03v3.sym} -760 -200 0 0 {name=MP2
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 -170 -500 -130 {}
C {devices/lab_pin.sym} -500 -130 0 0 {name=l9 lab=VREF}
N -540 -200 -600 -200 {}
C {devices/lab_pin.sym} -600 -200 0 0 {name=l10 lab=PG}
N -500 -230 -500 -270 {}
C {devices/lab_pin.sym} -500 -270 0 0 {name=l11 lab=VDD}
N -500 -200 -450 -200 {}
C {devices/lab_pin.sym} -450 -200 0 0 {name=l12 lab=VDD}
C {symbols/pfet_03v3.sym} -520 -200 0 0 {name=MP3
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -260 -170 -260 -130 {}
C {devices/lab_pin.sym} -260 -130 0 0 {name=l13 lab=IBIAS}
N -300 -200 -360 -200 {}
C {devices/lab_pin.sym} -360 -200 0 0 {name=l14 lab=PG}
N -260 -230 -260 -270 {}
C {devices/lab_pin.sym} -260 -270 0 0 {name=l15 lab=VDD}
N -260 -200 -210 -200 {}
C {devices/lab_pin.sym} -210 -200 0 0 {name=l16 lab=VDD}
C {symbols/pfet_03v3.sym} -280 -200 0 0 {name=MP4
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 -170 -20 -130 {}
C {devices/lab_pin.sym} -20 -130 0 0 {name=l17 lab=NT}
N -60 -200 -120 -200 {}
C {devices/lab_pin.sym} -120 -200 0 0 {name=l18 lab=PG}
N -20 -230 -20 -270 {}
C {devices/lab_pin.sym} -20 -270 0 0 {name=l19 lab=VDD}
N -20 -200 30 -200 {}
C {devices/lab_pin.sym} 30 -200 0 0 {name=l20 lab=VDD}
C {symbols/pfet_03v3.sym} -40 -200 0 0 {name=MT
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 -170 220 -130 {}
C {devices/lab_pin.sym} 220 -130 0 0 {name=l21 lab=PG}
N 180 -200 120 -200 {}
C {devices/lab_pin.sym} 120 -200 0 0 {name=l22 lab=PB}
N 220 -230 220 -270 {}
C {devices/lab_pin.sym} 220 -270 0 0 {name=l23 lab=VDD}
N 220 -200 270 -200 {}
C {devices/lab_pin.sym} 270 -200 0 0 {name=l24 lab=VDD}
C {symbols/pfet_03v3.sym} 200 -200 0 0 {name=MS2P
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 460 -170 460 -130 {}
C {devices/lab_pin.sym} 460 -130 0 0 {name=l25 lab=PB}
N 420 -200 360 -200 {}
C {devices/lab_pin.sym} 360 -200 0 0 {name=l26 lab=PB}
N 460 -230 460 -270 {}
C {devices/lab_pin.sym} 460 -270 0 0 {name=l27 lab=VDD}
N 460 -200 510 -200 {}
C {devices/lab_pin.sym} 510 -200 0 0 {name=l28 lab=VDD}
C {symbols/pfet_03v3.sym} 440 -200 0 0 {name=MBP
L=8u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 700 -230 700 -270 {}
C {devices/lab_pin.sym} 700 -270 0 0 {name=l29 lab=PB}
N 660 -200 600 -200 {}
C {devices/lab_pin.sym} 600 -200 0 0 {name=l30 lab=N1}
N 700 -170 700 -130 {}
C {devices/lab_pin.sym} 700 -130 0 0 {name=l31 lab=VSS}
N 700 -200 750 -200 {}
C {devices/lab_pin.sym} 750 -200 0 0 {name=l32 lab=VSS}
C {symbols/nfet_03v3.sym} 680 -200 0 0 {name=MBN
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {SENSING CORE  --  8:1 vertical-PNP emitter-area ratio (pnp_10p00x10p00 unit cell, per sim/devchar/SUMMARY.md),\neight unit cells in parallel rather than one par=8 instance (par= scales only the model's mismatch term).\nXR1 turns DVBE into the branch current I = DVBE/R1 ~ 60 nA. XQR + XR3 is the matched output leg:\nV(VREF) = VBE(XQR) + (R3/R1)*DVBE, a first-order bandgap. R3/R1 is a same-flavour ppolyf_u_3k ratio, so the\n-1545 ppm/C sheet tempco and the +/-25 % sheet corner cancel in the ratio instead of multiplying through.} -1100 170 0 0 0.4 0.4 {}
N -980 390 -980 430 {}
C {devices/lab_pin.sym} -980 430 0 0 {name=l33 lab=VSS}
N -1020 360 -1080 360 {}
C {devices/lab_pin.sym} -1080 360 0 0 {name=l34 lab=VSS}
N -980 330 -980 290 {}
C {devices/lab_pin.sym} -980 290 0 0 {name=l35 lab=NA}
C {symbols/pnp_10p00x10p00.sym} -1000 360 0 0 {name=Q1
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -740 390 -740 430 {}
C {devices/lab_pin.sym} -740 430 0 0 {name=l36 lab=VSS}
N -780 360 -840 360 {}
C {devices/lab_pin.sym} -840 360 0 0 {name=l37 lab=VSS}
N -740 330 -740 290 {}
C {devices/lab_pin.sym} -740 290 0 0 {name=l38 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -760 360 0 0 {name=Q8A
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -500 390 -500 430 {}
C {devices/lab_pin.sym} -500 430 0 0 {name=l39 lab=VSS}
N -540 360 -600 360 {}
C {devices/lab_pin.sym} -600 360 0 0 {name=l40 lab=VSS}
N -500 330 -500 290 {}
C {devices/lab_pin.sym} -500 290 0 0 {name=l41 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -520 360 0 0 {name=Q8B
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -260 390 -260 430 {}
C {devices/lab_pin.sym} -260 430 0 0 {name=l42 lab=VSS}
N -300 360 -360 360 {}
C {devices/lab_pin.sym} -360 360 0 0 {name=l43 lab=VSS}
N -260 330 -260 290 {}
C {devices/lab_pin.sym} -260 290 0 0 {name=l44 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -280 360 0 0 {name=Q8C
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -20 390 -20 430 {}
C {devices/lab_pin.sym} -20 430 0 0 {name=l45 lab=VSS}
N -60 360 -120 360 {}
C {devices/lab_pin.sym} -120 360 0 0 {name=l46 lab=VSS}
N -20 330 -20 290 {}
C {devices/lab_pin.sym} -20 290 0 0 {name=l47 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -40 360 0 0 {name=Q8D
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 220 390 220 430 {}
C {devices/lab_pin.sym} 220 430 0 0 {name=l48 lab=VSS}
N 180 360 120 360 {}
C {devices/lab_pin.sym} 120 360 0 0 {name=l49 lab=VSS}
N 220 330 220 290 {}
C {devices/lab_pin.sym} 220 290 0 0 {name=l50 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 200 360 0 0 {name=Q8E
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 460 390 460 430 {}
C {devices/lab_pin.sym} 460 430 0 0 {name=l51 lab=VSS}
N 420 360 360 360 {}
C {devices/lab_pin.sym} 360 360 0 0 {name=l52 lab=VSS}
N 460 330 460 290 {}
C {devices/lab_pin.sym} 460 290 0 0 {name=l53 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 440 360 0 0 {name=Q8F
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 700 390 700 430 {}
C {devices/lab_pin.sym} 700 430 0 0 {name=l54 lab=VSS}
N 660 360 600 360 {}
C {devices/lab_pin.sym} 600 360 0 0 {name=l55 lab=VSS}
N 700 330 700 290 {}
C {devices/lab_pin.sym} 700 290 0 0 {name=l56 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 680 360 0 0 {name=Q8G
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 940 390 940 430 {}
C {devices/lab_pin.sym} 940 430 0 0 {name=l57 lab=VSS}
N 900 360 840 360 {}
C {devices/lab_pin.sym} 840 360 0 0 {name=l58 lab=VSS}
N 940 330 940 290 {}
C {devices/lab_pin.sym} 940 290 0 0 {name=l59 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 920 360 0 0 {name=Q8H
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 1180 390 1180 430 {}
C {devices/lab_pin.sym} 1180 430 0 0 {name=l60 lab=VSS}
N 1140 360 1080 360 {}
C {devices/lab_pin.sym} 1080 360 0 0 {name=l61 lab=VSS}
N 1180 330 1180 290 {}
C {devices/lab_pin.sym} 1180 290 0 0 {name=l62 lab=NRE}
C {symbols/pnp_10p00x10p00.sym} 1160 360 0 0 {name=QR
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 1400 390 1400 430 {}
C {devices/lab_pin.sym} 1400 430 0 0 {name=l63 lab=NB}
N 1400 330 1400 290 {}
C {devices/lab_pin.sym} 1400 290 0 0 {name=l64 lab=NC}
N 1380 360 1320 360 {}
C {devices/lab_pin.sym} 1320 360 0 0 {name=l65 lab=VSS}
C {symbols/ppolyf_u_3k.sym} 1400 360 0 0 {name=R1
W=1u
L=299u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -1000 690 -1000 730 {}
C {devices/lab_pin.sym} -1000 730 0 0 {name=l66 lab=VREF}
N -1000 630 -1000 590 {}
C {devices/lab_pin.sym} -1000 590 0 0 {name=l67 lab=NRE}
N -1020 660 -1080 660 {}
C {devices/lab_pin.sym} -1080 660 0 0 {name=l68 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -1000 660 0 0 {name=R3
W=1u
L=3580u
model=ppolyf_u_3k
spiceprefix=X
m=1}
T {ERROR AMPLIFIER  --  PMOS input pair (the inputs sit at a VBE, 0.34-0.70 V over the rated range, far below an\nNMOS pair's usable common-mode floor), NMOS mirror load, NMOS common-source second stage, Miller-compensated\nwith a nulling resistor. XMS2N is a current-density copy of XML1, so stage 1's output sits at the diode node's\nown VGS and the systematic input offset is structurally near zero (measured |V(NA)-V(NB)| <= 2 uV).\nXMBP/XMBN make the stage-2 PMOS bias PB: stage 2 cannot use PG as its own load gate, because its drain IS PG.} -1100 1030 0 0 0.4 0.4 {}
N -980 1250 -980 1290 {}
C {devices/lab_pin.sym} -980 1290 0 0 {name=l69 lab=N1}
N -1020 1220 -1080 1220 {}
C {devices/lab_pin.sym} -1080 1220 0 0 {name=l70 lab=NA}
N -980 1190 -980 1150 {}
C {devices/lab_pin.sym} -980 1150 0 0 {name=l71 lab=NT}
N -980 1220 -930 1220 {}
C {devices/lab_pin.sym} -930 1220 0 0 {name=l72 lab=NT}
C {symbols/pfet_03v3.sym} -1000 1220 0 0 {name=MI1
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 1250 -740 1290 {}
C {devices/lab_pin.sym} -740 1290 0 0 {name=l73 lab=N2}
N -780 1220 -840 1220 {}
C {devices/lab_pin.sym} -840 1220 0 0 {name=l74 lab=NB}
N -740 1190 -740 1150 {}
C {devices/lab_pin.sym} -740 1150 0 0 {name=l75 lab=NT}
N -740 1220 -690 1220 {}
C {devices/lab_pin.sym} -690 1220 0 0 {name=l76 lab=NT}
C {symbols/pfet_03v3.sym} -760 1220 0 0 {name=MI2
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 1190 -500 1150 {}
C {devices/lab_pin.sym} -500 1150 0 0 {name=l77 lab=N1}
N -540 1220 -600 1220 {}
C {devices/lab_pin.sym} -600 1220 0 0 {name=l78 lab=N1}
N -500 1250 -500 1290 {}
C {devices/lab_pin.sym} -500 1290 0 0 {name=l79 lab=VSS}
N -500 1220 -450 1220 {}
C {devices/lab_pin.sym} -450 1220 0 0 {name=l80 lab=VSS}
C {symbols/nfet_03v3.sym} -520 1220 0 0 {name=ML1
L=8u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 1190 -260 1150 {}
C {devices/lab_pin.sym} -260 1150 0 0 {name=l81 lab=N2}
N -300 1220 -360 1220 {}
C {devices/lab_pin.sym} -360 1220 0 0 {name=l82 lab=N1}
N -260 1250 -260 1290 {}
C {devices/lab_pin.sym} -260 1290 0 0 {name=l83 lab=VSS}
N -260 1220 -210 1220 {}
C {devices/lab_pin.sym} -210 1220 0 0 {name=l84 lab=VSS}
C {symbols/nfet_03v3.sym} -280 1220 0 0 {name=ML2
L=8u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 1190 -20 1150 {}
C {devices/lab_pin.sym} -20 1150 0 0 {name=l85 lab=PG}
N -60 1220 -120 1220 {}
C {devices/lab_pin.sym} -120 1220 0 0 {name=l86 lab=N2}
N -20 1250 -20 1290 {}
C {devices/lab_pin.sym} -20 1290 0 0 {name=l87 lab=VSS}
N -20 1220 30 1220 {}
C {devices/lab_pin.sym} 30 1220 0 0 {name=l88 lab=VSS}
C {symbols/nfet_03v3.sym} -40 1220 0 0 {name=MS2N
L=8u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 200 1190 200 1150 {}
C {devices/lab_pin.sym} 200 1150 0 0 {name=l89 lab=PG}
N 200 1250 200 1290 {}
C {devices/lab_pin.sym} 200 1290 0 0 {name=l90 lab=NZ}
C {symbols/cap_mim_analog.sym} 200 1220 0 0 {name=CC
W=45u
L=45u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=1}
N 440 1250 440 1290 {}
C {devices/lab_pin.sym} 440 1290 0 0 {name=l91 lab=NZ}
N 440 1190 440 1150 {}
C {devices/lab_pin.sym} 440 1150 0 0 {name=l92 lab=N2}
N 420 1220 360 1220 {}
C {devices/lab_pin.sym} 360 1220 0 0 {name=l93 lab=VSS}
C {symbols/ppolyf_u_3k.sym} 440 1220 0 0 {name=RZ
W=2u
L=366u
model=ppolyf_u_3k
spiceprefix=X
m=1}
T {STARTUP KICK  --  RAIL-TO-RAIL dead-loop detector (DR-005 startup step 3), not a level detector on a core node.
XMSU4 is a 1:1 replica of a mirror leg (same gate PG), so it sources the loop current when the loop is alive and
essentially nothing when it is dead. XMNAT is the opposing always-on weak pull-down: a native (zero-Vt)
nfet_06v0_nvt at Vgs = 0, source-degenerated by XRDEG so that its ~5-decade process spread (sim/devchar/SUMMARY.md
measures a ~440 mV native-Vt corner spread, and this cell is the consumer DR-005 named for it) is compressed at the
strong end to a few tens of nA. Its source sits at VSS, NOT at the sensed node, which is the point: a pull-UP
referenced to the sensed node loses its own drive to the body effect as that node rises, and an earlier revision
of this cell stalled at ss/-40 C for exactly that reason.
Because the replica always outruns the degenerated native when the loop is alive, NK is a genuine rail-to-rail
node: ~VDD alive, ~0 dead. The kick XMSU3 is therefore a PMOS in its own nwell, source on PG: dead (NK ~ 0) it
sees the full rail across gate-source and pulls PG down; alive (NK ~ VDD) its VGS is zero and it is off. Nothing
in the kick path depends on an nfet threshold being reached, which is what makes it work at the slow/cold corner.} -1100 1590 0 0 0.4 0.4 {}
N -980 1810 -980 1850 {}
C {devices/lab_pin.sym} -980 1850 0 0 {name=l94 lab=NK}
N -1020 1780 -1080 1780 {}
C {devices/lab_pin.sym} -1080 1780 0 0 {name=l95 lab=PG}
N -980 1750 -980 1710 {}
C {devices/lab_pin.sym} -980 1710 0 0 {name=l96 lab=VDD}
N -980 1780 -930 1780 {}
C {devices/lab_pin.sym} -930 1780 0 0 {name=l97 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 1780 0 0 {name=MSU4
L=8u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 1750 -740 1710 {}
C {devices/lab_pin.sym} -740 1710 0 0 {name=l98 lab=NK}
N -780 1780 -840 1780 {}
C {devices/lab_pin.sym} -840 1780 0 0 {name=l99 lab=VSS}
N -740 1810 -740 1850 {}
C {devices/lab_pin.sym} -740 1850 0 0 {name=l100 lab=NSD}
N -740 1780 -690 1780 {}
C {devices/lab_pin.sym} -690 1780 0 0 {name=l101 lab=VSS}
C {symbols/nfet_06v0_nvt.sym} -760 1780 0 0 {name=MNAT
L=50u
W=0.8u
nf=1
m=16
model=nfet_06v0_nvt
spiceprefix=X}
N -520 1810 -520 1850 {}
C {devices/lab_pin.sym} -520 1850 0 0 {name=l102 lab=NSD}
N -520 1750 -520 1710 {}
C {devices/lab_pin.sym} -520 1710 0 0 {name=l103 lab=VSS}
N -540 1780 -600 1780 {}
C {devices/lab_pin.sym} -600 1780 0 0 {name=l104 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -520 1780 0 0 {name=RDEG
W=1u
L=1600u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -260 1810 -260 1850 {}
C {devices/lab_pin.sym} -260 1850 0 0 {name=l105 lab=VSS}
N -300 1780 -360 1780 {}
C {devices/lab_pin.sym} -360 1780 0 0 {name=l106 lab=NK}
N -260 1750 -260 1710 {}
C {devices/lab_pin.sym} -260 1710 0 0 {name=l107 lab=PG}
N -260 1780 -210 1780 {}
C {devices/lab_pin.sym} -210 1780 0 0 {name=l108 lab=PG}
C {symbols/pfet_03v3.sym} -280 1780 0 0 {name=MSU3
L=2u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 1810 -20 1850 {}
C {devices/lab_pin.sym} -20 1850 0 0 {name=l109 lab=NKB}
N -60 1780 -120 1780 {}
C {devices/lab_pin.sym} -120 1780 0 0 {name=l110 lab=NK}
N -20 1750 -20 1710 {}
C {devices/lab_pin.sym} -20 1710 0 0 {name=l111 lab=VDD}
N -20 1780 30 1780 {}
C {devices/lab_pin.sym} 30 1780 0 0 {name=l112 lab=VDD}
C {symbols/pfet_03v3.sym} -40 1780 0 0 {name=MNKP
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 1750 220 1710 {}
C {devices/lab_pin.sym} 220 1710 0 0 {name=l113 lab=NKB}
N 180 1780 120 1780 {}
C {devices/lab_pin.sym} 120 1780 0 0 {name=l114 lab=NK}
N 220 1810 220 1850 {}
C {devices/lab_pin.sym} 220 1850 0 0 {name=l115 lab=VSS}
N 220 1780 270 1780 {}
C {devices/lab_pin.sym} 270 1780 0 0 {name=l116 lab=VSS}
C {symbols/nfet_03v3.sym} 200 1780 0 0 {name=MNKN
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {BIAS_OK  --  asserts only when ALL THREE hold: the core is alive (NK high), VREF has risen past ~0.7 V, and the
rail has enough headroom over VREF for the mirror legs to be out of triode (XMHD conducts when VDD - VREF exceeds
a PMOS threshold, which is ~2.0 V of rail). The headroom term is what stops a false-early assertion: without it the
flag would follow the loop coming alive, which happens several hundred mV of rail earlier than the reference being
right. XMOKD forces NOK high (BIAS_OK low) whenever the core is not alive, and XMOKZ clamps BIAS_OK to VSS from
NKB, so the flag is DRIVEN low rather than merely undriven for every rail at which the 3.3 V devices can drive at
all. Below roughly 1 V of rail nothing in this PDK can drive anything -- see design/bias_core.md, 'Below the
operating floor', which states that regime explicitly rather than leaving it implied.
DR-005 startup step 4: por_comparator's release decision is gated on this flag.} -1100 2150 0 0 0.4 0.4 {}
N -980 2370 -980 2410 {}
C {devices/lab_pin.sym} -980 2410 0 0 {name=l117 lab=NOK}
N -1020 2340 -1080 2340 {}
C {devices/lab_pin.sym} -1080 2340 0 0 {name=l118 lab=PG}
N -980 2310 -980 2270 {}
C {devices/lab_pin.sym} -980 2270 0 0 {name=l119 lab=VDD}
N -980 2340 -930 2340 {}
C {devices/lab_pin.sym} -930 2340 0 0 {name=l120 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 2340 0 0 {name=MOKP
L=16u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 2370 -740 2410 {}
C {devices/lab_pin.sym} -740 2410 0 0 {name=l121 lab=NOK}
N -780 2340 -840 2340 {}
C {devices/lab_pin.sym} -840 2340 0 0 {name=l122 lab=NK}
N -740 2310 -740 2270 {}
C {devices/lab_pin.sym} -740 2270 0 0 {name=l123 lab=VDD}
N -740 2340 -690 2340 {}
C {devices/lab_pin.sym} -690 2340 0 0 {name=l124 lab=VDD}
C {symbols/pfet_03v3.sym} -760 2340 0 0 {name=MOKD
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 2310 -500 2270 {}
C {devices/lab_pin.sym} -500 2270 0 0 {name=l125 lab=NOK}
N -540 2340 -600 2340 {}
C {devices/lab_pin.sym} -600 2340 0 0 {name=l126 lab=VREF}
N -500 2370 -500 2410 {}
C {devices/lab_pin.sym} -500 2410 0 0 {name=l127 lab=VSS}
N -500 2340 -450 2340 {}
C {devices/lab_pin.sym} -450 2340 0 0 {name=l128 lab=VSS}
C {symbols/nfet_03v3.sym} -520 2340 0 0 {name=MOKS
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 2370 -260 2410 {}
C {devices/lab_pin.sym} -260 2410 0 0 {name=l129 lab=NHD}
N -300 2340 -360 2340 {}
C {devices/lab_pin.sym} -360 2340 0 0 {name=l130 lab=VREF}
N -260 2310 -260 2270 {}
C {devices/lab_pin.sym} -260 2270 0 0 {name=l131 lab=VDD}
N -260 2340 -210 2340 {}
C {devices/lab_pin.sym} -210 2340 0 0 {name=l132 lab=VDD}
C {symbols/pfet_03v3.sym} -280 2340 0 0 {name=MHD
L=2u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 2310 -20 2270 {}
C {devices/lab_pin.sym} -20 2270 0 0 {name=l133 lab=NHD}
N -60 2340 -120 2340 {}
C {devices/lab_pin.sym} -120 2340 0 0 {name=l134 lab=N1}
N -20 2370 -20 2410 {}
C {devices/lab_pin.sym} -20 2410 0 0 {name=l135 lab=VSS}
N -20 2340 30 2340 {}
C {devices/lab_pin.sym} 30 2340 0 0 {name=l136 lab=VSS}
C {symbols/nfet_03v3.sym} -40 2340 0 0 {name=MHDL
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 220 2370 220 2410 {}
C {devices/lab_pin.sym} 220 2410 0 0 {name=l137 lab=NHDB}
N 180 2340 120 2340 {}
C {devices/lab_pin.sym} 120 2340 0 0 {name=l138 lab=NHD}
N 220 2310 220 2270 {}
C {devices/lab_pin.sym} 220 2270 0 0 {name=l139 lab=VDD}
N 220 2340 270 2340 {}
C {devices/lab_pin.sym} 270 2340 0 0 {name=l140 lab=VDD}
C {symbols/pfet_03v3.sym} 200 2340 0 0 {name=MHBP
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 460 2310 460 2270 {}
C {devices/lab_pin.sym} 460 2270 0 0 {name=l141 lab=NHDB}
N 420 2340 360 2340 {}
C {devices/lab_pin.sym} 360 2340 0 0 {name=l142 lab=NHD}
N 460 2370 460 2410 {}
C {devices/lab_pin.sym} 460 2410 0 0 {name=l143 lab=VSS}
N 460 2340 510 2340 {}
C {devices/lab_pin.sym} 510 2340 0 0 {name=l144 lab=VSS}
C {symbols/nfet_03v3.sym} 440 2340 0 0 {name=MHBN
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 700 2370 700 2410 {}
C {devices/lab_pin.sym} 700 2410 0 0 {name=l145 lab=NRX}
N 660 2340 600 2340 {}
C {devices/lab_pin.sym} 600 2340 0 0 {name=l146 lab=NOK}
N 700 2310 700 2270 {}
C {devices/lab_pin.sym} 700 2270 0 0 {name=l147 lab=VDD}
N 700 2340 750 2340 {}
C {devices/lab_pin.sym} 750 2340 0 0 {name=l148 lab=VDD}
C {symbols/pfet_03v3.sym} 680 2340 0 0 {name=MNRP1
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 940 2370 940 2410 {}
C {devices/lab_pin.sym} 940 2410 0 0 {name=l149 lab=BIAS_OK}
N 900 2340 840 2340 {}
C {devices/lab_pin.sym} 840 2340 0 0 {name=l150 lab=NHDB}
N 940 2310 940 2270 {}
C {devices/lab_pin.sym} 940 2270 0 0 {name=l151 lab=NRX}
N 940 2340 990 2340 {}
C {devices/lab_pin.sym} 990 2340 0 0 {name=l152 lab=VDD}
C {symbols/pfet_03v3.sym} 920 2340 0 0 {name=MNRP2
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 1180 2310 1180 2270 {}
C {devices/lab_pin.sym} 1180 2270 0 0 {name=l153 lab=BIAS_OK}
N 1140 2340 1080 2340 {}
C {devices/lab_pin.sym} 1080 2340 0 0 {name=l154 lab=NOK}
N 1180 2370 1180 2410 {}
C {devices/lab_pin.sym} 1180 2410 0 0 {name=l155 lab=VSS}
N 1180 2340 1230 2340 {}
C {devices/lab_pin.sym} 1230 2340 0 0 {name=l156 lab=VSS}
C {symbols/nfet_03v3.sym} 1160 2340 0 0 {name=MNRN1
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 1420 2310 1420 2270 {}
C {devices/lab_pin.sym} 1420 2270 0 0 {name=l157 lab=BIAS_OK}
N 1380 2340 1320 2340 {}
C {devices/lab_pin.sym} 1320 2340 0 0 {name=l158 lab=NHDB}
N 1420 2370 1420 2410 {}
C {devices/lab_pin.sym} 1420 2410 0 0 {name=l159 lab=VSS}
N 1420 2340 1470 2340 {}
C {devices/lab_pin.sym} 1470 2340 0 0 {name=l160 lab=VSS}
C {symbols/nfet_03v3.sym} 1400 2340 0 0 {name=MNRN2
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -980 2610 -980 2570 {}
C {devices/lab_pin.sym} -980 2570 0 0 {name=l161 lab=BIAS_OK}
N -1020 2640 -1080 2640 {}
C {devices/lab_pin.sym} -1080 2640 0 0 {name=l162 lab=NKB}
N -980 2670 -980 2710 {}
C {devices/lab_pin.sym} -980 2710 0 0 {name=l163 lab=VSS}
N -980 2640 -930 2640 {}
C {devices/lab_pin.sym} -930 2640 0 0 {name=l164 lab=VSS}
C {symbols/nfet_03v3.sym} -1000 2640 0 0 {name=MOKZ
L=0.5u
W=16u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
