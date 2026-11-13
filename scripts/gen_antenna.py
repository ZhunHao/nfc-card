#!/usr/bin/env python3
"""Generate the ID-1 perimeter NFC antenna footprint with KiCad's own pcbnew API.

Run with KiCad's bundled Python (it ships pcbnew):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 \
      scripts/gen_antenna.py [--ntuas] [--out DIR]

Same structure as the NTUAS footprint: pad 1 (LA, outer end) is a custom pad whose
segment primitives draw the whole spiral; each lap closes on the bottom edge, jogs up
one pitch and starts the next lap; the innermost lap ends on pad 2 (LB). Pads 1 and 2
form a net tie so the coil may short LA to LB. --ntuas rebuilds the original NTUAS
coil, which scripts/check_antenna.py compares against the committed footprint to
prove this generator before trusting its option A output.
"""
import argparse
from pathlib import Path

import pcbnew

CARD_W, CARD_H = 85.60, 53.98   # ID-1; the footprint origin is the card centre
TURNS = 4
FEED_X = -22.8                  # pad 1 x: both NTUAS and option A keep U1's feed here

DESIGNS = {
    # name: (centreline inset of the outer turn, track, pitch, inner-end offset from FEED_X)
    "NFC_Antenna_Rect_ID1_4turn": (4.0, 0.35, 0.70, 4.0),
    "NFC_Antenna_Rect_ID1_4turn_W090": (2.45, 0.90, 1.40, 5.6),
}
DESCR = {
    "NFC_Antenna_Rect_ID1_4turn": "ID-1 perimeter NFC loop antenna, 4 turns, 0.35mm track, 0.35mm gap, "
        "4mm inset from an 85.60x53.98mm outline. Pad 1 = outer end (LA), pad 2 = inner end (LB). "
        "Spiral is F.Cu copper graphics belonging to the footprint. Target ~2.4uH.",
    "NFC_Antenna_Rect_ID1_4turn_W090": "ID-1 perimeter NFC loop antenna (option A), 4 turns, 0.90mm track, "
        "0.50mm gap, outer copper edge 2.0mm inside an 85.60x53.98mm outline. Pad 1 = outer end (LA), "
        "pad 2 = inner end (LB). Spiral is pad 1's custom-shape primitives. FastHenry 2.37uH at 13.56MHz, "
        "14.62MHz with 50pF; tune down with C1.",
}


def spiral(inset, pitch, end_offset):
    """Centreline polyline in footprint coordinates, pad 1 first, pad 2 last."""
    x_r, y_b = CARD_W / 2 - inset, CARD_H / 2 - inset
    pts = [(FEED_X, y_b)]
    for i in range(TURNS):
        o = i * pitch
        pts += [(x_r - o, y_b - o), (x_r - o, -y_b + o), (-x_r + o, -y_b + o), (-x_r + o, y_b - o)]
        if i < TURNS - 1:
            pts += [(FEED_X - o - pitch, y_b - o), (FEED_X - o - pitch, y_b - o - pitch)]
        else:
            pts.append((FEED_X - end_offset, y_b - o))
    return pts


def f_cu_only():
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    return layers


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def build(name):
    inset, track, pitch, end_offset = DESIGNS[name]
    pts = spiral(inset, pitch, end_offset)
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("nfc-card", name))
    fp.SetLibDescription(DESCR[name])
    fp.SetAttributes(pcbnew.FP_SMD)
    anchor = 0.6 if track < 0.6 else track

    x_r, y_b = CARD_W / 2 - inset, CARD_H / 2 - inset
    fp.Reference().SetText("REF**")
    fp.Reference().SetFPRelativePosition(mm(FEED_X - 2.0, y_b - TURNS * pitch - 0.85))
    fp.Value().SetText(name)
    fp.Value().SetFPRelativePosition(mm(FEED_X - 2.0, y_b + 1.55))

    p1 = pcbnew.PAD(fp)
    p1.SetNumber("1")
    p1.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p1.SetLayerSet(f_cu_only())
    p1.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CUSTOM)
    p1.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_RECTANGLE)
    p1.SetSize(pcbnew.F_Cu, mm(anchor, anchor))
    p1.SetCustomShapeInZoneOpt(pcbnew.CUSTOM_SHAPE_ZONE_MODE_OUTLINE)
    fp.Add(p1)
    p1.SetFPRelativePosition(mm(*pts[0]))
    x0, y0 = pts[0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        seg = pcbnew.PCB_SHAPE(None, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(mm(ax - x0, ay - y0))
        seg.SetEnd(mm(bx - x0, by - y0))
        seg.SetWidth(pcbnew.FromMM(track))
        p1.AddPrimitiveShape(pcbnew.F_Cu, seg)
        seg.thisown = False  # the pad owns it now; Python must not free it

    p2 = pcbnew.PAD(fp)
    p2.SetNumber("2")
    p2.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p2.SetLayerSet(f_cu_only())
    p2.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_RECTANGLE)
    p2.SetSize(pcbnew.F_Cu, mm(anchor, anchor))
    fp.Add(p2)
    p2.SetFPRelativePosition(mm(*pts[-1]))
    fp.AddNetTiePadGroup("1,2")

    # Courtyard ring: outside the outer copper edge, inside the inner copper edge.
    half = track / 2
    inner = (TURNS - 1) * pitch
    for sx, sy in ((x_r + half + 0.25, y_b + half + 0.25),
                   (x_r - inner - half - 0.25, y_b - inner - half - 0.25)):
        r = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
        r.SetLayer(pcbnew.F_CrtYd)
        r.SetWidth(pcbnew.FromMM(0.05))
        r.SetStart(mm(-sx, -sy))
        r.SetEnd(mm(sx, sy))
        fp.Add(r)
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ntuas", action="store_true", help="rebuild the original NTUAS coil")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "hardware/lib/nfc-card.pretty"))
    args = ap.parse_args()
    name = "NFC_Antenna_Rect_ID1_4turn" if args.ntuas else "NFC_Antenna_Rect_ID1_4turn_W090"
    Path(args.out).mkdir(parents=True, exist_ok=True)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(args.out, build(name))
    print(f"wrote {name} to {args.out}")


if __name__ == "__main__":
    main()
