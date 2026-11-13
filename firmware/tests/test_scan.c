#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "scan.h"
#if BOARD_SHARED_SLOTS
/* Pulse requested for LED k: one width in every slot it owns, else 0. */
static unsigned width_of(const scan_frame_t *f,unsigned k,unsigned *slots) {
    unsigned w=0;*slots=0;
    for(unsigned s=0;s<20;++s) {
        if(f->on_us[s]) assert(f->led[s]<20);
        if(f->on_us[s] && f->led[s]==k) {
            if(*slots) assert(f->on_us[s]==w);
            w=f->on_us[s];++*slots;
        }
    }
    return w;
}
/* Shared-slot layout: lit LEDs (>= 10 us) share BOARD_SHARED_SLOTS slots evenly
 * (one each if there are more of them), at even spacing from slot 0. */
static void check_layout(const uint8_t b[20],unsigned d,unsigned r,const scan_frame_t *f) {
    unsigned lit=0,owned[20];
    for(unsigned k=0;k<20;++k) {
        unsigned exact=(250UL*d*b[k]*r)/(16UL*255*255),slots,w=width_of(f,k,&slots);
        owned[k]=slots;
        if(slots) {assert(w>=BOARD_MIN_PULSE_US);assert(w<=exact);assert(exact-w<=1);++lit;}
        else assert(exact<BOARD_MIN_PULSE_US+1);
    }
    unsigned n=lit==0?0:lit>=BOARD_SHARED_SLOTS?1:BOARD_SHARED_SLOTS/lit,total=n*lit,used=0;
    for(unsigned k=0;k<20;++k) assert(owned[k]==0 || owned[k]==n);
    for(unsigned s=0;s<20;++s) if(f->on_us[s]) {
        assert(s%(20/total)==0 && s/(20/total)<total);++used;
    }
    assert(used==total);
}
#endif
int main(void) {
    uint8_t b[20]; scan_frame_t f;
    for (unsigned d=0; d<256; ++d) {
        memset(b,255,sizeof b); scan_prepare(b,d,255,&f);
        assert(f.on_us[0] == (d==4?62:d==2?31:d==1?15:0));
    }
#if BOARD_SHARED_SLOTS
    /* One lit LED takes every shared slot; two split them. */
    memset(b,0,sizeof b);b[7]=255;scan_prepare(b,4,255,&f);
    for(unsigned s=0;s<20;++s) assert(f.on_us[s]==(s%(20/BOARD_SHARED_SLOTS)==0 && s<20/BOARD_SHARED_SLOTS*BOARD_SHARED_SLOTS?62:0));
    for(unsigned s=0;s<20;++s) if(f.on_us[s]) assert(f.led[s]==7);
    b[12]=128;scan_prepare(b,4,255,&f);check_layout(b,4,255,&f);
    /* Below the ISR's 10 us minimum an LED gets no slot at all. */
    memset(b,0,sizeof b);b[3]=40;scan_prepare(b,4,255,&f);
    for(unsigned s=0;s<20;++s) assert(f.on_us[s]==0);
    /* Every lit count 0..20, in scattered positions, both scaler paths. */
    for(unsigned count=0;count<=20;++count) for(unsigned r=128;r<=255;r+=127) {
        memset(b,0,sizeof b);
        for(unsigned j=0;j<count;++j) b[(j*7+3)%20]=200;
        scan_prepare(b,4,r,&f);check_layout(b,4,r,&f);
    }
#endif
    for (unsigned d=1;d<=4;d*=2) for(unsigned r=0;r<256;++r)
        for(unsigned v=0;v<256;++v) {
            for(unsigned i=0;i<20;++i) b[i]=(v+i*37)%256;
            scan_prepare(b,d,r,&f);
#if BOARD_SHARED_SLOTS
            check_layout(b,d,r,&f);
#else
            for(unsigned i=0;i<20;++i) {
                unsigned cap=(250UL*d*b[i]*r)/(16UL*255*255);
                assert(f.on_us[i]<=cap); assert(cap-f.on_us[i]<=1);
            }
#endif
        }
    uint32_t seed=0x1616u;
    for(unsigned trial=0;trial<4096;++trial) {
        for(unsigned i=0;i<20;++i) {seed=seed*1664525u+1013904223u;b[i]=seed>>24;}
        uint8_t duty=(uint8_t)(1u<<(trial%3)),ramp=(uint8_t)trial;
        scan_prepare(b,duty,ramp,&f);
#if BOARD_SHARED_SLOTS
        check_layout(b,duty,ramp,&f);
#else
        for(unsigned i=0;i<20;++i)
            assert(f.on_us[i]<=(250UL*duty*b[i]*ramp)/(16UL*255*255));
#endif
    }
    puts("scan: exhaustive bounds passed");
}
