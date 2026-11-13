#ifndef SCAN_H
#define SCAN_H
#include <stdint.h>
#include "board_config.h"
#if BOARD_SHARED_SLOTS
/* Shared slots: slot s drives LED led[s] for on_us[s]. Lit LEDs (>= 10 us, the
 * ISR's shortest pulse) share BOARD_SHARED_SLOTS slots evenly, spread across the
 * frame; with more lit LEDs than that, each keeps one slot. */
typedef struct { uint8_t on_us[BOARD_LED_COUNT]; uint8_t led[BOARD_LED_COUNT]; } scan_frame_t;
#else
/* Fixed slots: slot k drives LED k. */
typedef struct { uint8_t on_us[BOARD_LED_COUNT]; } scan_frame_t;
#endif
void scan_prepare(const uint8_t brightness[BOARD_LED_COUNT], uint8_t duty_sixteenths,
                  uint8_t ramp, scan_frame_t *out);
#endif
