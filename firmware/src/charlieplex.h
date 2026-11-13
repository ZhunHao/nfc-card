#ifndef CHARLIEPLEX_H
#define CHARLIEPLEX_H
#include <stdbool.h>
#include <stdint.h>
#include "board_config.h"
/* Logical CP indices, not physical port bit numbers. */
typedef struct { uint8_t anode; uint8_t cathode; } cplex_pair_t;
bool cplex_pair_for(uint8_t led, cplex_pair_t *pair);
uint8_t cplex_output_mask(uint8_t led);
uint8_t cplex_level_mask(uint8_t led);
#endif
