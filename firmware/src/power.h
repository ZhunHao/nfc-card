#ifndef POWER_H
#define POWER_H
#include <stdbool.h>
#include <stdint.h>
#include "board_config.h"

typedef enum { POWER_STARTUP, POWER_REVEAL, POWER_TWINKLE,
               POWER_RECOVER, POWER_DARK } power_phase_t;
typedef struct {
    power_phase_t phase;
    uint8_t duty_sixteenths;
    uint16_t healthy_ms, reveal_ms, ramp_ms;
} power_state_t;
void power_init(power_state_t *s, uint8_t initial_duty_sixteenths);
/* Delta belongs to the entry state. True only on a new qualified reveal. */
bool power_step(power_state_t *s, bool voltage_low, bool low_event, uint16_t elapsed_ms);
bool power_enabled(const power_state_t *s);
uint8_t power_ramp(const power_state_t *s);
void power_timing_fault(power_state_t *s);
#endif
