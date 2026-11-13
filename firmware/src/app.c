#include "app.h"
#include "animation.h"
void app_init(app_state_t *s,bool diagnostic) {
    s->diagnostic=diagnostic;s->age_ms=s->bypass_ms=0;s->partial_healthy_frame=false;s->reservoir_bypass=false;
    power_init(&s->power,diagnostic?BOARD_DIAGNOSTIC_DUTY_SIXTEENTHS:BOARD_NORMAL_DUTY_SIXTEENTHS);
}
bool app_step(app_state_t *s,hal_events_t e,scan_frame_t *frame) {
    /* Process warnings before elapsed time; never credit a warning interval
     * toward recovery, nor attempt unbounded catch-up after missed frames. */
    uint16_t delta=e.elapsed_frames==1?BOARD_FRAME_MS:0;
    /* Warning/recovery edges may occur anywhere inside a frame. Exclude the
     * first subsequent healthy boundary, then count only complete intervals.
     * Keep the flag through zero-frame calls and repeated low observations. */
    if(e.voltage_low || e.low_event) s->partial_healthy_frame=true;
    else if(delta && s->partial_healthy_frame) {
        delta=0;s->partial_healthy_frame=false;
    }
    bool restart=power_step(&s->power,e.voltage_low,e.low_event,delta);
    if(e.timing_fault || e.elapsed_frames>1) power_timing_fault(&s->power);
    if(!s->reservoir_bypass) {
        if(e.voltage_low || e.low_event) s->bypass_ms=0;
        else if((s->bypass_ms+=delta)>=BOARD_BYPASS_QUALIFY_MS) s->reservoir_bypass=true;
    }
    if(restart) s->age_ms=0;
    else if(power_enabled(&s->power)) {
        s->age_ms+=delta;
        if(s->diagnostic) {if(s->age_ms>=17000) s->age_ms-=17000;}
        else if(s->age_ms>=10400) s->age_ms-=4800;
    }
    uint8_t brightness[BOARD_LED_COUNT];
    bool permit=power_enabled(&s->power);
    if(!permit) {
        for(uint8_t i=0;i<BOARD_LED_COUNT;++i) frame->on_us[i]=0;
        return false;
    }
    if(s->diagnostic) for(uint8_t i=0;i<BOARD_LED_COUNT;++i) brightness[i]=0;
    {
        if(!s->diagnostic) animation_render(s->age_ms,brightness);
        else if(s->age_ms<15000) {
            uint8_t led=s->age_ms/750;
            if(s->age_ms-(uint16_t)led*750<500) brightness[led]=255;
        }
    }
    scan_prepare(brightness,s->power.duty_sixteenths,power_ramp(&s->power),frame);
    return permit;
}
void app_run(bool diagnostic) {
    app_state_t state;scan_frame_t frame;bool bypassed=false;
    if(!diagnostic) hal_boot_flash();
    app_init(&state,diagnostic);hal_init();
    for(;;) {
        hal_events_t e=hal_take_events();
        if(e.elapsed_frames || e.low_event || e.timing_fault) {
            bool permit=app_step(&state,e,&frame);
            (void)hal_publish(&frame,permit);
            if(state.reservoir_bypass && !bypassed) {hal_bypass_reservoir();bypassed=true;}
        }
        hal_sleep();
    }
}
