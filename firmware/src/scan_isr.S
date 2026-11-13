/* ATtiny1616 AVRxt, level 0 only. C state and host seam: hal_avr.c.
 * Preserve r0/SREG, r1, r18-r21,r24-r25,Z. Clear r1 after saving: an
 * interrupted MUL or libgcc helper may temporarily hold a nonzero r1.
 * Direction output is a masked read/modify/write preserving PA0/PA6/PA7.
 * See timing.md and tests/check_avr_timing.py for emitted-code evidence.
 * BOARD_SHARED_SLOTS: the slot's LED index sits at hal_frames+40 beside its
 * on_us and indexes the mask table, with levels at +20 (r0 is free once SREG
 * is saved). */
#include <avr/io.h>
#include "animation_config.h"
#ifndef BOARD_SHARED_SLOTS
#define BOARD_SHARED_SLOTS 0
#endif
.global scan_shared_slots
.set scan_shared_slots, BOARD_SHARED_SLOTS
.global hal_anchor, hal_flags, hal_slot
.set hal_anchor, 0x1c
.set hal_flags, 0x1e
.set hal_slot, 0x1f
.global TCA0_CMP0_vect
.type TCA0_CMP0_vect, @function
TCA0_CMP0_vect:
    push r0
    in r0, 0x3f
    push r0
    push r1
    clr r1
    push r18
    push r19
    push r20
    push r21
    push r24
    push r25
    push r30
    push r31
    ldi r21, 0x3e
    sts 0x0402, r21
    ldi r21, 0x10
    sts 0x0a0b, r21
    in r18, 0x1e
    in r24, 0x1c
    in r25, 0x1d
    lds r30, 0x0a20
    lds r31, 0x0a21
    sub r30, r24
    sbc r31, r25
    cpi r30, 150
    cpc r31, r1
    brlo .Lontime
    ldi r18, 8
    lds r24, 0x0a20
    lds r25, 0x0a21
.Lontime:
    subi r24, lo8(-250)
    sbci r25, hi8(-250)
    out 0x1c, r24
    out 0x1d, r25
    sts 0x0a28, r24
    sts 0x0a29, r25
    in r19, 0x1f
    tst r19
    brne .Lframe_done
    lds r21, hal_elapsed_frames
    cpi r21, 255
    breq .Lfault_near
    inc r21
    sts hal_elapsed_frames, r21
    mov r21, r18
    andi r21, 12
    brne .Lframe_done
    sbrs r18, 1
    rjmp .Lno_frame
    lds r21, hal_active
    ldi r30, 20
    eor r21, r30
    sts hal_active, r21
    andi r18, 0xfc
    ori r18, 1
    rjmp .Lframe_done
.Lno_frame:
    sbrs r18, 0
    rjmp .Lframe_done
.Lfault_near:
    ldi r18, 8
.Lframe_done:
    sbrs r18, 0
    rjmp .Lcheck_dark
    lds r30, hal_active
    add r30, r19
    ldi r31, 0
    subi r30, lo8(-(hal_frames))
    sbci r31, hi8(-(hal_frames))
    ld r20, Z
    cpi r20, 10
    brlo .Lcheck_dark
#if BOARD_SHARED_SLOTS
    /* Levels follow masks (hal_masks[20..39]): one address for both. */
    ldd r0, Z+40
    mov r30, r0
    ldi r31, 0
    subi r30, lo8(-(hal_masks))
    sbci r31, hi8(-(hal_masks))
    ld r21, Z
    ldd r30, Z+20
#else
    mov r30, r19
    ldi r31, 0
    subi r30, lo8(-(hal_masks))
    sbci r31, hi8(-(hal_masks))
    ld r21, Z
    mov r30, r19
    ldi r31, 0
    subi r30, lo8(-(hal_levels))
    sbci r31, hi8(-(hal_levels))
    ld r30, Z
#endif
    ldi r31, 0x3e
    sts 0x0406, r31
    sts 0x0405, r30
    lds r30, 0x0a20
    lds r31, 0x0a21
    sub r24, r30
    sbc r25, r31
    subi r24, 121
    sbci r25, 0
    cpi r24, 130
    cpc r25, r1
    brsh .Lfault
    lds r30, 0x008b
    sbrc r30, 0
    rjmp .Llow_late
    lds r30, 0x008a
    sbrc r30, 0
    rjmp .Llow_late
    in r24, 0
    andi r24, 0xc1
    or r21, r24
    subi r20, 9
    lds r25, 0x0a20
    out 0, r21
.Lpulse:
    lds r30, 0x0a20
    sub r30, r25
    cp r30, r20
    brlo .Lpulse
    out 0, r24
    rjmp .Ldone
.Lcheck_dark:
    lds r21, 0x008b
    sbrc r21, 0
    rjmp .Llow_late
    lds r21, 0x008a
    sbrs r21, 0
    rjmp .Ldone
.Llow_late:
    andi r18, 0xf8
    ori r18, 4
    rjmp .Ldone
.Lfault:
    ldi r18, 8
.Ldone:
    out 0x1e, r18
    inc r19
    cpi r19, 20
    brlo .Lsave_slot
    ldi r19, 0
.Lsave_slot:
    out 0x1f, r19
    pop r31
    pop r30
    pop r25
    pop r24
    pop r21
    pop r20
    pop r19
    pop r18
    pop r1
    pop r0
    out 0x3f, r0
    pop r0
    reti
.size TCA0_CMP0_vect, .-TCA0_CMP0_vect
