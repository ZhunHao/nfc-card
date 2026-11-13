#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "animation.h"

/* Independent copy of the placement in hardware/orbit/README.md. */
static const unsigned iss[9] = {1, 2, 0, 3, 5, 6, 7, 4, 8};
static const unsigned high[8] = {9, 12, 13, 14, 16, 17, 18, 19};
static const int station[9] = {-1, -1, 10, -1, 15, -1, -1, 11, -1};

static unsigned lit(const uint8_t *b)
{
    unsigned n = 0;
    for (unsigned i = 0; i < 20; ++i) n += b[i] != 0;
    return n;
}
int main(void)
{
    uint8_t b[20], repeated[20];
    unsigned seen[20] = {0};
    for (unsigned i = 0; i < 9; ++i) ++seen[iss[i]];
    for (unsigned i = 0; i < 8; ++i) ++seen[high[i]];
    for (unsigned i = 0; i < 9; ++i) if (station[i] >= 0) ++seen[station[i]];
    for (unsigned i = 0; i < 20; ++i) assert(seen[i] == 1);

    /* Boot dark, then the first ISS LED ramps monotonically to full. */
    animation_render(0, b); assert(lit(b) == 0);
    uint8_t last = 0;
    for (uint32_t t = 0; t < 800; ++t) {
        animation_render(t, b);
        assert(lit(b) <= 1 && b[iss[0]] >= last);
        last = b[iss[0]];
    }
    animation_render(800, b); assert(b[iss[0]] == 255 && lit(b) == 1);

    /* ISS pass: bright head; station when overhead, otherwise a dim trail. */
    for (unsigned i = 0; i < 9; ++i) {
        animation_render(800u + 200u * i + 100u, b);
        assert(b[iss[i]] == 255);
        if (station[i] >= 0) assert(b[station[i]] == 230 && lit(b) == 2);
        else if (i) assert(b[iss[i - 1]] == 48 && lit(b) == 2);
        else assert(lit(b) == 1);
    }
    animation_render(800 + 1800 + 100, b); assert(lit(b) == 0);
    /* High orbit: one LED at a time, 1.5x slower than the ISS. */
    for (unsigned i = 0; i < 8; ++i) {
        animation_render(800u + 2000u + 300u * i, b);
        assert(b[high[i]] == 255 && lit(b) == 1);
        animation_render(800u + 2000u + 300u * i + 299u, b);
        assert(b[high[i]] == 255 && lit(b) == 1);
    }
    animation_render(800 + 4400, b); assert(lit(b) == 0);
    animation_render(800 + 4799, b); assert(lit(b) == 0);

    for (uint32_t t = 0; t < 20000; ++t) {
        animation_render(t, b);
        assert(lit(b) <= 2);
        unsigned bright = 0;
        for (unsigned i = 0; i < 20; ++i) bright += b[i] > 48;
        assert(bright <= 2);
        /* app.c folds age by 4800 ms; the cycle must repeat exactly. */
        if (t >= 800) {
            animation_render(t + 4800, repeated);
            assert(memcmp(b, repeated, sizeof b) == 0);
        }
    }
    animation_render(UINT32_MAX, b);
    animation_render(800 + (UINT32_MAX - 800) % 4800, repeated);
    assert(memcmp(b, repeated, sizeof b) == 0);
    /* Unsigned caller delta handles a hardware millisecond tick wrapping. */
    uint32_t start = UINT32_MAX - 99u;
    animation_render((uint32_t)(0u - start), b);
    assert(b[iss[0]] == (100u * 255u) / 800u && lit(b) == 1);
    puts("animation: reveal, ISS pass with stations, high orbit, period and large times passed");
}
