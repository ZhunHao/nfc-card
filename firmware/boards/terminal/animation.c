#include <stdbool.h>
#include "animation.h"
#include "led_map.h"

void animation_render(uint32_t elapsed_ms, uint8_t brightness[BOARD_LED_COUNT])
{
    for (uint8_t i = 0; i < BOARD_LED_COUNT; ++i) brightness[i] = 0;
    /* The schedule is periodic from 0. app.c keeps ages below 10400 ms, so two
     * subtractions replace a 32-bit modulo (~500 cycles) on every frame. */
    uint16_t t;
    if (elapsed_ms < 3UL * BOARD_CYCLE_MS) {
        t = (uint16_t)elapsed_ms;
        if (t >= 2u * BOARD_CYCLE_MS) t -= 2u * BOARD_CYCLE_MS;
        else if (t >= BOARD_CYCLE_MS) t -= BOARD_CYCLE_MS;
    } else t = (uint16_t)(elapsed_ms % BOARD_CYCLE_MS);

    if (t < BOARD_LINES_END_MS) {
        brightness[terminal_line_led[t / BOARD_LINE_STEP_MS]] = 255;
        return;
    }
    if (t < BOARD_BAR_START_MS) return;
    if (t < BOARD_BAR_END_MS) {
        brightness[terminal_bar_led[(t - BOARD_BAR_START_MS) / BOARD_BAR_STEP_MS]] = 255;
        return;
    }
    /* Two blinks of the last line and the bar's end, then dark until restart. */
    uint16_t b = t - BOARD_BAR_END_MS;
    bool on = b < BOARD_BLINK_ON_MS
        || (b >= BOARD_BLINK_ON_MS + BOARD_BLINK_OFF_MS
            && b < 2u * BOARD_BLINK_ON_MS + BOARD_BLINK_OFF_MS);
    if (on) {
        brightness[terminal_line_led[BOARD_LINE_COUNT - 1u]] = 255;
        brightness[terminal_bar_led[BOARD_BAR_COUNT - 1u]] = 255;
    }
}
