# Orbit bring-up, first cards (2026-11-08)

First hardware contact with order Y8 (`hardware/orbit/README.md`, "Ordering"). Programmer: Adafruit
UPDI Friend (3 V), Adafruit 5433 pogo clip, avrdude 8.3 (`/opt/homebrew/bin/avrdude`,
programmer `serialupdi`, port `/dev/cu.usbserial-110`). No multimeter was available.

## Result

| | Card 1 | Card 2 |
| --- | --- | --- |
| Tag reads on a phone (blank) | yes | yes |
| Reverse-powered by miswiring | yes, several brief attempts | no |
| UPDI signature read | `0x1e9421` with R6 bridged | `0x1e9421` with R6 bridged |
| Fuses, diagnostic, animation | done with `program-card.sh`, all verified | done, all verified |
| All 20 LEDs (diagnostic) | yes | yes, two full cycles counted on video |
| Orbit animation on USB power | yes, with the D16 power-up flash | yes, matches `animation.c` timing |
| Tag formatted and written | `https://wongzhunhao.com/nfc/orbit` | `https://wongzhunhao.com/nfc/orbit`, opens the site |
| Harvested power (probe image) | – | MCU starts and VLM reads healthy, card on the back of an iPhone |
| Animation on an iPhone tap | D16 blinks on every poll (see 4a) | no: the field is on for one burst of about 30–65 ms |
| Animation on Android | full cycle on a Samsung (2026-11-09): ISS pass, stations, then the 2,000 km pass | – |

Both cards now run the release image with the D16 power-up flash. The card programmed with
`firmware/tools/program-card.sh orbit-01` already had `freqsel`, `bodactive` and `bodlevel`
set when the script read it (only `sut` was still 64 ms), so the labels "card 1" and "card 2"
may have swapped between sessions. Either way, the reverse-powered card survived.

## Findings

### 1. R6 (4.7 kΩ) blocks the UPDI Friend

Both cards failed `UPDI link initialization` with correct wiring. The `-vvvv` trace showed
every byte echoed by the Friend's own loop-back, then no reply to `LDCS`. The Friend holds the
line high through its 1 kΩ TX resistor. The ATtiny's weak UPDI driver pulls low through R6, so the
line only falls to about 4.7 / 5.7 of the supply (≈ 2.7 V at 3.3 V) and the reply never reads as
low. 5 V would not help (same ratio) and exceeds the NTAG's 4.6 V VCC limit through JP1.

Shorting R6 with metal tweezers during each avrdude run made every step work. SpenceKonde's
[UPDI series resistor notes](https://github.com/SpenceKonde/AVR-Guidance/blob/master/HardwareNotes/UPDISeriesResistors.md)
call 4.7 kΩ inappropriately high and recommend 470 Ω.

Why it was missed: R6 came in with the NTUAS circuit and `check.sh` holds every board to that
netlist. The 2026-10-26 comparison with Wilson Harper's card noted that he has no UPDI resistor
and that his card "worked instantly" with the UPDI Friend, but not that the two facts together
rule out 4.7 kΩ with that programmer. No gate models the programmer side of the UPDI line, and
the firmware README's avrdude steps were only checked against the `dryrun` programmer.

Fix:
- **Existing cards:** bridge R6 (solder blob, conductive ink, or tweezers held across it while
  avrdude runs). D21 still clamps the UPDI pad. The bridge can stay.
- **Next revision:** R6 → 0 Ω (done 2026-11-08, LCSC C17168), regenerating `fab/reference/card-netlist.xml` in the
  same change. Terminal has the same R6.

### 2. The UPDI Friend's cable is not Adafruit's colour order

Adafruit's guide gives red = PWR, black = GND, white = UPDI. The cable that arrived is
**black = PWR, red = GND, yellow = UPDI**, per the silkscreen beside the JST socket. Wiring by the
guide put 3 V on the GND pad and ground on VCC; the Friend's PWR LED went out and the Mac
dropped the port. Card 1 took this several times. Always go by the socket's silkscreen.

### 3. The NTAG ships unformatted

NXP TagWriter (iOS) reports "Tag is not NDEF compliant"; NFC Tools reports "not supported".
The NT3H2111 datasheet (§8.3.10, "Memory content at delivery") ships the CC as `00000000h` and
gives the minimum NDEF content. NFC Tools → Other → Advanced NFC commands:

```
A2 03 E1 10 6D 00     → 0A   (CC: NDEF 1.0, 872-byte area, read/write)
A2 04 03 00 FE 00     → 0A   (empty NDEF TLV + terminator)
30 03                 → E1 10 6D 00 03 00 FE 00 …   (read back)
```

CC bits cannot be cleared from NFC (only over I²C, which is not wired), so the last CC byte
must be `00`; `0F` would make the tag read-only forever. After this, NFC Tools wrote the URL
record (30 bytes).

### 4. iPhone power: position and duration

- Harvesting only works with the card flat on the **back of the iPhone near the camera**. On
  the screen side nothing starts.
- A throwaway probe image (one LED pulses as soon as the MCU runs, a second only while the VLM
  reads healthy) lit both LEDs on an iPhone tap, but in one video frame at 30 fps only. iOS
  background reading powers the field for one burst of roughly 30–65 ms per tap, then stops
  until the tag leaves.
- The release firmware needs 100 ms healthy before anything and then fades in over 800 ms, so
  it shows nothing on an iPhone tap. Wilson Harper's card was shown on a Pixel (Android keeps
  the field on); Kevin Tang's single-LED card (no MCU) only flickers on an iPhone tap.
- Open: test the animation on an Android phone; decide whether to add an instant power-up blink
  for iPhones.

### 4a. The iPhone keeps polling, and SUT decides whether we see it

With the start-up fuse at its factory 64 ms, the probe showed light in only one frame
per tap. With `sut=sut_0ms` the same probe blinked repeatedly while the card was held on
the back of the iPhone, though iOS showed only one notification: single-frame flashes
at 13.08, 13.78, 15.22, 15.92 and 16.65 s in a 30 fps video, i.e. a poll about every
0.7 s, each powering the card for roughly one frame (≈ 30 ms). The 64 ms start-up
delay had been eating most of each burst.

So the Orbit firmware now flashes D16 (the middle ground station) for 50 ms at power-up,
before the 100 ms VLM qualification (`hal_boot_flash`, `BOARD_BOOT_FLASH_LED`), and the
fuse step sets `sut=sut_0ms`. On an iPhone a held card should blink about every 0.7 s;
with a continuous field (Android) the flash is followed by the normal reveal and
animation. Continuous animation on an iPhone is not possible without an app: the card
has no power between polls (~4 % duty).

Verified on hardware with D16: on USB the flash is followed by the reveal and the
animation, and on the back of an iPhone D16 blinks on every poll while the card is held.

### 5. JP1

The tag still reads with JP1 fitted after programming at 3.3 V, so JP1 stays fitted on every
card (build plan, "JP1 stays a fitted 0 Ω").

## Fuses after programming (card 2)

Before: `osccfg 0x02` (20 MHz), `bodcfg 0x00` (BOD off, 1.8 V), `syscfg0 0xf6` (UPDI), lock
`0xc5`. After: `freqsel=fcpu_16mhz`, `bodactive=bod_enabled`, `bodlevel=bod_1v8`,
`rstpincfg=updi`, `lb=nolock`. One read reported "device is locked" from a momentary tweezer
slip; a re-read after a power cycle showed `nolock`.
