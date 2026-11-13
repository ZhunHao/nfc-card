#ifndef ANIMATION_H
#define ANIMATION_H
#include <stdint.h>
#include "board_config.h"
/* Unsigned milliseconds since the most recent qualified reveal start. */
void animation_render(uint32_t elapsed_ms, uint8_t brightness[BOARD_LED_COUNT]);
#endif
