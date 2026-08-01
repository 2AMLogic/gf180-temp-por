v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {bias_core -- shared bias / reference core (issue #11)} -980 -1500 0 0 0.6 0.6 {}
T {Topology per DR-005 "Shared infrastructure": one bandgap-style core shared by
the temperature sensor and the POR comparator, plus its own startup kick.

  I     = DVBE / R1                                    (PTAT branch current)
  VREF  = VEB(XQR) + (R2/R1) * DVBE                    (first-order flat)
  IBIAS = (W(XMPIB)/W(XMBP)) * I / 4                   (shared bias mirror)

Sizing, error budget, startup analysis and the Iq apportionment against
spec/target-spec.md's por-iq row: design/bias_core.md.
Evidence: sim/bias-core-designer-check/records/.

Interface contract (unchanged from the #8 stub, PR #29):
  VDD/VSS  3.3 V core-flavour supply pair (DR-001)
  IBIAS    shared bias-mirror node feeding temp_core, por_comparator and
           por_output_chain. Convention set by #9/#10 and honoured here:
           bias_core SOURCES 0.5 uA (nominal, tt/27 C) INTO this pin. The
           pin is a current output; its compliance is V(IBIAS) <= VDD - 0.2 V.
  VREF     absolute reference the POR comparator compares its divided rail
           against. 1.2 V nominal, which is the value design/por_comparator.md
           sized its divider ratio against.
  BIAS_OK  "shared core is up and settled" flag, active high. Gates the POR
           release decision (DR-005 startup ordering, step 4).

This cell has NO enable pin and no off state: it is the always-on core, live
from the first millivolt of rail. Its whole draw is therefore charged to
spec/target-spec.md#por-iq by that file's SS5 accounting rule 1 -- see
design/bias_core.md, "Iq apportionment", for the arithmetic and for the
spec conflict it surfaces.} -980 -1440 0 0 0.3 0.3 {}
N -1180 -1000 -1120 -1000 {lab=VDD}
N -1180 -940 -1120 -940 {lab=VSS}
N -1180 -880 -1120 -880 {lab=IBIAS}
N -1180 -820 -1120 -820 {lab=VREF}
N -1180 -760 -1120 -760 {lab=BIAS_OK}
C {devices/iopin.sym} -1180 -1000 0 0 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -1180 -940 0 0 {name=p_vss lab=VSS}
C {devices/opin.sym} -1180 -880 0 0 {name=p_ibias lab=IBIAS}
C {devices/opin.sym} -1180 -820 0 0 {name=p_vref lab=VREF}
C {devices/opin.sym} -1180 -760 0 0 {name=p_bias_ok lab=BIAS_OK}
T {CORE MIRROR -- three matched legs on PG set the loop current; XMPBN is the
1/4-scale leg that generates the secondary bias rail. NOTHING ELSE hangs off
PG: every other current source is gated from PB instead, which is what keeps
the loop's second pole above its unity-gain frequency (design/bias_core.md,
"Compensation").} -1180 -250 0 0 0.4 0.4 {}
N -960 -150 -960 -190 {}
C {devices/lab_pin.sym} -960 -190 0 0 {name=l1 lab=VDD}
N -1000 -120 -1060 -120 {}
C {devices/lab_pin.sym} -1060 -120 0 0 {name=l2 lab=PG}
N -960 -90 -960 -50 {}
C {devices/lab_pin.sym} -960 -50 0 0 {name=l3 lab=NA}
N -960 -120 -910 -120 {}
C {devices/lab_pin.sym} -910 -120 0 0 {name=l4 lab=VDD}
C {symbols/pfet_03v3.sym} -980 -120 0 0 {name=MP1
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -720 -150 -720 -190 {}
C {devices/lab_pin.sym} -720 -190 0 0 {name=l5 lab=VDD}
N -760 -120 -820 -120 {}
C {devices/lab_pin.sym} -820 -120 0 0 {name=l6 lab=PG}
N -720 -90 -720 -50 {}
C {devices/lab_pin.sym} -720 -50 0 0 {name=l7 lab=NBTOP}
N -720 -120 -670 -120 {}
C {devices/lab_pin.sym} -670 -120 0 0 {name=l8 lab=VDD}
C {symbols/pfet_03v3.sym} -740 -120 0 0 {name=MP2
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -480 -150 -480 -190 {}
C {devices/lab_pin.sym} -480 -190 0 0 {name=l9 lab=VDD}
N -520 -120 -580 -120 {}
C {devices/lab_pin.sym} -580 -120 0 0 {name=l10 lab=PG}
N -480 -90 -480 -50 {}
C {devices/lab_pin.sym} -480 -50 0 0 {name=l11 lab=VREF}
N -480 -120 -430 -120 {}
C {devices/lab_pin.sym} -430 -120 0 0 {name=l12 lab=VDD}
C {symbols/pfet_03v3.sym} -500 -120 0 0 {name=MP3
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -240 -150 -240 -190 {}
C {devices/lab_pin.sym} -240 -190 0 0 {name=l13 lab=VDD}
N -280 -120 -340 -120 {}
C {devices/lab_pin.sym} -340 -120 0 0 {name=l14 lab=PG}
N -240 -90 -240 -50 {}
C {devices/lab_pin.sym} -240 -50 0 0 {name=l15 lab=NBG}
N -240 -120 -190 -120 {}
C {devices/lab_pin.sym} -190 -120 0 0 {name=l16 lab=VDD}
C {symbols/pfet_03v3.sym} -260 -120 0 0 {name=MPBN
L=4u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
T {SENSING CORE -- 8:1 vertical-PNP emitter-area ratio (pnp_10p00x10p00 unit
cell, eight parallel instances, per sim/devchar/SUMMARY.md). The amplifier
forces V(NA) = V(NB), so I = DVBE/R1 and the third leg drops that current on
R2 into a matched single PNP: VREF = VEB(XQR) + (R2/R1)*DVBE. XRT is the
small settle-detect offset resistor -- see the BIAS_OK band.} -1180 270 0 0 0.4 0.4 {}
N -960 370 -960 330 {}
C {devices/lab_pin.sym} -960 330 0 0 {name=l17 lab=NA}
N -1000 400 -1060 400 {}
C {devices/lab_pin.sym} -1060 400 0 0 {name=l18 lab=VSS}
N -960 430 -960 470 {}
C {devices/lab_pin.sym} -960 470 0 0 {name=l19 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -980 400 0 0 {name=Q1
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -740 430 -740 470 {}
C {devices/lab_pin.sym} -740 470 0 0 {name=l20 lab=NBTOP}
N -740 370 -740 330 {}
C {devices/lab_pin.sym} -740 330 0 0 {name=l21 lab=NB}
N -760 400 -820 400 {}
C {devices/lab_pin.sym} -820 400 0 0 {name=l22 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -740 400 0 0 {name=RT
W=2u
L=17.5u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -500 430 -500 470 {}
C {devices/lab_pin.sym} -500 470 0 0 {name=l23 lab=NB}
N -500 370 -500 330 {}
C {devices/lab_pin.sym} -500 330 0 0 {name=l24 lab=EC}
N -520 400 -580 400 {}
C {devices/lab_pin.sym} -580 400 0 0 {name=l25 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -500 400 0 0 {name=R1
W=2u
L=350.0u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -240 370 -240 330 {}
C {devices/lab_pin.sym} -240 330 0 0 {name=l26 lab=EC}
N -280 400 -340 400 {}
C {devices/lab_pin.sym} -340 400 0 0 {name=l27 lab=VSS}
N -240 430 -240 470 {}
C {devices/lab_pin.sym} -240 470 0 0 {name=l28 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -260 400 0 0 {name=Q8A
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 0 370 0 330 {}
C {devices/lab_pin.sym} 0 330 0 0 {name=l29 lab=EC}
N -40 400 -100 400 {}
C {devices/lab_pin.sym} -100 400 0 0 {name=l30 lab=VSS}
N 0 430 0 470 {}
C {devices/lab_pin.sym} 0 470 0 0 {name=l31 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -20 400 0 0 {name=Q8B
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 240 370 240 330 {}
C {devices/lab_pin.sym} 240 330 0 0 {name=l32 lab=EC}
N 200 400 140 400 {}
C {devices/lab_pin.sym} 140 400 0 0 {name=l33 lab=VSS}
N 240 430 240 470 {}
C {devices/lab_pin.sym} 240 470 0 0 {name=l34 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} 220 400 0 0 {name=Q8C
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N 480 370 480 330 {}
C {devices/lab_pin.sym} 480 330 0 0 {name=l35 lab=EC}
N 440 400 380 400 {}
C {devices/lab_pin.sym} 380 400 0 0 {name=l36 lab=VSS}
N 480 430 480 470 {}
C {devices/lab_pin.sym} 480 470 0 0 {name=l37 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} 460 400 0 0 {name=Q8D
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -960 630 -960 590 {}
C {devices/lab_pin.sym} -960 590 0 0 {name=l38 lab=EC}
N -1000 660 -1060 660 {}
C {devices/lab_pin.sym} -1060 660 0 0 {name=l39 lab=VSS}
N -960 690 -960 730 {}
C {devices/lab_pin.sym} -960 730 0 0 {name=l40 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -980 660 0 0 {name=Q8E
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -720 630 -720 590 {}
C {devices/lab_pin.sym} -720 590 0 0 {name=l41 lab=EC}
N -760 660 -820 660 {}
C {devices/lab_pin.sym} -820 660 0 0 {name=l42 lab=VSS}
N -720 690 -720 730 {}
C {devices/lab_pin.sym} -720 730 0 0 {name=l43 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -740 660 0 0 {name=Q8F
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -480 630 -480 590 {}
C {devices/lab_pin.sym} -480 590 0 0 {name=l44 lab=EC}
N -520 660 -580 660 {}
C {devices/lab_pin.sym} -580 660 0 0 {name=l45 lab=VSS}
N -480 690 -480 730 {}
C {devices/lab_pin.sym} -480 730 0 0 {name=l46 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -500 660 0 0 {name=Q8G
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -240 630 -240 590 {}
C {devices/lab_pin.sym} -240 590 0 0 {name=l47 lab=EC}
N -280 660 -340 660 {}
C {devices/lab_pin.sym} -340 660 0 0 {name=l48 lab=VSS}
N -240 690 -240 730 {}
C {devices/lab_pin.sym} -240 730 0 0 {name=l49 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} -260 660 0 0 {name=Q8H
model=pnp_10p00x10p00
spiceprefix=X
m=1}
N -20 690 -20 730 {}
C {devices/lab_pin.sym} -20 730 0 0 {name=l50 lab=VREF}
N -20 630 -20 590 {}
C {devices/lab_pin.sym} -20 590 0 0 {name=l51 lab=ER}
N -40 660 -100 660 {}
C {devices/lab_pin.sym} -100 660 0 0 {name=l52 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -20 660 0 0 {name=R2
W=2u
L=4104.0u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N 240 630 240 590 {}
C {devices/lab_pin.sym} 240 590 0 0 {name=l53 lab=ER}
N 200 660 140 660 {}
C {devices/lab_pin.sym} 140 660 0 0 {name=l54 lab=VSS}
N 240 690 240 730 {}
C {devices/lab_pin.sym} 240 730 0 0 {name=l55 lab=VSS}
C {symbols/pnp_10p00x10p00.sym} 220 660 0 0 {name=QR
model=pnp_10p00x10p00
spiceprefix=X
m=1}
T {SECONDARY BIAS RAIL PB -- PG -> XMPBN -> NBG -> XMBN2 -> XMBP -> PB. Every
wide-gate current source (the IBIAS output leg above all) is gated from PB,
not from PG, so its gate capacitance loads a low-impedance diode node instead
of the amplifier's output. PB is also the cell's "core is biased" indicator:
it collapses to VDD whenever the loop carries no current, which is what the
startup detector below keys off.} -1180 1050 0 0 0.4 0.4 {}
N -960 1150 -960 1110 {}
C {devices/lab_pin.sym} -960 1110 0 0 {name=l56 lab=NBG}
N -1000 1180 -1060 1180 {}
C {devices/lab_pin.sym} -1060 1180 0 0 {name=l57 lab=NBG}
N -960 1210 -960 1250 {}
C {devices/lab_pin.sym} -960 1250 0 0 {name=l58 lab=VSS}
N -960 1180 -910 1180 {}
C {devices/lab_pin.sym} -910 1180 0 0 {name=l59 lab=VSS}
C {symbols/nfet_03v3.sym} -980 1180 0 0 {name=MBN
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -720 1150 -720 1110 {}
C {devices/lab_pin.sym} -720 1110 0 0 {name=l60 lab=PB}
N -760 1180 -820 1180 {}
C {devices/lab_pin.sym} -820 1180 0 0 {name=l61 lab=NBG}
N -720 1210 -720 1250 {}
C {devices/lab_pin.sym} -720 1250 0 0 {name=l62 lab=VSS}
N -720 1180 -670 1180 {}
C {devices/lab_pin.sym} -670 1180 0 0 {name=l63 lab=VSS}
C {symbols/nfet_03v3.sym} -740 1180 0 0 {name=MBN2
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -480 1150 -480 1110 {}
C {devices/lab_pin.sym} -480 1110 0 0 {name=l64 lab=VDD}
N -520 1180 -580 1180 {}
C {devices/lab_pin.sym} -580 1180 0 0 {name=l65 lab=PB}
N -480 1210 -480 1250 {}
C {devices/lab_pin.sym} -480 1250 0 0 {name=l66 lab=PB}
N -480 1180 -430 1180 {}
C {devices/lab_pin.sym} -430 1180 0 0 {name=l67 lab=VDD}
C {symbols/pfet_03v3.sym} -500 1180 0 0 {name=MBP
L=4u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -240 1150 -240 1110 {}
C {devices/lab_pin.sym} -240 1110 0 0 {name=l68 lab=VDD}
N -280 1180 -340 1180 {}
C {devices/lab_pin.sym} -340 1180 0 0 {name=l69 lab=PB}
N -240 1210 -240 1250 {}
C {devices/lab_pin.sym} -240 1250 0 0 {name=l70 lab=IBIAS}
N -240 1180 -190 1180 {}
C {devices/lab_pin.sym} -190 1180 0 0 {name=l71 lab=VDD}
C {symbols/pfet_03v3.sym} -260 1180 0 0 {name=MPIB
L=4u
W=40u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
T {ERROR AMPLIFIER -- PMOS input pair (the inputs sit at a VEB, which falls to
~0.36 V at 125 C, far below an NMOS pair's usable common mode), NMOS mirror
load, NMOS common-source second stage, Miller-compensated with a nulling
resistor. Same structure as design/temp_core.sch's amplifier. XMS2N is a
current-density copy of XML1, so the systematic input offset is structurally
near zero rather than a residual.} -1180 1570 0 0 0.4 0.4 {}
N -960 1670 -960 1630 {}
C {devices/lab_pin.sym} -960 1630 0 0 {name=l72 lab=VDD}
N -1000 1700 -1060 1700 {}
C {devices/lab_pin.sym} -1060 1700 0 0 {name=l73 lab=PB}
N -960 1730 -960 1770 {}
C {devices/lab_pin.sym} -960 1770 0 0 {name=l74 lab=NT}
N -960 1700 -910 1700 {}
C {devices/lab_pin.sym} -910 1700 0 0 {name=l75 lab=VDD}
C {symbols/pfet_03v3.sym} -980 1700 0 0 {name=MPT
L=4u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -720 1670 -720 1630 {}
C {devices/lab_pin.sym} -720 1630 0 0 {name=l76 lab=NT}
N -760 1700 -820 1700 {}
C {devices/lab_pin.sym} -820 1700 0 0 {name=l77 lab=NA}
N -720 1730 -720 1770 {}
C {devices/lab_pin.sym} -720 1770 0 0 {name=l78 lab=N1}
N -720 1700 -670 1700 {}
C {devices/lab_pin.sym} -670 1700 0 0 {name=l79 lab=VDD}
C {symbols/pfet_03v3.sym} -740 1700 0 0 {name=MI1
L=4u
W=16u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -480 1670 -480 1630 {}
C {devices/lab_pin.sym} -480 1630 0 0 {name=l80 lab=NT}
N -520 1700 -580 1700 {}
C {devices/lab_pin.sym} -580 1700 0 0 {name=l81 lab=NB}
N -480 1730 -480 1770 {}
C {devices/lab_pin.sym} -480 1770 0 0 {name=l82 lab=N2}
N -480 1700 -430 1700 {}
C {devices/lab_pin.sym} -430 1700 0 0 {name=l83 lab=VDD}
C {symbols/pfet_03v3.sym} -500 1700 0 0 {name=MI2
L=4u
W=16u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -240 1670 -240 1630 {}
C {devices/lab_pin.sym} -240 1630 0 0 {name=l84 lab=N1}
N -280 1700 -340 1700 {}
C {devices/lab_pin.sym} -340 1700 0 0 {name=l85 lab=N1}
N -240 1730 -240 1770 {}
C {devices/lab_pin.sym} -240 1770 0 0 {name=l86 lab=VSS}
N -240 1700 -190 1700 {}
C {devices/lab_pin.sym} -190 1700 0 0 {name=l87 lab=VSS}
C {symbols/nfet_03v3.sym} -260 1700 0 0 {name=ML1
L=8u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 0 1670 0 1630 {}
C {devices/lab_pin.sym} 0 1630 0 0 {name=l88 lab=N2}
N -40 1700 -100 1700 {}
C {devices/lab_pin.sym} -100 1700 0 0 {name=l89 lab=N1}
N 0 1730 0 1770 {}
C {devices/lab_pin.sym} 0 1770 0 0 {name=l90 lab=VSS}
N 0 1700 50 1700 {}
C {devices/lab_pin.sym} 50 1700 0 0 {name=l91 lab=VSS}
C {symbols/nfet_03v3.sym} -20 1700 0 0 {name=ML2
L=8u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 240 1670 240 1630 {}
C {devices/lab_pin.sym} 240 1630 0 0 {name=l92 lab=PG}
N 200 1700 140 1700 {}
C {devices/lab_pin.sym} 140 1700 0 0 {name=l93 lab=N2}
N 240 1730 240 1770 {}
C {devices/lab_pin.sym} 240 1770 0 0 {name=l94 lab=VSS}
N 240 1700 290 1700 {}
C {devices/lab_pin.sym} 290 1700 0 0 {name=l95 lab=VSS}
C {symbols/nfet_03v3.sym} 220 1700 0 0 {name=MS2N
L=8u
W=8u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 480 1670 480 1630 {}
C {devices/lab_pin.sym} 480 1630 0 0 {name=l96 lab=VDD}
N 440 1700 380 1700 {}
C {devices/lab_pin.sym} 380 1700 0 0 {name=l97 lab=PB}
N 480 1730 480 1770 {}
C {devices/lab_pin.sym} 480 1770 0 0 {name=l98 lab=PG}
N 480 1700 530 1700 {}
C {devices/lab_pin.sym} 530 1700 0 0 {name=l99 lab=VDD}
C {symbols/pfet_03v3.sym} 460 1700 0 0 {name=MS2P
L=4u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -980 1930 -980 1890 {}
C {devices/lab_pin.sym} -980 1890 0 0 {name=l100 lab=PG}
N -980 1990 -980 2030 {}
C {devices/lab_pin.sym} -980 2030 0 0 {name=l101 lab=NZ}
C {symbols/cap_mim_analog.sym} -980 1960 0 0 {name=CC
W=20u
L=20u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=1}
N -740 1990 -740 2030 {}
C {devices/lab_pin.sym} -740 2030 0 0 {name=l102 lab=NZ}
N -740 1930 -740 1890 {}
C {devices/lab_pin.sym} -740 1890 0 0 {name=l103 lab=N2}
N -760 1960 -820 1960 {}
C {devices/lab_pin.sym} -820 1960 0 0 {name=l104 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -740 1960 0 0 {name=RZ
W=2u
L=1016.0u
model=ppolyf_u_3k
spiceprefix=X
m=1}
T {STARTUP KICK (DR-005 step 3) -- CURRENT-referenced dead-loop detector.
XKS0..XKS4 is a five-deep diode-connected nfet stack: a rail-referenced
pull-up on NKG that is deliberately deep in subthreshold, so it costs <20 nA
at every corner yet always conducts. XKA is a PB-gated replica -- it delivers
current only while the loop is biased -- and XKAN/XKPD mirror it into a
pull-down on NKG that beats the stack by >2x. Loop alive: NKG ~ 0, XKICK
idle. Loop dead: PB collapses to VDD, XKA delivers nothing, NKG rises and
XKICK pulls the mirror gate PG down until the loop restarts.
The comparison is loop current vs. rail-referenced current, NOT a voltage
level on VREF: an earlier revision gated this on V(VREF) > Vt and left the
core sitting near zero current for ~200 us after a deep brownout at fs/-40 C,
because 0.7 V of a not-yet-settled VREF already looks like "alive" to an
nfet gate. Measured, not hypothetical -- see design/bias_core.md, "Startup".} -1180 2350 0 0 0.4 0.4 {}
N -960 2450 -960 2410 {}
C {devices/lab_pin.sym} -960 2410 0 0 {name=l105 lab=VDD}
N -1000 2480 -1060 2480 {}
C {devices/lab_pin.sym} -1060 2480 0 0 {name=l106 lab=VDD}
N -960 2510 -960 2550 {}
C {devices/lab_pin.sym} -960 2550 0 0 {name=l107 lab=KS1}
N -960 2480 -910 2480 {}
C {devices/lab_pin.sym} -910 2480 0 0 {name=l108 lab=VSS}
C {symbols/nfet_03v3.sym} -980 2480 0 0 {name=KS0
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -720 2450 -720 2410 {}
C {devices/lab_pin.sym} -720 2410 0 0 {name=l109 lab=KS1}
N -760 2480 -820 2480 {}
C {devices/lab_pin.sym} -820 2480 0 0 {name=l110 lab=KS1}
N -720 2510 -720 2550 {}
C {devices/lab_pin.sym} -720 2550 0 0 {name=l111 lab=KS2}
N -720 2480 -670 2480 {}
C {devices/lab_pin.sym} -670 2480 0 0 {name=l112 lab=VSS}
C {symbols/nfet_03v3.sym} -740 2480 0 0 {name=KS1
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -480 2450 -480 2410 {}
C {devices/lab_pin.sym} -480 2410 0 0 {name=l113 lab=KS2}
N -520 2480 -580 2480 {}
C {devices/lab_pin.sym} -580 2480 0 0 {name=l114 lab=KS2}
N -480 2510 -480 2550 {}
C {devices/lab_pin.sym} -480 2550 0 0 {name=l115 lab=KS3}
N -480 2480 -430 2480 {}
C {devices/lab_pin.sym} -430 2480 0 0 {name=l116 lab=VSS}
C {symbols/nfet_03v3.sym} -500 2480 0 0 {name=KS2
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -240 2450 -240 2410 {}
C {devices/lab_pin.sym} -240 2410 0 0 {name=l117 lab=KS3}
N -280 2480 -340 2480 {}
C {devices/lab_pin.sym} -340 2480 0 0 {name=l118 lab=KS3}
N -240 2510 -240 2550 {}
C {devices/lab_pin.sym} -240 2550 0 0 {name=l119 lab=KS4}
N -240 2480 -190 2480 {}
C {devices/lab_pin.sym} -190 2480 0 0 {name=l120 lab=VSS}
C {symbols/nfet_03v3.sym} -260 2480 0 0 {name=KS3
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 0 2450 0 2410 {}
C {devices/lab_pin.sym} 0 2410 0 0 {name=l121 lab=KS4}
N -40 2480 -100 2480 {}
C {devices/lab_pin.sym} -100 2480 0 0 {name=l122 lab=KS4}
N 0 2510 0 2550 {}
C {devices/lab_pin.sym} 0 2550 0 0 {name=l123 lab=NKG}
N 0 2480 50 2480 {}
C {devices/lab_pin.sym} 50 2480 0 0 {name=l124 lab=VSS}
C {symbols/nfet_03v3.sym} -20 2480 0 0 {name=KS4
L=8u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 240 2450 240 2410 {}
C {devices/lab_pin.sym} 240 2410 0 0 {name=l125 lab=VDD}
N 200 2480 140 2480 {}
C {devices/lab_pin.sym} 140 2480 0 0 {name=l126 lab=PB}
N 240 2510 240 2550 {}
C {devices/lab_pin.sym} 240 2550 0 0 {name=l127 lab=NKM}
N 240 2480 290 2480 {}
C {devices/lab_pin.sym} 290 2480 0 0 {name=l128 lab=VDD}
C {symbols/pfet_03v3.sym} 220 2480 0 0 {name=KA
L=4u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 480 2450 480 2410 {}
C {devices/lab_pin.sym} 480 2410 0 0 {name=l129 lab=NKM}
N 440 2480 380 2480 {}
C {devices/lab_pin.sym} 380 2480 0 0 {name=l130 lab=NKM}
N 480 2510 480 2550 {}
C {devices/lab_pin.sym} 480 2550 0 0 {name=l131 lab=VSS}
N 480 2480 530 2480 {}
C {devices/lab_pin.sym} 530 2480 0 0 {name=l132 lab=VSS}
C {symbols/nfet_03v3.sym} 460 2480 0 0 {name=KAN
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -960 2710 -960 2670 {}
C {devices/lab_pin.sym} -960 2670 0 0 {name=l133 lab=NKG}
N -1000 2740 -1060 2740 {}
C {devices/lab_pin.sym} -1060 2740 0 0 {name=l134 lab=NKM}
N -960 2770 -960 2810 {}
C {devices/lab_pin.sym} -960 2810 0 0 {name=l135 lab=VSS}
N -960 2740 -910 2740 {}
C {devices/lab_pin.sym} -910 2740 0 0 {name=l136 lab=VSS}
C {symbols/nfet_03v3.sym} -980 2740 0 0 {name=KPD
L=4u
W=8u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -720 2710 -720 2670 {}
C {devices/lab_pin.sym} -720 2670 0 0 {name=l137 lab=PG}
N -760 2740 -820 2740 {}
C {devices/lab_pin.sym} -820 2740 0 0 {name=l138 lab=NKG}
N -720 2770 -720 2810 {}
C {devices/lab_pin.sym} -720 2810 0 0 {name=l139 lab=VSS}
N -720 2740 -670 2740 {}
C {devices/lab_pin.sym} -670 2740 0 0 {name=l140 lab=VSS}
C {symbols/nfet_03v3.sym} -740 2740 0 0 {name=KICK
L=4u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {BIAS_OK -- settle detector (DR-005 startup ordering, step 4). XRT taps a
small same-flavour fraction of R1 off branch B, so
  V(NBTOP) - V(NA) = I*(R1 + RT) - DVBE,
which is negative until the loop current reaches R1/(R1+RT) = 95.2 % of its
settled value and is +I*RT (a PVT-stable 2.1-3.6 mV, PTAT) once settled.
XMOKA/XMOKB compare exactly that, XMOK2 turns the comparison into a
rail-to-rail level, and XMO1P/XMO1N buffer it out. XMOKC forces the answer
to "not valid" whenever the startup detector says the loop is dead -- without
it, a collapsed core leaves NOKO stale (no tail current to move it) and
BIAS_OK reads a false valid for as long as the restart takes.
The detector is deliberately ONE-SIDED. Reference LOW is the dangerous
direction (it lowers por_comparator's threshold, i.e. early release / late
re-assert) and is what this gate catches; reference HIGH only delays release,
which is safe by construction. XCOK holds NOKX up through the first
microseconds of a rail ramp so BIAS_OK cannot glitch valid before anything
is biased; XMO1P is deliberately weak and XMO1N strong for the same reason.} -1180 3130 0 0 0.4 0.4 {}
N -960 3230 -960 3190 {}
C {devices/lab_pin.sym} -960 3190 0 0 {name=l141 lab=VDD}
N -1000 3260 -1060 3260 {}
C {devices/lab_pin.sym} -1060 3260 0 0 {name=l142 lab=PB}
N -960 3290 -960 3330 {}
C {devices/lab_pin.sym} -960 3330 0 0 {name=l143 lab=TOK}
N -960 3260 -910 3260 {}
C {devices/lab_pin.sym} -910 3260 0 0 {name=l144 lab=VDD}
C {symbols/pfet_03v3.sym} -980 3260 0 0 {name=MPOK
L=4u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -720 3230 -720 3190 {}
C {devices/lab_pin.sym} -720 3190 0 0 {name=l145 lab=TOK}
N -760 3260 -820 3260 {}
C {devices/lab_pin.sym} -820 3260 0 0 {name=l146 lab=NA}
N -720 3290 -720 3330 {}
C {devices/lab_pin.sym} -720 3330 0 0 {name=l147 lab=NOKO}
N -720 3260 -670 3260 {}
C {devices/lab_pin.sym} -670 3260 0 0 {name=l148 lab=VDD}
C {symbols/pfet_03v3.sym} -740 3260 0 0 {name=MOKA
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -480 3230 -480 3190 {}
C {devices/lab_pin.sym} -480 3190 0 0 {name=l149 lab=TOK}
N -520 3260 -580 3260 {}
C {devices/lab_pin.sym} -580 3260 0 0 {name=l150 lab=NBTOP}
N -480 3290 -480 3330 {}
C {devices/lab_pin.sym} -480 3330 0 0 {name=l151 lab=NOKL}
N -480 3260 -430 3260 {}
C {devices/lab_pin.sym} -430 3260 0 0 {name=l152 lab=VDD}
C {symbols/pfet_03v3.sym} -500 3260 0 0 {name=MOKB
L=4u
W=8u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -240 3230 -240 3190 {}
C {devices/lab_pin.sym} -240 3190 0 0 {name=l153 lab=NOKL}
N -280 3260 -340 3260 {}
C {devices/lab_pin.sym} -340 3260 0 0 {name=l154 lab=NOKL}
N -240 3290 -240 3330 {}
C {devices/lab_pin.sym} -240 3330 0 0 {name=l155 lab=VSS}
N -240 3260 -190 3260 {}
C {devices/lab_pin.sym} -190 3260 0 0 {name=l156 lab=VSS}
C {symbols/nfet_03v3.sym} -260 3260 0 0 {name=MOL1
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 0 3230 0 3190 {}
C {devices/lab_pin.sym} 0 3190 0 0 {name=l157 lab=NOKO}
N -40 3260 -100 3260 {}
C {devices/lab_pin.sym} -100 3260 0 0 {name=l158 lab=NOKL}
N 0 3290 0 3330 {}
C {devices/lab_pin.sym} 0 3330 0 0 {name=l159 lab=VSS}
N 0 3260 50 3260 {}
C {devices/lab_pin.sym} 50 3260 0 0 {name=l160 lab=VSS}
C {symbols/nfet_03v3.sym} -20 3260 0 0 {name=MOL2
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 240 3230 240 3190 {}
C {devices/lab_pin.sym} 240 3190 0 0 {name=l161 lab=NOKO}
N 200 3260 140 3260 {}
C {devices/lab_pin.sym} 140 3260 0 0 {name=l162 lab=NKG}
N 240 3290 240 3330 {}
C {devices/lab_pin.sym} 240 3330 0 0 {name=l163 lab=VSS}
N 240 3260 290 3260 {}
C {devices/lab_pin.sym} 290 3260 0 0 {name=l164 lab=VSS}
C {symbols/nfet_03v3.sym} 220 3260 0 0 {name=MOKC
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 480 3230 480 3190 {}
C {devices/lab_pin.sym} 480 3190 0 0 {name=l165 lab=NOKX}
N 440 3260 380 3260 {}
C {devices/lab_pin.sym} 380 3260 0 0 {name=l166 lab=NOKO}
N 480 3290 480 3330 {}
C {devices/lab_pin.sym} 480 3330 0 0 {name=l167 lab=VSS}
N 480 3260 530 3260 {}
C {devices/lab_pin.sym} 530 3260 0 0 {name=l168 lab=VSS}
C {symbols/nfet_03v3.sym} 460 3260 0 0 {name=MOK2
L=4u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -960 3490 -960 3450 {}
C {devices/lab_pin.sym} -960 3450 0 0 {name=l169 lab=VDD}
N -1000 3520 -1060 3520 {}
C {devices/lab_pin.sym} -1060 3520 0 0 {name=l170 lab=PB}
N -960 3550 -960 3590 {}
C {devices/lab_pin.sym} -960 3590 0 0 {name=l171 lab=NOKX}
N -960 3520 -910 3520 {}
C {devices/lab_pin.sym} -910 3520 0 0 {name=l172 lab=VDD}
C {symbols/pfet_03v3.sym} -980 3520 0 0 {name=MOK2P
L=4u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 3490 -740 3450 {}
C {devices/lab_pin.sym} -740 3450 0 0 {name=l173 lab=VDD}
N -740 3550 -740 3590 {}
C {devices/lab_pin.sym} -740 3590 0 0 {name=l174 lab=NOKX}
C {symbols/cap_mim_analog.sym} -740 3520 0 0 {name=COK
W=6u
L=6u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=1}
N -480 3490 -480 3450 {}
C {devices/lab_pin.sym} -480 3450 0 0 {name=l175 lab=VDD}
N -520 3520 -580 3520 {}
C {devices/lab_pin.sym} -580 3520 0 0 {name=l176 lab=NOKX}
N -480 3550 -480 3590 {}
C {devices/lab_pin.sym} -480 3590 0 0 {name=l177 lab=BIAS_OK}
N -480 3520 -430 3520 {}
C {devices/lab_pin.sym} -430 3520 0 0 {name=l178 lab=VDD}
C {symbols/pfet_03v3.sym} -500 3520 0 0 {name=MO1P
L=4u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -240 3490 -240 3450 {}
C {devices/lab_pin.sym} -240 3450 0 0 {name=l179 lab=BIAS_OK}
N -280 3520 -340 3520 {}
C {devices/lab_pin.sym} -340 3520 0 0 {name=l180 lab=NOKX}
N -240 3550 -240 3590 {}
C {devices/lab_pin.sym} -240 3590 0 0 {name=l181 lab=VSS}
N -240 3520 -190 3520 {}
C {devices/lab_pin.sym} -190 3520 0 0 {name=l182 lab=VSS}
C {symbols/nfet_03v3.sym} -260 3520 0 0 {name=MO1N
L=0.5u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
