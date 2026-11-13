#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "charlieplex.h"
#include "fixtures/card_led_pairs.h"

int main(void)
{
    bool seen[5][5] = {{false}};
    for (unsigned i = 0; i < 256; ++i) {
        cplex_pair_t pair = {255,255};
        if (i < 20) {
            assert(cplex_pair_for((uint8_t)i, &pair));
            assert(pair.anode == card_led_pairs[i][0]);
            assert(pair.cathode == card_led_pairs[i][1]);
            assert(cplex_output_mask((uint8_t)i) == card_led_pairs[i][2]);
            assert(cplex_level_mask((uint8_t)i) == card_led_pairs[i][3]);
            assert(!seen[pair.anode][pair.cathode]);
            seen[pair.anode][pair.cathode] = true;
        } else {
            assert(!cplex_pair_for((uint8_t)i, &pair));
            assert(cplex_output_mask((uint8_t)i) == 0);
            assert(cplex_level_mask((uint8_t)i) == 0);
        }
    }
    assert(!cplex_pair_for(0, NULL));
    puts("charlieplex: all directed pairs, polarity, and invalid inputs passed");
}
