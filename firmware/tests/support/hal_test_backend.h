#ifndef HAL_TEST_BACKEND_H
#define HAL_TEST_BACKEND_H
#include <stdbool.h>
#include <stdint.h>
extern uint8_t test_dir, test_out, test_last_drive, test_last_level;
extern bool test_low, test_edge, test_config_ok, test_inject, test_reservoir_bypassed;
extern uint16_t test_now, test_compare;
extern unsigned test_drives, test_sleeps;
void test_reset(void);
void test_blank(void);
void test_levels(uint8_t level);
void test_pulse(uint8_t drive, uint8_t blank, uint8_t duration);
void test_publish_hook(void);
void hal_test_slot(void);
void hal_test_vlm(void);
#endif
