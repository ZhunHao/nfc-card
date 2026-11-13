#include "hal_avr.h"
#include "charlieplex.h"
#ifdef HAL_HOST_TEST
#include "hal_test_backend.h"
#define LOCK() uint8_t saved=0
#define UNLOCK() ((void)saved)
#define LOW() test_low
#define EDGE() test_edge
#define ACK_EDGE() (test_edge=false)
#define NOW() test_now
#define COMPARE(v) (test_compare=(v))
#define ACK_SLOT() ((void)0)
#define BLANK() test_blank()
#define LEVEL(v) test_levels(v)
#define DIR() test_dir
#define PUBLISH_HOOK() test_publish_hook()
#define PULSE(d,b,t) test_pulse(d,b,t)
#else
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/cpufunc.h>
#include <avr/sleep.h>
#include <util/delay.h>
#define LOCK() uint8_t saved=SREG; cli()
#define UNLOCK() __asm__ volatile("out 0x3f, %0\n\tnop" :: "r"(saved) : "memory")
#define LOW() (BOD.STATUS & BOD_VLMS_bm)
#define EDGE() (BOD.INTFLAGS & BOD_VLMIF_bm)
#define ACK_EDGE() (BOD.INTFLAGS=BOD_VLMIF_bm)
#define NOW() TCA0.SINGLE.CNT
#define COMPARE(v) (TCA0.SINGLE.CMP0=(v))
#define ACK_SLOT() (TCA0.SINGLE.INTFLAGS=TCA_SINGLE_CMP0_bm)
#define BLANK() (PORTA.DIRCLR=BOARD_CP_PORT_MASK)
#define LEVEL(v) do {PORTA.OUTCLR=BOARD_CP_PORT_MASK;PORTA.OUTSET=(v);} while(0)
#define DIR() VPORTA.DIR
#define PUBLISH_HOOK() ((void)0)
#endif

enum { ENABLED=1, PENDING=2, LOW_LATCH=4, FAULT=8 };
/* hal_frames: two 20-byte on_us buffers (active = 0 or 20); with shared slots,
 * the slots' LED indices follow at +40, which the ISR reads with LDD Z+40. */
#if BOARD_SHARED_SLOTS
/* Levels follow masks so the ISR reaches both from one address. */
uint8_t hal_frames[80],hal_masks[40];
#define levels (hal_masks+20)
#define LED_OF(i) frames[active+(i)+40]
#else
uint8_t hal_frames[40],hal_masks[20],hal_levels[20];
#define levels hal_levels
#define LED_OF(i) (i)
#endif
#define frames hal_frames
#define masks hal_masks
volatile uint8_t hal_active,hal_elapsed_frames;
#define active hal_active
#define elapsed_frames hal_elapsed_frames
#ifdef HAL_HOST_TEST
static volatile uint8_t flags;
static uint8_t slot;
static uint16_t anchor;
#else
/* Dedicated low-I/O scratch registers: six cycles saved per anchor update,
 * plus constant-time flag/slot exchange. No other module owns registers. */
#define flags GPIOR2
#define slot GPIOR3
#define anchor _SFR_IO16(0x1c)
#endif
static inline __attribute__((always_inline)) void inhibit(void) {
    BLANK();flags=(flags & (uint8_t)~(ENABLED|PENDING))|LOW_LATCH;
}
static inline __attribute__((always_inline)) void fail(void) {
    BLANK();flags=FAULT;
}
static inline __attribute__((always_inline)) void voltage_irq(void) {
    inhibit();ACK_EDGE();
}
#ifdef HAL_HOST_TEST
/* Host register-seam reference; emitted scan_isr.S is independently executed
 * by check_avr_timing.py, including all register saves and real GPIO writes. */
static inline void slot_irq(void) {
    ACK_SLOT();BLANK();
    uint8_t state=flags;
    uint16_t now=NOW();
    if ((uint16_t)(now-anchor)>=150u) { state=FAULT;anchor=now; }
    anchor+=BOARD_SCAN_SLOT_US;COMPARE(anchor);
    if (LOW() || EDGE()) state=(state & (uint8_t)~(ENABLED|PENDING))|LOW_LATCH;
    uint8_t index=slot;
    if(index==0) {
        uint8_t count=elapsed_frames;
        if(count==UINT8_MAX) state=FAULT; else elapsed_frames=count+1;
        if(!(state&(FAULT|LOW_LATCH))) {
            if(state&PENDING) {active^=20;state=(state & (uint8_t)~PENDING)|ENABLED;}
            else if(state&ENABLED) state=FAULT;
        }
    }
    if(state&ENABLED) {
        uint8_t duration=frames[active+index];
        if(duration>9) {
            uint8_t blank=DIR() & (uint8_t)~BOARD_CP_PORT_MASK;
            uint8_t led=LED_OF(index);
            uint8_t drive=blank|masks[led];
            LEVEL(levels[led]);
            uint16_t remaining=anchor-NOW();
            if(remaining<121u || remaining>250u) state=FAULT;
            else if(LOW() || EDGE()) state=(state & (uint8_t)~(ENABLED|PENDING))|LOW_LATCH;
            else PULSE(drive,blank,duration-9);
        }
    }
    flags=state;
    if(++index==BOARD_LED_COUNT) index=0;
    slot=index;
}
void hal_test_slot(void) { slot_irq(); }
void hal_test_vlm(void) { voltage_irq(); }
#else
/* TCA0_CMP0 vector is in scan_isr.S; it preserves the full interrupted ABI. */
ISR(BOD_VLM_vect) { voltage_irq(); }
#endif

void hal_init(void) {
    LOCK();BLANK();
    active=flags=elapsed_frames=0;
    slot=0;anchor=5000;
    for(uint8_t i=0;i<20;++i) {masks[i]=cplex_output_mask(i);levels[i]=cplex_level_mask(i);}
#ifdef HAL_HOST_TEST
    if(!test_config_ok) flags=FAULT;
#else
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB,CLKCTRL_PDIV_16X_gc|CLKCTRL_PEN_bm);
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLA,CLKCTRL_CLKSEL_OSC20M_gc);
    PORTA.PIN1CTRL=0;PORTA.PIN2CTRL=0;PORTA.PIN3CTRL=0;PORTA.PIN4CTRL=0;PORTA.PIN5CTRL=0;
    _PROTECTED_WRITE(BOD.CTRLA,BOD_ACTIVE_ENABLED_gc|BOD_SLEEP_ENABLED_gc);
    _PROTECTED_WRITE(BOD.CTRLB,BOD_LVL_BODLEVEL0_gc);
    BOD.VLMCTRLA=BOD_VLMLVL_5ABOVE_gc;
    BOD.INTCTRL=BOD_VLMIE_bm|BOD_VLMCFG_CROSS_gc;
    if((FUSE.OSCCFG&FUSE_FREQSEL_gm)!=FREQSEL_16MHZ_gc ||
       (FUSE.BODCFG&(FUSE_ACTIVE_gm|FUSE_LVL_gm))!=ACTIVE_ENABLED_gc ||
       (FUSE.SYSCFG0&FUSE_RSTPINCFG_gm)!=RSTPINCFG_UPDI_gc ||
       CLKCTRL.MCLKCTRLB!=(CLKCTRL_PDIV_16X_gc|CLKCTRL_PEN_bm) ||
       (CLKCTRL.MCLKCTRLA&CLKCTRL_CLKSEL_gm)!=CLKCTRL_CLKSEL_OSC20M_gc ||
       (BOD.CTRLA&BOD_ACTIVE_gm)!=BOD_ACTIVE_ENABLED_gc ||
       (BOD.CTRLB&BOD_LVL_gm)!=BOD_LVL_BODLEVEL0_gc) flags=FAULT;
    TCA0.SINGLE.CTRLA=0;TCA0.SINGLE.CTRLB=0;TCA0.SINGLE.CTRLD=0;
    TCA0.SINGLE.PER=0xffff;TCA0.SINGLE.CNT=0;
    TCA0.SINGLE.INTFLAGS=0xff;TCA0.SINGLE.INTCTRL=TCA_SINGLE_CMP0_bm;
#endif
    if(LOW()||EDGE()) inhibit();
    ACK_EDGE();COMPARE(anchor);
#ifndef HAL_HOST_TEST
    TCA0.SINGLE.CTRLA=TCA_SINGLE_CLKSEL_DIV1_gc|TCA_SINGLE_ENABLE_bm;
    set_sleep_mode(SLEEP_MODE_IDLE);
    sleep_enable();
#endif
    UNLOCK();
#ifndef HAL_HOST_TEST
    sei();
#endif
}

hal_events_t hal_take_events(void) {
    /* The status check runs with interrupts enabled. Any crossing between it
     * and the exchange is preserved in the IRQ latch or next event batch. */
    if(LOW()||EDGE()) {LOCK();inhibit();ACK_EDGE();UNLOCK();}
    uint8_t count,state;
    {LOCK();count=elapsed_frames;elapsed_frames=0;state=flags;
     flags&=(uint8_t)~LOW_LATCH;UNLOCK();}
    hal_events_t e={count,!!LOW(),!!(state&LOW_LATCH),!!(state&FAULT)};
    return e;
}
bool hal_publish(const scan_frame_t *frame,bool permit) {
    if(!permit) {LOCK();flags&=(uint8_t)~(ENABLED|PENDING);BLANK();UNLOCK();return false;}
    /* With pending clear the ISR cannot change active: writer owns inactive.
     * No memcpy under cli; the final byte exchange alone publishes the frame. */
    bool available;uint8_t target;
    {LOCK();available=!(flags&(PENDING|FAULT|LOW_LATCH));target=active^20;UNLOCK();}
    if(!available) return false;
    for(uint8_t i=0;i<20;++i) {
        if(frame->on_us[i]>62) {LOCK();fail();UNLOCK();return false;}
        frames[target+i]=frame->on_us[i];
#if BOARD_SHARED_SLOTS
        /* A lit slot's LED indexes the ISR's 20-entry mask/level tables; a dark
         * slot's is never read, so it is neither checked nor copied. */
        if(frame->on_us[i]>=BOARD_MIN_PULSE_US) {
            if(frame->led[i]>=BOARD_LED_COUNT) {LOCK();fail();UNLOCK();return false;}
            frames[target+40+i]=frame->led[i];
        }
#endif
    }
    PUBLISH_HOOK();
    LOCK();
    /* Read both registers without branch-dependent masking time. */
    if(LOW()|EDGE()) {inhibit();UNLOCK();return false;}
    if(flags&(FAULT|LOW_LATCH)) {UNLOCK();return false;}
    flags|=PENDING;
    UNLOCK();return true;
}
void hal_sleep(void) {
#ifndef HAL_HOST_TEST
    for(;;) {
#endif
        LOCK();
        if(elapsed_frames || (flags&LOW_LATCH) || EDGE()) {UNLOCK();return;}
#ifdef HAL_HOST_TEST
        ++test_sleeps;
#else
        /* AVR executes the instruction after SEI before an interrupt. */
        __asm__ volatile("sei\n\tsleep" ::: "memory");
#endif
        UNLOCK();
#ifndef HAL_HOST_TEST
    }
#endif
}
/* Kept after hal_sleep so the audited hal_publish..hal_sleep window is unchanged. */
void hal_bypass_reservoir(void) {
#ifdef HAL_HOST_TEST
    test_reservoir_bypassed=true;
#else
    PORTC.OUTCLR=PIN0_bm;PORTC.DIRSET=PIN0_bm;
#endif
}
/* Instant power-up flash. An iPhone tap powers the card for ~30 ms every ~0.7 s
 * (docs/bringup/2026-11-08-orbit-first-cards.md), shorter than the 100 ms VLM
 * qualification, so without this the card stays dark on an iPhone. Runs before
 * hal_init starts the scan timer or interrupts: one LED, 1 ms on / 1 ms off,
 * BOARD_BOOT_FLASH_PULSES times. It deliberately skips the VLM gate; BOD still
 * holds reset below BODLEVEL0. Fuse SUT=0 ms lets it start inside the burst. */
void hal_boot_flash(void) {
#ifdef BOARD_BOOT_FLASH_LED
    const uint8_t mask=cplex_output_mask(BOARD_BOOT_FLASH_LED);
    const uint8_t level=cplex_level_mask(BOARD_BOOT_FLASH_LED);
#ifndef HAL_HOST_TEST
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB,CLKCTRL_PDIV_16X_gc|CLKCTRL_PEN_bm);
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLA,CLKCTRL_CLKSEL_OSC20M_gc);
    PORTA.PIN1CTRL=0;PORTA.PIN2CTRL=0;PORTA.PIN3CTRL=0;PORTA.PIN4CTRL=0;PORTA.PIN5CTRL=0;
#endif
    BLANK();
    for(uint8_t i=0;i<BOARD_BOOT_FLASH_PULSES;++i) {
        LEVEL(level);
#ifdef HAL_HOST_TEST
        {uint8_t blank=DIR()&(uint8_t)~BOARD_CP_PORT_MASK;PULSE(blank|mask,blank,1);}
#else
        PORTA.DIRSET=mask;_delay_ms(1);BLANK();_delay_ms(1);
#endif
    }
    BLANK();
#endif
}
