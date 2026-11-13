#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

/* Hardware constants shared by every card. Each board under firmware/boards/<name>/
   supplies animation_config.h (must define BOARD_REVEAL_MS, used by power.c)
   and animation.c; select it with `make BOARD=<name>`. */

#define BOARD_LED_COUNT 20u
#define BOARD_CP_PIN_COUNT 5u
#define BOARD_CP_PORT_MASK 0x3eu
#define BOARD_CPU_HZ 1000000UL
#define BOARD_SCAN_SLOT_US 250u
#define BOARD_FRAME_MS 5u
#define BOARD_POWER_QUALIFY_MS 100u
/* Q1 bypasses R7 after this long continuously healthy (counted like the
   qualification above). 300 ms is ~14 R7*C4 time constants, so C4 has caught up
   with VCC even in a weak field and switching Q1 on does not step VCC down
   (sim/revb_power.cir; Wilson Harper's card waits the same 300 ms). */
#define BOARD_BYPASS_QUALIFY_MS 300u
#define BOARD_POWER_RAMP_MS 200u
#define BOARD_NORMAL_DUTY_SIXTEENTHS 4u
#define BOARD_DIAGNOSTIC_DUTY_SIXTEENTHS 2u

_Static_assert(BOARD_LED_COUNT == BOARD_CP_PIN_COUNT * (BOARD_CP_PIN_COUNT - 1u),
               "all directed Charlieplex pairs must be populated");
_Static_assert(BOARD_SCAN_SLOT_US * BOARD_LED_COUNT == BOARD_FRAME_MS * 1000u,
               "scan slots must form one frame");
_Static_assert((BOARD_CP_PORT_MASK & 1u) == 0, "PA0/UPDI must be preserved");
_Static_assert(BOARD_BYPASS_QUALIFY_MS >= BOARD_POWER_QUALIFY_MS &&
               BOARD_BYPASS_QUALIFY_MS % BOARD_FRAME_MS == 0,
               "bypass must follow qualification on a frame boundary");

#include "animation_config.h"
/* Boards opt in to shared slots (src/scan.h); 0 keeps one fixed slot per LED. */
#ifndef BOARD_SHARED_SLOTS
#define BOARD_SHARED_SLOTS 0
#endif
#define BOARD_MIN_PULSE_US 10u  /* the ISR omits requests below this */
/* Boards opt in to an instant power-up flash (hal_boot_flash) by defining
 * BOARD_BOOT_FLASH_LED in animation_config.h. 25 x 2 ms = 50 ms. */
#if defined(BOARD_BOOT_FLASH_LED) && !defined(BOARD_BOOT_FLASH_PULSES)
#define BOARD_BOOT_FLASH_PULSES 25u
#endif
#if defined(BOARD_BOOT_FLASH_LED) && !defined(__ASSEMBLER__)
_Static_assert(BOARD_BOOT_FLASH_LED < BOARD_LED_COUNT, "boot flash LED must exist");
#endif
_Static_assert(BOARD_SHARED_SLOTS <= BOARD_LED_COUNT, "shared slots must fit in a frame");
#endif
