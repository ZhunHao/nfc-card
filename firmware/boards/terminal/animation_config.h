#ifndef ANIMATION_CONFIG_H
#define ANIMATION_CONFIG_H
/* B3 Terminal card: the nine output lines "print" top to bottom, the progress
 * bar steps left to right, then the last line and the bar's end blink twice.
 * One LED is lit at a time, two during the blink. */
#define BOARD_LINE_COUNT 9u
#define BOARD_BAR_COUNT 11u
#define BOARD_LINE_STEP_MS 220u
#define BOARD_LINES_END_MS (BOARD_LINE_COUNT * BOARD_LINE_STEP_MS)   /* 1980 */
#define BOARD_BAR_START_MS 2200u
#define BOARD_BAR_STEP_MS 160u
#define BOARD_BAR_END_MS (BOARD_BAR_START_MS + BOARD_BAR_COUNT * BOARD_BAR_STEP_MS) /* 3960 */
#define BOARD_BLINK_ON_MS 240u
#define BOARD_BLINK_OFF_MS 180u
#define BOARD_CYCLE_MS 4800u
/* power.c only relabels its phase REVEAL -> TWINKLE at this age; LED output is
 * unaffected. Kept at the NTUAS 800 ms that the shared tests/test_power.c asserts. */
#define BOARD_REVEAL_MS 800u
/* Lit LEDs share up to this many scan slots per frame (src/scan.h); one or two
 * LEDs are lit at once, so each gets 6 or 3 slots instead of 1. */
#define BOARD_SHARED_SLOTS 6  /* no suffix: scan_isr.S uses it too */

/* scan_isr.S includes this header for BOARD_SHARED_SLOTS. */
#ifndef __ASSEMBLER__
_Static_assert(BOARD_LINE_COUNT + BOARD_BAR_COUNT == BOARD_LED_COUNT,
               "lines and bar must cover the board");
_Static_assert(BOARD_LINES_END_MS <= BOARD_BAR_START_MS, "bar starts after the last line");
_Static_assert(BOARD_BAR_END_MS + 2u * BOARD_BLINK_ON_MS + BOARD_BLINK_OFF_MS < BOARD_CYCLE_MS,
               "blinks end before the cycle restarts");
/* app.c wraps the animation age from 10400 ms back by 4800 ms. */
_Static_assert(BOARD_CYCLE_MS == 4800u, "cycle must match the app's age wrap");
#endif
#endif
