# ATtiny1616 prototype timing audit

Physical validation is pending. These are nominal-clock, emitted-instruction
bounds, not oscilloscope measurements or a harvested-power acceptance result.

## Reproduce

```
make -C firmware verify BOARD=<orbit|terminal> AVR_CC=/opt/homebrew/Cellar/avr-gcc@14/14.3.0/bin/avr-gcc
```

Ordinary PATH discovery uses `avr-gcc`, `avr-objcopy`, `avr-objdump`, `avr-nm`, and
`avr-size`. `AVR_PREFIX=/complete/toolchain/bin/avr-` selects a complete toolchain;
individual `AVR_CC`, `AVR_OBJCOPY`, `AVR_OBJDUMP`, `AVR_NM`, and `AVR_SIZE` overrides
support split installations. The verified compiler is Homebrew AVR GCC 14.3.0;
binutils is 2.46.0.20260210. Flags are C11, `-O2 -g -Wall -Wextra -Werror`,
`-mmcu=attiny1616 -DF_CPU=1000000UL`, section garbage collection, and stack-usage
output. `build/` contains both ELF/HEX images, disassembly `.lst`, link maps,
per-translation-unit `.su` files, and `size.txt`. The timing checker prints the
exact ELF SHA256 with each result, and fails for unsupported ISR instructions.
Changing compiler, flags, assembly, clock, or peripheral settings requires a new
instruction audit.

The NTUAS images occupy 3477 bytes of flash and 82 bytes of static RAM; Orbit
and Terminal (shared slots, below) occupy 3210 and 3130 bytes and 122 bytes,
the extra 40 bytes being the per-slot LED indices.
The device provides 16384 bytes of flash and 2048 bytes of SRAM. Compiler stack
reports plus the deepest synchronous call chain and the non-nested ISR give a
static/call-graph estimate below 160 bytes (not a measured worst-case stack
proof); reserving at least 512 bytes beyond static RAM leaves 1454 bytes unused. No heap or EEPROM allocation/write is present.

## Clock, timer and interrupt ABI

The oscillator fuse must select 16 MHz. Runtime clock setup deliberately keeps
prescaling enabled while selecting DIV16; GPIO permission is withheld unless
clock registers, the oscillator fuse, continuous BOD fuse field/level, and UPDI
fuse field match. BOD remains continuously enabled, VLM uses its lowest setting
and both-edge interrupts, and an already-low initial status is latched.

TCA runs DIV1 in normal mode with PER=65535. All waveform outputs are disabled.
CMP0 advances by an absolute 250 ticks. The first event is at 5000 ticks to avoid
crediting a partial initial frame toward the 100 ms qualification; subsequent
slot-0 events are exactly 5000 ticks apart. Blank slots still consume their time.
After any voltage-low observation or warning event, the application discards
the first subsequent healthy frame interval because its starting edge is not
known healthy. Zero-frame calls do not clear that pending exclusion. Twenty
complete healthy intervals then qualify STARTUP/RECOVER, guaranteeing at least
100 ms healthy and allowing up to one additional 5 ms frame of delay. A reset
without any warning retains the original 20-frame startup qualification.

`src/scan_isr.S` is the complete slot ISR and its ABI contract. It preserves r0,
SREG, r1, r18–r21, r24–r25 and Z. Saving and clearing r1 is necessary because an
interrupted multiply or libgcc helper may temporarily use it. No nested interrupt
is enabled. GPIOR0/1 hold the absolute next-slot anchor, GPIOR2 holds permission,
pending, low and fault flags, and GPIOR3 holds the slot. Other modules never own
these registers. Main transfers ownership using short atomic flag exchanges;
the 20-byte frame copy runs with interrupts enabled. No arithmetic division or
animation work occurs in the ISR.

## Emitted pulse bounds

`tests/check_avr_timing.py` parses the linked instructions and executes the actual
ISR instruction sequence, including saves/restores, branches, GPIO writes,
timer reads, register-address calculations and the polling loop. It tests all
20 slots and requested widths 0–62 with both two- and three-cycle LDS models,
checks preserved registers including nonzero interrupted r1, timer rollover,
late entry, missing next frame, low status, pending edges, and warnings arriving
at every cycle offset. The host HAL backend separately checks the C publication
and event paths. The host slot reference is not the timing proof.

The conservative instruction model uses AVRxt PUSH=1, POP=2, LD=2, STS=2,
LDS=3, IN/OUT=1, branch=1/2, skip=1/2/3 and RETI=4. Testing LDS=2 as well covers
the faster I/O-access case and checks that the pulse never grows beyond its
requested cap under that timing. The nominal audit starts the handler at cycle11: the ATtiny1614/1616/1617
datasheet §13.3.2.3 gives a minimum active response of6 cycles (including vector
dispatch) and an additional5 cycles from sleep. This replaces the earlier,
incorrect4-response/3-JMP/4-wake decomposition. To check publication masking,
the regression deliberately charges6 response cycles PLUS the emitted3-cycle
JMP separately, overcounting dispatch rather than relying on a minimum as a
maximum. Instruction completion after interrupt re-enable is charged explicitly.
The instruction executor remains an accounting model, not a peripheral simulator.

| Requested duration | Emulated pulse, LDS=2 | Emulated pulse, LDS=3 |
| --- | --- | --- |
| 0–9 us | omitted | omitted |
| 10 us | 6 us | 7 us |
| 15 us | 12 us | 14 us |
| 31 us | 30 us | 28 us |
| 62 us | 60 us | 56 us |

The bounded loop captures CNTL, enables the prepared pair using VPORTA.DIR,
compares elapsed unsigned 8-bit ticks against `requested-9`, and immediately
blanks with VPORTA.DIR. Its loop is 6 or 7 cycles; the final iteration replaces
the taken branch with a one-cycle branch and the blank OUT. Consequently every
emitted on-time is at most the requested duration. The loop lasts far less than
256 ticks and cannot alias a wrapped comparison. No interrupts can stretch it.

This prototype omits requested widths below 10 us and has approximately 6–7 us
physical width resolution. That materially reduces dim-star/ramp resolution,
especially at the 6.25% tier; brightness and visible flicker must be assessed on
hardware. The pure scanner's staged scaling itself loses at most 1 us relative
to the exact formula, independently of this pulse omission/quantization.

The longest nominal ISR is 232 cycles including Idle entry/wake (slot 0 with a
full pulse and a queued frame swap). The ordinary full-pulse path is shorter.
Before driving, the ISR requires 121–250 ticks remaining to the next anchor;
this includes its pulse and return path. The delayed-entry sweep verifies that
any lit path returns strictly before the next slot and that expired paths latch
a permanent fault and remain dark. At nominal entry, the longest pulse blanks
at cycle 197 and the ISR returns at cycle 232.

## Main-loop masking and voltage warnings

The healthy final publication critical section is bounded separately from the
ISR. Voltage status, pending edges, and the low/fault latch are rechecked before
setting PENDING. An edge after that check cannot cause a stale frame to light:
the slot ISR rechecks status/edge immediately before drive, and the BOD ISR
clears enabled and pending before main resumes. An unconsumed low indication
cannot be cleared by a rising edge.

VLM remains ordinary level 0. It may wait for a slot ISR already in progress;
that ISR always blanks its pulse before returning. The emitted BOD ISR blanks
six cycles after entering its handler, then clears permission/pending and
latches the event. Its body including RETI takes 22 cycles; add vector/response
and any interrupted-instruction or Idle wake allowance. A conservative warning
service bound is 275 nominal cycles including an entire delayed slot, intervening
instruction, BOD dispatch and its first blank. BOD remains the hardware fallback
for a collapse faster than software can service. No analog threshold or response
latency has been measured.

## Frame budget and remaining acceptance

The instruction checker reports 3109 cycles for a deliberately conservative
steady frame: three 62 us requests, four 46 us requests, one 31 us request, two
23 us field requests, and ten blank slots. Both field stars cannot actually be
at peak simultaneously, so this bounds the application's steady scan load.
The report includes an Idle wake allowance on every slot even while main may
be active. Main prepares at most one frame per event; more than one unconsumed
frame or missing publication at an enabled frame boundary fails dark.

The independent main-code audit used these conservative phase allowances,
including return from the preceding frame-event sleep:

| Phase | ISR frame upper bound | Main allowance | Total before publication |
| --- | --- | --- | --- |
| 0–200 ms ramp | 2542 | 2024 | 4566 |
| Belt completion | 2605 | 1824 | 4429 |
| Limbs reveal | 2925 | 1824 | 4749 |
| M42 reveal | 2991 | 1824 | 4815 |
| Steady twinkle | 3109 | 1494 | 4603 |
| Diagnostic | 2389 | 1774 | 4163 |

Main continuously prepares and publishes its frame before calling hal_sleep;
there are no empty-slot sleep checks while it is doing that work. The available
remainder is used for Idle and approximately 20-cycle empty-wake checks. Charging
20 such checks additionally to the whole main budget would describe an impossible
execution path. That overestimate now exceeds a frame for steady twinkle
(4603+400=5003); phase-aware accounting is required. The smallest publication
margin is 185 cycles. Prior full-ramp steady component estimates are scan_prepare449,
animation_render316, power_ramp29, power_step73, app control and enabled checks198,
event capture62, publication252, and dispatch48; include the bounded event-return
cost to obtain the prior rounded1470 allowance. The first-ramp and diagnostic bounds
allow for the slower general scanner path.

The warning-interval fix was recounted against the preceding 3375-byte image
with the same compiler and flags. The emitted healthy one-frame `app_step`
control path, including CALL instructions but excluding callee bodies, grows
from 150 to 170 cycles for a normal non-wrapping active frame. The changed prefix
adds 18 cycles (warning/partial-interval checks, delta setup, spilled fault flag
and branch layout); the additional saved register costs another 2 cycles in
the epilogue. Diagnostic and age-wrap paths share that increment; the newly
qualified restart path adds only 18 cycles. Callee bodies and recurring
`app_run` dispatch operations are unchanged. Each previous rounded allowance
is increased by 24 cycles, preserving its old rounding margin and adding four
cycles above the measured 20-cycle increment. Warning and excluded-interval
calls remain dark and skip animation/scaling. The extra flag and saved register
increase the synchronous stack estimate by two bytes (`app_run` 42 and
`app_step` 38 bytes in GCC stack reports); the 512-byte reservation is unchanged.

The soft-start reservoir bypass (Q1/R7/C4, PC0) was recounted against the
preceding 3439-byte image with the same compiler and flags. `app_step` gains
`ldi`/`std` (3 cycles) only inside the newly-qualified restart branch; its healthy
path is instruction-identical. `app_run` adds a check after `hal_publish` on every
dispatched frame: `ldd, cp, breq, cp, breq, mov` = 7 cycles once bypassed, 5
before. Each steady allowance therefore rises by 8 cycles. The one-time
`hal_bypass_reservoir` call (CALL, two `ldi`/`sts` pairs, RET; about 14 cycles plus
the 7-cycle check and the 3-cycle restart store) runs only on the qualifying frame,
which is dark (all slots request 0 us), so that frame's ISR load is the 20-slot
minimum rather than a lit scene. The function is placed after `hal_sleep`, so the
audited `hal_publish`..`hal_sleep` window is unchanged. `app_run` stack grows from
42 to 43 bytes; the 512-byte reservation is unchanged.

The healthy final publication section now masks interrupts for16 cycles,
inclusive of CLI and SREG restoration. Every HAL unlock emits OUT SREG followed
by an explicit one-cycle NOP in the same assembly block; a deferred interrupt
therefore cannot inherit a four-cycle RET immediately after restoration. The
checker executes each actual emitted publication critical section through that
following instruction. The largest healthy mask-plus-following interval is17
cycles. Adding the deliberately conservative9-cycle response/dispatch allowance
gives entry delay26: slot0/full pulse returns at247, leaving a3-cycle guard.
The original OUT-SREG/four-cycle-RET sequence fails this regression.

The existing remaining-time gate is unchanged. Delay28 still returns at249;
delay29 rejects the pulse and latches a permanent fault. Physical blanking
occurs approximately35 cycles before return. Longer warning branches already
inhibit outputs. The shorter publication section offsets the new NOPs on the
other steady main paths in the prior allowances; the table above separately
adds the warning-interval fix's cost. Empty-wake loops gain one cycle, accounted
as20 instead of19.
Actual interrupt entry, oscillator and GPIO timing still require scope checks;
the post-enable instruction is now budgeted rather than left as an assumption.
The bounded animation-age fast path, saturated
ramp fast path, single-scale full-ramp scanner, and sleep-internal empty-wake
loop are required to fit the frame budget; removing them requires re-audit.

Before hardware release, scope all three tiers, clock/slot cadence, startup,
blank guard, VLM latency and marginal-supply behavior; measure current, brightness,
flicker and NFC read reliability on the assembled cards. Automated checks do
not constitute physical sign-off.

Primary cycle references: [Microchip AVR instruction summary](https://onlinedocs.microchip.com/oxy/GUID-0B644D8F-67E7-49E6-82C9-1B2B9ABE6A0D-en-US-23/GUID-BA59618D-4850-490B-B176-0BCC3D9438A1.html),
[Microchip LDS detail](https://onlinedocs.microchip.com/oxy/GUID-0B644D8F-67E7-49E6-82C9-1B2B9ABE6A0D-en-US-23/GUID-42EBE7FA-6359-4986-827E-28F00A3B2FAF.html),
and [Microchip AVR instruction manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf).

## Shared slots (Orbit, Terminal)

`BOARD_SHARED_SLOTS` (in a board's `animation_config.h`; Orbit and Terminal set
6, NTUAS leaves it 0) lets the lit LEDs use dark LEDs' slots. `scan_prepare`
computes each LED's width exactly as before, keeps only LEDs at or above the
ISR's 10 us minimum, and gives each `6 / lit` slots (one each when six or more
are lit), spaced evenly from slot 0. A slot carries its LED index beside its
width: `hal_frames[40..79]`, read by the ISR with `ldd r0, Z+40` (r0 is free once
SREG is saved). The level table follows the mask table (`hal_masks[20..39]`), so
one address reaches both with `ldd r30, Z+20`. `hal_publish` copies and checks
(index < 20) the index only for lit slots; the ISR never reads a dark slot's.

With one LED lit it now gets 6 pulses per frame instead of 1 (7.4 % instead of
1.25 % of the time at the 4/16 tier), with two lit, 3 each. Pulse widths, the
62 us cap, the duty tiers and the 10 us minimum are unchanged. The NTUAS images
are byte-identical to the fixed-slot build.

The shared ISR path is 2 cycles shorter than the fixed one before the deadline
check: the publication-delayed full pulse returns at 245 instead of 247, the
latest pulsing entry is 30 instead of 28 (returning at 249), and a lit 62 us
slot costs 94 cycles more than a dark one in either layout.
`check_avr_timing.py` repeats the slot sweep with permuted, repeated and
reversed LED maps and checks the driven pins follow the map.

## Executed frame proof

The phase table above is a hand count of the NTUAS animation; it assumed
`animation_render` costs 316 cycles on every board. Executing the emitted code
gives worst cases of 649 (NTUAS reveal), 774 (Orbit reveal ramp, a 32-bit
`t*255/800`) and 938 cycles (Terminal, a 32-bit `% 4800` on every frame). Orbit
now computes the ramp as the equal 16-bit `t*51/160`, and Terminal folds its age
by subtraction (app.c keeps ages below 10400 ms), with the modulo kept only for
larger ages.

`check_avr_timing.py` now also runs every image from `main()` for 3600 frames
(18 s: qualification, ramp, the whole animation and its age fold, and the 17 s
diagnostic cycle). hal_init and hal_boot_flash (Orbit's one-time 50 ms power-up
flash, which finishes before hal_init starts the scan timer) are skipped and
hal_init's RAM state set directly; each SLEEP
is a frame boundary where the slot-0 bookkeeping is applied (elapsed frame,
PENDING to ENABLED with the buffer swap, an unpublished frame to fault). Every
frame's main-loop cycles plus the larger ISR load of the frames shown before and
after it must stay below 5000. The executor uses the ISR model's costs plus
ST/STD 2 (AVRxt: 1), CALL 3, RCALL 2, MUL/ADIW/SBIW 2 and one extra cycle per LD
from memory-mapped flash, and rejects unknown opcodes and N/V/S/H branches.

| Image | Worst frame (main + ISR) | Most lit slots |
| --- | --- | --- |
| NTUAS animation | 1835 + 2984 = 4819 | 10 |
| NTUAS diagnostic | 1752 + 2389 = 4141 | 1 |
| Orbit animation | 1886 + 2875 = 4761 | 6 |
| Terminal animation | 1907 + 2875 = 4782 | 6 |
| Orbit / Terminal diagnostic | 1705 + 2707 = 4412 | 6 |

These include the 300 ms bypass counter (next section); before it the same run gave
4807, 4115, 4749, 4757 and 4386.

## Bypass after 300 ms (2026-10-27)

`BOARD_BYPASS_QUALIFY_MS` (300) now times Q1 on its own instead of the first
qualified reveal (100 ms). `sim/revb_power.cir` showed that at 100 ms in a weak
field (0.5-0.6 mA harvested) C4 still lags VCC by R7's drop, so switching Q1 on
pulls 0.4-0.5 A of charge from C2/C3 and steps VCC down about 0.2 V; at 300 ms VCC
has settled (3.1-3.3 V) and the Q1 pulse is under 1 mA. Wilson Harper's card also
waits 300 ms. The reveal still starts at 100 ms, since R7 only feeds C4.
`app_step` counts `bypass_ms` exactly like the power qualification: complete
healthy frames only, zero on any voltage-low status or warning event, nothing for
a missed-frame backlog, and it stops once latched; only a reset releases it. The
count runs on every frame until the latch, so the healthy path is no longer
instruction-identical to the 3439-byte audit above. The executed proof below
covers it, including the latch frame (frame 60, now lit rather than dark): the
worst frames rise by 12 to 25 cycles and stay below 5000.

Before these changes the same run gave Terminal 4900 (4 lit slots fewer). With
`BOARD_SHARED_SLOTS 12` Orbit overruns at frame 110 (1858 + 3175), so the check
can fail. It covers healthy frames at the starting duty tier; lower tiers only
shorten pulses, and a recovery replays the startup frames. `test_app.c` checks
that no frame of a shared-slot board lights more than `BOARD_SHARED_SLOTS`
slots, the bound the ISR load above assumes.
