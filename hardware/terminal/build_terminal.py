#!/usr/bin/env python3
"""Lay out the B3 Terminal card on the copied NTUAS board.

Run with KiCad 10's bundled Python (it needs `pcbnew`, plus the macOS fonts
Menlo and Helvetica Neue):

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        hardware/terminal/build_terminal.py

It is idempotent. It keeps L1, U1, C1, C2, JP1 and the hand-routed RF/VOUT
copper exactly as copied from the NTUAS card, then rewrites everything else:
placement, Charlieplex/power/UPDI routing and all silkscreen art. Concept
coordinates (mm from the card's top-left) map to KiCad as (100 + x, 100 + y).

Silkscreen text is rendered by KiCad's own TTF engine, then emboldened and
stored as filled polygons. Menlo's thinnest strokes (`%`, `@`, `~`, the
dotted zero) are ~0.10 mm at a 1.0 mm cap height, below JLCPCB's 0.15 mm
minimum, so every glyph is grown by EMBOLDEN_MM; check_silk.py verifies the
result on the saved board.
Storing polygons also means the board no longer depends on installed fonts.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PCB = HERE / "terminal.kicad_pcb"
LAYOUT_NOTE = HERE / "LAYOUT.md"
LED_MAP = HERE.parents[1] / "firmware/boards/terminal/led_map.h"
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
sys.path.insert(0, str(HERE.parent))
import board_thickness  # noqa: E402
import contact  # noqa: E402
import jlc_dfm  # noqa: E402
MM = pcbnew.FromMM
OX, OY = 100.0, 100.0
CARD_W = 85.6

MONO = "Menlo"
SANS = "Helvetica Neue"
EMBOLDEN_MM = 0.035
SILK_W = 0.15  # line art stroke, JLCPCB minimum
BACK_X = 15.6  # back text block left edge, card mm (see back_art)

# ---------------------------------------------------------------- geometry
# Rows/columns of the Charlieplex bus, ordered to match the resistor stack
# top-to-bottom (R4, R5, R1, R2, R3). Index = position in this list.
BUS_ORDER = [3, 4, 0, 1, 2]                 # CP numbers
ROW_Y = [141.0, 141.65, 142.3, 142.95, 143.6]  # B.Cu rows above the bar
COL_X = [170.6, 171.25, 171.9, 172.55, 173.2]  # B.Cu columns left of the line LEDs
STAIR_X = [143.75, 143.1, 142.45, 141.8, 141.15]  # row left ends
SLOT_Y = [136.0, 137.2, 138.4, 139.6, 140.8]   # resistor stack
R_X = 139.2
PA_VIA_X = 137.85
CP_VIA_X = 140.55

LINE_LED_X = 175.0
LINE_BASE_Y = [113.4 + 2.25 * i for i in range(9)]   # text baselines
LINE_LED_Y = [y - 0.5 for y in LINE_BASE_Y]          # centred on the 1.0 mm cap height
BAR_Y = 144.6
BAR_X = [175.0 - 3.2 * i for i in range(11)]         # right to left, chain order
LED_PAD = 0.787
# Cathode dot below each LED's pad 1: pad half-height 0.475 + the 0.25 mm silk
# cut-back + 0.02 so jlc_dfm leaves it whole.
DOT_R = 0.2
DOT_DY = 0.475 + 0.25 + DOT_R + 0.02

U2_POS = (129.6, 139.3)
U2_ROT = 180          # QFN-20: pins 1-5 face east (pin 5 PA4 top), 6-10 north, 15 SS_GATE west
C3_POS = (132.7, 138.7)  # rot 0: VCC pad west, GND pad east; 0.2 mm above pin 4 so
                          # C3's GND can return to pin 3 between its VCC pad and PA3
# Test pads on B.Cu in a 2.54 mm row inside the coil's lower-left corner, read
# UPDI-VCC-GND left to right from the back (so KiCad x runs GND, VCC, UPDI).
TP_ROW_Y = 145.0
TP_X = {"TP3": 108.6, "TP2": 108.6 + 2.54, "TP1": 108.6 + 5.08}
TP_LABEL = {"TP1": "UPDI", "TP2": "VCC", "TP3": "GND"}
TP_VIA_Y = TP_ROW_Y - 1.4   # each pad's via sits 1.4 mm north of it
GND_SPINE_Y = 142.2         # B.Cu ground spine from the GND via east to the bottom rail
R6_POS = (118.0, 138.6)
D21_POS = (115.5, 139.5)    # rot 90: UPDI pad up under the TP1-R6 line (0.2 mm mask gap), GND pad down
# Soft-start cluster west of U2, hanging off the VCC rail (y 133.2).
R7_POS = (124.6, 134.8)     # rot -90: VCC pad up, SS_CAP down
Q1_POS = (126.0, 135.0)     # rot 180: SS_CAP pad 3 west, gate/VCC east
R8_POS = (127.4, 134.8)     # rot -90: VCC pad up, SS_GATE down
C4_POS = (125.65, 137.0)    # rot -90: SS_CAP pad up, GND pad down

TRACK = 0.2
VIA_D, VIA_DRILL = 0.65, 0.3  # 0.175 mm ring; JLCDFM grades 0.15 mm a warning

KEEP_REFS = {"L1", "U1", "C1", "C2", "JP1"}


def kp(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def mm_of(v):
    return pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)


# --------------------------------------------------------- the LED chain
def led_index(anode, cathode):
    """NTUAS mapping: index k has anode CP[k/4], cathode CP[c]."""
    return 4 * anode + (cathode if cathode < anode else cathode - 1)


def chain_nets():
    """Eulerian circuit through all 20 ordered CP pairs.

    Consecutive LEDs share a net at their junction (cathode of LED j+1 = anode
    of LED j), so 20 LEDs need only 21 bus taps. The circuit starts and ends on
    CP1 because the leftmost bar tap sits on bus row 3 (see STAIR_X).
    """
    out = {a: [c for c in range(5) if c != a] for a in range(5)}
    # Prefer a fixed, readable order: always take the smallest unused neighbour.
    stack, circuit = [1], []
    while stack:
        v = stack[-1]
        if out[v]:
            stack.append(out[v].pop(0))
        else:
            circuit.append(stack.pop())
    circuit.reverse()
    assert len(circuit) == 21 and circuit[0] == circuit[-1] == 1
    return circuit  # n0..n20; LED j: cathode n_j, anode n_{j+1}


def led_positions():
    """(x, y, rotation) for chain positions P0..P19."""
    pos = [(LINE_LED_X, y, 0) for y in LINE_LED_Y]           # cathode left
    pos += [(x, BAR_Y, 180) for x in BAR_X]                  # cathode right
    return pos


# ---------------------------------------------------------------- board ops
class Board:
    def __init__(self, path):
        self.b = pcbnew.LoadBoard(str(path))

    def net(self, name):
        return self.b.FindNet(name)

    def fp(self, ref):
        return self.b.FindFootprintByReference(ref)

    def place(self, ref, x, y, rot):
        f = self.fp(ref)
        f.SetOrientationDegrees(rot)
        f.SetPosition(kp(x, y))
        return f

    def pad(self, ref, num):
        for p in self.fp(ref).Pads():
            if p.GetNumber() == str(num):
                return p
        raise KeyError((ref, num))

    def pad_xy(self, ref, num):
        return mm_of(self.pad(ref, num).GetPosition())

    def track(self, pts, net, layer, width=TRACK):
        n = self.net(net) if isinstance(net, str) else net
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(kp(x0, y0))
            t.SetEnd(kp(x1, y1))
            t.SetWidth(MM(width))
            t.SetLayer(layer)
            t.SetNet(n)
            self.b.Add(t)

    def via(self, x, y, net):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(kp(x, y))
        v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL))
        v.SetNet(self.net(net) if isinstance(net, str) else net)
        self.b.Add(v)


# Antenna-feed pieces that no longer fit the rev B coil (pads moved to
# LA (120.0, 151.53), LB (114.4, 147.33)); feed_antenna() replaces them. The
# first five are NTUAS's; the last two fed LB at (115.0, 147.93) for the
# 0.30 mm-gap coil.
DROPPED_FEED = {
    ("/LA", pcbnew.F_Cu, (120.0, 149.98), (120.0, 150.7)),
    ("/LA", pcbnew.B_Cu, (115.8, 147.3), (119.2, 150.7)),
    ("/LA", pcbnew.B_Cu, (119.2, 150.7), (120.0, 150.7)),
    ("/LA", None, (120.0, 150.7), (120.0, 150.7)),  # via
    ("/LB", pcbnew.F_Cu, (114.7, 146.58), (116.0, 147.88)),
    ("/LB", pcbnew.F_Cu, (114.7, 146.58), (115.0, 146.88)),
    ("/LB", pcbnew.F_Cu, (115.0, 146.88), (115.0, 147.93)),
}


def _rounded(t):
    a, b = mm_of(t.GetStart()), mm_of(t.GetEnd())
    return tuple(round(v, 2) for v in a), tuple(round(v, 2) for v in b)


def kept_track(t):
    """Copper copied verbatim from NTUAS: the RF feed, VOUT, and U1-C2 ground."""
    net = t.GetNetname()
    if net in ("/LA", "/LB", "/VOUT"):
        a, b = _rounded(t)
        layer = None if t.GetClass() == "PCB_VIA" else t.GetLayer()
        for n, ly, p0, p1 in DROPPED_FEED:
            if n == net and ly == layer and {a, b} == {p0, p1}:
                return False
        # Our own feed (feed_antenna) is rebuilt on every run.
        if (net, layer) + tuple(sorted((a, b))) in FEED_OWN:
            return False
        return True
    if net == "/GND" and t.GetClass() == "PCB_TRACK":
        pts = [mm_of(t.GetStart()), mm_of(t.GetEnd())]
        return all(116.7 <= x <= 120.7 and 143.4 <= y <= 145.2 for x, y in pts)
    return False


_graveyard = []


def clear(bd):
    b = bd.b
    # Collect everything first: SWIG iterators go stale once the board changes.
    tracks = [t for t in b.GetTracks() if not kept_track(t)]
    # NTUAS's `LIFT JP1 TO FLASH` goes too: these cards program with JP1 fitted.
    drawings = [d for d in b.GetDrawings()
                if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    groups = list(b.Groups())
    for item in groups + tracks + drawings:
        b.Remove(item)
    # Removed items are owned by nobody; if Python collects their proxies,
    # KiCad 10's SWIG type table breaks. Keep them alive until exit.
    _graveyard.extend(groups + tracks + drawings)


# ---------------------------------------------------------------- placement
def place(bd, chain):
    mapping = []
    for j, (x, y, rot) in enumerate(led_positions()):
        cathode, anode = chain[j], chain[j + 1]
        k = led_index(anode, cathode)
        ref = f"D{k + 1}"
        f = bd.place(ref, x, y, rot)
        assert bd.pad(ref, 1).GetNetname() == f"/CP{cathode}", ref
        assert bd.pad(ref, 2).GetNetname() == f"/CP{anode}", ref
        mapping.append((j, k, ref, anode, cathode, x, y))
    bd.place("U2", *U2_POS, U2_ROT)
    for num, side in ((5, "E"), (1, "E"), (6, "N"), (20, "S"), (15, "W")):
        x, y = bd.pad_xy("U2", num)
        assert {"E": x > U2_POS[0] + 1, "N": y < U2_POS[1] - 1,
                "S": y > U2_POS[1] + 1, "W": x < U2_POS[0] - 1}[side], (num, x, y)
    bd.place("C3", *C3_POS, 0)
    assert bd.pad_xy("C3", 1)[0] < C3_POS[0], "C3 pad 1 (VCC) must face U2"
    for i, slot in enumerate(SLOT_Y):
        cp = BUS_ORDER[i]
        bd.place(f"R{cp + 1}", R_X, slot, 0)
    bd.place("R6", *R6_POS, 0)
    bd.place("D21", *D21_POS, 90)
    for f in bd.b.GetFootprints():  # the art carries the labels; no ref designators
        f.Reference().SetVisible(False)
    for ref, xy, rot in (("R7", R7_POS, -90), ("Q1", Q1_POS, 180), ("R8", R8_POS, -90),
                         ("C4", C4_POS, -90)):
        bd.place(ref, *xy, rot)
    for ref in ("D21", "R7", "Q1", "R8", "C4"):
        print(ref, "at (%.2f, %.2f)" % mm_of(bd.fp(ref).GetPosition()),
              " ".join("%s:%s(%.3f,%.3f)" % (p.GetNumber(), p.GetNetname(), *mm_of(p.GetPosition()))
                       for p in bd.fp(ref).Pads() if p.GetNumber()))
    for ref, x in TP_X.items():
        f = bd.fp(ref)
        if f.GetLayer() != pcbnew.B_Cu:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        assert f.GetLayer() == pcbnew.B_Cu, ref
        bd.place(ref, x, TP_ROW_Y, 0)
    return mapping


# ---------------------------------------------------------------- routing
def route(bd, chain):
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    pos = led_positions()
    taps = defaultdict(list)  # net -> [(kind, x, y)]

    def cp(n):
        return f"/CP{n}"

    # Line LEDs: 45-degree junctions between anode (right) and the next cathode (left).
    for j in range(8):
        x, y, _ = pos[j]
        y2 = pos[j + 1][1]
        dy = y2 - y
        bend = (dy - 2 * LED_PAD) / 2
        bd.track([(x + LED_PAD, y), (x + LED_PAD, y + bend),
                  (x - LED_PAD, y2 - bend), (x - LED_PAD, y2)], cp(chain[j + 1]), F)
    # Column taps: each line LED's cathode runs left to its net's column.
    for j in range(9):
        x, y, _ = pos[j]
        n = chain[j]
        cx = COL_X[BUS_ORDER.index(n)]
        bd.track([(x - LED_PAD, y), (cx, y)], cp(n), F)
        bd.via(cx, y, cp(n))
        taps[n].append(("col", cx, y))
    # Line 9 anode drops straight to the rightmost bar LED's cathode.
    n9 = chain[9]
    x8, y8, _ = pos[8]
    bd.track([(x8 + LED_PAD, y8), (x8 + LED_PAD, BAR_Y)], cp(n9), F)
    cx = COL_X[BUS_ORDER.index(n9)]
    tap_y = 140.0  # back view y 40: the gap between "web" and the footer
    bd.track([(x8 + LED_PAD, tap_y), (cx, tap_y)], cp(n9), F)
    bd.via(cx, tap_y, cp(n9))
    taps[n9].append(("col", cx, tap_y))
    # Bar: straight junctions; each tap rises to its net's row.
    for j in range(9, 20):
        x, y, _ = pos[j]
        n_out = chain[j + 1]
        left = x - LED_PAD
        if j < 19:
            nxt = pos[j + 1][0] + LED_PAD
            bd.track([(left, y), (nxt, y)], cp(n_out), F)
            tx = (left + nxt) / 2
        else:
            tx = left
        r = BUS_ORDER.index(n_out)
        ry = ROW_Y[r]
        vx = min(tx, COL_X[r])
        bd.track([(tx, y), (tx, ry), (vx, ry)], cp(n_out), F)
        bd.via(vx, ry, cp(n_out))
        taps[n_out].append(("row", vx, ry))
    # Bus: rows from the staircase to their column, columns up to the top tap.
    for r, n in enumerate(BUS_ORDER):
        col_taps = [t for t in taps[n] if t[0] == "col"]
        top = min([t[2] for t in col_taps] + [ROW_Y[r]])
        right = max([COL_X[r]] * bool(col_taps) + [t[1] for t in taps[n] if t[0] == "row"])
        bd.track([(STAIR_X[r], ROW_Y[r]), (right, ROW_Y[r])], cp(n), B)
        bd.track([(COL_X[r], ROW_Y[r]), (COL_X[r], top)], cp(n), B)
        # Staircase from the resistor's CP via down to the row.
        bd.via(CP_VIA_X, SLOT_Y[r], cp(n))
        bd.track([(CP_VIA_X, SLOT_Y[r]), (STAIR_X[r], SLOT_Y[r]), (STAIR_X[r], ROW_Y[r])], cp(n), B)
        ref = f"R{n + 1}"
        bd.track([bd.pad_xy(ref, 2), (CP_VIA_X, SLOT_Y[r])], cp(n), F)

    # PA lines. U2's east side reads PA4, VCC, GND, PA3, PA2 top to bottom, PA5
    # sits on the north side and PA1 on the south; the stack wants PA4, PA5,
    # PA1, PA2, PA3. Each line escapes on 0.15 mm F.Cu to a via, then runs
    # B.Cu (under the U2 body where needed) to a via left of its resistor.
    #   PA4: east, north past C3 to a via above PA5's row.
    #   PA5: straight north.
    #   PA1: south to a via, then B.Cu back north under the body to its row.
    #   PA2/PA3: east under C3; PA3 turns down further out and lower than
    #   PA2, so PA2's B.Cu row passes above PA3's via.
    def upad(num):
        return bd.pad_xy("U2", num)

    fan = {
        "/PA4": [upad(5), (131.6, upad(5)[1]), (131.6, 136.2)],
        "/PA5": [upad(6), (upad(6)[0], 136.9)],
        "/PA1": [upad(20), (upad(20)[0], 141.3), (130.85, 141.75)],
        "/PA2": [upad(1), (131.9, upad(1)[1]), (132.4, upad(1)[1] + 0.5), (132.4, 140.9)],
        "/PA3": [upad(2), (133.4, upad(2)[1]), (133.4, 141.7)],
    }
    bend_x = {"/PA4": 133.0, "/PA5": 133.0, "/PA2": 134.0, "/PA3": 134.6}
    for r, n in enumerate(BUS_ORDER):
        ref = f"R{n + 1}"
        pa = bd.pad(ref, 1).GetNetname()
        pts = fan[pa]
        bd.track(pts, pa, F, 0.15)
        vx, vy = pts[-1]
        bd.via(vx, vy, pa)
        sy = SLOT_Y[r]
        if pa == "/PA1":
            back = [(vx, vy), (vx, sy)]
        else:
            bx = bend_x[pa]
            back = [(vx, vy), (bx, vy), (bx + abs(vy - sy), sy)]
        bd.track(back + [(PA_VIA_X, sy)], pa, B, 0.15)
        bd.via(PA_VIA_X, sy, pa)
        bd.track([(PA_VIA_X, sy), bd.pad_xy(ref, 1)], pa, F)

    # VCC: TP2 -> JP1 -> top rail -> down onto C3's VCC pad <- U2 pin 4.
    # Test pads: VCC and UPDI pads have a via 1.4 mm north and run F.Cu north
    # from it. GND stays on B.Cu: its stub joins the B.Cu spine directly, so it
    # needs no via (one there would dangle).
    tp = {}
    for ref in TP_X:
        x, y = bd.pad_xy(ref, 1)
        net = bd.pad(ref, 1).GetNetname()
        if net != "/GND":
            bd.via(x, TP_VIA_Y, net)
        bd.track([(x, TP_VIA_Y), (x, y)], net, B)
        tp[net] = (x, TP_VIA_Y)
    tp2 = tp["/VCC"]
    vcc_y = 135.0
    jp = bd.pad_xy("JP1", 2 if bd.pad("JP1", 2).GetNetname() == "/VCC" else 1)
    rail = 133.2
    c3v, c3g = bd.pad_xy("C3", 1), bd.pad_xy("C3", 2)
    vcc_x = 132.25
    bd.track([tp2, (tp2[0], vcc_y), (jp[0], vcc_y)], "/VCC", F)
    bd.track([jp, (jp[0], rail), (vcc_x, rail), (vcc_x, c3v[1])], "/VCC", F)
    # Pin 4 jogs up to C3's VCC pad, clear of PA4's corner at (131.6, pin 5).
    u4 = upad(4)
    bd.track([u4, (131.9, u4[1]), c3v], "/VCC", F, 0.15)
    # GND: C3 decouples U2 directly: its GND pad drops to pin 3's line and runs
    # west into pin 3 (a ~2.6 mm loop; rev A's ran 33.7 mm round the bottom rail).
    # Pin 3 ties to the exposed pad, which drops through a via to B.Cu and out
    # west to the F.Cu trunk at GND_X; that trunk is U2's only link to the
    # bottom rail and the U1/C2 ground, so the GND net stays a tree.
    u3 = upad(3)
    bd.track([c3g, (c3g[0], u3[1]), u3], "/GND", F, 0.15)
    bd.track([u3, upad(21)], "/GND", F, 0.15)
    ep = upad(21)
    bd.via(*ep, "/GND")
    gnd_x, bottom = 124.6, 146.3
    bd.track([ep, (gnd_x, ep[1])], "/GND", B)
    bd.via(gnd_x, ep[1], "/GND")
    bd.track([(gnd_x, ep[1]), (gnd_x, bottom), (120.638, bottom), (120.638, 144.782)], "/GND", F)
    v1 = tp["/GND"]
    rise = v1[1] - GND_SPINE_Y
    bd.track([v1, (v1[0] + rise, GND_SPINE_Y), (121.2, GND_SPINE_Y), (121.2, bottom)], "/GND", B)
    bd.via(121.2, bottom, "/GND")
    # UPDI: TP1 -> R6 -> via -> B.Cu below the GND link -> via -> pin 19.
    tp1 = tp["/UPDI"]
    r6a, r6b = bd.pad_xy("R6", 1), bd.pad_xy("R6", 2)
    bd.track([tp1, (tp1[0], r6a[1]), r6a], "/UPDI", F)
    ux, uy = upad(19)
    v_a = (r6b[0] + 1.0, r6b[1])
    v_b = (ux, 141.75)
    bd.track([r6b, v_a], "/UPDI_MCU", F)
    bd.via(*v_a, "/UPDI_MCU")
    bd.track([v_a, (v_a[0], v_b[1]), v_b], "/UPDI_MCU", B, 0.15)
    bd.via(*v_b, "/UPDI_MCU")
    bd.track([v_b, (ux, uy)], "/UPDI_MCU", F, 0.15)
    # UPDI clamp D21 sits on the TP1-R6 line; its GND drops to the B.Cu spine.
    d_u, d_g = bd.pad_xy("D21", 2), bd.pad_xy("D21", 1)
    assert d_u[1] < d_g[1]
    bd.track([(d_u[0], r6a[1]), d_u], "/UPDI", F)
    dv = (d_g[0] - 1.0, d_g[1])
    bd.track([d_g, dv], "/GND", F)
    bd.via(*dv, "/GND")
    bd.track([dv, (dv[0], GND_SPINE_Y)], "/GND", B)

    # Soft-start: R7, Q1 (source) and R8 hang off the VCC rail; SS_CAP joins
    # R7, Q1 and C4; SS_GATE joins Q1, R8 and U2 pin 15; C4 grounds at GND_X.
    def pp(ref, num):
        return bd.pad_xy(ref, num)
    for ref, num in (("R7", 1), ("Q1", 2), ("R8", 1)):
        x, y = pp(ref, num)
        assert bd.pad(ref, num).GetNetname() == "/VCC" and y < Q1_POS[1], (ref, num)
        bd.track([(x, rail), (x, y)], "/VCC", F, 0.15)
    r7c, q1c, c4c = pp("R7", 2), pp("Q1", 3), pp("C4", 1)
    sc_y = 135.8
    bd.track([r7c, (r7c[0], sc_y), (q1c[0], sc_y)], "/SS_CAP", F, 0.15)
    bd.track([q1c, (q1c[0], sc_y), c4c], "/SS_CAP", F, 0.15)
    q1g, r8g, u15 = pp("Q1", 1), pp("R8", 2), upad(15)
    bd.track([q1g, (r8g[0], q1g[1])], "/SS_GATE", F, 0.15)
    bd.track([r8g, (r8g[0], u15[1]), u15], "/SS_GATE", F, 0.15)
    c4g = pp("C4", 2)
    bd.track([c4g, (c4g[0], ep[1] - 0.8), (gnd_x, ep[1])], "/GND", F, 0.15)
    for num in (1, 2, 3, 4, 5, 6, 15, 19, 20, 21):
        print("U2 pad %d %s at (%.3f, %.3f)" % (num, bd.pad("U2", num).GetNetname(), *upad(num)))


# Rev B coil feed: LA runs B.Cu under the inner turns to a via beside its pad,
# LB drops straight onto its pad. (net, layer, points); layer None = via.
FEED = [
    ("/LA", pcbnew.B_Cu, [(115.8, 147.3), (115.8, 152.9), (120.0, 152.9)]),
    ("/LA", None, [(120.0, 152.9)]),
    ("/LA", pcbnew.F_Cu, [(120.0, 152.9), (120.0, 151.53)]),
    ("/LB", pcbnew.F_Cu, [(114.7, 146.58), (114.4, 146.88), (114.4, 147.33)]),
]
FEED_OWN = set()
for _n, _ly, _pts in FEED:
    for _a, _b in (zip(_pts, _pts[1:]) if _ly is not None else [(_pts[0], _pts[0])]):
        FEED_OWN.add((_n, _ly) + tuple(sorted((_a, _b))))


def feed_antenna(bd):
    for num, xy in ((1, (120.0, 151.53)), (2, (114.4, 147.33))):
        assert all(abs(a - b) < 1e-3 for a, b in zip(bd.pad_xy("L1", num), xy)), num
    for net, layer, pts in FEED:
        if layer is None:
            bd.via(*pts[0], net)
        else:
            bd.track(pts, net, layer, 0.15)


# ---------------------------------------------------------------- artwork
_scratch = pcbnew.BOARD()
_metrics = {}


def _text_polys(s, font, bold, cap):
    t = pcbnew.PCB_TEXT(_scratch)
    t.SetText(s)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetUnresolvedFontName(font)
    t.ResolveFont(None)
    if t.GetFontName() != font:
        raise RuntimeError(f"font {font!r} not available")
    t.SetBold(bold)
    t.SetTextSize(kp(cap, cap))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_BOTTOM)
    t.SetPosition(kp(0, 0))
    ps = pcbnew.SHAPE_POLY_SET()
    t.TransformTextToPolySet(ps, 0, MM(0.002), pcbnew.ERROR_INSIDE)
    ps.Simplify()
    return ps


def _bbox(ps):
    bb = ps.BBox()
    return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def metrics(font, bold, cap):
    key = (font, bold, cap)
    if key not in _metrics:
        h = _bbox(_text_polys("H", font, bold, cap))
        base = h[3]  # H sits on the baseline
        w1 = _bbox(_text_polys("H" * 2, font, bold, cap))
        w2 = _bbox(_text_polys("H" * 22, font, bold, cap))
        _metrics[key] = (base, (w2[2] - w1[2]) / 20)
    return _metrics[key]


def advance(c, font, bold, cap):
    a = _bbox(_text_polys("H" + c + "H", font, bold, cap))
    b = _bbox(_text_polys("HH", font, bold, cap))
    return (a[2] - a[0]) - (b[2] - b[0])


def shift(ps, dx, dy):
    ps.Move(kp(dx, dy))
    return ps


class Art:
    """Collects silkscreen polygons in card coordinates, front or back view."""

    def __init__(self):
        self.items = []  # (layer, SHAPE_POLY_SET in KiCad coordinates)
        self.lines = []  # (layer, kind, data)

    def _to_kicad(self, ps, back):
        out = pcbnew.SHAPE_POLY_SET()
        for i in range(ps.OutlineCount()):
            for k in range(-1, ps.HoleCount(i)):
                ch = ps.Outline(i) if k < 0 else ps.Hole(i, k)
                pts = [(pcbnew.ToMM(ch.CPoint(j).x), pcbnew.ToMM(ch.CPoint(j).y))
                       for j in range(ch.PointCount())]
                chain = pcbnew.SHAPE_LINE_CHAIN()
                for x, y in (reversed(pts) if back else pts):
                    X = OX + (CARD_W - x if back else x)
                    chain.Append(MM(X), MM(OY + y))
                chain.SetClosed(True)
                if k < 0:
                    out.AddOutline(chain)
                else:
                    out.AddHole(chain, out.OutlineCount() - 1)
        return out

    def text(self, runs, x, base, cap, back=False, anchor="left", track=0.0):
        """runs: [(string, font, bold)]; x/base in card mm (back = as seen from the back)."""
        polys = pcbnew.SHAPE_POLY_SET()
        pen = 0.0
        for s, font, bold in runs:
            b0, adv = metrics(font, bold, cap)
            mono = font == MONO
            if mono and not track:
                ps = _text_polys(s, font, bold, cap)
                polys.Append(shift(ps, pen, -b0))
                pen += adv * len(s)
            else:
                for c in s:
                    if c != " ":
                        polys.Append(shift(_text_polys(c, font, bold, cap), pen, -b0))
                    pen += (adv if mono else advance(c, font, bold, cap)) + track
        polys.Simplify()
        if anchor != "left":
            x0, _, x1, _ = _bbox(polys)
            w = x1 - x0
            x -= w / 2 + x0 if anchor == "middle" else w + x0
        polys.Move(kp(x, base))
        polys.Inflate(MM(EMBOLDEN_MM), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.002))
        polys.Simplify()
        layer = pcbnew.B_SilkS if back else pcbnew.F_SilkS
        self.items.append((layer, self._to_kicad(polys, back), runs))
        return _bbox(polys)

    def rect(self, x, y, w, h, r, back=False):
        self.lines.append(("rrect", back, (x, y, w, h, r)))

    def hline(self, x0, x1, y, back=False):
        self.lines.append(("line", back, ((x0, y), (x1, y))))

    def dot(self, x, y, r, back=False):
        self.lines.append(("dot", back, (x, y, r)))

    def arc(self, cx, cy, r, a0, a1, w, back=False):
        self.lines.append(("arc", back, (cx, cy, r, a0, a1, w)))

    def emit(self, board):
        group = pcbnew.PCB_GROUP(board)
        group.SetName("terminal-art")
        board.Add(group)

        def P(x, y, back):
            return kp(OX + (CARD_W - x if back else x), OY + y)

        def add(shape):
            board.Add(shape)
            group.AddItem(shape)

        for layer, ps, _ in self.items:
            ps.Fracture()
            for i in range(ps.OutlineCount()):
                s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_POLY)
                s.SetLayer(layer)
                s.SetFilled(True)
                s.SetWidth(0)
                one = pcbnew.SHAPE_POLY_SET()
                one.AddOutline(ps.Outline(i))
                s.SetPolyShape(one)
                add(s)
        for kind, back, d in self.lines:
            layer = pcbnew.B_SilkS if back else pcbnew.F_SilkS
            if kind == "line":
                s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
                s.SetStart(P(*d[0], back))
                s.SetEnd(P(*d[1], back))
                s.SetWidth(MM(SILK_W))
            elif kind == "dot":
                x, y, r = d
                s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE)
                s.SetCenter(P(x, y, back))
                s.SetEnd(P(x + r, y, back))
                s.SetFilled(True)
                s.SetWidth(0)
            elif kind == "arc":
                cx, cy, r, a0, a1, w = d
                s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
                pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (a0, (a0 + a1) / 2, a1)]
                s.SetArcGeometry(P(*pts[0], back), P(*pts[1], back), P(*pts[2], back))
                s.SetWidth(MM(w))
            elif kind == "rrect":
                x, y, w, h, r = d
                for seg in ([(x + r, y), (x + w - r, y)], [(x + r, y + h), (x + w - r, y + h)],
                            [(x, y + r), (x, y + h - r)], [(x + w, y + r), (x + w, y + h - r)]):
                    s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
                    s.SetStart(P(*seg[0], back))
                    s.SetEnd(P(*seg[1], back))
                    s.SetWidth(MM(SILK_W))
                    s.SetLayer(layer)
                    add(s)
                for cx, cy, a0 in ((x + r, y + r, math.pi), (x + w - r, y + r, -math.pi / 2),
                                   (x + w - r, y + h - r, 0), (x + r, y + h - r, math.pi / 2)):
                    s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
                    pts = [(cx + r * math.cos(a), cy + r * math.sin(a))
                           for a in (a0, a0 + math.pi / 4, a0 + math.pi / 2)]
                    s.SetArcGeometry(P(*pts[0], back), P(*pts[1], back), P(*pts[2], back))
                    s.SetWidth(MM(SILK_W))
                    s.SetLayer(layer)
                    add(s)
                continue
            s.SetLayer(layer)
            add(s)


ME_NAME = "WONG ZHUN HAO"
ME_TITLE = "B.Eng. Electrical & Electronic Engineering · NTU"
PROMPT = "zhunhao ~ % "
HOST = "wongzhunhao.com"


def front_art(art):
    R, Bd = (MONO, False), (MONO, True)
    # Window: frame, title bar rule, traffic lights, centred title.
    art.rect(8.0, 7.8, 69.6, 25.0, 1.6)
    art.hline(8.0, 77.6, 10.8)
    for i in range(3):
        art.dot(10.0 + 1.6 * i, 9.3, 0.55)
    art.text([("zhunhao — -zsh — 80×24", SANS, True)], 42.8, 9.8, 1.0, anchor="middle")
    lines = [[(PROMPT, *Bd), (f"ping -c 4 {HOST}", *R)],
             [(f"PING {HOST}: 56 data bytes", *R)]]
    # Easter egg: the round-trip times' digits are ASCII codes, 87 90 72 33 = "WZH!".
    # ttl=64 with zero hops keeps sub-millisecond times realistic (same LAN).
    lines += [[(f"64 bytes: icmp_seq={n} ttl=64 time=0.{ord(c):03d} ms", *R)]
              for n, c in enumerate("WZH!")]
    lines += [[("4 packets transmitted, 4 packets received, 0.0% packet loss", *R)],
              [(PROMPT, *Bd), ("whoami", *R)],
              [(f"Wong Zhun Hao  # {ME_TITLE}", *R)]]
    boxes = []
    for i, runs in enumerate(lines):
        boxes.append(art.text(runs, 9.6, LINE_BASE_Y[i] - OY, 1.0))
    # Name, tagline, and the progress bar's brackets.
    bar0 = BAR_X[-1] - OX
    art.text([(ME_NAME, SANS, True)], bar0, 37.6, 1.75, track=0.3)
    art.text([("tap to connect ▍", *R)], bar0, 39.9, 1.0)
    art.text([("[", MONO, True)], bar0 - LED_PAD - 0.44 - 0.25, BAR_Y - OY + 0.7, 1.4, anchor="end")
    art.text([("]", MONO, True)], BAR_X[0] - OX + LED_PAD + 0.44 + 0.3, BAR_Y - OY + 0.7, 1.4)
    art.text([("JP1", *Bd)], 21.1, 41.0, 1.0, anchor="middle")
    # LED cathode marks (the library outline is cut away by jlc_dfm). Above each
    # LED run its junction and bus taps, so the dot goes below pad 1: left on
    # the line LEDs, right on the bar.
    for x, y, rot in led_positions():
        art.dot(x + (-LED_PAD if rot == 0 else LED_PAD) - OX, y + DOT_DY - OY, DOT_R)
    return boxes


def back_art(art):
    """Back view. The block starts at BACK_X, not the concept's 10 mm, so the
    five Charlieplex bus columns and their vias (back x 12.1-15.3) sit in a clear
    strip instead of on the letters; every other via lands between lines."""
    R, Bd = (MONO, False), (MONO, True)
    x = BACK_X
    boxes = [art.text([(PROMPT, *Bd), (f"whois {HOST}", *R)], x, 13.5, 1.05, back=True),
             art.text([(ME_NAME, SANS, True)], x, 21.0, 2.9, back=True, track=0.45),
             art.text([(ME_TITLE.upper(), SANS, True)], x, 25.4, 1.05, back=True, track=0.15)]
    # The tel line is only printed when a private contact file supplies a phone.
    rows = [("tel", contact.PHONE), ("mail", "zhunhaowong@gmail.com"), ("web", HOST)]
    for i, (k, v) in enumerate(r for r in rows if r[1]):
        boxes.append(art.text([(k, *Bd)], x, 31.5 + 3 * i, 1.27, back=True))
        boxes.append(art.text([(v, *R)], x + 7, 31.5 + 3 * i, 1.27, back=True))
    # NFC glyph (three arcs + dot, opening to the right) and the call to action.
    cx, cy, s = 70.0, 31.0, 1.6
    for i in range(3):
        art.arc(cx, cy, (1 + 0.9 * i) * s, -0.8, 0.8, 0.4, back=True)
    art.dot(cx, cy, 0.35 * s, back=True)
    boxes.append(art.text([("TAP TO CONNECT", SANS, True)], 70.0, 37.6, 1.0, back=True,
                          anchor="middle", track=0.2))
    boxes.append(art.text([("64 bytes from zhunhao: icmp_seq=1 ttl=64 time=0.1 ms", *R)],
                          x, 45.0, 1.0, back=True))
    # Test-pad labels, centred on each B.Cu pad. At 2.54 mm pitch the three
    # words do not fit side by side, so VCC (middle) goes above its pad, just
    # over its via (top y TP_VIA_Y - 0.3), and UPDI/GND go below, clear of the
    # footprint's r0.95 silk ring. They were placed above the coil's inner edge at
    # card y 47.5; the 0.50 mm-gap coil's inner edge is at card y 46.9, but the coil
    # is F.Cu and these labels are B.SilkS, so nothing overlaps on either side.
    for ref, kx in TP_X.items():
        base = TP_VIA_Y - 0.5 if ref == "TP2" else TP_ROW_Y + 2.25
        art.text([(TP_LABEL[ref], *Bd)], CARD_W - (kx - OX), base - OY,
                 1.0, back=True, anchor="middle")
    return boxes


def main():
    bd = Board(PCB)
    chain = chain_nets()
    clear(bd)
    mapping = place(bd, chain)
    route(bd, chain)
    feed_antenna(bd)
    art = Art()
    front_art(art)
    for box in back_art(art):
        print("back text bbox (back-view mm): %.2f %.2f %.2f %.2f" % box)
    art.emit(bd.b)
    jlc_dfm.apply(bd.b)
    # Optional output path (used by export-card.py --contact for a private copy).
    board_thickness.save(bd.b, Path(sys.argv[1]) if len(sys.argv) > 1 else PCB)
    with LAYOUT_NOTE.open("w") as f:
        f.write("# B3 Terminal LED placement (generated by build_terminal.py)\n\n")
        f.write("Chain position P0-P8 are the line-status LEDs top to bottom; P9-P19 the bar right to left.\n")
        f.write("LED index k is D[k+1]: anode CP[k/4], cathode as in the NTUAS mapping.\n\n")
        f.write("| Position | Role | Ref | Index k | Anode | Cathode | KiCad x, y (mm) |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for j, k, ref, a, c, x, y in mapping:
            role = f"line {j + 1}" if j < 9 else f"bar {20 - j}"
            f.write(f"| P{j} | {role} | {ref} | {k} | CP{a} | CP{c} | {x:.2f}, {y:.2f} |\n")
    lines = [k for j, k, *_ in mapping[:9]]
    bar = [k for j, k, *_ in reversed(mapping[9:])]  # left to right
    LED_MAP.write_text(
        "#ifndef TERMINAL_LED_MAP_H\n#define TERMINAL_LED_MAP_H\n"
        "/* Generated by hardware/terminal/build_terminal.py from the board placement;\n"
        " * see hardware/terminal/LAYOUT.md. Values are LED indices k (D[k+1]). */\n"
        "#include <stdint.h>\n"
        f"static const uint8_t terminal_line_led[9] = {{{', '.join(map(str, lines))}}};\n"
        "/* Progress bar, left to right. */\n"
        f"static const uint8_t terminal_bar_led[11] = {{{', '.join(map(str, bar))}}};\n"
        "#endif\n")
    for row in mapping:
        print(*row)


if __name__ == "__main__":
    main()
