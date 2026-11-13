#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "animation.h"
#include "led_map.h"

static unsigned lit(const uint8_t *b, int *first)
{
    unsigned n = 0;
    *first = -1;
    for (int i = 0; i < 20; ++i) if (b[i]) { if (*first < 0) *first = i; ++n; }
    return n;
}
int main(void)
{
    uint8_t b[20], repeated[20];
    int first;
    /* The placement map covers every LED exactly once. */
    unsigned seen = 0;
    for (unsigned i = 0; i < 9; ++i) seen |= 1u << terminal_line_led[i];
    for (unsigned i = 0; i < 11; ++i) seen |= 1u << terminal_bar_led[i];
    assert(seen == 0xfffffu);

    /* Lines print top to bottom, one at a time. */
    for (unsigned line = 0; line < 9; ++line)
        for (uint32_t t = line * 220u; t < (line + 1u) * 220u; t += 5) {
            animation_render(t, b);
            assert(lit(b, &first) == 1 && first == terminal_line_led[line]);
            assert(b[first] == 255);
        }
    animation_render(1980, b); assert(lit(b, &first) == 0);
    animation_render(2195, b); assert(lit(b, &first) == 0);
    /* Bar steps left to right. */
    for (unsigned seg = 0; seg < 11; ++seg) {
        animation_render(2200u + 160u * seg, b);
        assert(lit(b, &first) == 1 && first == terminal_bar_led[seg]);
        animation_render(2200u + 160u * seg + 155u, b);
        assert(lit(b, &first) == 1 && first == terminal_bar_led[seg]);
    }
    /* Blink: last line and bar end together, twice; then dark. */
    const uint8_t a = terminal_line_led[8], e = terminal_bar_led[10];
    for (uint32_t t = 3960; t < 4800; t += 5) {
        animation_render(t, b);
        bool on = t < 4200 || (t >= 4380 && t < 4620);
        assert(lit(b, &first) == (on ? 2u : 0u));
        if (on) assert(b[a] == 255 && b[e] == 255);
    }
    /* Never more than two LEDs; periodic everywhere, so app.c's age wrap
     * (10400 -> 5600) is seamless; huge timestamps stay in range. */
    for (uint32_t t = 0; t < 20000; ++t) {
        animation_render(t, b);
        assert(lit(b, &first) <= 2);
        animation_render(t + 4800u, repeated);
        assert(memcmp(b, repeated, sizeof b) == 0);
    }
    animation_render(10399, b); animation_render(10399 - 4800, repeated);
    assert(memcmp(b, repeated, sizeof b) == 0);
    animation_render(UINT32_MAX, b);
    animation_render(UINT32_MAX % 4800u, repeated);
    assert(memcmp(b, repeated, sizeof b) == 0);
    /* Boot: line 1 is first, under power.c's dark start and ramp. */
    animation_render(0, b); assert(lit(b, &first) == 1 && first == terminal_line_led[0]);
    puts("animation: line printout, bar fill, blink, LED budget and periodicity passed");
}
