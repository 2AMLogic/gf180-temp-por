v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {temp_core -- PTAT / CTAT temperature-sensing core (issue #9)} -900 -1500 0 0 0.6 0.6 {}
T {Topology per DR-005: DVBE/VBE bandgap-style core, deliberately left\nuncompensated -- the PTAT term is published raw. 8:1 emitter-area PNP\npair (XQ1 : XQ8A..XQ8H) sets DVBE = (kT/q)*ln(8); the error amplifier\nforces V(NA) = V(NB) so the branch current is I = DVBE/R1 (PTAT), and\nthe matched mirror leg XMP3/XMPC3 drops that same current on R2 =\nR2FIX + trim ladder, giving V(PTAT) = (R2/R1)*(kT/q)*ln(8) -- PTAT by\nconstruction and free of R's absolute value and tempco, which cancel in\nthe same-flavour ppolyf_u ratio.\n\nSizing and the full error budget: design/temp_core.md.\nEvidence: sim/temp-core-designer-check/records/.\n\nInterface contract (unchanged from the #8 stub):\n  VDD/VSS  3.3 V core-flavour supply pair (DR-001)\n  IBIAS    shared bias-mirror node from bias_core (DR-005). Convention:\n           bias_core SOURCES 0.5 uA into this pin; XMBD is the local\n           mirror diode. Nothing here depends on its absolute accuracy --\n           it sets only amplifier tail / cascode bias, never the PTAT\n           current, which is DVBE/R1.\n  EN       enable, active high. Driven from RESETn at the top level, so\n           the sensor is enabled only after POR releases (DR-005 startup\n           ordering step 6). EN low: mirror gate PG pulled to VDD, local\n           bias node NBG pulled to VSS, PTAT and CTAT pulled to VSS.\n  PTAT     analog PTAT output (DR-002). Rout = R2 ~ 516 kohm: this cell\n           has NO output buffer (DR-005 puts that in a separate\n           temp_buffer cell). Specify Rload >= 1 Gohm.\n  CTAT     analog CTAT output (DR-002) = VEB of XQ1, the same single\n           diode-connected vertical PNP that forms the 1x leg of the\n           ratio pair, tapped through XRISO so pad capacitance never\n           sees the loop node. Rout ~ 30 kohm.} -900 -1440 0 0 0.3 0.3 {}
N -1100 -1000 -1040 -1000 {}
C {devices/iopin.sym} -1100 -1000 0 0 {name=p_vdd lab=VDD}
N -1100 -940 -1040 -940 {}
C {devices/iopin.sym} -1100 -940 0 0 {name=p_vss lab=VSS}
N -1100 -880 -1040 -880 {}
C {devices/ipin.sym} -1100 -880 0 0 {name=p_ibias lab=IBIAS}
N -1100 -820 -1040 -820 {}
C {devices/ipin.sym} -1100 -820 0 0 {name=p_en lab=EN}
N -1100 -760 -1040 -760 {}
C {devices/opin.sym} -1100 -760 0 0 {name=p_ptat lab=PTAT}
N -1100 -700 -1040 -700 {}
C {devices/opin.sym} -1100 -700 0 0 {name=p_ctat lab=CTAT}
T {BIAS + ENABLE  --  local mirror off IBIAS; every branch dies with EN low} -1100 -120 0 0 0.4 0.4 {}
N -980 -30 -980 -70 {}
C {devices/lab_pin.sym} -980 -70 0 0 {name=l1 lab=IBIAS}
N -1020 0 -1080 0 {}
C {devices/lab_pin.sym} -1080 0 0 0 {name=l2 lab=NBG}
N -980 30 -980 70 {}
C {devices/lab_pin.sym} -980 70 0 0 {name=l3 lab=VSS}
N -980 0 -930 0 {}
C {devices/lab_pin.sym} -930 0 0 0 {name=l4 lab=VSS}
C {symbols/nfet_03v3.sym} -1000 0 0 0 {name=MBD
L=2u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -740 -30 -740 -70 {}
C {devices/lab_pin.sym} -740 -70 0 0 {name=l5 lab=IBIAS}
N -780 0 -840 0 {}
C {devices/lab_pin.sym} -840 0 0 0 {name=l6 lab=EN}
N -740 30 -740 70 {}
C {devices/lab_pin.sym} -740 70 0 0 {name=l7 lab=NBG}
N -740 0 -690 0 {}
C {devices/lab_pin.sym} -690 0 0 0 {name=l8 lab=VSS}
C {symbols/nfet_03v3.sym} -760 0 0 0 {name=MPASS
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 -30 -500 -70 {}
C {devices/lab_pin.sym} -500 -70 0 0 {name=l9 lab=NBG}
N -540 0 -600 0 {}
C {devices/lab_pin.sym} -600 0 0 0 {name=l10 lab=ENB}
N -500 30 -500 70 {}
C {devices/lab_pin.sym} -500 70 0 0 {name=l11 lab=VSS}
N -500 0 -450 0 {}
C {devices/lab_pin.sym} -450 0 0 0 {name=l12 lab=VSS}
C {symbols/nfet_03v3.sym} -520 0 0 0 {name=MDNB
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 1180 -30 1180 -70 {}
C {devices/lab_pin.sym} 1180 -70 0 0 {name=l13 lab=IBIAS}
N 1140 0 1080 0 {}
C {devices/lab_pin.sym} 1080 0 0 0 {name=l14 lab=ENB}
N 1180 30 1180 70 {}
C {devices/lab_pin.sym} 1180 70 0 0 {name=l15 lab=VSS}
N 1180 0 1230 0 {}
C {devices/lab_pin.sym} 1230 0 0 0 {name=l16 lab=VSS}
C {symbols/nfet_03v3.sym} 1160 0 0 0 {name=MDIB
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 -30 -260 -70 {}
C {devices/lab_pin.sym} -260 -70 0 0 {name=l17 lab=PB}
N -300 0 -360 0 {}
C {devices/lab_pin.sym} -360 0 0 0 {name=l18 lab=NBG}
N -260 30 -260 70 {}
C {devices/lab_pin.sym} -260 70 0 0 {name=l19 lab=VSS}
N -260 0 -210 0 {}
C {devices/lab_pin.sym} -210 0 0 0 {name=l20 lab=VSS}
C {symbols/nfet_03v3.sym} -280 0 0 0 {name=MBN1
L=2u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 30 -20 70 {}
C {devices/lab_pin.sym} -20 70 0 0 {name=l21 lab=PB}
N -60 0 -120 0 {}
C {devices/lab_pin.sym} -120 0 0 0 {name=l22 lab=PB}
N -20 -30 -20 -70 {}
C {devices/lab_pin.sym} -20 -70 0 0 {name=l23 lab=VDD}
N -20 0 30 0 {}
C {devices/lab_pin.sym} 30 0 0 0 {name=l24 lab=VDD}
C {symbols/pfet_03v3.sym} -40 0 0 0 {name=MBP
L=4u
W=10u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 -30 220 -70 {}
C {devices/lab_pin.sym} 220 -70 0 0 {name=l25 lab=PCAS}
N 180 0 120 0 {}
C {devices/lab_pin.sym} 120 0 0 0 {name=l26 lab=NBG}
N 220 30 220 70 {}
C {devices/lab_pin.sym} 220 70 0 0 {name=l27 lab=VSS}
N 220 0 270 0 {}
C {devices/lab_pin.sym} 270 0 0 0 {name=l28 lab=VSS}
C {symbols/nfet_03v3.sym} 200 0 0 0 {name=MBN2
L=2u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 460 30 460 70 {}
C {devices/lab_pin.sym} 460 70 0 0 {name=l29 lab=PCAS}
N 420 0 360 0 {}
C {devices/lab_pin.sym} 360 0 0 0 {name=l30 lab=PCAS}
N 460 -30 460 -70 {}
C {devices/lab_pin.sym} 460 -70 0 0 {name=l31 lab=VDD}
N 460 0 510 0 {}
C {devices/lab_pin.sym} 510 0 0 0 {name=l32 lab=VDD}
C {symbols/pfet_03v3.sym} 440 0 0 0 {name=MCB
L=8u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 700 30 700 70 {}
C {devices/lab_pin.sym} 700 70 0 0 {name=l33 lab=ENB}
N 660 0 600 0 {}
C {devices/lab_pin.sym} 600 0 0 0 {name=l34 lab=EN}
N 700 -30 700 -70 {}
C {devices/lab_pin.sym} 700 -70 0 0 {name=l35 lab=VDD}
N 700 0 750 0 {}
C {devices/lab_pin.sym} 750 0 0 0 {name=l36 lab=VDD}
C {symbols/pfet_03v3.sym} 680 0 0 0 {name=MINVP
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 940 -30 940 -70 {}
C {devices/lab_pin.sym} 940 -70 0 0 {name=l37 lab=ENB}
N 900 0 840 0 {}
C {devices/lab_pin.sym} 840 0 0 0 {name=l38 lab=EN}
N 940 30 940 70 {}
C {devices/lab_pin.sym} 940 70 0 0 {name=l39 lab=VSS}
N 940 0 990 0 {}
C {devices/lab_pin.sym} 990 0 0 0 {name=l40 lab=VSS}
C {symbols/nfet_03v3.sym} 920 0 0 0 {name=MINVN
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {ERROR AMPLIFIER  --  PMOS pair + NMOS mirror load, NMOS common-source 2nd stage.\nXMS2N is a current-density copy of XML1, so the stage-1 output sits at the diode node's own\nVGS and the systematic input offset is < 10 uV at every PVT corner (measured).} -1100 120 0 0 0.4 0.4 {}
N -980 290 -980 330 {}
C {devices/lab_pin.sym} -980 330 0 0 {name=l41 lab=NT}
N -1020 260 -1080 260 {}
C {devices/lab_pin.sym} -1080 260 0 0 {name=l42 lab=PB}
N -980 230 -980 190 {}
C {devices/lab_pin.sym} -980 190 0 0 {name=l43 lab=VDD}
N -980 260 -930 260 {}
C {devices/lab_pin.sym} -930 260 0 0 {name=l44 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 260 0 0 {name=MT
L=4u
W=20u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 290 -740 330 {}
C {devices/lab_pin.sym} -740 330 0 0 {name=l45 lab=N1}
N -780 260 -840 260 {}
C {devices/lab_pin.sym} -840 260 0 0 {name=l46 lab=NA}
N -740 230 -740 190 {}
C {devices/lab_pin.sym} -740 190 0 0 {name=l47 lab=NT}
N -740 260 -690 260 {}
C {devices/lab_pin.sym} -690 260 0 0 {name=l48 lab=NT}
C {symbols/pfet_03v3.sym} -760 260 0 0 {name=MI1
L=4u
W=32u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 290 -500 330 {}
C {devices/lab_pin.sym} -500 330 0 0 {name=l49 lab=N2}
N -540 260 -600 260 {}
C {devices/lab_pin.sym} -600 260 0 0 {name=l50 lab=NB}
N -500 230 -500 190 {}
C {devices/lab_pin.sym} -500 190 0 0 {name=l51 lab=NT}
N -500 260 -450 260 {}
C {devices/lab_pin.sym} -450 260 0 0 {name=l52 lab=NT}
C {symbols/pfet_03v3.sym} -520 260 0 0 {name=MI2
L=4u
W=32u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -260 230 -260 190 {}
C {devices/lab_pin.sym} -260 190 0 0 {name=l53 lab=N1}
N -300 260 -360 260 {}
C {devices/lab_pin.sym} -360 260 0 0 {name=l54 lab=N1}
N -260 290 -260 330 {}
C {devices/lab_pin.sym} -260 330 0 0 {name=l55 lab=VSS}
N -260 260 -210 260 {}
C {devices/lab_pin.sym} -210 260 0 0 {name=l56 lab=VSS}
C {symbols/nfet_03v3.sym} -280 260 0 0 {name=ML1
L=8u
W=8u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 230 -20 190 {}
C {devices/lab_pin.sym} -20 190 0 0 {name=l57 lab=N2}
N -60 260 -120 260 {}
C {devices/lab_pin.sym} -120 260 0 0 {name=l58 lab=N1}
N -20 290 -20 330 {}
C {devices/lab_pin.sym} -20 330 0 0 {name=l59 lab=VSS}
N -20 260 30 260 {}
C {devices/lab_pin.sym} 30 260 0 0 {name=l60 lab=VSS}
C {symbols/nfet_03v3.sym} -40 260 0 0 {name=ML2
L=8u
W=8u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 220 230 220 190 {}
C {devices/lab_pin.sym} 220 190 0 0 {name=l61 lab=PG}
N 180 260 120 260 {}
C {devices/lab_pin.sym} 120 260 0 0 {name=l62 lab=N2}
N 220 290 220 330 {}
C {devices/lab_pin.sym} 220 330 0 0 {name=l63 lab=VSS}
N 220 260 270 260 {}
C {devices/lab_pin.sym} 270 260 0 0 {name=l64 lab=VSS}
C {symbols/nfet_03v3.sym} 200 260 0 0 {name=MS2N
L=8u
W=8u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 460 290 460 330 {}
C {devices/lab_pin.sym} 460 330 0 0 {name=l65 lab=PG}
N 420 260 360 260 {}
C {devices/lab_pin.sym} 360 260 0 0 {name=l66 lab=PB}
N 460 230 460 190 {}
C {devices/lab_pin.sym} 460 190 0 0 {name=l67 lab=VDD}
N 460 260 510 260 {}
C {devices/lab_pin.sym} 510 260 0 0 {name=l68 lab=VDD}
C {symbols/pfet_03v3.sym} 440 260 0 0 {name=MS2P
L=4u
W=10u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 680 230 680 190 {}
C {devices/lab_pin.sym} 680 190 0 0 {name=l69 lab=PG}
N 680 290 680 330 {}
C {devices/lab_pin.sym} 680 330 0 0 {name=l70 lab=NZ}
C {symbols/cap_mim_analog.sym} 680 260 0 0 {name=CC
W=12u
L=12u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=1}
N 920 290 920 330 {}
C {devices/lab_pin.sym} 920 330 0 0 {name=l71 lab=NZ}
N 920 230 920 190 {}
C {devices/lab_pin.sym} 920 190 0 0 {name=l72 lab=N2}
N 900 260 840 260 {}
C {devices/lab_pin.sym} 840 260 0 0 {name=l73 lab=VSS}
C {symbols/ppolyf_u.sym} 920 260 0 0 {name=RZ
W=2u
L=1000u
model=ppolyf_u
spiceprefix=X
m=1}
T {CASCODED PMOS MIRROR  --  three matched legs at ~2.5 uA. XMP1/XMP2 see identical VGS *and*\nidentical VDS (the loop forces V(NA) = V(NB)), so the 1:1 ratio that sets DVBE is exact by\nconstruction; the cascode keeps leg 3 on ratio despite its ~1 V higher drain swing.} -1100 380 0 0 0.4 0.4 {}
N -980 550 -980 590 {}
C {devices/lab_pin.sym} -980 590 0 0 {name=l74 lab=M1D}
N -1020 520 -1080 520 {}
C {devices/lab_pin.sym} -1080 520 0 0 {name=l75 lab=PG}
N -980 490 -980 450 {}
C {devices/lab_pin.sym} -980 450 0 0 {name=l76 lab=VDD}
N -980 520 -930 520 {}
C {devices/lab_pin.sym} -930 520 0 0 {name=l77 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 520 0 0 {name=MP1
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 550 -740 590 {}
C {devices/lab_pin.sym} -740 590 0 0 {name=l78 lab=NA}
N -780 520 -840 520 {}
C {devices/lab_pin.sym} -840 520 0 0 {name=l79 lab=PCAS}
N -740 490 -740 450 {}
C {devices/lab_pin.sym} -740 450 0 0 {name=l80 lab=M1D}
N -740 520 -690 520 {}
C {devices/lab_pin.sym} -690 520 0 0 {name=l81 lab=VDD}
C {symbols/pfet_03v3.sym} -760 520 0 0 {name=MPC1
L=1u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 550 -500 590 {}
C {devices/lab_pin.sym} -500 590 0 0 {name=l82 lab=M2D}
N -540 520 -600 520 {}
C {devices/lab_pin.sym} -600 520 0 0 {name=l83 lab=PG}
N -500 490 -500 450 {}
C {devices/lab_pin.sym} -500 450 0 0 {name=l84 lab=VDD}
N -500 520 -450 520 {}
C {devices/lab_pin.sym} -450 520 0 0 {name=l85 lab=VDD}
C {symbols/pfet_03v3.sym} -520 520 0 0 {name=MP2
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -260 550 -260 590 {}
C {devices/lab_pin.sym} -260 590 0 0 {name=l86 lab=NB}
N -300 520 -360 520 {}
C {devices/lab_pin.sym} -360 520 0 0 {name=l87 lab=PCAS}
N -260 490 -260 450 {}
C {devices/lab_pin.sym} -260 450 0 0 {name=l88 lab=M2D}
N -260 520 -210 520 {}
C {devices/lab_pin.sym} -210 520 0 0 {name=l89 lab=VDD}
C {symbols/pfet_03v3.sym} -280 520 0 0 {name=MPC2
L=1u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 550 -20 590 {}
C {devices/lab_pin.sym} -20 590 0 0 {name=l90 lab=M3D}
N -60 520 -120 520 {}
C {devices/lab_pin.sym} -120 520 0 0 {name=l91 lab=PG}
N -20 490 -20 450 {}
C {devices/lab_pin.sym} -20 450 0 0 {name=l92 lab=VDD}
N -20 520 30 520 {}
C {devices/lab_pin.sym} 30 520 0 0 {name=l93 lab=VDD}
C {symbols/pfet_03v3.sym} -40 520 0 0 {name=MP3
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 550 220 590 {}
C {devices/lab_pin.sym} 220 590 0 0 {name=l94 lab=PTAT}
N 180 520 120 520 {}
C {devices/lab_pin.sym} 120 520 0 0 {name=l95 lab=PCAS}
N 220 490 220 450 {}
C {devices/lab_pin.sym} 220 450 0 0 {name=l96 lab=M3D}
N 220 520 270 520 {}
C {devices/lab_pin.sym} 270 520 0 0 {name=l97 lab=VDD}
C {symbols/pfet_03v3.sym} 200 520 0 0 {name=MPC3
L=1u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
T {STARTUP KICK + ENABLE GATING  --  CURRENT-referenced dead-loop detector, not a level detector.\nXMSU4 is a 1:8 replica of the mirror leg (same gate PG), so it carries ~0.31 uA when the loop is\nalive and ~0 when it is dead; XMSU5 turns that into a gate voltage NR and XMSU2 mirrors it against\nXMSU1's ~25 nA IBIAS-referenced pull-up on ND. Alive: XMSU2 wins by >10x, ND ~ 0, kick idle.\nDead: XMSU4 delivers nothing, ND rises to VDD, XMSU3 pulls PG down and the loop starts.\nThe comparison is loop current vs. IBIAS current -- both scale together over PVT -- which is why\nthis survives the corners where an absolute-level detector cannot: V(NA) is a VBE, and a DEAD\ncore's VBE at -40 C (~0.48 V) is HIGHER than a LIVE core's VBE at 125 C (~0.46 V), so no fixed\nvoltage threshold on NA separates the two states across the rated range. The level-sensing\nversion of this block left a second stable DC solution that ngspice found at fs/-40 C and at\nboth resistor corners; see design/temp_core.md, "Startup".} -1100 620 0 0 0.4 0.4 {}
N -980 810 -980 850 {}
C {devices/lab_pin.sym} -980 850 0 0 {name=l98 lab=ND}
N -1020 780 -1080 780 {}
C {devices/lab_pin.sym} -1080 780 0 0 {name=l99 lab=PB}
N -980 750 -980 710 {}
C {devices/lab_pin.sym} -980 710 0 0 {name=l100 lab=VDD}
N -980 780 -930 780 {}
C {devices/lab_pin.sym} -930 780 0 0 {name=l101 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 780 0 0 {name=MSU1
L=8u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 750 -740 710 {}
C {devices/lab_pin.sym} -740 710 0 0 {name=l102 lab=ND}
N -780 780 -840 780 {}
C {devices/lab_pin.sym} -840 780 0 0 {name=l103 lab=NR}
N -740 810 -740 850 {}
C {devices/lab_pin.sym} -740 850 0 0 {name=l104 lab=VSS}
N -740 780 -690 780 {}
C {devices/lab_pin.sym} -690 780 0 0 {name=l105 lab=VSS}
C {symbols/nfet_03v3.sym} -760 780 0 0 {name=MSU2
L=2u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 750 -500 710 {}
C {devices/lab_pin.sym} -500 710 0 0 {name=l106 lab=PG}
N -540 780 -600 780 {}
C {devices/lab_pin.sym} -600 780 0 0 {name=l107 lab=ND}
N -500 810 -500 850 {}
C {devices/lab_pin.sym} -500 850 0 0 {name=l108 lab=VSS}
N -500 780 -450 780 {}
C {devices/lab_pin.sym} -450 780 0 0 {name=l109 lab=VSS}
C {symbols/nfet_03v3.sym} -520 780 0 0 {name=MSU3
L=1u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 750 -260 710 {}
C {devices/lab_pin.sym} -260 710 0 0 {name=l110 lab=ND}
N -300 780 -360 780 {}
C {devices/lab_pin.sym} -360 780 0 0 {name=l111 lab=ENB}
N -260 810 -260 850 {}
C {devices/lab_pin.sym} -260 850 0 0 {name=l112 lab=VSS}
N -260 780 -210 780 {}
C {devices/lab_pin.sym} -210 780 0 0 {name=l113 lab=VSS}
C {symbols/nfet_03v3.sym} -280 780 0 0 {name=MDND
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 810 -20 850 {}
C {devices/lab_pin.sym} -20 850 0 0 {name=l114 lab=PG}
N -60 780 -120 780 {}
C {devices/lab_pin.sym} -120 780 0 0 {name=l115 lab=EN}
N -20 750 -20 710 {}
C {devices/lab_pin.sym} -20 710 0 0 {name=l116 lab=VDD}
N -20 780 30 780 {}
C {devices/lab_pin.sym} 30 780 0 0 {name=l117 lab=VDD}
C {symbols/pfet_03v3.sym} -40 780 0 0 {name=MENPG
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 750 220 710 {}
C {devices/lab_pin.sym} 220 710 0 0 {name=l118 lab=PTAT}
N 180 780 120 780 {}
C {devices/lab_pin.sym} 120 780 0 0 {name=l119 lab=ENB}
N 220 810 220 850 {}
C {devices/lab_pin.sym} 220 850 0 0 {name=l120 lab=VSS}
N 220 780 270 780 {}
C {devices/lab_pin.sym} 270 780 0 0 {name=l121 lab=VSS}
C {symbols/nfet_03v3.sym} 200 780 0 0 {name=MENPT
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 460 750 460 710 {}
C {devices/lab_pin.sym} 460 710 0 0 {name=l122 lab=CTAT}
N 420 780 360 780 {}
C {devices/lab_pin.sym} 360 780 0 0 {name=l123 lab=ENB}
N 460 810 460 850 {}
C {devices/lab_pin.sym} 460 850 0 0 {name=l124 lab=VSS}
N 460 780 510 780 {}
C {devices/lab_pin.sym} 510 780 0 0 {name=l125 lab=VSS}
C {symbols/nfet_03v3.sym} 440 780 0 0 {name=MENCT
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 700 810 700 850 {}
C {devices/lab_pin.sym} 700 850 0 0 {name=l204 lab=NR}
N 660 780 600 780 {}
C {devices/lab_pin.sym} 600 780 0 0 {name=l205 lab=PG}
N 700 750 700 710 {}
C {devices/lab_pin.sym} 700 710 0 0 {name=l206 lab=VDD}
N 700 780 750 780 {}
C {devices/lab_pin.sym} 750 780 0 0 {name=l207 lab=VDD}
C {symbols/pfet_03v3.sym} 680 780 0 0 {name=MSU4
L=4u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 940 750 940 710 {}
C {devices/lab_pin.sym} 940 710 0 0 {name=l208 lab=NR}
N 900 780 840 780 {}
C {devices/lab_pin.sym} 840 780 0 0 {name=l209 lab=NR}
N 940 810 940 850 {}
C {devices/lab_pin.sym} 940 850 0 0 {name=l210 lab=VSS}
N 940 780 990 780 {}
C {devices/lab_pin.sym} 990 780 0 0 {name=l211 lab=VSS}
C {symbols/nfet_03v3.sym} 920 780 0 0 {name=MSU5
L=2u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 1180 750 1180 710 {}
C {devices/lab_pin.sym} 1180 710 0 0 {name=l212 lab=N2}
N 1140 780 1080 780 {}
C {devices/lab_pin.sym} 1080 780 0 0 {name=l213 lab=ENB}
N 1180 810 1180 850 {}
C {devices/lab_pin.sym} 1180 850 0 0 {name=l214 lab=VSS}
N 1180 780 1230 780 {}
C {devices/lab_pin.sym} 1230 780 0 0 {name=l215 lab=VSS}
C {symbols/nfet_03v3.sym} 1160 780 0 0 {name=MDN2
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 1420 750 1420 710 {}
C {devices/lab_pin.sym} 1420 710 0 0 {name=l216 lab=NT}
N 1380 780 1320 780 {}
C {devices/lab_pin.sym} 1320 780 0 0 {name=l217 lab=ENB}
N 1420 810 1420 850 {}
C {devices/lab_pin.sym} 1420 850 0 0 {name=l218 lab=VSS}
N 1420 780 1470 780 {}
C {devices/lab_pin.sym} 1470 780 0 0 {name=l219 lab=VSS}
C {symbols/nfet_03v3.sym} 1400 780 0 0 {name=MDNT
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {XMSU4 : 1/8 replica of the mirror leg        XMSU5 : replica-current diode (NR)\nXMDN2 / XMDNT : disable clamps. With the tail off, NT and the stage-1 output N2 are\nhigh-impedance and float; at the fs corner N2 drifted above the (low-Vt) threshold of\nXMS2N and opened a VDD -> XMENPG -> PG -> XMS2N -> VSS path worth ~1.2 uA at -40 C\nwhile the cell was supposed to be OFF. Measured, not hypothetical -- see\nsim/temp-core-startup/ and design/temp_core.md, "Disabled state".} 600 890 0 0 0.3 0.3 {}
T {SENSING CORE  --  8:1 vertical-PNP emitter-area ratio (pnp_10p00x10p00 unit cell, per\nsim/devchar/SUMMARY.md). Eight unit cells in parallel, NOT one instance with par=8: the\ngf180mcu vertical-PNP model's par= scales only the mismatch term, not Is (SUMMARY.md).\nR1 turns DVBE into the PTAT branch current; XQ1's VEB is also the CTAT output.} -1100 880 0 0 0.4 0.4 {}
N -980 1070 -980 1110 {}
C {devices/lab_pin.sym} -980 1110 0 0 {name=l126 lab=VSS}
N -1020 1040 -1080 1040 {}
C {devices/lab_pin.sym} -1080 1040 0 0 {name=l127 lab=VSS}
N -980 1010 -980 970 {}
C {devices/lab_pin.sym} -980 970 0 0 {name=l128 lab=NA}
C {symbols/pnp_10p00x10p00.sym} -1000 1040 0 0 {name=Q1
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -740 1070 -740 1110 {}
C {devices/lab_pin.sym} -740 1110 0 0 {name=l129 lab=VSS}
N -780 1040 -840 1040 {}
C {devices/lab_pin.sym} -840 1040 0 0 {name=l130 lab=VSS}
N -740 1010 -740 970 {}
C {devices/lab_pin.sym} -740 970 0 0 {name=l131 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -760 1040 0 0 {name=Q8A
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -500 1070 -500 1110 {}
C {devices/lab_pin.sym} -500 1110 0 0 {name=l132 lab=VSS}
N -540 1040 -600 1040 {}
C {devices/lab_pin.sym} -600 1040 0 0 {name=l133 lab=VSS}
N -500 1010 -500 970 {}
C {devices/lab_pin.sym} -500 970 0 0 {name=l134 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -520 1040 0 0 {name=Q8B
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -260 1070 -260 1110 {}
C {devices/lab_pin.sym} -260 1110 0 0 {name=l135 lab=VSS}
N -300 1040 -360 1040 {}
C {devices/lab_pin.sym} -360 1040 0 0 {name=l136 lab=VSS}
N -260 1010 -260 970 {}
C {devices/lab_pin.sym} -260 970 0 0 {name=l137 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -280 1040 0 0 {name=Q8C
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -20 1070 -20 1110 {}
C {devices/lab_pin.sym} -20 1110 0 0 {name=l138 lab=VSS}
N -60 1040 -120 1040 {}
C {devices/lab_pin.sym} -120 1040 0 0 {name=l139 lab=VSS}
N -20 1010 -20 970 {}
C {devices/lab_pin.sym} -20 970 0 0 {name=l140 lab=NC}
C {symbols/pnp_10p00x10p00.sym} -40 1040 0 0 {name=Q8D
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 220 1070 220 1110 {}
C {devices/lab_pin.sym} 220 1110 0 0 {name=l141 lab=VSS}
N 180 1040 120 1040 {}
C {devices/lab_pin.sym} 120 1040 0 0 {name=l142 lab=VSS}
N 220 1010 220 970 {}
C {devices/lab_pin.sym} 220 970 0 0 {name=l143 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 200 1040 0 0 {name=Q8E
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 460 1070 460 1110 {}
C {devices/lab_pin.sym} 460 1110 0 0 {name=l144 lab=VSS}
N 420 1040 360 1040 {}
C {devices/lab_pin.sym} 360 1040 0 0 {name=l145 lab=VSS}
N 460 1010 460 970 {}
C {devices/lab_pin.sym} 460 970 0 0 {name=l146 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 440 1040 0 0 {name=Q8F
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 700 1070 700 1110 {}
C {devices/lab_pin.sym} 700 1110 0 0 {name=l147 lab=VSS}
N 660 1040 600 1040 {}
C {devices/lab_pin.sym} 600 1040 0 0 {name=l148 lab=VSS}
N 700 1010 700 970 {}
C {devices/lab_pin.sym} 700 970 0 0 {name=l149 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 680 1040 0 0 {name=Q8G
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 940 1070 940 1110 {}
C {devices/lab_pin.sym} 940 1110 0 0 {name=l150 lab=VSS}
N 900 1040 840 1040 {}
C {devices/lab_pin.sym} 840 1040 0 0 {name=l151 lab=VSS}
N 940 1010 940 970 {}
C {devices/lab_pin.sym} 940 970 0 0 {name=l152 lab=NC}
C {symbols/pnp_10p00x10p00.sym} 920 1040 0 0 {name=Q8H
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 1160 1070 1160 1110 {}
C {devices/lab_pin.sym} 1160 1110 0 0 {name=l153 lab=NB}
N 1160 1010 1160 970 {}
C {devices/lab_pin.sym} 1160 970 0 0 {name=l154 lab=NC}
N 1140 1040 1080 1040 {}
C {devices/lab_pin.sym} 1080 1040 0 0 {name=l155 lab=VSS}
C {symbols/ppolyf_u.sym} 1160 1040 0 0 {name=R1
W=2u
L=119.47u
model=ppolyf_u
spiceprefix=X
m=1}
T {PTAT GAIN RESISTOR + 6-BIT TRIM LADDER  --  same ppolyf_u flavour as R1 (lowest |TC| of the\neight flavours measured in sim/devchar/SUMMARY.md), so absolute value and tempco cancel in\nthe R2/R1 ratio. R2(nominal) = 24 * R1. TRIM<5:0> are the switch gates: strapping one to VDD\nshorts its segment (lower gain), to VSS leaves it in circuit. 1 LSB = 0.237 % of R2, full\nrange -7.8 %/+7.8 % -- enough to null a +/-4.1 mV amplifier offset at the 25 C trim point.\nWave-1 code is 100000b: XSW5 gate to VDD, XSW4..XSW0 gates to VSS. The straps are a metal-1\nmask option in wave 1 and are the drop-in hook-up point for a fuse/OTP bit-cell array later;\nno trim pad exists or is needed (DR-002/DR-003 pinout).} -1100 1100 0 0 0.4 0.4 {}
N -1000 1330 -1000 1370 {}
C {devices/lab_pin.sym} -1000 1370 0 0 {name=l156 lab=PTAT}
N -1000 1270 -1000 1230 {}
C {devices/lab_pin.sym} -1000 1230 0 0 {name=l157 lab=T5}
N -1020 1300 -1080 1300 {}
C {devices/lab_pin.sym} -1080 1300 0 0 {name=l158 lab=VSS}
C {symbols/ppolyf_u.sym} -1000 1300 0 0 {name=R2F
W=2u
L=2652.6u
model=ppolyf_u
spiceprefix=X
m=1}
N -760 1330 -760 1370 {}
C {devices/lab_pin.sym} -760 1370 0 0 {name=l159 lab=T5}
N -760 1270 -760 1230 {}
C {devices/lab_pin.sym} -760 1230 0 0 {name=l160 lab=T4}
N -780 1300 -840 1300 {}
C {devices/lab_pin.sym} -840 1300 0 0 {name=l161 lab=VSS}
C {symbols/ppolyf_u.sym} -760 1300 0 0 {name=R2T5
W=2u
L=229.71u
model=ppolyf_u
spiceprefix=X
m=1}
N -520 1330 -520 1370 {}
C {devices/lab_pin.sym} -520 1370 0 0 {name=l162 lab=T4}
N -520 1270 -520 1230 {}
C {devices/lab_pin.sym} -520 1230 0 0 {name=l163 lab=T3}
N -540 1300 -600 1300 {}
C {devices/lab_pin.sym} -600 1300 0 0 {name=l164 lab=VSS}
C {symbols/ppolyf_u.sym} -520 1300 0 0 {name=R2T4
W=2u
L=114.69u
model=ppolyf_u
spiceprefix=X
m=1}
N -280 1330 -280 1370 {}
C {devices/lab_pin.sym} -280 1370 0 0 {name=l165 lab=T3}
N -280 1270 -280 1230 {}
C {devices/lab_pin.sym} -280 1230 0 0 {name=l166 lab=T2}
N -300 1300 -360 1300 {}
C {devices/lab_pin.sym} -360 1300 0 0 {name=l167 lab=VSS}
C {symbols/ppolyf_u.sym} -280 1300 0 0 {name=R2T3
W=2u
L=57.18u
model=ppolyf_u
spiceprefix=X
m=1}
N -40 1330 -40 1370 {}
C {devices/lab_pin.sym} -40 1370 0 0 {name=l168 lab=T2}
N -40 1270 -40 1230 {}
C {devices/lab_pin.sym} -40 1230 0 0 {name=l169 lab=T1}
N -60 1300 -120 1300 {}
C {devices/lab_pin.sym} -120 1300 0 0 {name=l170 lab=VSS}
C {symbols/ppolyf_u.sym} -40 1300 0 0 {name=R2T2
W=2u
L=28.42u
model=ppolyf_u
spiceprefix=X
m=1}
N 200 1330 200 1370 {}
C {devices/lab_pin.sym} 200 1370 0 0 {name=l171 lab=T1}
N 200 1270 200 1230 {}
C {devices/lab_pin.sym} 200 1230 0 0 {name=l172 lab=T0}
N 180 1300 120 1300 {}
C {devices/lab_pin.sym} 120 1300 0 0 {name=l173 lab=VSS}
C {symbols/ppolyf_u.sym} 200 1300 0 0 {name=R2T1
W=2u
L=14.03u
model=ppolyf_u
spiceprefix=X
m=1}
N 440 1330 440 1370 {}
C {devices/lab_pin.sym} 440 1370 0 0 {name=l174 lab=T0}
N 440 1270 440 1230 {}
C {devices/lab_pin.sym} 440 1230 0 0 {name=l175 lab=VSS}
N 420 1300 360 1300 {}
C {devices/lab_pin.sym} 360 1300 0 0 {name=l176 lab=VSS}
C {symbols/ppolyf_u.sym} 440 1300 0 0 {name=R2T0
W=2u
L=6.85u
model=ppolyf_u
spiceprefix=X
m=1}
N 920 1330 920 1370 {}
C {devices/lab_pin.sym} 920 1370 0 0 {name=l177 lab=NA}
N 920 1270 920 1230 {}
C {devices/lab_pin.sym} 920 1230 0 0 {name=l178 lab=CTAT}
N 900 1300 840 1300 {}
C {devices/lab_pin.sym} 840 1300 0 0 {name=l179 lab=VSS}
C {symbols/ppolyf_u.sym} 920 1300 0 0 {name=RISO
W=2u
L=111.05u
model=ppolyf_u
spiceprefix=X
m=1}
T {XRISO: CTAT pad isolation} 840 1420 0 0 0.3 0.3 {}
N -740 1530 -740 1490 {}
C {devices/lab_pin.sym} -740 1490 0 0 {name=l180 lab=T5}
N -780 1560 -840 1560 {}
C {devices/lab_pin.sym} -840 1560 0 0 {name=l181 lab=VDD}
N -740 1590 -740 1630 {}
C {devices/lab_pin.sym} -740 1630 0 0 {name=l182 lab=T4}
N -740 1560 -690 1560 {}
C {devices/lab_pin.sym} -690 1560 0 0 {name=l183 lab=VSS}
C {symbols/nfet_03v3.sym} -760 1560 0 0 {name=SW5
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 1530 -500 1490 {}
C {devices/lab_pin.sym} -500 1490 0 0 {name=l184 lab=T4}
N -540 1560 -600 1560 {}
C {devices/lab_pin.sym} -600 1560 0 0 {name=l185 lab=VSS}
N -500 1590 -500 1630 {}
C {devices/lab_pin.sym} -500 1630 0 0 {name=l186 lab=T3}
N -500 1560 -450 1560 {}
C {devices/lab_pin.sym} -450 1560 0 0 {name=l187 lab=VSS}
C {symbols/nfet_03v3.sym} -520 1560 0 0 {name=SW4
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 1530 -260 1490 {}
C {devices/lab_pin.sym} -260 1490 0 0 {name=l188 lab=T3}
N -300 1560 -360 1560 {}
C {devices/lab_pin.sym} -360 1560 0 0 {name=l189 lab=VSS}
N -260 1590 -260 1630 {}
C {devices/lab_pin.sym} -260 1630 0 0 {name=l190 lab=T2}
N -260 1560 -210 1560 {}
C {devices/lab_pin.sym} -210 1560 0 0 {name=l191 lab=VSS}
C {symbols/nfet_03v3.sym} -280 1560 0 0 {name=SW3
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 1530 -20 1490 {}
C {devices/lab_pin.sym} -20 1490 0 0 {name=l192 lab=T2}
N -60 1560 -120 1560 {}
C {devices/lab_pin.sym} -120 1560 0 0 {name=l193 lab=VSS}
N -20 1590 -20 1630 {}
C {devices/lab_pin.sym} -20 1630 0 0 {name=l194 lab=T1}
N -20 1560 30 1560 {}
C {devices/lab_pin.sym} 30 1560 0 0 {name=l195 lab=VSS}
C {symbols/nfet_03v3.sym} -40 1560 0 0 {name=SW2
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 220 1530 220 1490 {}
C {devices/lab_pin.sym} 220 1490 0 0 {name=l196 lab=T1}
N 180 1560 120 1560 {}
C {devices/lab_pin.sym} 120 1560 0 0 {name=l197 lab=VSS}
N 220 1590 220 1630 {}
C {devices/lab_pin.sym} 220 1630 0 0 {name=l198 lab=T0}
N 220 1560 270 1560 {}
C {devices/lab_pin.sym} 270 1560 0 0 {name=l199 lab=VSS}
C {symbols/nfet_03v3.sym} 200 1560 0 0 {name=SW1
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 460 1530 460 1490 {}
C {devices/lab_pin.sym} 460 1490 0 0 {name=l200 lab=T0}
N 420 1560 360 1560 {}
C {devices/lab_pin.sym} 360 1560 0 0 {name=l201 lab=VSS}
N 460 1590 460 1630 {}
C {devices/lab_pin.sym} 460 1630 0 0 {name=l202 lab=VSS}
N 460 1560 510 1560 {}
C {devices/lab_pin.sym} 510 1560 0 0 {name=l203 lab=VSS}
C {symbols/nfet_03v3.sym} 440 1560 0 0 {name=SW0
L=0.5u
W=32u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {TRIM<5>=1 (strapped to VDD)          TRIM<4:0>=0 (strapped to VSS)} -800 1680 0 0 0.4 0.4 {}
