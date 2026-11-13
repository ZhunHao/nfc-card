#ifndef APP_H
#define APP_H
#include "hal_avr.h"
#include "power.h"
/* reservoir_bypass latches once VCC has been healthy for BOARD_BYPASS_QUALIFY_MS
 * (bypass_ms counts complete healthy frames; any warning restarts it): R7 has then
 * charged C4 for ~14 time constants, so Q1 may bypass it until the next reset. */
typedef struct { power_state_t power; uint16_t age_ms, bypass_ms; bool diagnostic, partial_healthy_frame, reservoir_bypass; } app_state_t;
void app_init(app_state_t *s,bool diagnostic);
bool app_step(app_state_t *s,hal_events_t events,scan_frame_t *frame);
void app_run(bool diagnostic);
#endif
