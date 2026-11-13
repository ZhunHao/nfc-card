#!/usr/bin/env python3
"""Put Terminal and Orbit side by side in one JLC panel (KiCad 10 Python).

JLC charges assembly setup, stencil, feeder loading and fixture once per order,
and both cards use the same twelve parts, so one two-design panel may cost less
than two orders. Run with KiCad 10's bundled Python:

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        scripts/build_panel.py

Layout: the two cards GAP apart, RAIL-wide rails top and bottom RAIL_GAP away
(three fiducials and four 1.152 mm tooling holes on the rails, JLC's assembly
convention), joined by TAB_W tabs. Each tab is perforated along the card edge
by 0.5 mm mouse bites whose centres sit BITE_OFFSET inside the card, so the
break stays on the card's own outline. Nets become T_* / O_*; references gain
100 (Terminal) or 200 (Orbit), so D1 is D101 on Terminal and D201 on Orbit.
"""
import re
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import board_thickness  # noqa: E402

OUT = ROOT / 'fab/panel-v2/panel.kicad_pcb'
CARDS = [('terminal', 'T', 100), ('orbit', 'O', 200)]
CARD_X0, CARD_Y0, CARD_W, CARD_H = 100.0, 100.0, 85.6, 53.98   # both cards' outline
GAP, RAIL, RAIL_GAP = 3.0, 6.2, 2.0      # 53.98 + 2 * 8.2 = 70.38 mm: JLC Standard PCBA needs > 70 mm
TAB_W = 3.0
SIDE_TABS = (0.3, 0.7)            # fractions of the card height, card-to-card tabs
RAIL_TABS = (0.2, 0.5, 0.8)       # fractions of the card width, card-to-rail tabs
BITE_D, BITE_PITCH, BITE_OFFSET = 0.5, 0.8, 0.25
FID_COPPER, FID_OPENING, TOOLING_D = 1.0, 2.0, 1.152

MM = pcbnew.FromMM
_graveyard = []   # keep removed SWIG proxies alive (see build_terminal.py)


def v(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def rect(x0, y0, x1, y1):
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        s.Append(MM(x), MM(y))
    return s


def copy_card(panel, name, prefix, offset, dx):
    """Copy one card into `panel`, shifted dx mm, with renamed nets and references."""
    card = pcbnew.LoadBoard(str(ROOT / f'hardware/{name}/{name}.kicad_pcb'))
    nets = {}

    def net(old):
        if old.GetNetCode() <= 0:
            return panel.GetNetInfo().OrphanedItem()
        key = old.GetNetname()
        if key not in nets:
            n = pcbnew.NETINFO_ITEM(panel, f'{prefix}_{key.lstrip("/")}')
            panel.Add(n)
            nets[key] = n
        return nets[key]

    shift = v(dx, 0)
    for f in list(card.GetFootprints()):
        c = pcbnew.FOOTPRINT(f)
        c.SetReference(re.sub(r'\d+$', lambda m: str(int(m.group(0)) + offset), f.GetReference()))
        panel.Add(c)
        for p_new, p_old in zip(c.Pads(), f.Pads()):
            p_new.SetNet(net(p_old.GetNet()))
        c.Move(shift)
    for t in list(card.GetTracks()):
        c = t.Duplicate()
        c.SetNet(net(t.GetNet()))
        panel.Add(c)
        c.Move(shift)
    for d in list(card.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            continue                       # the panel draws its own outline
        c = d.Duplicate()
        panel.Add(c)
        c.Move(shift)
    _graveyard.append(card)
    outline = pcbnew.SHAPE_POLY_SET()
    card.GetBoardPolygonOutlines(outline, True)
    outline.Move(shift)
    return outline


def hole_fp(panel, ref, x, y, drill):
    fp = pcbnew.FOOTPRINT(panel)
    fp.SetReference(ref)
    fp.Reference().SetVisible(False)
    fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM)
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(MM(drill), MM(drill)))
    pad.SetDrillSize(pcbnew.VECTOR2I(MM(drill), MM(drill)))
    pad.SetLayerSet(pad.UnplatedHoleMask())
    fp.Add(pad)
    fp.SetPosition(v(x, y))
    panel.Add(fp)


def fiducial(panel, ref, x, y):
    fp = pcbnew.FOOTPRINT(panel)
    fp.SetReference(ref)
    fp.Reference().SetVisible(False)
    fp.SetAttributes(pcbnew.FP_SMD | pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM)
    pad = pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(MM(FID_COPPER), MM(FID_COPPER)))
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.F_Mask)
    pad.SetLayerSet(ls)
    pad.SetLocalSolderMaskMargin(MM((FID_OPENING - FID_COPPER) / 2))
    fp.Add(pad)
    fp.SetPosition(v(x, y))
    panel.Add(fp)


def bites(panel, n, x0, y0, x1, y1):
    """Mouse bites along the card edge from (x0, y0) to (x1, y1), spanning one tab."""
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    count = int(length / BITE_PITCH) + 1
    start = (length - (count - 1) * BITE_PITCH) / 2
    for i in range(count):
        t = (start + i * BITE_PITCH) / length
        hole_fp(panel, f'MB{n}_{i}', x0 + t * (x1 - x0), y0 + t * (y1 - y0), BITE_D)


def build():
    panel = pcbnew.LoadBoard(str(ROOT / 'hardware/terminal/terminal.kicad_pcb'))
    old = list(panel.GetFootprints()) + list(panel.GetTracks()) + list(panel.GetDrawings())
    for item in old:
        panel.Remove(item)
    _graveyard.extend(old)

    substrate = pcbnew.SHAPE_POLY_SET()
    for i, (name, prefix, offset) in enumerate(CARDS):
        substrate.BooleanAdd(copy_card(panel, name, prefix, offset, i * (CARD_W + GAP)))

    x_left, x_right = CARD_X0, CARD_X0 + 2 * CARD_W + GAP
    y_top, y_bot = CARD_Y0, CARD_Y0 + CARD_H
    rail_top = (y_top - RAIL_GAP - RAIL, y_top - RAIL_GAP)
    rail_bot = (y_bot + RAIL_GAP, y_bot + RAIL_GAP + RAIL)
    substrate.BooleanAdd(rect(x_left, *rail_top[:1], x_right, rail_top[1]))
    substrate.BooleanAdd(rect(x_left, rail_bot[0], x_right, rail_bot[1]))

    n = 0
    gap_x0 = CARD_X0 + CARD_W
    for f in SIDE_TABS:                       # card to card
        y = y_top + f * CARD_H
        substrate.BooleanAdd(rect(gap_x0 - 0.5, y - TAB_W / 2, gap_x0 + GAP + 0.5, y + TAB_W / 2))
        bites(panel, n, gap_x0 - BITE_OFFSET, y - TAB_W / 2, gap_x0 - BITE_OFFSET, y + TAB_W / 2)
        bites(panel, n + 1, gap_x0 + GAP + BITE_OFFSET, y - TAB_W / 2, gap_x0 + GAP + BITE_OFFSET, y + TAB_W / 2)
        n += 2
    for i in range(len(CARDS)):               # card to rails
        cx0 = CARD_X0 + i * (CARD_W + GAP)
        for f in RAIL_TABS:
            x = cx0 + f * CARD_W
            substrate.BooleanAdd(rect(x - TAB_W / 2, rail_top[1] - 0.5, x + TAB_W / 2, y_top + 0.5))
            substrate.BooleanAdd(rect(x - TAB_W / 2, y_bot - 0.5, x + TAB_W / 2, rail_bot[0] + 0.5))
            bites(panel, n, x - TAB_W / 2, y_top + BITE_OFFSET, x + TAB_W / 2, y_top + BITE_OFFSET)
            bites(panel, n + 1, x - TAB_W / 2, y_bot - BITE_OFFSET, x + TAB_W / 2, y_bot - BITE_OFFSET)
            n += 2
    substrate.Simplify()

    for o in range(substrate.OutlineCount()):
        chains = [substrate.Outline(o)] + [substrate.Hole(o, h) for h in range(substrate.HoleCount(o))]
        for chain in chains:
            edge = pcbnew.PCB_SHAPE(panel, pcbnew.SHAPE_T_POLY)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetPolyShape(pcbnew.SHAPE_POLY_SET(chain))
            edge.SetFilled(False)
            edge.SetWidth(MM(0.05))
            panel.Add(edge)

    ymid_top, ymid_bot = sum(rail_top) / 2, sum(rail_bot) / 2
    for k, (x, y) in enumerate(((x_left + 10, ymid_top), (x_right - 10, ymid_top), (x_left + 10, ymid_bot))):
        fiducial(panel, f'FID{k + 1}', x, y)
    for k, (x, y) in enumerate(((x_left + 5, ymid_top), (x_right - 5, ymid_top),
                                (x_left + 5, ymid_bot), (x_right - 5, ymid_bot))):
        hole_fp(panel, f'TH{k + 1}', x, y, TOOLING_D)

    board_thickness.save(panel, OUT)
    bb = panel.GetBoardEdgesBoundingBox()
    print('saved', OUT, f'{pcbnew.ToMM(bb.GetWidth()):.2f} x {pcbnew.ToMM(bb.GetHeight()):.2f} mm,',
          f'{len(list(panel.GetFootprints()))} footprints')


if __name__ == '__main__':
    build()
