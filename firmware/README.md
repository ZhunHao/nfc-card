# ATtiny1616 card firmware

Both animation and diagnostic firmware are implemented and build-verified
prototype images. **Partly validated on hardware (2026-11-08, one Orbit card):** the
diagnostic lit all 20 LEDs and the Orbit animation ran with the correct timing on 3.3 V
programmer power. On an iPhone tap the field lasts only about 30–65 ms, shorter than the
100 ms qualification, so only the D16 power-up flash shows there; on Android the full
animation runs on harvested power (`docs/bringup/2026-11-08-orbit-first-cards.md`). Terminal has not been programmed.

Every build names its card: `BOARD=orbit` or `BOARD=terminal`. There is no default, so a plain `make`
stops instead of building the wrong animation. Output goes to
`firmware/build/<board>/`.

## Build and inspect

Run from the repository root with Python 3, a host C compiler, GNU Make and the
reviewed AVR tools. AVR GCC 14.3.0 and AVR binutils 2.46.0.20260210 are required by
the current [instruction and main-loop timing audit](docs/timing.md). Other
versions or changes to `AVR_FLAGS` fail the gate and need a new audit; merely passing the host suite does
not establish AVR timing. The compiler targets `attiny1616` with C11, `-O2`,
`-Wall -Wextra -Werror` and `F_CPU=1000000UL`.

```sh
export AVR_CC=/opt/homebrew/Cellar/avr-gcc@14/14.3.0/bin/avr-gcc
BOARD=orbit                    # or terminal
make -C firmware test BOARD=$BOARD     # host behavior and hardware-fixture checks
make -C firmware verify BOARD=$BOARD   # host + fresh AVR images, memory, emitted ISR checks
make -C firmware release BOARD=$BOARD  # verification followed by prototype packaging
./scripts/check.sh             # firmware plus existing KiCad project gates
```

The default compiler is `avr-gcc` on PATH. `AVR_PREFIX=/path/to/avr-` selects a
complete toolchain. Individual `AVR_CC`, `AVR_OBJCOPY`, `AVR_OBJDUMP`, `AVR_NM`
and `AVR_SIZE` overrides work as environment variables or Make arguments;
export them when invoking the root shell gate. Missing tools fail even when
old images exist. Verification forces both AVR images to rebuild so a tool
selection change cannot reuse stale ELF output.

`firmware/build/<board>/` contains `animation.elf/.hex`, `diagnostic.elf/.hex`, source
interleaved disassemblies (`.lst`), link maps, compiler stack reports (`.su`),
`size.txt`, and `memory.json`. Flash load must be at most 16384 bytes; static RAM
(`.data + .bss + .noinit`) must be at most 1536 bytes, leaving a 512-byte stack
budget within 2048 bytes SRAM. This reservation is not proof of worst-case stack
use. The timing checker audits emitted ISR instructions in both images; the
whole-application frame budget remains the separate manual audit in `timing.md`.
No analog/peripheral simulation or scope validation is implied.

`firmware/build/<board>/release/` contains `card.elf/.hex` (animation aliases),
`diagnostic.elf/.hex`, `manifest.json` and `SHA256SUMS`. The manifest records source
commit and dirty state, compiler/binutils versions, clock, intended fuse fields,
image hashes, timing-document hash and memory. Packaging adds no timestamps;
identical inputs/provenance produce identical bytes. ELF debug/symbol data retains build paths and GCC temporary object names, so
fresh ELF rebuilds may differ even when executable HEX bytes agree. The manifest
records this build provenance limitation; byte-for-byte ELF rebuilds are not
promised. Build from a clean committed tree to obtain clean source provenance.
`tools/release.py` is an internal packaging helper; use `make release` to run
the required verification before packaging. All binary output stays under ignored `build/`; `release` means a prototype
package and does not authorize production sign-off.

```sh
(cd firmware/build/$BOARD/release && shasum -a 256 -c SHA256SUMS)
```

## Connect and identify before programming

These steps programmed the first Orbit card on 2026-11-08 with an Adafruit UPDI Friend
and avrdude 8.3 (`docs/bringup/2026-11-08-orbit-first-cards.md`). Three things learned there:

- **Bridge R6 first (Y8 Orbit cards).** On the 15 assembled Y8 Orbit cards R6 is 4.7 kΩ
  (UPDI pad to pin 19), which stops the UPDI Friend hearing the chip. The design now has
  a 0 Ω link (from 2026-11-08), electrically the same as the bridge, so later Orbit and
  Terminal orders should not need this. At 4.7 kΩ: its 1 kΩ TX pull-up holds the line at ≈ 2.7 V when the ATtiny pulls low, so avrdude
  reports `UPDI link initialization failed` with correct wiring. Short R6 with a solder blob,
  conductive ink, or metal tweezers held across it for every avrdude command. D21 still
  protects the pad. 5 V does not help and overstresses the NTAG through JP1.
- **Wire by the silkscreen, not the cable colours.** On the cable that shipped, black is PWR,
  red is GND and yellow is UPDI (Adafruit's guide says red is PWR). Swapping them reverse-powers
  the card: the Friend's green LED goes out and the Mac drops the port.
- **Set the Friend to 3V.** The clip goes on the back with UPDI/VCC/GND on three adjacent pogo
  pins; the other three rest on solder mask.

1. Remove the phone/RF source and all external power. With JP1 fitted, programmer
   or bench VCC also drives the tag's VOUT. The NT3H2111 datasheet neither allows
   nor forbids that; Wilson Harper's similar card has no JP1 and programs fine.
   Program the **first** card with JP1 fitted, at 3.3 V, current-limited, then check
   it still reads on a phone. If it does, leave JP1 fitted on the rest. If not,
   lift JP1 before applying power to every later card, isolating the MCU rail
   from tag VOUT (build plan, "JP1 stays a fitted 0 Ω").
2. Identify TP1=UPDI (PA0, MCU pin 19 via R6), TP2=VCC (pin 4), TP3=GND (pin 3 and the exposed pad).
   Connect ground, a suitable regulated/current-limited target supply, and UPDI.
   Use a UPDI programmer whose output levels and target-voltage sensing are
   compatible with the chosen VCC. Do not connect a fixed 5 V signal to a lower
   voltage target. Avoid two competing target supplies; the programmer's power
   capability is device-specific. Keep RF absent during externally powered work.
3. Start at a stable supply that is within the ATtiny1616 and connected LED
   circuit ratings and supported by the programmer.
   Harvested ~2 V operation is a later isolated-supply test, not a reason to
   assume any USB programmer can communicate at that voltage.
4. Select the exact ATtiny1616 device, read the signature, and stop on mismatch.
   Expected signature is **0x1e9421**. Never bypass it with `-F`.

```sh
AVRDUDE=/opt/homebrew/bin/avrdude   # avrdude 8.3 (brew install avrdude)
BOARD=orbit                    # or terminal: picks firmware/build/$BOARD/release/
PROGRAMMER=serialupdi          # Adafruit UPDI Friend
PORT=/dev/cu.usbserial-110     # check with: ls /dev/cu.usbserial-*
mkdir -p firmware/build/readback
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U signature:r:firmware/build/readback/signature-before.txt:h
```

Read all fuse fields and save the relevant raw fuse bytes **before any edits**.
Back up flash and EEPROM if preserving existing device contents matters; flash
programming may erase existing contents according to device and EESAVE settings.
NDEF provisioning in the separate NFC tag is outside this firmware workflow.

```sh
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -T 'config -f' \
  -U osccfg:r:firmware/build/readback/osccfg-before.txt:h \
  -U bodcfg:r:firmware/build/readback/bodcfg-before.txt:h \
  -U syscfg0:r:firmware/build/readback/syscfg0-before.txt:h \
  > firmware/build/readback/fuse-fields-before.txt 2>&1
```

Inspect the saved output and command exit status. Require `rstpincfg=updi`.
If UPDI is not selected, stop and diagnose the actual part/programming setup;
do not apply a blanket byte repair. Preserve lock, watchdog, startup, EEPROM,
reserved and other unrelated fields. avrdude aliases are `osccfg=fuse2`,
`bodcfg=fuse1`, `syscfg0=fuse5`; bytes are not interchangeable with field values.

## Set the four required fields, then read them back

avrdude 8 terminal `config` performs field-preserving updates. These four
commands select the 16 MHz oscillator, continuous active-mode BOD (also used
in Idle), BODLEVEL0, and a 0 ms start-up time. They do not change UPDI or other
fuse fields. SUT=0 ms (factory 64 ms) lets the Orbit power-up flash
(`hal_boot_flash`) start inside an iPhone's ~30 ms poll burst; BOD still holds the
chip in reset until VCC passes BODLEVEL0, so the start-up delay is not needed.
The runtime clock divides 16 MHz by 16 to nominal 1 MHz and configures VLM at its
lowest threshold. The firmware stays dark if clock/fuse permission checks fail.

```sh
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -T 'config freqsel=fcpu_16mhz' \
  -T 'config bodactive=bod_enabled' \
  -T 'config bodlevel=bod_1v8' \
  -T 'config sut=sut_0ms'
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -T 'config -f' \
  -U osccfg:r:firmware/build/readback/osccfg-after.txt:h \
  -U bodcfg:r:firmware/build/readback/bodcfg-after.txt:h \
  -U syscfg0:r:firmware/build/readback/syscfg0-after.txt:h \
  -U syscfg1:r:firmware/build/readback/syscfg1-after.txt:h \
  > firmware/build/readback/fuse-fields-after.txt 2>&1
```

Compare before/after fields: only `freqsel`, `bodactive`, `bodlevel`, `sut` may change;
`rstpincfg` must remain `updi`. Power-cycle the isolated target after fuse setup.
BODLEVEL0 is nominally 1.8 V with a specified 1.7–2.0 V spread; VLM level 0 is
not a calibrated 1.89 V trip. Measure the individual card's thresholds.

## Program and verify, then perform bring-up

Program the diagnostic image first. avrdude normally verifies writes; retain
that behavior and also run an explicit independent flash verification. Do not
use `-V`. Check exit status after every command.

```sh
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U flash:w:firmware/build/$BOARD/release/diagnostic.hex:i
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U flash:v:firmware/build/$BOARD/release/diagnostic.hex:i \
  -T 'config freqsel' -T 'config bodactive' -T 'config bodlevel' -T 'config rstpincfg'
```

The diagnostic walks D1–D20: 500 ms selected LED, 250 ms dark per LED, an
additional 2 seconds dark after D20, then repeats. It uses the ordinary twenty
250 us slots, starts with a 200 ms ramp after 100 ms healthy qualification, and
starts at a 12.5% slot ceiling. On Orbit and Terminal the selected LED uses 6 of
the 20 slots (shared slots, `docs/timing.md`), so it pulses six times per frame. Recovery restarts at D1 and backs off to 6.25%
then DARK. Check every LED lights in turn before moving on to the animation.

Replace the diagnostic with the animation image before evaluating final behavior:

```sh
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U flash:w:firmware/build/$BOARD/release/card.hex:i
"$AVRDUDE" -N -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U flash:v:firmware/build/$BOARD/release/card.hex:i \
  -T 'config freqsel' -T 'config bodactive' -T 'config bodlevel' -T 'config rstpincfg'
```

Remove the programmer, then tap the card on a phone. (If you had to lift JP1,
refit it first.) Flash verification confirms stored bytes only; the phone test is
the real check. Hold the card flat on the back of the phone; on an iPhone, near the
camera. The first card still read on a phone with JP1 fitted, so JP1 stays fitted.

If R6 is bridged with tweezers rather than solder, contact is intermittent. This loop
retries a write until one attempt verifies; a failed connection writes nothing:

```sh
for i in $(seq 1 30); do "$AVRDUDE" -p t1616 -c "$PROGRAMMER" -P "$PORT" \
  -U flash:w:firmware/build/$BOARD/release/card.hex:i \
  -U flash:v:firmware/build/$BOARD/release/card.hex:i && echo "=== FLASHED OK ===" && break
  sleep 1; done
```

For a batch, `firmware/tools/program-card.sh <label> [--diagnostic]` runs every step above
for one card (signature, fuse readback, the four fields if not already set, then flash write
and verify), retrying each until it succeeds, and logs to `firmware/build/readback/<label>/`.

A blank NTAG must be NDEF-formatted before any app will write the URL;
see `docs/nfc-tag.md`.
