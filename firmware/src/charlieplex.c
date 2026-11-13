#include "charlieplex.h"
#include <stddef.h>

bool cplex_pair_for(uint8_t led, cplex_pair_t *pair)
{
    if (led >= BOARD_LED_COUNT || pair == NULL) return false;
    pair->anode = led / 4u;
    pair->cathode = led % 4u;
    if (pair->cathode >= pair->anode) ++pair->cathode;
    return true;
}

uint8_t cplex_output_mask(uint8_t led)
{
    cplex_pair_t pair;
    if (!cplex_pair_for(led, &pair)) return 0;
    return (uint8_t)((2u << pair.anode) | (2u << pair.cathode));
}

uint8_t cplex_level_mask(uint8_t led)
{
    if (led >= BOARD_LED_COUNT) return 0;
    return (uint8_t)(2u << (led / 4u));
}
