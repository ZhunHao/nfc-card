#include "scan.h"
/* Exact floor(x/255), for 0 <= x <= 65025, without a divide helper. */
static uint8_t scale(uint8_t a, uint8_t b) {
    uint16_t x=(uint16_t)a*b;
    return (uint8_t)((x+1u+(x>>8))>>8);
}
#if BOARD_SHARED_SLOTS
#define SHARED_FOR(k) ((k)>=BOARD_SHARED_SLOTS?1u:BOARD_SHARED_SLOTS/(k))
/* Slots per lit LED, and the spacing of the lit slots, by lit count (no divide). */
static const uint8_t slots_for[BOARD_LED_COUNT+1]={0,
    SHARED_FOR(1),SHARED_FOR(2),SHARED_FOR(3),SHARED_FOR(4),SHARED_FOR(5),SHARED_FOR(6),SHARED_FOR(7),
    SHARED_FOR(8),SHARED_FOR(9),SHARED_FOR(10),SHARED_FOR(11),SHARED_FOR(12),SHARED_FOR(13),SHARED_FOR(14),
    SHARED_FOR(15),SHARED_FOR(16),SHARED_FOR(17),SHARED_FOR(18),SHARED_FOR(19),SHARED_FOR(20)};
#define STEP_FOR(k) (BOARD_LED_COUNT/(SHARED_FOR(k)*(k)))
static const uint8_t step_for[BOARD_LED_COUNT+1]={0,
    STEP_FOR(1),STEP_FOR(2),STEP_FOR(3),STEP_FOR(4),STEP_FOR(5),STEP_FOR(6),STEP_FOR(7),
    STEP_FOR(8),STEP_FOR(9),STEP_FOR(10),STEP_FOR(11),STEP_FOR(12),STEP_FOR(13),STEP_FOR(14),
    STEP_FOR(15),STEP_FOR(16),STEP_FOR(17),STEP_FOR(18),STEP_FOR(19),STEP_FOR(20)};
#endif
void scan_prepare(const uint8_t b[BOARD_LED_COUNT], uint8_t d, uint8_t r,
                  scan_frame_t *out) {
    uint8_t cap=d==4?62:d==2?31:d==1?15:0;
#if BOARD_SHARED_SLOTS
    /* Widths as in fixed slots; only LEDs the ISR would light get slots. Dark
     * LEDs cost one test each: the main-loop budget relies on that. */
    uint8_t width[BOARD_LED_COUNT],led[BOARD_LED_COUNT],lit=0;
    for(uint8_t i=0;i<BOARD_LED_COUNT;++i) {
        uint8_t v=b[i];
        if(!v) continue;
        uint8_t w=r==255?scale(v,cap):scale(scale(v,r),cap);
        if(w>=BOARD_MIN_PULSE_US) {width[lit]=w;led[lit]=i;++lit;}
    }
    /* One pass over the slots. led[] is written only where a pulse lands; the
     * ISR and hal_publish read it only there. */
    uint8_t step=step_for[lit],left=slots_for[lit],next=0,j=0;
    for(uint8_t s=0;s<BOARD_LED_COUNT;++s) {
        if(s==next && left) {
            out->on_us[s]=width[j];out->led[s]=led[j];next+=step;
            if(++j==lit) {j=0;--left;}
        } else out->on_us[s]=0;
    }
#else
    if(r==255) {
        for(uint8_t i=0;i<BOARD_LED_COUNT;++i) out->on_us[i]=scale(b[i],cap);
    } else {
        for(uint8_t i=0;i<BOARD_LED_COUNT;++i) out->on_us[i]=scale(scale(b[i],r),cap);
    }
#endif
}
