#include "animation.h"

/* LED indices in pass order, left to right across the card (D = index + 1). */
static const uint8_t iss_leds[BOARD_ISS_COUNT] = {1, 2, 0, 3, 5, 6, 7, 4, 8};
static const uint8_t high_leds[BOARD_HIGH_COUNT] = {9, 12, 13, 14, 16, 17, 18, 19};
/* Ground station under each ISS position, or 0xff where there is none. */
static const uint8_t station_under[BOARD_ISS_COUNT] = {
    0xff, 0xff, 10, 0xff, 15, 0xff, 0xff, 11, 0xff
};

void animation_render(uint32_t elapsed_ms, uint8_t brightness[BOARD_LED_COUNT])
{
    for (uint8_t i = 0; i < BOARD_LED_COUNT; ++i) brightness[i] = 0;
    if (elapsed_ms < BOARD_REVEAL_MS) {
        /* The ISS rises over the left limb before its first step. */
        /* t*255/800 == t*51/160 exactly; 16-bit avoids a 32-bit divide. */
        brightness[iss_leds[0]] = (uint8_t)(((uint16_t)elapsed_ms * 51u) / 160u);
        return;
    }

    /* One bounded 32-bit reduction per frame; app.c bounds age below 10400 ms. */
    uint32_t cycle_ms = elapsed_ms - BOARD_REVEAL_MS;
    uint16_t cycle;
    if (cycle_ms < 2UL * BOARD_CYCLE_MS) {
        cycle = (uint16_t)cycle_ms;
        if (cycle >= BOARD_CYCLE_MS) cycle -= BOARD_CYCLE_MS;
    } else cycle = (uint16_t)(cycle_ms % BOARD_CYCLE_MS);

    if (cycle < BOARD_ISS_END_MS) {
        uint8_t step = (uint8_t)(cycle / BOARD_ISS_STEP_MS);
        brightness[iss_leds[step]] = 255;
        /* Second LED: the station being passed over, else the dim trail. */
        if (station_under[step] != 0xff) brightness[station_under[step]] = BOARD_STATION_LEVEL;
        else if (step > 0) brightness[iss_leds[step - 1u]] = BOARD_TRAIL_LEVEL;
    } else if (cycle >= BOARD_HIGH_START_MS && cycle < BOARD_HIGH_END_MS) {
        uint8_t step = (uint8_t)((cycle - BOARD_HIGH_START_MS) / BOARD_HIGH_STEP_MS);
        brightness[high_leds[step]] = 255;
    }
}
