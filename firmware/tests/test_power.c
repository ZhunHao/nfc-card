#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "power.h"

static void qualify(power_state_t *s)
{
    assert(!power_step(s, false, false, 99));
    assert(power_step(s, false, false, 1));
    assert(s->phase == POWER_REVEAL);
    assert(power_enabled(s) && power_ramp(s) == 0);
    assert(s->reveal_ms == 0 && s->ramp_ms == 0);
}
int main(void)
{
    power_state_t s;
    power_init(&s, 4);
    assert(!power_enabled(&s) && power_ramp(&s) == 0);
    qualify(&s);
    assert(!power_step(&s, false, true, 5));
    assert(!power_enabled(&s) && s.duty_sixteenths == 2);
    for (unsigned tier = 2; tier > 0; tier >>= 1) {
        assert(s.phase == POWER_RECOVER);
        assert(!power_step(&s, false, false, 99));
        assert(!power_step(&s, true, false, UINT16_MAX));
        assert(s.healthy_ms == 0 && s.duty_sixteenths == tier);
        assert(!power_step(&s, false, true, 99));
        assert(s.healthy_ms == 0 && s.duty_sixteenths == tier);
        qualify(&s);
        assert(!power_step(&s, false, false, 1)); assert(power_ramp(&s) == 1);
        assert(!power_step(&s, false, false, 198)); assert(power_ramp(&s) == 253);
        assert(!power_step(&s, false, false, 1)); assert(power_ramp(&s) == 255);
        assert(!power_step(&s, false, false, 599)); assert(s.phase == POWER_REVEAL);
        assert(!power_step(&s, false, false, 1)); assert(s.phase == POWER_TWINKLE);
        for (unsigned i = 0; i < 3; ++i) {
            assert(!power_step(&s, false, false, UINT16_MAX));
            assert(s.reveal_ms == 800 && s.ramp_ms == 200);
        }
        assert(!power_step(&s, true, true, UINT16_MAX));
        assert(s.duty_sixteenths == (tier >> 1));
        assert(s.reveal_ms == 0 && s.ramp_ms == 0);
        assert(power_ramp(&s) == 0);
    }
    assert(s.phase == POWER_DARK);
    assert(!power_step(&s, false, false, UINT16_MAX));
    assert(!power_enabled(&s));
    for (unsigned tier = 0; tier < 256; ++tier) {
        power_init(&s, (uint8_t)tier);
        if (tier == 1 || tier == 2 || tier == 4) {
            assert(s.phase == POWER_STARTUP);
            assert(!power_step(&s, false, false, 99));
            assert(!power_step(&s, true, false, 1));
            assert(s.healthy_ms == 0 && s.duty_sixteenths == tier);
            assert(power_step(&s, false, false, UINT16_MAX));
            assert(s.reveal_ms == 0 && s.ramp_ms == 0);
            power_timing_fault(&s);
            assert(s.phase == POWER_DARK && !power_enabled(&s));
            assert(!power_step(&s, false, false, UINT16_MAX));
        } else {
            assert(s.phase == POWER_DARK && !power_enabled(&s));
            assert(!power_step(&s, false, false, UINT16_MAX));
        }
    }
    power_init(&s, 4); qualify(&s);
    assert(!power_step(&s, false, false, 0)); assert(s.reveal_ms == 0);
    puts("power: qualification, dips, event races, tiers, timers, cold reset passed");
}
