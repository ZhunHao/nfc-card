#ifndef ANIMATION_CONFIG_H
#define ANIMATION_CONFIG_H
/* C1 Orbit to scale: the ISS sweeps its 420 km orbit with a dim trail and
 * lights each ground station it passes over, then a satellite on the 2,000 km
 * orbit crosses more slowly. LED index k is D[k+1]; the position tables in
 * animation.c follow the placement in hardware/orbit/README.md. */
#define BOARD_REVEAL_MS 800u /* shared tests/test_power.c and test_app.c assume 800 */
#define BOARD_ISS_COUNT 9u
#define BOARD_HIGH_COUNT 8u
#define BOARD_STATION_COUNT 3u
#define BOARD_ISS_STEP_MS 200u
#define BOARD_ISS_GAP_MS 200u
#define BOARD_HIGH_STEP_MS 300u
#define BOARD_CYCLE_MS 4800u
#define BOARD_TRAIL_LEVEL 48u
#define BOARD_STATION_LEVEL 230u
/* Lit LEDs share up to this many scan slots per frame (src/scan.h); at most two
 * LEDs are lit at once, so each gets 3 or 6 slots instead of 1. */
#define BOARD_SHARED_SLOTS 6  /* no suffix: scan_isr.S uses it too */
/* Flash D16 (index 15, the middle ground station at x = 43) at power-up, so each
 * of an iPhone's ~30 ms poll bursts shows as the station pinging (src/hal_avr.c). */
#define BOARD_BOOT_FLASH_LED 15u

#define BOARD_ISS_END_MS (BOARD_ISS_COUNT * BOARD_ISS_STEP_MS)
#define BOARD_HIGH_START_MS (BOARD_ISS_END_MS + BOARD_ISS_GAP_MS)
#define BOARD_HIGH_END_MS (BOARD_HIGH_START_MS + BOARD_HIGH_COUNT * BOARD_HIGH_STEP_MS)

/* scan_isr.S includes this header for BOARD_SHARED_SLOTS. */
#ifndef __ASSEMBLER__
_Static_assert(BOARD_ISS_COUNT + BOARD_HIGH_COUNT + BOARD_STATION_COUNT == BOARD_LED_COUNT,
               "orbit groups must cover the board");
_Static_assert(BOARD_HIGH_END_MS <= BOARD_CYCLE_MS, "both passes must fit in one cycle");
/* app.c folds ages >= 10400 ms back by 4800 ms; the cycle must match it. */
_Static_assert(BOARD_CYCLE_MS == 4800u, "cycle must equal the app's age fold");
_Static_assert(BOARD_REVEAL_MS + BOARD_CYCLE_MS <= 10400u, "fold must land inside the cycle");
_Static_assert(BOARD_REVEAL_MS == 800u, "animation.c ramps with t*51/160 == t*255/800");
#endif
#endif
