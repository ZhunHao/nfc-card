"""JLCDFM clean-up shared by both build scripts (KiCad 10 Python).

JLCONE's DFM tool (checked 2026-10-28) grades these as good only above its
thresholds, so `apply` runs on the finished board before it is saved:

- Soldermask web >= 0.15 mm. Black mask needs wider webs than green, and the
  0.4 mm-pitch U2 (and Q1, U1) only had 0.10 mm at the board's 0.05 mm mask
  expansion. Their pads get MASK_MARGIN instead.
- Vias get a VIA_D pad: a 0.15 mm annular ring is only a warning.
- Silkscreen strokes and text are wider than JLC's 0.15 mm minimum line.
- Silkscreen keeps SILK_CLEAR from every pad and hole on its side (JLCDFM's
  "good" is >= 0.18 mm, measured a little tighter than KiCad). Lines and
  outlines closer than that are cut back and stored as filled polygons in the
  same footprint or on the board, then opened by SILK_MIN so no cut leaves a
  sliver thinner than the minimum line.
- Text is only cut back from pads. A 0.25 mm ring round every via punches
  0.8 mm holes through letters and the opening shreds narrow glyphs (Orbit's
  TLE line), so text over a via stays whole and JLC clips the ink at the hole.

Running it twice changes nothing: the cut polygons already clear everything.
Usage as a script: jlc_dfm.py <board.kicad_pcb>...
"""
import sys

import pcbnew

MASK_MARGIN = 0.02              # mm, for the fine-pitch parts below
FINE_PITCH = {'U1', 'U2', 'Q1'}
VIA_D = 0.65                    # 0.3 mm drill -> 0.175 mm ring
SILK_MIN = 0.16                 # JLCDFM grades exactly 0.15 mm a warning
SILK_CLEAR = 0.25               # JLC's recommendation; JLCDFM measured 0.2 as 0.15
MAX_ERR = pcbnew.FromMM(0.005)
SIDES = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}


def mm(v):
    return pcbnew.FromMM(v)


# Removed items are owned by nobody; if Python collects their proxies, KiCad 10's
# SWIG type table breaks (as in build_terminal.py). Keep them alive until exit.
_graveyard = []


def keepouts(footprints, vias, silk):
    """(pads, pads + holes) on the silk's side, each grown by SILK_CLEAR."""
    cu, pads, ko = SIDES[silk], pcbnew.SHAPE_POLY_SET(), pcbnew.SHAPE_POLY_SET()
    for f in footprints:
        for p in f.Pads():
            if p.IsOnLayer(cu):
                p.TransformShapeToPolygon(pads, cu, mm(SILK_CLEAR), MAX_ERR, pcbnew.ERROR_OUTSIDE)
            if p.GetDrillSizeX() > 0:
                hole = pcbnew.PCB_SHAPE(None, pcbnew.SHAPE_T_CIRCLE)
                hole.SetCenter(p.GetPosition())
                hole.SetRadius(p.GetDrillSizeX() // 2)
                hole.SetFilled(True)
                hole.TransformShapeToPolygon(ko, cu, mm(SILK_CLEAR), MAX_ERR, pcbnew.ERROR_OUTSIDE)
    for v in vias:
        hole = pcbnew.PCB_SHAPE(None, pcbnew.SHAPE_T_CIRCLE)
        hole.SetCenter(v.GetPosition())
        hole.SetRadius(v.GetDrill() // 2)
        hole.SetFilled(True)
        hole.TransformShapeToPolygon(ko, cu, mm(SILK_CLEAR), MAX_ERR, pcbnew.ERROR_OUTSIDE)
    pads.Simplify()
    ko.BooleanAdd(pads)
    ko.Simplify()
    return pads, ko


def widen(item):
    if item.GetClass() in ('PCB_TEXT', 'PCB_FIELD'):
        if item.IsVisible() and item.GetTextThickness() < mm(SILK_MIN):
            item.SetTextThickness(mm(SILK_MIN))
    elif 0 < item.GetWidth() < mm(SILK_MIN):
        item.SetWidth(mm(SILK_MIN))


def cut(items, silk, pads, ko):
    """Cut (item, owner) pairs on `silk` back (text from `pads`, the rest from `ko`)."""
    n = 0
    for item, owner in items:
        if item.GetClass() not in ('PCB_SHAPE', 'PCB_TEXT'):
            continue
        widen(item)
        poly = pcbnew.SHAPE_POLY_SET()
        text = item.GetClass() == 'PCB_TEXT'
        if text:
            # TransformShapeToPolygon gives a text's bounding box, not its glyphs.
            item.TransformTextToPolySet(poly, 0, MAX_ERR, pcbnew.ERROR_INSIDE)
            ko_item = pads
        else:
            item.TransformShapeToPolygon(poly, silk, 0, MAX_ERR, pcbnew.ERROR_INSIDE)
            ko_item = ko
        hit = pcbnew.SHAPE_POLY_SET(poly)
        hit.BooleanIntersection(ko_item)
        if hit.Area() < mm(0.001) ** 2:
            continue
        poly.BooleanSubtract(ko_item)
        if not text:
            # Morphological opening: drop anything narrower than the minimum line.
            half = mm(SILK_MIN / 2) + 1
            poly.Deflate(half, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MAX_ERR)
            poly.Inflate(half, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MAX_ERR)
            poly.BooleanSubtract(ko_item)
        poly.Fracture()
        for i in range(poly.OutlineCount()):
            piece = pcbnew.PCB_SHAPE(owner, pcbnew.SHAPE_T_POLY)
            piece.SetLayer(silk)
            piece.SetPolyShape(pcbnew.SHAPE_POLY_SET(poly.Outline(i)))
            piece.SetFilled(True)
            piece.SetWidth(0)
            owner.Add(piece)
        owner.Remove(item)
        _graveyard.append(item)
        n += 1
    return n


def apply(board):
    # Collect everything first: SWIG iterators go stale once the board changes.
    footprints = list(board.GetFootprints())
    vias = [v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA']
    drawings = list(board.GetDrawings())
    graphics = [(g, f) for f in footprints for g in f.GraphicalItems()]
    for f in footprints:
        if f.GetReference() in FINE_PITCH:
            for p in f.Pads():
                p.SetLocalSolderMaskMargin(mm(MASK_MARGIN))
    for v in vias:
        v.SetWidth(mm(VIA_D))
    kos = {s: keepouts(footprints, vias, s) for s in SIDES}
    cuts = {}
    for s, (pads, ko) in kos.items():
        items = [(d, board) for d in drawings if d.GetLayer() == s]
        items += [(g, f) for g, f in graphics if g.GetLayer() == s]
        cuts[pcbnew.LayerName(s)] = cut(items, s, pads, ko)
    print('jlc_dfm: silk items cut back', cuts)


if __name__ == '__main__':
    sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
    import board_thickness
    from pathlib import Path
    for arg in sys.argv[1:]:
        path = Path(arg).resolve()
        b = pcbnew.LoadBoard(str(path))
        apply(b)
        board_thickness.save(b, path)
