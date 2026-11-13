#include "power.h"

static uint16_t saturate(uint16_t value, uint16_t delta, uint16_t limit)
{
    if (value >= limit || delta >= limit - value) return limit;
    return value + delta;
}

void power_init(power_state_t *s, uint8_t initial_duty_sixteenths)
{
    s->healthy_ms = s->reveal_ms = s->ramp_ms = 0;
    bool valid = initial_duty_sixteenths == 4 || initial_duty_sixteenths == 2 || initial_duty_sixteenths == 1;
    s->duty_sixteenths = valid ? initial_duty_sixteenths : 0;
    s->phase = valid ? POWER_STARTUP : POWER_DARK;
}

bool power_enabled(const power_state_t *s)
{
    return s->duty_sixteenths != 0 && (s->phase == POWER_REVEAL || s->phase == POWER_TWINKLE);
}

bool power_step(power_state_t *s, bool voltage_low, bool low_event, uint16_t elapsed_ms)
{
    if (s->phase == POWER_DARK) return false;
    if (voltage_low || low_event) {
        s->healthy_ms = 0;
        if (power_enabled(s)) {
            s->duty_sixteenths >>= 1;
            s->phase = s->duty_sixteenths ? POWER_RECOVER : POWER_DARK;
            s->ramp_ms = s->reveal_ms = 0;
        }
        return false;
    }
    if (s->phase == POWER_STARTUP || s->phase == POWER_RECOVER) {
        s->healthy_ms = saturate(s->healthy_ms, elapsed_ms, BOARD_POWER_QUALIFY_MS);
        if (s->healthy_ms == BOARD_POWER_QUALIFY_MS) {
            s->phase = POWER_REVEAL;
            s->reveal_ms = s->ramp_ms = 0;
            return true;
        }
    } else if (power_enabled(s)) {
        s->ramp_ms = saturate(s->ramp_ms, elapsed_ms, BOARD_POWER_RAMP_MS);
        s->reveal_ms = saturate(s->reveal_ms, elapsed_ms, BOARD_REVEAL_MS);
        if (s->reveal_ms == BOARD_REVEAL_MS) s->phase = POWER_TWINKLE;
    }
    return false;
}

uint8_t power_ramp(const power_state_t *s)
{
    if (!power_enabled(s)) return 0;
    if (s->ramp_ms == BOARD_POWER_RAMP_MS) return 255;
    return (uint8_t)((s->ramp_ms * 255u) / BOARD_POWER_RAMP_MS);
}

void power_timing_fault(power_state_t *s)
{
    s->phase = POWER_DARK;
    s->duty_sixteenths = 0;
    s->healthy_ms = s->reveal_ms = s->ramp_ms = 0;
}
