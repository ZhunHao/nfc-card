#include <assert.h>
#include <stdio.h>
#include "hal_avr.h"
#include "support/hal_test_backend.h"
#include "charlieplex.h"
static void slots(unsigned n) { while(n--) {test_now=test_compare;hal_test_slot();} }
int main(void) {
    scan_frame_t f;for(unsigned i=0;i<20;++i) f.on_us[i]=31;
#if BOARD_SHARED_SLOTS
    for(unsigned i=0;i<20;++i) f.led[i]=i;
#endif
    test_reset();hal_init();assert((test_dir&0x3e)==0);
    assert(hal_publish(&f,true));slots(20);assert(test_drives>0);assert(test_dir==0xc1);assert((test_out&~0x3e)==0x81);
    hal_events_t e=hal_take_events();assert(e.elapsed_frames==1);assert(!e.timing_fault);
    unsigned before=test_drives;test_low=true;test_edge=true;hal_test_vlm();slots(20);assert(test_drives==before);
    test_low=false;test_edge=true;hal_test_vlm();assert(!hal_publish(&f,true));e=hal_take_events();assert(e.low_event);
    assert(hal_publish(&f,true));slots(20);assert(test_drives>before);
    test_reset();hal_init();test_inject=true;assert(!hal_publish(&f,true));slots(20);assert(!test_drives);
    test_reset();test_low=true;hal_init();assert(!hal_publish(&f,true));assert(hal_take_events().low_event);
    test_reset();test_config_ok=false;hal_init();assert(!hal_publish(&f,true));assert(hal_take_events().timing_fault);
    test_reset();hal_init();assert(hal_publish(&f,true));slots(40);assert(hal_take_events().timing_fault);
    test_reset();hal_init();assert(hal_publish(&f,true));test_now=test_compare+250;hal_test_slot();assert(hal_take_events().timing_fault);assert(!test_drives);
    test_reset();hal_init();f.on_us[3]=63;assert(!hal_publish(&f,true));assert(!test_drives);
    test_reset();hal_init();hal_sleep();assert(test_sleeps==1);slots(20);hal_sleep();assert(test_sleeps==1);
    test_reset();hal_init();slots(20*256);assert(hal_take_events().timing_fault);assert(!test_drives);
    test_reset();hal_init();assert(!test_reservoir_bypassed);hal_bypass_reservoir();assert(test_reservoir_bypassed);
    /* Power-up flash: only the configured LED, a fixed pulse count, pins blank after. */
    test_reset();hal_boot_flash();assert((test_dir&0x3e)==0);
#ifdef BOARD_BOOT_FLASH_LED
    assert(test_drives==BOARD_BOOT_FLASH_PULSES);
    assert((test_last_drive&0x3e)==cplex_output_mask(BOARD_BOOT_FLASH_LED));
    assert((test_last_level&0x3e)==cplex_level_mask(BOARD_BOOT_FLASH_LED));
#else
    assert(!test_drives);
#endif
#if BOARD_SHARED_SLOTS
    /* Each slot drives the LED its frame names, not the slot's own LED. */
    for(unsigned i=0;i<20;++i) {f.on_us[i]=31;f.led[i]=7;}
    test_reset();hal_init();assert(hal_publish(&f,true));slots(20);
    assert(test_drives==20);assert((test_last_drive&0x3e)==cplex_output_mask(7));assert((test_last_level&0x3e)==cplex_level_mask(7));
    test_reset();hal_init();f.led[5]=20;assert(!hal_publish(&f,true));slots(20);assert(!test_drives);assert(hal_take_events().timing_fault);
#endif
    puts("hal: GPIO ordering, publication, warning, stale and deadline tests passed");
}
