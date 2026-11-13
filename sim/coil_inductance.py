#!/usr/bin/env python3
"""Coil inductance and coil-to-supply-loop coupling from the routed copper (KiCad Python).

  coil_inductance.py BOARD.kicad_pcb [--top N]

L1's spiral comes from its footprint's pad primitives (scripts/check_antenna.py parses
them), placed and rotated as on the board. Each supply loop is the copper path
scripts/check_loops.py finds. Inductances are Neumann integrals over 0.25 mm pieces
with the kernel 1/sqrt(r^2 + g^2), g = the track's geometric mean distance (GMD), so a
piece's own term is a bar's partial self-inductance. Current is uniform (no skin or
proximity effect), so L is the low-frequency value. A Grover rectangle self-check runs first.

Prints L1, then per loop: area, self-inductance, mutual M to L1, k, and the resonance shift
of a 50 pF tank, df/f = k^2/2 for a loop whose resistance is small against its reactance.
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_antenna  # noqa: E402
import check_loops  # noqa: E402

MU0 = 4e-7 * math.pi
PIECE_MM = 0.25
LIB = Path(__file__).resolve().parent.parent / "hardware/lib/nfc-card.pretty"
BOARD_MM = 0.8
CU_MM = 0.035


def gmd(width, thick=CU_MM):
    return 0.2235 * (width + thick)


def pieces(path, closed):
    """Midpoints and vectors (mm) of a polyline cut into <= PIECE_MM pieces."""
    pts = path + path[:1] if closed else path
    mids, vecs = [], []
    for a, b in zip(pts, pts[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        n = max(1, math.ceil(np.linalg.norm(b - a) / PIECE_MM))
        for i in range(n):
            p, q = a + (b - a) * i / n, a + (b - a) * (i + 1) / n
            mids.append((p + q) / 2)
            vecs.append(q - p)
    return np.array(mids), np.array(vecs)


def neumann(m1, v1, m2, v2, g):
    """mu0/4pi sum dl1.dl2 / sqrt(r^2 + g^2), in henries. Positions in mm."""
    total = 0.0
    for i in range(0, len(m1), 2000):
        d = m1[i:i + 2000, None, :] - m2[None, :, :]
        r = np.sqrt((d ** 2).sum(-1) + g * g)
        total += ((v1[i:i + 2000] @ v2.T) / r).sum()
    return 1e-7 * total * 1e-3


def grover_rect(a, b, r):
    a, b, r = a * 1e-3, b * 1e-3, r * 1e-3
    d = math.hypot(a, b)
    return MU0 / math.pi * (a * math.log(2 * a * b / (r * (a + d))) + b * math.log(2 * a * b / (r * (b + d)))
                            - 2 * (a + b - d) + (a + b) / 4)


def self_check():
    a, b, w = 26.3, 3.48, 0.3
    path = [(0, 0, 0), (a, 0, 0), (a, b, 0), (0, b, 0)]
    m, v = pieces(path, True)
    num, ref = neumann(m, v, m, v, gmd(w)), grover_rect(a, b, gmd(w))
    print(f"self-check {a} x {b} mm rectangle, 0.3 mm track: {num * 1e9:.2f} nH, Grover {ref * 1e9:.2f} nH "
          f"({(num / ref - 1) * 100:+.1f} %)")


def coil(board):
    fp = board.FindFootprintByReference("L1")
    pads, segs, _ = check_antenna.parse(LIB / (fp.GetFPID().GetLibItemName().wx_str() + ".kicad_mod"))
    pos, ang = fp.GetPosition(), math.radians(fp.GetOrientationDegrees())
    ox, oy = pos.x / pcbnew.PCB_IU_PER_MM, pos.y / pcbnew.PCB_IU_PER_MM
    c, s = math.cos(ang), math.sin(ang)
    z = BOARD_MM - CU_MM / 2 if fp.GetLayer() == pcbnew.F_Cu else CU_MM / 2

    def place(p):  # KiCad rotation is clockwise on screen (y down)
        return (ox + p[0] * c + p[1] * s, oy - p[0] * s + p[1] * c, z)

    path = [place(segs[0][0])] + [place(e) for _, e, _ in segs]
    for (a, b, _), (n, _, _) in zip(segs, segs[1:]):
        if math.dist(b, n) > 1e-3:
            sys.exit("L1 spiral segments are not end to end; ordered path assumption broken")
    board_pad = {p.GetNumber(): p.GetPosition() for p in fp.Pads()}["1"]
    lib_pad = place(pads["1"][1:3])
    if math.dist((board_pad.x / pcbnew.PCB_IU_PER_MM, board_pad.y / pcbnew.PCB_IU_PER_MM), lib_pad[:2]) > 0.01:
        sys.exit("library footprint placement does not land on the board's pad 1")
    return path, segs[0][2]


def supply_paths(cu):
    """check_loops.supply_loops, but keeping each loop's centreline polygon."""
    rails = [e for e in cu.edges if e["net"] in check_loops.SUPPLY_NETS]
    rails += [cu.part("JP1", "1", "2"),
              cu.part("Q1", cu.pad_on("Q1", "/VCC"), cu.pad_on("Q1", "/SS_CAP"), "Q1(on)")]
    shunts = [cu.part("C2", "1", "2"), cu.part("C3", "1", "2"), cu.part("C4", "1", "2"),
              cu.part("U1", cu.pad_on("U1", "/VOUT"), cu.pad_on("U1", "/GND")),
              cu.part("U2", cu.pad_on("U2", "/VCC"), cu.pad_on("U2", "/GND"))]
    out = []
    for i, a in enumerate(shunts):
        for b in shunts[i + 1:]:
            edges = rails + [b, a]
            cycle = check_loops.loop_through(edges, len(edges) - 1)
            pts = []
            for n0, _, j in cycle:
                poly = edges[j]["poly"]
                pts += poly if edges[j]["u"] == n0 else poly[::-1]
            dedup = [p for k, p in enumerate(pts) if k == 0 or math.dist(p, pts[k - 1]) > 1e-6]
            out.append((check_loops.area(dedup), f"{a['kind']}-{b['kind']}",
                        [(x, y, BOARD_MM / 2) for x, y in dedup]))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--loop-track-mm", type=float, default=0.3)
    args = ap.parse_args()
    self_check()
    board = pcbnew.LoadBoard(args.board)
    path, width = coil(board)
    cm, cv = pieces(path, False)
    l1 = neumann(cm, cv, cm, cv, gmd(width))
    print(f"L1 {l1 * 1e6:.3f} uH ({len(cm)} pieces, {width} mm track); "
          f"f0 at 50 pF {1 / (2 * math.pi * math.sqrt(l1 * 50e-12)) / 1e6:.2f} MHz")
    for area, name, loop in supply_paths(check_loops.Copper(board))[:args.top]:
        lm, lv = pieces(loop, True)
        l2 = neumann(lm, lv, lm, lv, gmd(args.loop_track_mm))
        m = abs(neumann(cm, cv, lm, lv, 0.0))
        k = m / math.sqrt(l1 * l2)
        print(f"  {name:7s} {area:6.1f} mm2  Lloop {l2 * 1e9:6.1f} nH  M {m * 1e9:6.2f} nH  k {k:.4f}  "
              f"df/f {k * k / 2 * 100:.3f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
