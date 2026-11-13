# B3 Terminal card (rev B)

The NTUAS card's circuit with the rev B electronics (QFN-20 MCU, UPDI clamp D21, VCC
soft-start Q1/R7/R8/C4, rev B coil), laid out as a macOS Terminal window running `ping`. Concept: `docs/design/concepts.html`
(`b3`). Fab package: `python3 scripts/export-card.py terminal` writes `fab/terminal-v2/` (not committed).

## How the board is made

`build_terminal.py` (run with KiCad 10's bundled Python) rewrites the copied NTUAS board:
placement, routing and all silkscreen. It keeps L1, U1, C1, C2, JP1 and the RF/VOUT copper
as copied, except the coil feed (below). It is idempotent, and it also writes `LAYOUT.md` and
`firmware/boards/terminal/led_map.h`, so the animation order always follows the placement.
FreeRouting was not used.

- **LED chain.** The 20 LEDs form one Eulerian circuit through the 20 ordered CP pairs:
  9 line LEDs top to bottom, then the bar right to left. Neighbouring LEDs share a net at
  their junction, so only 21 taps reach the bus. The bus is five B.Cu rows above the bar
  and five B.Cu columns left of the line LEDs, nested so nothing crosses. The resistors
  feed it through a staircase. LED mapping: [LAYOUT.md](LAYOUT.md).
- **Coil feed (rev B coil, `NFC_Antenna_Rect_ID1_4turn_W090`).** The pads moved to LA
  (120.0, 151.53) and LB (114.4, 147.33). The script drops the NTUAS feed pieces, and the
  rev B ones for the 0.30 mm-gap coil, that no longer reach them. LA now runs B.Cu down
  x = 115.8 under the inner turns to a via at (120.0, 152.9), then F.Cu up to its pad. LB
  steps from (114.7, 146.58) onto its pad on F.Cu. Since 2026-10-27 the coil has 0.50 mm
  gaps (see the Orbit README's pre-order checks), so its inner edge is 7.10 mm from the card
  edge; the closest other-net copper is a GND via at (121.2, 146.3), about 0.3 mm away.
- **MCU block (QFN-20 fan-out).** U2 (QFN-20 3×3 mm, 0.4 mm pitch) sits at (129.6, 139.3),
  rotated 180°. Its east side reads PA4, VCC, GND, PA3, PA2 top to bottom, with PA5 on the
  north side, PA1 and UPDI on the south side, and SS_GATE on the west. Each PA pin escapes
  on 0.15 mm F.Cu to a via. From there B.Cu, sometimes running under the body, brings it to
  the existing via column left of the R stack, which wants PA4, PA5, PA1, PA2, PA3 top to
  bottom. PA2 turns down before PA3 does, and higher, so their rows swap without crossing.
  PA1 comes back north under the body. C3 sits right of pins 3–4, 0.2 mm above pin 4: pin 4
  jogs up into C3's VCC pad, the VCC rail drops onto the same pad, and C3's GND pad drops to
  pin 3's line and runs straight into pin 3. That decoupling loop is 4.0 mm long and
  encloses 1.1 mm² (the first rev B layout sent C3's ground 33.7 mm round the bottom rail:
  34.8 mm, 76.6 mm²; rev A was 9.7 mm, 4.5 mm²). In `sim/u2_decoupling.cir` the dip at
  U2's pins under assumed 10 mA, 4 ns core spikes is 42 mV, as on Orbit (91 mV before the
  fix). The exposed pad ties to pin 3 inside the body and drops through a via (0.3 mm, at
  the pad centre) to a B.Cu link to the GND trunk at x = 124.6, which runs to the bottom
  GND rail. That trunk is U2's only ground link, so the GND net stays a tree. The
  VOUT→JP1→C3→GND loop now encloses 86.9 mm² (rev A 184.5 mm²).
- **UPDI clamp D21** (SOD-882) sits under the TP1–R6 line at (115.5, 139.5), 0.1 mm lower than first
  placed so the line clears D21's mask opening by 0.2 mm (JLCDFM, 2026-10-28). Its GND pad drops
  through a via to the B.Cu ground spine (y = 142.2).
- **Soft-start** (Q1 DFN1006-3, R7 2.2k, R8 100k, C4 10 µF) is a cluster west of U2 at
  x 124.6–127.4, y 134.3–137.5. R7, R8 and Q1's VCC pin hang off the VCC rail (y = 133.2).
  SS_CAP joins R7, Q1 and C4. SS_GATE joins Q1 and R8, then runs down to U2 pin 15. C4
  grounds into the x = 124.6 trunk.
- **Test pads on the back.** TP1/TP2/TP3 (UPDI/VCC/GND, 1.5 mm pads) are on B.Cu in a
  straight row at 2.54 mm pitch, y = 145.0, inside the coil's lower-left corner. From the
  back they read UPDI, VCC, GND left to right. VCC and UPDI each have a via 1.4 mm north of
  their pad and run F.Cu north from it. GND needs no via: its B.Cu stub joins the B.Cu
  ground spine directly.
  The labels are back silkscreen at 1.0 mm cap height. The three words don't fit side by
  side at 2.54 mm, so `VCC` sits above its pad and `UPDI`/`GND` sit below theirs. The front
  keeps only the `JP1` label.
- **Text.** KiCad renders Menlo (terminal lines, labels) and Helvetica Neue (title, name,
  back headings) as TTF. The script then grows every glyph by 0.035 mm and stores it as
  filled polygons. At a 1.0 mm cap height, Menlo's `%`, `@`, `~` and dotted zero are about
  0.10–0.13 mm thick, below JLCPCB's 0.15 mm minimum
  ([character spec](https://jlcpcb.com/blog/character-design-specifications)).
  `check_silk.py` opens every polygon with a 0.15 mm disc and checks it survives. All 621
  passed before the JLCDFM clean-up below (not re-run since: it needs numpy in KiCad's Python). The same check at 0.25 mm fails 475, which shows the check can fail. All text has
  a cap height of at least 1.0 mm. Because the text is stored as polygons, the board no
  longer depends on installed fonts. Re-running the script needs macOS (Menlo, Helvetica Neue).

## Deviations from the concept

- **MCU block extends to x ≈ 41 mm (concept: 29.5 mm).** U1 must stay at the antenna feed
  (concept 15–23, 41–46), which is where the concept drew U2. U2 therefore sits to U1's
  right. The bar starts at x = 43 with a 3.2 mm pitch (concept: x = 33, 4.2 mm), and the
  name and tagline start at x = 43.
- **Name and `tap to connect ▍` sit about 1.9 mm higher** (baselines 37.6 and 39.9), so the
  bar's bus vias stay clear of the tagline.
- **Back text block starts at x = 15.6 mm (concept: 10).** The five bus columns and their
  vias sit at back x 12.1–15.3, so the block moved right to keep the vias off the letters.
  `TAP TO CONNECT` and the title have tighter letter-spacing so they fit inside the antenna.
- **LED cathode dots** (added after the Orbit order Y8): a 0.4 mm silk dot 0.27 mm below
  each LED's pad 1 (the cathode): under the left pad of the line-status LEDs and the right
  pad of the bar LEDs. The library LED outline sits 0.1 mm from the pads, so the 0.25 mm silk
  cut-back removed it and the card had no LED polarity mark. The junction and bus-tap tracks
  run above each LED, so the dots go below. A line LED's dot is 0.63 mm above the next LED
  down, so it reads as belonging to the LED above it.
- **All terminal text is 1.0 mm cap height** (concept: 1.2 mm font, about 0.87 mm cap). Prompts
  are bold and output is regular, as in the concept.
- **Ping replies (easter egg).** The four times are 0.087, 0.090, 0.072 and 0.033 ms. Their
  digits are the ASCII codes 87 90 72 33, which spell `WZH!`. The concept's `ttl=56` became
  `ttl=64`: zero hops, so the sub-millisecond times read as a real local-network ping.

## Manufacturing notes

- Same order settings as NTUAS except thickness (2 layers, **0.8 mm**, ENIG; mask black for
  B3). Set PCB Thickness to 0.8 in the JLC quote; the gerber job file also says 0.8. C1, L1 and
  TP1–TP3 are not in the BOM/CPL. There are 36 assembled parts.
- **JLC rotation offsets (checked 2026-10-28 in JLCONE's placement viewer).** JLC's library
  turns U2 (C507118) 90° and Q1 (C155329) 180° away from KiCad's footprints, so
  `scripts/export-card.py` adds -90° and 180° to their CPL rotations (`JLC_ROTATION`). With that,
  U2's and Q1's pin-1 dots land on the silkscreen triangles, U1's on its dot, and every LED's
  cathode on pad 1. D21 is bidirectional.
- DRC with schematic parity is clean. `lib_footprint_mismatch` is set to ignore: `scripts/jlc_dfm.py`
  deliberately trims footprint silkscreen and sets U1/U2/Q1's mask margin, so every touched
  footprint differs from its library copy.
- **JLCDFM (JLCONE's DFM tool), 2026-10-28.** The first run flagged soldermask webs (U2/Q1 0.10 mm,
  U1 0.13 mm on black mask), silkscreen on pads and holes, 0.12 mm outlines, 0.15 mm via rings and
  D21's UPDI line. `scripts/jlc_dfm.py` (run by the build script before saving) gives U1/U2/Q1 pads a
  0.02 mm mask margin, all vias a 0.65 mm pad, widens silkscreen to 0.16 mm and cuts it back 0.25 mm
  from every pad and hole. The final PCB check has no danger or warning items. The SMT check still
  reports three things that are left on purpose: U2's pins are as wide as their 0.20 mm pads (the
  maximum in Microchip's land pattern C04-21380), U2's centre pad overlaps "16 %" because KiCad
  splits its paste into four windows, and the GND via in U2's centre pad sits under a lead
  (Microchip's pattern also puts 0.30 mm vias there, tented, as here). U1 reads 90 % lead/pad
  overlap on one pad; lengthening its pads did not change that, so its footprint is unchanged.

## Unverified

**Fixed from Orbit bring-up (2026-11-08):** R6 at 4.7 kΩ stopped the Adafruit UPDI Friend
from reading the chip on Orbit (`docs/bringup/2026-11-08-orbit-first-cards.md`). R6 is now
a 0 Ω link (UNI-ROYAL 0402WGF0000TCE, LCSC C17168, JLC basic, same 0402 footprint), and
`fab/terminal-v2/` was re-exported with it. That matches the bridged Y8 Orbit cards, which
programmed correctly; see `hardware/orbit/README.md` (Bring-up) for why no resistor is needed. The re-export
also picked up the LED cathode dots, which the earlier `fab/terminal-v2/` predated; copper,
mask, paste, outline and drill are unchanged.

Physical NFC range, resonance, harvested power and LED brightness are still unproven on the
NTUAS card, and this board inherits that risk. Moving U2 and the bus vias near the coil may
detune the antenna slightly. Nothing here has been measured. How the 0.035 mm emboldened
text actually prints was checked in gerber geometry and renders only, not on a JLC board.
