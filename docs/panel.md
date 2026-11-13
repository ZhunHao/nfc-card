# Two-card panel (Terminal + Orbit)

Output goes to `fab/panel-v2/` (generated, not committed).

`python3 scripts/export-panel.py` builds `panel.kicad_pcb` with `scripts/build_panel.py`
(both cards side by side, 3 mm apart, 6.2 mm rails top and bottom with three fiducials
and four 1.152 mm tooling holes, 3 mm tabs perforated by 0.5 mm mouse bites set 0.25 mm
inside each card) and exports gerbers, a merged BOM and a CPL. References are the cards'
plus 100 (Terminal) or 200 (Orbit); nets are `T_*` / `O_*`. CPL rotations use the same JLC
offsets as the single cards (U2 −90°, Q1 180°).

**Re-exported 2026-11-08** with R6 (R106, R206) as a 0 Ω link, LCSC C17168 (was 4.7 kΩ, C25900),
and the LED cathode dots on both cards, which the 2026-10-28 export predated. Copper, mask,
paste, outline and drill geometry are unchanged; only F.Silkscreen and the R6 BOM line
differ. The quotes and DFM notes below are for the 2026-10-28 export and were not re-run.

**JLCONE quotes, 2026-10-28** (6.2 mm rails as committed, 15 panels of PCB, 0.8 mm, black,
ENIG, Standard PCBA, rails "Added by Customer", Confirm Parts Placement, JLC depanels and
removes rails):

| | Panel, 13 assembled (13 of each card) | Panel, 2 assembled (2 of each) | Two separate orders (13 each) |
| --- | --- | --- | --- |
| PCB (15 panels) | $46.66 | $46.66 | 2 × $31.60 |
| Assembly | $150.19 | $108.04 | 2 × $100.77 (Terminal quoted; Orbit assumed equal) |
| Total | **$196.85** | **$154.70** | ≈ $264.74 |

The panel pays setup ($25.75), stencil ($8.27), feeder loading ($18.60) and fixture
($16.54) once, plus a $25.75 assembly panel fee and a $4.06 PCB panel fee, so about $95 of
the assembly price is fixed. The first quote, with 5 mm rails and JLC adding its own, was $199.26
(JLC Standard PCBA needs both panel sides over 70 mm).

JLCDFM (PCB) on the 6.2 mm-rail panel: no danger items except silkscreen-to-hole on Orbit's
back text, where text crosses vias (kept whole on purpose, see `scripts/jlc_dfm.py`; JLC
clips ink at holes), and three fiducial warnings with no details given. Same as the 5 mm
version.
