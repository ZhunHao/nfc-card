#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "app.h"
#include "animation.h"
#include "scan.h"
/* Frames must match the selected board's own animation, not any one board's. */
static bool any_lit(const scan_frame_t *f) {for(unsigned k=0;k<20;++k) if(f->on_us[k]) return true; return false;}
/* Requested pulse for LED k, whichever slot carries it. */
static unsigned led_us(const scan_frame_t *f,unsigned k) {
#if BOARD_SHARED_SLOTS
    for(unsigned s=0;s<20;++s) if(f->on_us[s] && f->led[s]==k) return f->on_us[s];
    return 0;
#else
    return f->on_us[k];
#endif
}
/* The timing proof (check_avr_timing.py) covers frames with at most this many lit slots. */
static void check_lit_slots(const scan_frame_t *f) {
#if BOARD_SHARED_SLOTS
    unsigned lit=0;for(unsigned s=0;s<20;++s) lit+=f->on_us[s]>=BOARD_MIN_PULSE_US;
    assert(lit<=BOARD_SHARED_SLOTS);
#else
    (void)f;
#endif
}
static bool step(app_state_t *s,scan_frame_t *f) {return app_step(s,(hal_events_t){.elapsed_frames=1},f);}
/* A warning just before a boundary must not earn a full healthy frame.
 * Otherwise boundary 20 qualifies at only 95.1 ms and another warning at
 * 97.1 ms consumes a tier while recovery should still be qualifying. */
static void warning_qualification(bool diagnostic,bool recovery,unsigned warning_frames) {
    app_state_t s;scan_frame_t f;app_init(&s,diagnostic);
    if(recovery) for(unsigned i=0;i<60;++i) step(&s,&f);
    else for(unsigned i=0;i<19;++i) assert(!step(&s,&f));
    assert(!app_step(&s,(hal_events_t){.low_event=true,.elapsed_frames=warning_frames},&f));
    unsigned duty=diagnostic?2:4;if(recovery) duty/=2;
    power_phase_t phase=recovery?POWER_RECOVER:POWER_STARTUP;
    assert(s.power.duty_sixteenths==duty);
    assert(!app_step(&s,(hal_events_t){0},&f)); /* no boundary yet */
    assert(!step(&s,&f));assert(s.power.healthy_ms==0);
    for(unsigned i=0;i<19;++i) assert(!step(&s,&f));
    assert(s.power.healthy_ms==95);assert(s.power.phase==phase);
    /* Still less than 100 ms healthy: this must not consume another tier. */
    assert(!app_step(&s,(hal_events_t){.low_event=true},&f));
    assert(s.power.duty_sixteenths==duty);assert(s.power.phase==phase);
    for(unsigned i=0;i<3;++i) {
        assert(!app_step(&s,(hal_events_t){.voltage_low=true,.elapsed_frames=1},&f));
        assert(s.power.healthy_ms==0);assert(s.power.duty_sixteenths==duty);
    }
    /* A continued low status also leaves the first healthy interval partial. */
    assert(!step(&s,&f));assert(s.power.healthy_ms==0);
    for(unsigned i=0;i<19;++i) assert(!step(&s,&f));
    assert(s.power.healthy_ms==95);assert(s.power.phase==phase);
    assert(step(&s,&f));assert(s.power.healthy_ms==100);
    assert(s.power.phase==POWER_REVEAL);assert(s.power.duty_sixteenths==duty);
    assert(s.age_ms==0);assert(s.power.ramp_ms==0);
    for(unsigned i=0;i<20;++i) assert(f.on_us[i]==0);
    assert(step(&s,&f));assert(s.age_ms==5);assert(s.power.ramp_ms==5);
}
/* The bypass needs 300 ms of complete healthy frames: any warning restarts the count,
 * the interval after it is not credited, and a missed-frame backlog earns nothing. */
static void bypass_qualification(bool diagnostic,bool event) {
    app_state_t s;scan_frame_t f;app_init(&s,diagnostic);
    for(unsigned i=0;i<59;++i) {step(&s,&f);assert(!s.reservoir_bypass);}
    assert(s.bypass_ms==295);
    hal_events_t warn=event?(hal_events_t){.low_event=true}:(hal_events_t){.voltage_low=true,.elapsed_frames=1};
    app_step(&s,warn,&f);assert(s.bypass_ms==0);assert(!s.reservoir_bypass);
    step(&s,&f);assert(s.bypass_ms==0); /* partial interval after the warning */
    for(unsigned i=0;i<59;++i) {step(&s,&f);assert(!s.reservoir_bypass);}
    app_step(&s,(hal_events_t){.elapsed_frames=2},&f);assert(s.bypass_ms==295);assert(!s.reservoir_bypass);
    step(&s,&f);assert(s.bypass_ms==300);assert(s.reservoir_bypass);
    app_step(&s,(hal_events_t){.voltage_low=true,.elapsed_frames=1},&f);
    assert(s.reservoir_bypass); /* only a reset releases it */
}
int main(void) {
    for(unsigned mode=0;mode<2;++mode)
        for(unsigned event=0;event<2;++event)
            bypass_qualification(mode,event);
    for(unsigned mode=0;mode<2;++mode)
        for(unsigned recovery=0;recovery<2;++recovery)
            for(unsigned frames=0;frames<2;++frames)
                warning_qualification(mode,recovery,frames);
    for(unsigned mode=0;mode<2;++mode) {
        app_state_t s;scan_frame_t f;app_init(&s,mode);
        for(unsigned i=0;i<19;++i) {assert(!step(&s,&f));assert(!s.reservoir_bypass);}
        assert(step(&s,&f));assert(s.age_ms==0);assert(f.on_us[0]==0);
        assert(!s.reservoir_bypass); /* the reveal starts at 100 ms; Q1 waits for 300 ms */
        for(unsigned i=0;i<39;++i) {assert(step(&s,&f));assert(!s.reservoir_bypass);}
        assert(step(&s,&f));assert(s.bypass_ms==300);assert(s.reservoir_bypass);
        assert(s.age_ms==200);assert(any_lit(&f));
        assert(!app_step(&s,(hal_events_t){.low_event=true,.elapsed_frames=1},&f));
        assert(s.power.duty_sixteenths==(mode?1:2));
        assert(!step(&s,&f)); /* exclude the interval after the warning */
        for(unsigned i=0;i<19;++i) assert(!step(&s,&f));
        assert(step(&s,&f));assert(s.age_ms==0);assert(f.on_us[0]==0);
        assert(!app_step(&s,(hal_events_t){.elapsed_frames=2},&f));assert(s.power.phase==POWER_DARK);
        assert(s.reservoir_bypass); /* a timing fault leaves the reservoir connected */
    }
    app_state_t s;scan_frame_t f;app_init(&s,true);
    for(unsigned i=0;i<20;++i) step(&s,&f);
    for(unsigned t=5;t<=17000;t+=5) {
        assert(step(&s,&f));check_lit_slots(&f);unsigned age=t%17000;
        for(unsigned k=0;k<20;++k) {
            bool lit=age<15000 && age%750<500 && k==age/750;
            if(age>=200) assert((led_us(&f,k)>0)==lit);
        }
    }
    assert(s.age_ms==0);assert(f.on_us[0]==31);
    app_init(&s,false);for(unsigned i=0;i<20;++i) step(&s,&f);
    for(unsigned i=0;i<30000;++i) {
        step(&s,&f);check_lit_slots(&f);
        if(i>160) {
            uint8_t brightness[BOARD_LED_COUNT];scan_frame_t want;
            animation_render(s.age_ms,brightness);
            scan_prepare(brightness,BOARD_NORMAL_DUTY_SIXTEENTHS,255,&want);
            assert(memcmp(f.on_us,want.on_us,sizeof want.on_us)==0);
#if BOARD_SHARED_SLOTS
            for(unsigned s=0;s<20;++s) if(f.on_us[s]) assert(f.led[s]==want.led[s]);
#endif
            for(unsigned k=0;k<20;++k) assert(f.on_us[k]<=62);
        }
    }
    assert(s.age_ms>=800 && s.age_ms<10400);
    puts("app: qualification, reservoir bypass, recovery, diagnostic timing, backlog and long-run tests passed");
}
/* app_run's hardware calls are linked to the real HAL test backend. */
