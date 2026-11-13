#!/usr/bin/env python3
"""Check that every silkscreen polygon on a board has strokes >= a minimum width.

Each filled polygon is rasterised at 5 um and morphologically opened with a
disc of the minimum stroke diameter. A stroke or join narrower than the disc
disappears, which splits the glyph or removes most of its area; acute corners
only lose their tips and pass. Run with KiCad 10's Python:

    .../Python.framework/Versions/Current/bin/python3 hardware/terminal/check_silk.py \
        hardware/terminal/terminal.kicad_pcb [min_stroke_mm, default 0.15]

Exit status 1 if any polygon fails. A run at 0.25 mm fails most glyphs, which
is the check that the test can fail.
"""
import sys
from collections import deque

import numpy as np
import pcbnew
from PIL import Image, ImageDraw

PX = 200  # pixels per mm


def components(a):
    lab = np.zeros(a.shape, np.int32)
    n = 0
    for y, x in zip(*np.nonzero(a)):
        if lab[y, x]:
            continue
        n += 1
        q = deque([(y, x)])
        lab[y, x] = n
        while q:
            cy, cx = q.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = cy + dy, cx + dx
                if a[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
    return n


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    min_stroke = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
    r = int(round((min_stroke / 2 - 0.0005) * PX))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    offsets = [(dy - r, dx - r) for dy, dx in zip(*np.nonzero(xx * xx + yy * yy <= r * r))]

    def erode(a):
        out = np.ones_like(a)
        for dy, dx in offsets:
            out &= np.roll(np.roll(a, dy, 0), dx, 1)
        return out

    def dilate(a):
        out = np.zeros_like(a)
        for dy, dx in offsets:
            out |= np.roll(np.roll(a, dy, 0), dx, 1)
        return out

    checked, failed = 0, []
    for s in board.GetDrawings():
        if (s.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS) or s.GetClass() != "PCB_SHAPE"
                or s.GetShape() != pcbnew.SHAPE_T_POLY):
            continue
        ps = s.GetPolyShape()
        bb = ps.BBox()
        x0, y0 = bb.GetX(), bb.GetY()
        w = int(pcbnew.ToMM(bb.GetWidth()) * PX) + 4 * r
        h = int(pcbnew.ToMM(bb.GetHeight()) * PX) + 4 * r
        img = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(img)
        for i in range(ps.OutlineCount()):
            ch = ps.Outline(i)
            draw.polygon([((ch.CPoint(j).x - x0) / 1e6 * PX + 2 * r,
                           (ch.CPoint(j).y - y0) / 1e6 * PX + 2 * r)
                          for j in range(ch.PointCount())], fill=255)
        a = np.array(img) > 127
        opened = dilate(erode(a))
        checked += 1
        if components(opened) != components(a) or opened.sum() < 0.5 * a.sum():
            failed.append((s.GetLayerName(), round(pcbnew.ToMM(x0), 2), round(pcbnew.ToMM(y0), 2)))
    for f in failed[:20]:
        print("thin stroke:", *f)
    print(f"silk strokes >= {min_stroke} mm: {checked - len(failed)}/{checked} polygons pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
