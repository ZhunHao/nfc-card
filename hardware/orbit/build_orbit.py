#!/usr/bin/env python3
"""Lay out the C1 Orbit card from its true-scale geometry.

Run with KiCad 10's Python (it needs pcbnew):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      hardware/orbit/build_orbit.py

Idempotent. Keeps L1, U1, C1, C2 and the U1-C2 VOUT/GND stubs as copied from
the NTUAS card, and rebuilds the LA/LB feed for the rev B antenna (option A,
whose outer pad moved); regenerates everything else: LED/MCU placement, the
Charlieplex routing, the power runs, the back test pads and all silkscreen.

Rev B MCU block (concept mm, U2 = ATtiny1616 VQFN-20 at 90 deg, pin 1
bottom-left): PA1 leaves the left side and PA2/PA3 the bottom side straight to
R1-R3 on F.Cu; PA4/PA5 drop to vias and run under the block on B.Cu to R4/R5.
VCC and GND leave the bottom side into C3 (EP tied to pin 3 inside the body).
UPDI (via R6) and the soft-start's SS_GATE cross over the top; Q1/R7/R8/C4
sit right of U2 against a VCC spine that climbs to the back test pads.
TP1-TP3 are on B.Cu in a 2.54 mm column at the top right, each fed by a via
beside the pad; D21 sits on the front behind TP1.

Geometry (concept mm from the card's top-left; KiCad = concept + 100):
Earth R = 80 mm centred at (43, 118), 1 mm = 6371/80 km. Every arc, bus and
LED shares that centre, so the orbits are concentric with Earth.

Routing scheme: each orbit row has five concentric B.Cu bus arcs (one per
Charlieplex net). Every LED pad drops a short radial F.Cu stub to a via on its
net's bus. One radial F.Cu trunk, between LEDs, joins both bus sets to R1-R5
and carries VOUT/GND up from U1. The ground stations share the ISS buses; the
ISS LED above each station only uses buses outside the station's.
"""
import math
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))
sys.path.insert(0, str(HERE.parent))
import board_thickness  # noqa: E402
import contact  # noqa: E402
import jlc_dfm  # noqa: E402
BOARD_PATH = HERE / 'orbit.kicad_pcb'
# Optional output path (used by export-card.py --contact for a private copy).
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else BOARD_PATH

CX, CY, R_EARTH = 43.0, 118.0, 80.0
KM_PER_MM = 6371.0 / 80.0
R_ISS = R_EARTH + 420.0 / KM_PER_MM
R_TOP = R_EARTH + 2000.0 / KM_PER_MM
ISS_X = [12, 19.8, 27.6, 35.4, 43.2, 51, 58.8, 66.6, 74.4]
TOP_X = [11, 19.5, 28, 36.5, 45, 53.5, 62, 70.5]
# Concept stations are x = 20, 43, 66. x = 20 lands on U1/C2 at the antenna
# feed, so that station moves right along the limb to sit under the ISS LED
# at x = 27.6 (see README.md).
STATION_X = [27.6, 43, 66]
STATION_DROP = 2.6

# LED index k (D[k+1]) per position. Anode CP[k/4], cathode CP[c] with
# c = (k%4) < (k/4) ? k%4 : k%4+1. The ISS LED over each station uses only
# nets numbered below both of the station's nets (bus layering, see above).
ISS_K = [1, 2, 0, 3, 5, 6, 7, 4, 8]
TOP_K = [9, 12, 13, 14, 16, 17, 18, 19]
STATION_K = [10, 15, 11]

BUS_PITCH = 0.85
ISS_BUS = [R_ISS - 1.35 - i * BUS_PITCH for i in range(5)]   # index = CP net
TOP_BUS = [R_TOP + 1.35 + i * BUS_PITCH for i in range(5)]
TRUNK_SIN = 12.0 / R_ISS            # radial line through the ISS arc at x = 55
TRUNK_T = {'/CP4': -2.1, '/CP3': -1.4, '/CP2': -0.7, '/CP1': 0.0, '/CP0': 0.7,
           '/GND': 1.4, '/VOUT': 2.1}
W_SIG, W_PWR = 0.2, 0.25
VIA_D, VIA_DRILL = 0.65, 0.3  # 0.175 mm ring; JLCDFM grades 0.15 mm a warning

U2_AT = (69.5, 23.0)                 # VQFN-20, 90 deg: pins 1-5 along the bottom
R_X = 61.8
R_Y = {'R1': 23.8, 'R2': 24.8, 'R3': 25.8, 'R4': 26.8, 'R5': 27.8}   # PA1..PA5
JP1_AT, C3_AT = (61.2, 30.6), (69.7, 26.7)
R6_AT = (66.7, 20.6)                 # UPDI series resistor, above U2
SS_AT = {'R8': ((74.2, 21.3), 180), 'R7': ((74.2, 22.3), 180),
         'Q1': ((73.9, 23.6), 90), 'C4': ((72.75, 22.6), 90)}
PA4_VIA, PA5_VIA = (70.6, 25.7), (71.5, 25.0)
PA_NEAR_X = 63.3                     # B.Cu PA4/PA5 surface next to R4/R5
SS_GATE_Y, SS_GATE_X = 20.6, 72.0
UPDI_Y, UPDI_X = 19.4, 74.25         # UPDI over the top, then up to TP1
VCC_X = 75.5                         # VCC spine up the right side to TP2
GND_X = VCC_X                        # B.Cu GND runs right under the VCC rail and
                                     # spine (broadside pair: tiny VCC/GND loop area)
C4_GND_VIA = (72.75, 21.3)
GND_C3_VIA = (69.0, 29.8)
# Back test pads: 2.54 mm column (0.1" pogo clip), UPDI-VCC-GND, VCC in the
# middle. Each pad's via sits 1.25 mm to its left, never in the pad.
TP_X, TP_VIA_X = 77.5, 76.25
TP_Y = {'TP1': 7.8, 'TP2': 10.34, 'TP3': 12.88}   # GND label clears the back name
TP_LABEL = {'TP1': 'UPDI', 'TP2': 'VCC', 'TP3': 'GND'}
D21_AT = (77.55, 8.25)               # front, behind TP1; GND runs down to TP3's via
VCC_Y, VOUT_Y, GND_BRANCH_Y = 30.6, 30.6, 29.8
U1_VOUT_NODE, U1_VOUT_VIA = (21.112, 42.937), (21.9, 42.937)
U1_GND_NODE, U1_GND_VIA = (20.638, 44.577), (21.4, 44.577)

# Copied NTUAS U1-C2 stubs that stay (KiCad coordinates, width).
KEEP_TRACKS = {
    '/VOUT': [((118.6, 143.5), (119.102, 143.5), 0.15), ((119.102, 143.5), (119.102, 143.359), 0.2),
              ((119.102, 143.359), (119.524, 142.937), 0.2), ((119.524, 142.937), (121.112, 142.937), 0.2),
              ((120.0, 144.48), (119.258, 143.738), 0.2), ((119.258, 143.738), (119.258, 143.565), 0.2),
              ((119.258, 143.565), (119.166, 143.565), 0.15), ((119.166, 143.565), (119.102, 143.5), 0.15)],
    '/GND': [((117.4, 144.0), (117.335, 144.065), 0.15), ((117.335, 144.065), (116.884, 144.065), 0.15),
             ((116.884, 144.065), (116.847, 144.065), 0.15), ((116.847, 144.065), (116.745, 144.167), 0.15),
             ((116.745, 144.167), (116.745, 144.658), 0.2), ((116.745, 144.658), (117.216, 145.13), 0.2),
             ((117.216, 145.13), (120.29, 145.13), 0.2), ((120.29, 145.13), (120.638, 144.782), 0.2),
             ((120.638, 144.782), (120.638, 144.158), 0.2), ((120.638, 144.158), (120.0, 143.52), 0.2)],
}

CLIP = (6.6, 6.6, 85.6 - 6.6, 53.98 - 6.6)   # artwork stays inside the antenna
SILK_PAD_CLEAR = 0.25                         # JLC recommends >= 0.25 mm to pads
TEXT_H, TEXT_W = 1.0, 0.15                    # JLC standard silkscreen minimum
TLE_CW = 0.62                                 # TLE glyph width (height stays 1.0)

board = pcbnew.LoadBoard(str(BOARD_PATH))
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
FSILK, BSILK = pcbnew.F_SilkS, pcbnew.B_SilkS


def kv(p):
    return pcbnew.VECTOR2I(pcbnew.FromMM(100 + p[0]), pcbnew.FromMM(100 + p[1]))


def polar(r, th):
    return (CX + r * math.sin(th), CY - r * math.cos(th))


def to_polar(p):
    dx, dy = p[0] - CX, CY - p[1]
    return math.hypot(dx, dy), math.atan2(dx, dy)


def arc_y(r, x):
    return CY - math.sqrt(r * r - (x - CX) ** 2)


def net(name):
    return board.GetNetInfo().GetNetItem(name)


# Antenna feed (KiCad coordinates). The NTUAS U1-C1 part stays; option A's
# outer pad (LA) moved to (120, 151.53) and its inner pad (LB) to (114.4, 147.33),
# so the old LA via at (120, 150.7), now inside coil turn 2, is gone: LA runs
# on B.Cu outside the coil to a via at (120, 152.9) and back up to the pad.
LA_LB_TRACKS = [
    ('/LA', FCU, [(117.4, 143.5), (116.6, 143.5), (116.0, 142.9), (116.0, 142.48)]),
    ('/LA', BCU, [(116.6, 143.5), (115.8, 143.5), (115.8, 147.3), (115.8, 152.9), (120.0, 152.9)]),
    ('/LA', FCU, [(120.0, 152.9), (120.0, 151.53)]),
    ('/LB', FCU, [(118.0, 143.4), (118.0, 142.4), (117.12, 141.52), (116.0, 141.52),
                  (115.3, 140.82), (114.7, 140.82), (114.7, 146.58), (114.4, 146.88),
                  (114.4, 147.33)]),
]
LA_VIAS = [(116.6, 143.5), (120.0, 152.9)]

# ---------------------------------------------------------------- clean slate
stale = [d for d in board.GetDrawings() if d.GetLayer() != pcbnew.Edge_Cuts]
stale += list(board.GetTracks())
for item in stale:
    board.Remove(item)


def track(a, b, name, w=W_SIG, layer=FCU, kicad=False):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])) if kicad else kv(a))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])) if kicad else kv(b))
    t.SetWidth(pcbnew.FromMM(w))
    t.SetLayer(layer)
    t.SetNet(net(name))
    board.Add(t)


def path(points, name, w=W_SIG, layer=FCU):
    for a, b in zip(points, points[1:]):
        track(a, b, name, w, layer)


def via(p, name, kicad=False):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])) if kicad else kv(p))
    v.SetWidth(pcbnew.FromMM(VIA_D))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetNet(net(name))
    board.Add(v)


def bus_arc(r, th0, th1, name, w=W_SIG):
    a = pcbnew.PCB_ARC(board)
    a.SetStart(kv(polar(r, th0)))
    a.SetMid(kv(polar(r, (th0 + th1) / 2)))
    a.SetEnd(kv(polar(r, th1)))
    a.SetWidth(pcbnew.FromMM(w))
    a.SetLayer(BCU)
    a.SetNet(net(name))
    board.Add(a)


for name, segs in KEEP_TRACKS.items():
    for a, b, w in segs:
        track(a, b, name, w, kicad=True)
for name, layer, pts in LA_LB_TRACKS:
    for a, b in zip(pts, pts[1:]):
        track(a, b, name, 0.15, layer, kicad=True)
for p in LA_VIAS:
    via(p, '/LA', kicad=True)

# ------------------------------------------------------------------ placement
fp = {f.GetReference(): f for f in board.GetFootprints()}


for f in fp.values():                # as on the NTUAS card: no reference text on silk
    f.Reference().SetVisible(False)


def place(ref, p, rot):
    f = fp[ref]
    f.SetPosition(kv(p))
    f.SetOrientationDegrees(rot)


def pad_xy(ref, num):
    for pd in fp[ref].Pads():
        if pd.GetNumber() == num:
            q = pd.GetPosition()
            return (pcbnew.ToMM(q.x) - 100, pcbnew.ToMM(q.y) - 100)
    raise KeyError((ref, num))


def pad_net(ref, num):
    return next(pd.GetNetname() for pd in fp[ref].Pads() if pd.GetNumber() == num)


def cp_index(name):
    return int(name[-1])


leds = []   # (ref, row, centre, theta)
for x, k in zip(ISS_X, ISS_K):
    leds.append((f'D{k + 1}', 'iss', x))
for x, k in zip(TOP_X, TOP_K):
    leds.append((f'D{k + 1}', 'top', x))
for x, k in zip(STATION_X, STATION_K):
    leds.append((f'D{k + 1}', 'station', x))
assert sorted(int(r[1:]) for r, _, _ in leds) == list(range(1, 21))

placed = []
for ref, row, x in leds:
    if row == 'station':
        c = (x, arc_y(R_EARTH, x) + STATION_DROP)
        r, th = to_polar(c)
    else:
        r = R_ISS if row == 'iss' else R_TOP
        th = math.asin((x - CX) / r)
        c = polar(r, th)
    # Tangent to the orbit; lower-numbered net on the left-hand pad.
    flip = cp_index(pad_net(ref, '1')) > cp_index(pad_net(ref, '2'))
    place(ref, c, round(-math.degrees(th) + (180 if flip else 0), 1))
    placed.append((ref, row, r, th))

place('U2', U2_AT, 90)
for ref, y in R_Y.items():
    place(ref, (R_X, y), 180)
place('JP1', JP1_AT, 0)
place('C3', C3_AT, 180)              # GND pad left, VCC pad right, under pins 3/4
place('R6', R6_AT, 270)              # UPDI on top, UPDI_MCU at the bottom
for ref, (p, rot) in SS_AT.items():
    place(ref, p, rot)
place('D21', D21_AT, 90)             # UPDI pad on top, GND below


def place_back(ref, p):
    f = fp[ref]
    if f.GetLayer() != BCU:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetPosition(kv(p))
    f.SetOrientationDegrees(0)
    assert f.GetLayer() == BCU, ref


for ref, y in TP_Y.items():
    place_back(ref, (TP_X, y))

# The routing below relies on this pinout (ATtiny1616 VQFN-20 and friends).
EXPECT = {('U2', '1'): '/PA2', ('U2', '2'): '/PA3', ('U2', '3'): '/GND', ('U2', '4'): '/VCC',
          ('U2', '5'): '/PA4', ('U2', '6'): '/PA5', ('U2', '15'): '/SS_GATE',
          ('U2', '19'): '/UPDI_MCU', ('U2', '20'): '/PA1', ('U2', '21'): '/GND',
          ('R1', '1'): '/PA1', ('R2', '1'): '/PA2', ('R3', '1'): '/PA3', ('R4', '1'): '/PA4',
          ('R5', '1'): '/PA5', ('R6', '1'): '/UPDI', ('R6', '2'): '/UPDI_MCU',
          ('C3', '1'): '/VCC', ('C3', '2'): '/GND', ('JP1', '1'): '/VOUT', ('JP1', '2'): '/VCC',
          ('Q1', '1'): '/SS_GATE', ('Q1', '2'): '/VCC', ('Q1', '3'): '/SS_CAP',
          ('R7', '1'): '/VCC', ('R7', '2'): '/SS_CAP', ('R8', '1'): '/VCC', ('R8', '2'): '/SS_GATE',
          ('C4', '1'): '/SS_CAP', ('C4', '2'): '/GND', ('D21', '1'): '/GND', ('D21', '2'): '/UPDI',
          ('TP1', '1'): '/UPDI', ('TP2', '1'): '/VCC', ('TP3', '1'): '/GND'}
for (ref, num), want in EXPECT.items():
    assert pad_net(ref, num) == want, (ref, num, pad_net(ref, num), want)

# -------------------------------------------------- Charlieplex buses + stubs
bus_vias = {'iss': {}, 'top': {}}   # row -> net -> [theta]
for ref, row, r, th in placed:
    for num in ('1', '2'):
        name = pad_net(ref, num)
        p = pad_xy(ref, num)
        pr, pth = to_polar(p)
        bus_row = 'top' if row == 'top' else 'iss'
        rb = (TOP_BUS if row == 'top' else ISS_BUS)[cp_index(name)]
        v = polar(rb, pth)
        track(p, v, name)
        via(v, name)
        bus_vias[bus_row].setdefault(name, []).append(pth)

trunk_th = math.asin(TRUNK_SIN)
U = (math.sin(trunk_th), -math.cos(trunk_th))
N = (math.cos(trunk_th), math.sin(trunk_th))


def trunk_pt(t, s):
    return (CX + s * U[0] + t * N[0], CY + s * U[1] + t * N[1])


def trunk_at_r(t, r):
    return trunk_pt(t, math.sqrt(r * r - t * t))


def trunk_at_y(t, y):
    return trunk_pt(t, (CY - y + t * N[1]) / -U[1])


for i in range(5):
    name = f'/CP{i}'
    t = TRUNK_T[name]
    lo, hi = trunk_at_r(t, ISS_BUS[i]), trunk_at_r(t, TOP_BUS[i])
    via(lo, name)
    via(hi, name)
    bus_vias['iss'][name].append(to_polar(lo)[1])
    bus_vias['top'][name].append(to_polar(hi)[1])
    ref = f'R{i + 1}'
    tap = trunk_at_y(t, R_Y[ref])
    via(tap, name)
    path([lo, tap, hi], name)
    cp_pad = pad_xy(ref, '2')
    near = (cp_pad[0] - 0.95, cp_pad[1])
    via(near, name)
    track(tap, near, name, layer=BCU)
    track(near, cp_pad, name)

for row, radii in (('iss', ISS_BUS), ('top', TOP_BUS)):
    for name, ths in bus_vias[row].items():
        bus_arc(radii[cp_index(name)], min(ths), max(ths), name)

# ------------------------------------------------------- MCU block wiring
u2 = lambda n: pad_xy('U2', str(n))
W_ESC = 0.15                         # QFN escapes: 0.2 mm pads on 0.4 mm pitch

# PA1 (left side) and PA2/PA3 (bottom side) straight to R1-R3 on F.Cu.
path([u2(20), pad_xy('R1', '1')], '/PA1', W_ESC)
for pin, ref in ((1, 'R2'), (2, 'R3')):
    pa = pad_xy(ref, '1')
    path([u2(pin), (u2(pin)[0], pa[1]), pa], pad_net(ref, '1'), W_ESC)
# PA4/PA5 drop to vias and pass under the block on B.Cu.
for pin, ref, v, mid in ((5, 'R4', PA4_VIA, (u2(5)[0], 25.1)),
                         (6, 'R5', PA5_VIA, (71.5, 24.35))):
    name, pa = pad_net(ref, '1'), pad_xy(ref, '1')
    path([u2(pin), mid, v], name, W_ESC)
    via(v, name)
    near = (PA_NEAR_X, pa[1])
    path([v, (v[0], pa[1]), near], name, W_SIG, BCU)
    via(near, name)
    track(near, pa, name)

# GND: pin 3 to the exposed pad inside the body, and down into C3.
track(u2(3), u2(21), '/GND', W_ESC)
path([u2(3), (u2(3)[0], 25.9), pad_xy('C3', '2')], '/GND', W_ESC)
# VCC: pin 4 down into C3.
path([u2(4), (u2(4)[0], 25.9), pad_xy('C3', '1')], '/VCC', W_ESC)

# VCC rail: JP1 -> C3 -> spine up the right side to TP2's via.
c3_vcc = pad_xy('C3', '1')
tp_via = {ref: (TP_VIA_X, y) for ref, y in TP_Y.items()}
path([pad_xy('JP1', '2'), (c3_vcc[0], VCC_Y), (VCC_X, VCC_Y), (VCC_X, TP_Y['TP2']), tp_via['TP2']],
     '/VCC', W_PWR)
track((c3_vcc[0], VCC_Y), c3_vcc, '/VCC', W_PWR)

# UPDI: pin 19 -> R6 above U2 -> over the top -> up to TP1's via -> D21.
r6_mcu, r6_tp = pad_xy('R6', '2'), pad_xy('R6', '1')
path([u2(19), (r6_mcu[0], u2(19)[1]), r6_mcu], '/UPDI_MCU', W_ESC)
path([r6_tp, (r6_tp[0], UPDI_Y), (UPDI_X, UPDI_Y), (UPDI_X, TP_Y['TP1']), tp_via['TP1']], '/UPDI')
track(tp_via['TP1'], pad_xy('D21', '2'), '/UPDI', W_ESC)
d21_gnd = pad_xy('D21', '1')
path([d21_gnd, (d21_gnd[0], TP_Y['TP3']), tp_via['TP3']], '/GND', W_SIG)

# Soft-start: SS_GATE over the top to R8 and Q1's gate; VCC stubs to the spine.
gate = pad_xy('Q1', '1')
r8_gate = pad_xy('R8', '2')
path([u2(15), (u2(15)[0], SS_GATE_Y), (r8_gate[0], SS_GATE_Y), r8_gate], '/SS_GATE', W_ESC)
path([(SS_GATE_X, SS_GATE_Y), (SS_GATE_X, gate[1]), gate], '/SS_GATE', W_ESC)
for ref, num in (('R8', '1'), ('R7', '1'), ('Q1', '2')):
    p = pad_xy(ref, num)
    track(p, (VCC_X, p[1]), '/VCC', W_ESC)
drain = pad_xy('Q1', '3')
track(drain, pad_xy('R7', '2'), '/SS_CAP', W_ESC)
track(drain, pad_xy('C4', '1'), '/SS_CAP', W_ESC)
track(pad_xy('C4', '2'), C4_GND_VIA, '/GND', W_ESC)
via(C4_GND_VIA, '/GND')

# Back test pads: via beside each pad, short B.Cu stub into the pad.
for ref, v in tp_via.items():
    via(v, pad_net(ref, '1'))
    track(v, pad_xy(ref, '1'), pad_net(ref, '1'), W_PWR, BCU)

# ------------------------------------------ VOUT and GND from U1 to the block
for name, node, v, top_y in (('/VOUT', U1_VOUT_NODE, U1_VOUT_VIA, VOUT_Y),
                             ('/GND', U1_GND_NODE, U1_GND_VIA, GND_BRANCH_Y)):
    track(node, v, name, W_PWR)
    via(v, name)
    r, th0 = to_polar(v)
    t = TRUNK_T[name]
    foot = trunk_at_r(t, r)
    via(foot, name)
    bus_arc(r, th0, to_polar(foot)[1], name, W_PWR)
    top = trunk_at_y(t, top_y)
    track(foot, top, name, W_PWR)
    if name == '/VOUT':
        track(top, pad_xy('JP1', '1'), name, W_PWR)
    else:
        # B.Cu under the block: hop up to C3, then the GND spine to TP3's via,
        # with a branch to C4.
        via(top, name)
        path([top, GND_C3_VIA, (GND_C3_VIA[0] + VCC_Y - GND_BRANCH_Y, VCC_Y), (GND_X, VCC_Y),
              (GND_X, C4_GND_VIA[1]), (GND_X, TP_Y['TP3']), tp_via['TP3']], name, W_PWR, BCU)
        via(GND_C3_VIA, name)
        track(GND_C3_VIA, pad_xy('C3', '2'), name, W_PWR)
        track(C4_GND_VIA, (GND_X, C4_GND_VIA[1]), name, W_PWR, BCU)

# ----------------------------------------------------------------- silkscreen
keepouts = []   # (polygon, margin) in concept mm
pad_keepouts = {}   # ref -> its pad keepouts (axis-aligned, so loose on tilted parts)
for f in board.GetFootprints():
    if f.GetReference() == 'L1':
        continue
    for pd in f.Pads():
        if not pd.IsOnLayer(FCU):
            continue
        bb = pd.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - 100, pcbnew.ToMM(bb.GetTop()) - 100
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - 100, pcbnew.ToMM(bb.GetBottom()) - 100
        keepouts.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], SILK_PAD_CLEAR))
        pad_keepouts.setdefault(f.GetReference(), []).append(keepouts[-1])
    crt = [g.GetBoundingBox() for g in f.GraphicalItems() if g.GetLayer() == pcbnew.F_CrtYd]
    if crt:
        x0 = min(pcbnew.ToMM(b.GetLeft()) for b in crt) - 100
        y0 = min(pcbnew.ToMM(b.GetTop()) for b in crt) - 100
        x1 = max(pcbnew.ToMM(b.GetRight()) for b in crt) - 100
        y1 = max(pcbnew.ToMM(b.GetBottom()) for b in crt) - 100
        keepouts.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 0.05))


def seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    u = 0 if L == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - ax - u * dx, p[1] - ay - u * dy)


def inside(poly, p):
    c = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > p[1]) != (by > p[1]) and p[0] < ax + (p[1] - ay) * (bx - ax) / (by - ay):
            c = not c
    return c


def blocked(p, w):
    x0, y0, x1, y1 = CLIP
    if not (x0 + w / 2 <= p[0] <= x1 - w / 2 and y0 + w / 2 <= p[1] <= y1 - w / 2):
        return True
    for poly, m in keepouts:
        if inside(poly, p):
            return True
        if any(seg_dist(p, a, b) < m + w / 2 for a, b in zip(poly, poly[1:] + poly[:1])):
            return True
    return False


def silk_seg(a, b, w, layer=FSILK):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(kv(a))
    s.SetEnd(kv(b))
    s.SetWidth(pcbnew.FromMM(w))
    s.SetLayer(layer)
    board.Add(s)


def silk_curve(pts, w, dash=None):
    """Draw a sampled curve, dropping pieces that leave the clip or touch pads.

    dash = (on, off) in mm along the curve; None for a solid line."""
    run, along = [], 0.0
    period = sum(dash) if dash else None

    def flush():
        if len(run) >= 2:
            for a, b in zip(run, run[1:]):
                silk_seg(a, b, w)
        run.clear()

    prev = None
    for p in pts:
        if prev is not None:
            along += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
        on = dash is None or (along % period) < dash[0]
        if on and not blocked(p, w):
            run.append(p)
        else:
            flush()
    flush()


def circle_pts(r, step=0.05, a0=-math.pi / 2, a1=math.pi / 2):
    n = max(2, int((a1 - a0) * r / step))
    return [polar(r, a0 + (a1 - a0) * i / n) for i in range(n + 1)]


def resample(pts, step):
    """Merge a dense curve into chords of about `step` mm (fewer silk segments)."""
    out, acc = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if acc >= step:
            out.append(b)
            acc = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def solid(pts, w):
    """Solid curves: clip on a fine grid, then emit coarse chords per visible run."""
    runs, run = [], []
    for p in pts:
        if blocked(p, w):
            if run:
                runs.append(run)
            run = []
        else:
            run.append(p)
    if run:
        runs.append(run)
    for r in runs:
        r = resample(r, 0.6)
        for a, b in zip(r, r[1:]):
            silk_seg(a, b, w)


def text(s, at, h=TEXT_H, w=TEXT_W, justify='left', layer=FSILK, bold=False, cw=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(cw or h), pcbnew.FromMM(h)))   # cw: glyph width
    t.SetTextThickness(pcbnew.FromMM(w))
    t.SetHorizJustify({'left': pcbnew.GR_TEXT_H_ALIGN_LEFT, 'center': pcbnew.GR_TEXT_H_ALIGN_CENTER,
                       'right': pcbnew.GR_TEXT_H_ALIGN_RIGHT}[justify])
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_BOTTOM)    # `at` is the baseline, as in the concept SVG
    if layer == BSILK:
        t.SetMirrored(True)
    t.SetPosition(kv(at))
    board.Add(t)
    return t


def nfc_glyph(at, scale, layer=FSILK, mirror=False):
    """Three arcs and a dot opening to the right (to the left when mirrored)."""
    w, sx = 0.35 * scale, -1 if mirror else 1
    for i in range(3):
        r = (1 + i * 0.9) * scale
        a = pcbnew.PCB_SHAPE(board)
        a.SetShape(pcbnew.SHAPE_T_ARC)
        p = lambda ang: kv((at[0] + sx * r * math.cos(ang), at[1] + r * math.sin(ang)))
        a.SetArcGeometry(p(-0.8), p(0.0), p(0.8))
        a.SetWidth(pcbnew.FromMM(max(w, 0.15)))
        a.SetLayer(layer)
        board.Add(a)
    dot = pcbnew.PCB_SHAPE(board)
    dot.SetShape(pcbnew.SHAPE_T_CIRCLE)
    dot.SetCenter(kv(at))
    dot.SetEnd(kv((at[0] + 0.35 * scale, at[1])))
    dot.SetFilled(True)
    dot.SetWidth(0)
    dot.SetLayer(layer)
    board.Add(dot)


text('ISS · 420 km', (43.5, arc_y(R_ISS, 43.5) - 1.4))
text('2,000 km · TOP OF LEO', (31, arc_y(R_TOP, 31) - 2.4))
for i, ch in enumerate('EARTH'):
    text(ch, (43 + (i - 2) * 1.6, 46.4), justify='center')
text('WONG ZHUN HAO', (9, 27.4), h=2.6, w=0.42)
nfc_glyph((48, 26.5), 0.85)
text('JP1', (JP1_AT[0], JP1_AT[1] - 0.85), justify='center')

# Lines stop short of the front lettering.
for item in board.GetDrawings():
    if isinstance(item, pcbnew.PCB_TEXT) and item.GetLayer() == FSILK:
        bb = item.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetLeft()) - 100, pcbnew.ToMM(bb.GetTop()) - 100
        x1, y1 = pcbnew.ToMM(bb.GetRight()) - 100, pcbnew.ToMM(bb.GetBottom()) - 100
        keepouts.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 0.3))

# LED cathode dots. The pads' ends face along the orbit line, where a dot would
# read as one more orbit dot, so each sits beside pad 1 (the cathode) on the
# side away from its bus stubs: outward on the ISS row, inward elsewhere.
DOT_D = 0.4
for ref, row, r, th in placed:
    pd = next(p for p in fp[ref].Pads() if p.GetNumber() == '1')
    off = pcbnew.ToMM(pd.GetSize(FCU).y) / 2 + SILK_PAD_CLEAR + DOT_D / 2 + 0.02
    pr, pth = to_polar(pad_xy(ref, '1'))
    c = polar(pr + off if row == 'iss' else pr - off, pth)
    # `off` clears the LED's own pad; check every other footprint's pads.
    assert not any(inside(poly, c) or any(seg_dist(c, a, b) < m + DOT_D / 2
                                          for a, b in zip(poly, poly[1:] + poly[:1]))
                   for other, kos in pad_keepouts.items() if other != ref
                   for poly, m in kos), ref
    dot = pcbnew.PCB_SHAPE(board)
    dot.SetShape(pcbnew.SHAPE_T_CIRCLE)
    dot.SetCenter(kv(c))
    dot.SetEnd(kv((c[0] + DOT_D / 2, c[1])))
    dot.SetFilled(True)
    dot.SetWidth(0)
    dot.SetLayer(FSILK)
    board.Add(dot)
    h = DOT_D / 2
    keepouts.append(([(c[0] - h, c[1] - h), (c[0] + h, c[1] - h), (c[0] + h, c[1] + h),
                      (c[0] - h, c[1] + h)], 0.2))

# Earth: limb, three inner limb rings, faint meridian ellipses.
solid(circle_pts(R_EARTH), 0.25)
for i in range(1, 4):
    silk_curve(circle_pts(R_EARTH - i * 2.4, 0.05), 0.15, dash=(1.2, 0.6))
for a in (-.45, -.3, -.15, .15, .3, .45):
    rx = R_EARTH * abs(math.sin(a))
    n = 4000
    ell = [(CX + rx * math.sin(math.pi * (j / n - 0.5)), CY - R_EARTH * math.cos(math.pi * (j / n - 0.5)))
           for j in range(n + 1)]
    silk_curve(ell, 0.15, dash=(0.5, 0.5))
silk_curve([(CX, CY - R_EARTH + i * 0.05) for i in range(int(R_EARTH / 0.05))], 0.15, dash=(0.5, 0.5))

# Orbits: dashed ISS (420 km), dotted upper (2,000 km).
silk_curve(circle_pts(R_ISS, 0.03), 0.16, dash=(0.6, 0.45))
silk_curve(circle_pts(R_TOP, 0.03), 0.15, dash=(0.25, 0.5))

# Ground-station chevrons under each station LED, along the local tangent.
for ref, row, r, th in placed:
    if row != 'station':
        continue
    c = polar(r, th)
    t = (math.cos(th), math.sin(th))      # tangent
    d = (-math.sin(th), math.cos(th))     # towards Earth's centre
    pt = lambda u, v: (c[0] + u * t[0] + v * d[0], c[1] + u * t[1] + v * d[1])
    silk_seg(pt(-1.3, 1.95), pt(0, 1.2), 0.15)     # 0.35 lower than the concept,
    silk_seg(pt(0, 1.2), pt(1.3, 1.95), 0.15)      # clear of the cathode dot


# Back, laid out as seen from the back: concept x maps to KiCad 85.6 - x.
bx = lambda x: 85.6 - x
text('WONG ZHUN HAO', (bx(10), 18.5), h=4.0, w=0.6, layer=BSILK)
text('B.ENG. ELECTRICAL & ELECTRONIC ENGINEERING · NTU', (bx(10), 22.9), h=1.45, w=0.2, layer=BSILK)
# The phone line is only printed when a private contact file supplies one.
for i, line in enumerate(l for l in (contact.PHONE, 'zhunhaowong@gmail.com', 'wongzhunhao.com') if l):
    text(line, (bx(10), 29 + i * 3), h=1.75, w=0.22, layer=BSILK)
nfc_glyph((bx(68.5), 28), 1.6, BSILK, mirror=True)
text('TAP TO CONNECT', (bx(68.5), 34.6), h=1.3, w=0.18, justify='center', layer=BSILK)
TLE = ('1 25544U 98067A   26297.20915682  .00007800  00000+0  14938-3 0  9991',
       '2 25544  51.6335  21.6229 0006884 302.9098  57.1228 15.49030149591752')
for i, line in enumerate(TLE):
    # Height stays at JLC's 1.0 mm; narrower glyphs bring the line back to the
    # concept's 0.95 mm monospace length (37.6 mm) instead of 61.7 mm.
    text(line, (bx(10), 43 + i * 1.7), layer=BSILK, cw=TLE_CW)
# Test-pad labels, read from the back: left-aligned with the contact block
# (back x = 10), just right of each pad's via; centred on the pad. Glyphs are
# 0.8 mm wide (height stays 1.0) so GND clears the 2,000 km bus via at its end.
for ref, label in TP_LABEL.items():
    text(label, (bx(10), TP_Y[ref] + TEXT_H / 2), layer=BSILK, cw=0.8)

jlc_dfm.apply(board)
board_thickness.save(board, OUT_PATH)
print('saved', OUT_PATH, f'({board_thickness.THICKNESS_MM} mm)')
