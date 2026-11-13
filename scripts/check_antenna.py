#!/usr/bin/env python3
"""Verify antenna footprints by geometry (read-only).

  check_antenna.py same A.kicad_mod B.kicad_mod   pads, net tie and every spiral segment match
  check_antenna.py check FILE.kicad_mod          option A design rules (inset, clearance, turns)

`same` proves scripts/gen_antenna.py by rebuilding the committed NTUAS coil (--ntuas) and
comparing it with the original. `check` then holds the generated option A coil to its
design numbers and JLCPCB's 0.10/0.10 mm 1 oz track/space minimum.
"""
import math
import re
import sys
from pathlib import Path

CARD_W, CARD_H = 85.60, 53.98
TOL = 1e-4


def parse(path):
    s = Path(path).read_text()
    pads = {}
    for m in re.finditer(r'\(pad "(\d+)" smd (\w+)\s*\(at ([-\d.]+) ([-\d.]+)\)\s*\(size ([-\d.]+) ([-\d.]+)\)', s):
        pads[m.group(1)] = (m.group(2), float(m.group(3)), float(m.group(4)), float(m.group(5)), float(m.group(6)))
    x0, y0 = pads["1"][1:3]
    segs = [((x0 + float(a), y0 + float(b)), (x0 + float(c), y0 + float(d)), float(w))
            for a, b, c, d, w in re.findall(
                r'\(gr_line\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)\s*\(width ([-\d.]+)\)', s)]
    tie = re.findall(r'\(net_tie_pad_groups "([^"]+)"\)', s)
    return pads, segs, tie


def same(a, b):
    pa, sa, ta = parse(a)
    pb, sb, tb = parse(b)
    problems = []
    if pa.keys() != pb.keys() or any(
            pa[k][0] != pb[k][0] or any(abs(x - y) > TOL for x, y in zip(pa[k][1:], pb[k][1:])) for k in pa):
        problems.append(f"pads differ: {pa} vs {pb}")
    if ta != tb:
        problems.append(f"net tie differs: {ta} vs {tb}")
    if len(sa) != len(sb):
        problems.append(f"segment count {len(sa)} vs {len(sb)}")
    for i, (u, v) in enumerate(zip(sa, sb)):
        if any(abs(p - q) > TOL for p, q in zip((*u[0], *u[1], u[2]), (*v[0], *v[1], v[2]))):
            problems.append(f"segment {i}: {u} vs {v}")
    return problems, f"{len(sa)} segments, pads {sorted(pa)}"


def seg_dist(p, q, r, s):
    def pt(a, b, c):
        (ax, ay), (bx, by), (cx, cy) = a, b, c
        dx, dy = cx - bx, cy - by
        t = 0 if dx == dy == 0 else max(0, min(1, ((ax - bx) * dx + (ay - by) * dy) / (dx * dx + dy * dy)))
        return math.hypot(ax - bx - t * dx, ay - by - t * dy)
    # axis-aligned segments never cross here without sharing an endpoint, so endpoint distances suffice
    return min(pt(p, r, s), pt(q, r, s), pt(r, p, q), pt(s, p, q))


def check(path, inset=2.0, track=0.90, gap=0.50, turns=4, jlc=0.10):
    pads, segs, tie = parse(path)
    problems = []
    if tie != ["1,2"]:
        problems.append(f"net tie {tie}, want ['1,2']")
    if any(abs(w - track) > TOL for *_, w in segs):
        problems.append("not every segment is the specified track width")
    for i in range(len(segs) - 1):
        if any(abs(a - b) > TOL for a, b in zip(segs[i][1], segs[i + 1][0])):
            problems.append(f"spiral breaks between segments {i} and {i + 1}")
    xs = [x for (a, b, _) in segs for x in (a[0], b[0])]
    ys = [y for (a, b, _) in segs for y in (a[1], b[1])]
    edge = min(CARD_W / 2 - max(map(abs, xs)), CARD_H / 2 - max(map(abs, ys))) - track / 2
    if abs(edge - inset) > TOL:
        problems.append(f"outer copper edge {edge:.3f} mm from the card edge, want {inset}")
    vertical_runs = sorted({round(a[0], 4) for a, b, _ in segs if abs(a[0] - b[0]) < TOL and a[0] > 0})
    if len(vertical_runs) != turns:
        problems.append(f"{len(vertical_runs)} right-side runs, want {turns} turns")
    worst = min(seg_dist(*segs[i][:2], *segs[j][:2]) - track
                for i in range(len(segs)) for j in range(i + 2, len(segs)))
    if worst < gap - TOL:
        problems.append(f"closest non-adjacent copper {worst:.3f} mm, want >= {gap}")
    if worst < jlc or track < jlc:
        problems.append("below JLCPCB 0.10/0.10 mm")
    end = segs[-1][1]
    if math.hypot(pads["2"][1] - end[0], pads["2"][2] - end[1]) > TOL:
        problems.append("pad 2 is not on the spiral's inner end")
    inner = min(CARD_W / 2 - min(vertical_runs), CARD_H / 2 - min(abs(y) for (a, b, _) in segs
                for y in (a[1], b[1]) if abs(a[1] - b[1]) < TOL)) + track / 2
    return problems, (f"{len(segs)} segments, {len(vertical_runs)} turns, outer edge {edge:.2f} mm, "
                      f"inner edge {inner:.2f} mm from card edge, min copper gap {worst:.3f} mm")


if __name__ == "__main__":
    mode, *files = sys.argv[1:]
    problems, summary = same(*files) if mode == "same" else check(*files)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"antenna {mode}: {summary}")
