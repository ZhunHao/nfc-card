#ifndef HAL_AVR_H
#define HAL_AVR_H
#include <stdbool.h>
#include <stdint.h>
#include "scan.h"
typedef struct { uint16_t elapsed_frames; bool voltage_low, low_event, timing_fault; } hal_events_t;
void hal_init(void);
hal_events_t hal_take_events(void);
bool hal_publish(const scan_frame_t *frame, bool permit);
void hal_sleep(void);
/* Drive PC0 low: Q1 bypasses the R7 soft-start resistor. Reset leaves PC0 an
 * input and R8 holds Q1 off, so every power-up starts soft again. */
void hal_bypass_reservoir(void);
/* Before hal_init: flash BOARD_BOOT_FLASH_LED at once, ahead of the VLM
 * qualification, so even a ~30 ms field burst (iPhone tap) shows light.
 * No-op on boards that do not define BOARD_BOOT_FLASH_LED. */
void hal_boot_flash(void);
#endif
