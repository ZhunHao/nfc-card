#include "hal_test_backend.h"
#include <assert.h>
uint8_t test_dir,test_out,test_last_drive,test_last_level;
bool test_low,test_edge,test_config_ok,test_inject,test_reservoir_bypassed;
uint16_t test_now,test_compare;
unsigned test_drives,test_sleeps;
void test_reset(void) { test_dir=0xc1;test_out=0x81;test_low=test_edge=test_inject=test_reservoir_bypassed=false;test_config_ok=true;test_now=0;test_compare=250;test_drives=test_sleeps=0; }
void test_blank(void) { test_dir&=~0x3e; }
void test_levels(uint8_t level) { assert((test_dir&0x3e)==0);test_out=(test_out&~0x3e)|level; }
void test_pulse(uint8_t drive,uint8_t blank,uint8_t duration) {
    assert((test_dir&0x3e)==0); assert((drive&~0x3e)==0xc1);
    uint8_t bits=drive&0x3e;assert(bits && (bits&(bits-1)));bits&=bits-1;assert(!(bits&(bits-1)));
    assert((test_out&drive&0x3e)!=0);assert((test_out&drive&0x3e)!=(drive&0x3e));
    test_dir=drive;test_last_drive=drive;test_last_level=test_out;++test_drives;test_now+=duration;test_dir=blank;
}
void test_publish_hook(void) { if(test_inject) {test_edge=true;test_low=true;test_inject=false;} }
