#!/usr/bin/env python3
"""Execute the emitted slot ISR's instruction subset, not a source imitation.
This is an instruction/cycle audit, not an analog/peripheral hardware simulator.
Reject unknown instructions so compiler/linker changes require explicit review.
"""
import argparse
import hashlib
import re
import subprocess

class Image:
    def __init__(self, elf, objdump, nm):
        self.ins = {}
        for line in subprocess.check_output([objdump, '-d', '-z', elf], text=True).splitlines():
            m = re.match(r'\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s*([a-z]+)\s*(.*)', line)
            if m:
                self.ins[int(m[1], 16)] = (len(m[2].split()), m[3], m[4])
        self.symbols = {}
        for line in subprocess.check_output([nm, '-n', elf], text=True).splitlines():
            parts = line.split()
            if len(parts) == 3:
                self.symbols[parts[2]] = int(parts[0], 16) & 0xffff

def levels_base(image):
    # Shared slots keep levels at hal_masks+20; fixed slots have hal_levels.
    return image.symbols.get('hal_levels',image.symbols['hal_masks']+20)

class Machine:
    def __init__(self, image, slot, duration, *, memory_cycles=3, latency=11,
                 flags=None, low=False, edge=False, warning_at=None, origin=10000, stop_after_restore=False,
                 leds=None):
        self.image=image; self.mem={}; self.r=[(i*7+13)&255 for i in range(32)];self.r[1]=0
        self.original=self.r[:];self.c=False;self.z=False;self.stack=[]
        self.cycles=latency;self.origin=origin;self.memory_cycles=memory_cycles
        self.stop_after_restore=stop_after_restore;self.restore_cycle=0;self.following_cycles=0
        self.pc=image.symbols['__vector_10'];self.dir=0xc1;self.out=0x81;self.trace=[]
        self.low=low;self.edge=edge;self.warning_at=warning_at;self.timer_high=0
        self.put('hal_slot', slot);self.put('hal_flags', flags if flags is not None else (3 if slot==0 else 1))
        self.put('hal_active',0);self.put('hal_elapsed_frames',0)
        self.put('hal_anchor', origin&255);self.mem[image.symbols['hal_anchor']+1]=origin>>8
        pairs=[(1,2),(1,3),(1,4),(1,5),(2,1),(2,3),(2,4),(2,5),
               (3,1),(3,2),(3,4),(3,5),(4,1),(4,2),(4,3),(4,5),(5,1),(5,2),(5,3),(5,4)]
        levels=levels_base(image)
        for i,(a,b) in enumerate(pairs):
            self.mem[image.symbols['hal_masks']+i]=(1<<a)|(1<<b)
            self.mem[levels+i]=1<<a
        for i in range(40):self.mem[image.symbols['hal_frames']+i]=duration
        # Shared slots: per-slot LED indices follow at +40 (both buffers); default identity.
        self.shared=image.symbols.get('scan_shared_slots',0)
        if self.shared:
            leds=leds or list(range(20))
            for i in range(40):self.mem[image.symbols['hal_frames']+40+i]=leds[i%20]
        self.leds=leds or list(range(20))
    def put(self,name,value):self.mem[self.image.symbols[name]]=value
    def get(self,name):return self.mem.get(self.image.symbols[name],0)
    def read(self,address,cost=0):
        if address==0xa20:
            ticks=(self.origin+self.cycles+cost-1)&65535;self.timer_high=ticks>>8
            return ticks&255
        if address==0xa21:return self.timer_high
        if address==0x8b:return int(self.low or (self.warning_at is not None and self.cycles>=self.warning_at))
        if address==0x8a:return int(self.edge)
        return self.mem.get(address,0)
    def write(self,address,value,cost):
        if address==0x402:self.dir&=~value;self.trace.append(('blank',self.cycles+cost,self.dir,self.out))
        elif address==0x406:
            assert not self.dir&0x3e,'levels changed before blank';self.out&=~value
        elif address==0x405:
            assert not self.dir&0x3e,'levels changed before blank';self.out|=value
        else:self.mem[address]=value
    def run(self):
        for _ in range(2000):
            stop_next=bool(self.restore_cycle)
            size,op,raw=self.image.ins[self.pc];args=raw.split(';')[0].strip().split(', ')
            nxt=self.pc+size;cost=1
            def reg(s):return int(s[1:])
            def val(s):return int(s,0)
            def target():return int(re.search(r'; 0x([0-9a-f]+)',raw)[1],16)
            if op=='push':self.stack.append(self.r[reg(args[0])])
            elif op=='pop':self.r[reg(args[0])]=self.stack.pop();cost=2
            elif op=='in':
                a=val(args[1]);self.r[reg(args[0])]=self.dir if a==0 else (int(self.c)|(int(self.z)<<1)) if a==0x3f else self.mem.get(a,0)
            elif op=='out':
                a=val(args[0]);v=self.r[reg(args[1])]
                if a==0:
                    self.dir=v;self.trace.append(('dir',self.cycles+1,self.dir,self.out))
                    assert (v&0xc1)==0xc1,'unrelated GPIO changed'
                    if v&0x3e:
                        assert bin(v&0x3e).count("1")==2
                        assert bin(self.out&v&0x3e).count("1")==1
                elif a==0x3f:
                    self.c=bool(v&1);self.z=bool(v&2)
                    if self.stop_after_restore:self.restore_cycle=self.cycles+1
                else:self.mem[a]=v
            elif op in ('nop','cli'):pass
            elif op in ('sbi','cbi'):
                a=val(args[0]);bit=1<<val(args[1])
                self.mem[a]=(self.mem.get(a,0)|bit) if op=='sbi' else (self.mem.get(a,0)&~bit)
            elif op=='ret' and self.stop_after_restore:cost=4
            elif op=='ldi':self.r[reg(args[0])]=val(args[1])
            elif op=='lds':cost=self.memory_cycles;self.r[reg(args[0])]=self.read(val(args[1]),cost)
            elif op=='sts':cost=2;self.write(val(args[0]),self.r[reg(args[1])],cost)
            elif op=='ld':
                assert args[1]=='Z';cost=2;self.r[reg(args[0])]=self.read(self.r[30]|self.r[31]<<8)
            elif op=='ldd':
                base,q=args[1].split('+');assert base=='Z';cost=2
                self.r[reg(args[0])]=self.read((self.r[30]|self.r[31]<<8)+int(q))
            elif op=='mov':self.r[reg(args[0])]=self.r[reg(args[1])]
            elif op in ('andi','ori','or','eor','and'):
                d=reg(args[0]);a=self.r[d];b=val(args[1]) if op in ('andi','ori') else self.r[reg(args[1])]
                v=a&b if op in ('andi','and') else a^b if op=='eor' else a|b
                self.r[d]=v;self.z=v==0
            elif op in ('sub','sbc','subi','sbci','cp','cpc','cpi','add'):
                d=reg(args[0]);a=self.r[d];b=val(args[1]) if op in ('subi','sbci','cpi') else self.r[reg(args[1])]
                carry=int(self.c) if op in ('sbc','sbci','cpc') else 0
                v=a+b if op=='add' else a-b-carry
                self.c=v>255 if op=='add' else v<0
                zero=(v&255)==0;self.z=zero and self.z if op in ('sbc','sbci','cpc') else zero
                if op not in ('cp','cpc','cpi'):self.r[d]=v&255
            elif op=='inc':
                d=reg(args[0]);self.r[d]=(self.r[d]+1)&255;self.z=self.r[d]==0
            elif op=='cpse':
                if self.r[reg(args[0])]==self.r[reg(args[1])]:
                    skipped=self.image.ins[nxt][0];cost=1+skipped//2;nxt+=skipped
            elif op in ('sbrs','sbrc'):
                bit=bool(self.r[reg(args[0])]&(1<<val(args[1])))
                if bit==(op=='sbrs'):
                    skipped=self.image.ins[nxt][0];cost=1+skipped//2;nxt+=skipped
            elif op in ('brcs','brcc','breq','brne'):
                take={'brcs':self.c,'brcc':not self.c,'breq':self.z,'brne':not self.z}[op]
                if take:nxt=target();cost=2
            elif op=='rjmp':nxt=target();cost=2
            elif op=='reti':
                self.cycles+=4
                assert self.r==self.original,'interrupted register ABI corrupted'
                assert not self.stack
                return self
            else:raise AssertionError(f'unsupported opcode {op} at {self.pc:x}')
            self.cycles+=cost;self.pc=nxt
            if stop_next:
                self.following_cycles=cost
                return self
        raise AssertionError('unbounded ISR')
    def pulses(self):
        result=[];start=None
        for _,t,d,_ in self.trace:
            if d&0x3e:start=t
            elif start is not None:result.append(t-start);start=None
        assert start is None,'ISR returned lit'
        return result

class Call:
    """Execute emitted main-loop code and count cycles. Same conservative AVRxt
    model as Machine (LDS=3, LD/LDD=2, POP=2, RET=4), plus ST/STD charged 2
    (AVRxt: 1), CALL 3, RCALL 2, MUL/ADIW/SBIW 2, and an extra cycle for every
    LD from memory-mapped flash (>= 0x8000). Only C, Z and T are modelled; a
    branch needing N/V/S/H is rejected, as is any unknown opcode."""
    SP=0x3fff;SENTINEL=0x7fff  # word address returned to by the outermost RET
    def __init__(self,image,flash):
        self.image=image;self.mem=dict(flash);self.mem[0x3d]=self.SP&255;self.mem[0x3e]=self.SP>>8
        self.r=[0]*32;self.c=self.z=self.t=False;self.cycles=0
    def sp(self):return self.mem[0x3d]|self.mem[0x3e]<<8
    def push(self,v):
        a=self.sp();self.mem[a]=v&255;a-=1;self.mem[0x3d]=a&255;self.mem[0x3e]=a>>8
    def pop(self):
        a=self.sp()+1;self.mem[0x3d]=a&255;self.mem[0x3e]=a>>8;return self.mem.get(a,0)
    def push_return(self,byte_address):
        w=byte_address//2;self.push(w);self.push(w>>8)
    def pop_return(self):
        hi=self.pop();lo=self.pop();return (hi<<8|lo)*2
    def call(self,name,regs):
        """Run one function from entry to its RET; checks callee-saved registers."""
        self.r=[0]*32
        for k,v in regs.items():self.r[k]=v
        self.c=self.z=self.t=False;self.cycles=0;self.mem[0x3d]=self.SP&255;self.mem[0x3e]=self.SP>>8
        self.push_return(self.SENTINEL*2)
        saved=self.r[2:18]+self.r[28:30];pc=self.image.symbols[name]
        for _ in range(200000):
            pc=self.exec_one(pc)
            if pc is None:
                assert self.r[2:18]+self.r[28:30]==saved and self.r[1]==0,(name,'callee-saved registers corrupted')
                assert self.sp()==self.SP,(name,'stack not balanced')
                return self
        raise AssertionError(f'unbounded {name}')
    def exec_one(self,pc):
        """Execute the instruction at pc; return the next pc, or None on the outermost RET."""
        r=self.r
        def pair(i):return r[i]|r[i+1]<<8
        def setpair(i,v):r[i]=v&255;r[i+1]=(v>>8)&255
        def ld(a):
            self.cycles+=2+(a>=0x8000);return self.mem.get(a,0)
        size,op,raw=self.image.ins[pc];args=raw.split(';')[0].strip().split(', ');nxt=pc+size;cost=1
        def reg(s):return int(s[1:])
        def val(s):return int(s,0)
        def target():return int(re.search(r'; 0x([0-9a-f]+)',raw)[1],16)
        def ptr(s):return {'X':26,'Y':28,'Z':30}[s.strip('-+')]
        if op=='push':self.push(r[reg(args[0])])
        elif op=='pop':r[reg(args[0])]=self.pop();cost=2
        elif op=='in':
            a=val(args[1]);r[reg(args[0])]=(int(self.c)|int(self.z)<<1) if a==0x3f else self.mem.get(a,0)
        elif op=='out':
            a=val(args[0]);v=r[reg(args[1])]
            if a==0x3f:self.c=bool(v&1);self.z=bool(v&2)
            else:self.mem[a]=v
        elif op in ('nop','cli','sei'):pass
        elif op=='ldi':r[reg(args[0])]=val(args[1])
        elif op=='mov':r[reg(args[0])]=r[reg(args[1])]
        elif op=='movw':
            d,s_=reg(args[0]),reg(args[1]);r[d]=r[s_];r[d+1]=r[s_+1]
        elif op in ('add','adc','sub','sbc','subi','sbci','cp','cpc','cpi'):
            d=reg(args[0]);a=r[d];b=val(args[1]) if op in ('subi','sbci','cpi') else r[reg(args[1])]
            carry=int(self.c) if op in ('adc','sbc','sbci','cpc') else 0
            v=a+b+carry if op in ('add','adc') else a-b-carry
            self.c=v>255 if op in ('add','adc') else v<0
            zero=(v&255)==0;self.z=zero and self.z if op in ('sbc','sbci','cpc') else zero
            if op not in ('cp','cpc','cpi'):r[d]=v&255
        elif op in ('and','andi','or','ori','eor'):
            d=reg(args[0]);a=r[d];b=val(args[1]) if op in ('andi','ori') else r[reg(args[1])]
            v=a&b if op in ('and','andi') else a|b if op in ('or','ori') else a^b;r[d]=v;self.z=v==0
        elif op in ('inc','dec'):
            d=reg(args[0]);r[d]=(r[d]+(1 if op=='inc' else -1))&255;self.z=r[d]==0
        elif op in ('lsr','ror','rol','lsl','swap','com'):
            d=reg(args[0]);a=r[d]
            if op=='lsr':self.c=bool(a&1);v=a>>1
            elif op=='ror':v=(a>>1)|(int(self.c)<<7);self.c=bool(a&1)
            elif op in ('rol','lsl'):v=((a<<1)|(int(self.c) if op=='rol' else 0))&255;self.c=bool(a&128)
            elif op=='swap':v=((a<<4)|(a>>4))&255
            else:v=a^255;self.c=True
            r[d]=v
            if op!='swap':self.z=v==0
        elif op=='mul':
            v=r[reg(args[0])]*r[reg(args[1])];r[0]=v&255;r[1]=v>>8;self.c=bool(v&0x8000);self.z=v==0;cost=2
        elif op=='neg':
            d=reg(args[0]);v=(-r[d])&255;self.c=v!=0;self.z=v==0;r[d]=v
        elif op=='bst':self.t=bool(r[reg(args[0])]&(1<<val(args[1])))
        elif op=='bld':
            d=reg(args[0]);bit=1<<val(args[1]);r[d]=(r[d]|bit) if self.t else (r[d]&~bit)
        elif op in ('adiw','sbiw'):
            d=reg(args[0]);a=pair(d);v=a+val(args[1]) if op=='adiw' else a-val(args[1])
            self.c=v>65535 if op=='adiw' else v<0;setpair(d,v);self.z=(v&65535)==0;cost=2
        elif op in ('ld','st'):
            rr,p=(args[0],args[1]) if op=='ld' else (args[1],args[0]);b=ptr(p);a=pair(b)
            if p.startswith('-'):a=(a-1)&65535;setpair(b,a)
            if op=='ld':r[reg(rr)]=ld(a);cost=0
            else:self.mem[a]=r[reg(rr)];cost=2
            if p.endswith('+'):setpair(b,a+1)
        elif op in ('ldd','std'):
            rr,p=(args[0],args[1]) if op=='ldd' else (args[1],args[0]);base,q=p.split('+');a=pair(ptr(base))+int(q)
            if op=='ldd':r[reg(rr)]=ld(a);cost=0
            else:self.mem[a]=r[reg(rr)];cost=2
        elif op=='lds':r[reg(args[0])]=self.mem.get(val(args[1]),0);cost=3
        elif op=='sts':self.mem[val(args[0])]=r[reg(args[1])];cost=2
        elif op in ('sbi','cbi'):
            a=val(args[0]);bit=1<<val(args[1]);self.mem[a]=(self.mem.get(a,0)|bit) if op=='sbi' else (self.mem.get(a,0)&~bit)
        elif op in ('brne','breq','brcs','brcc','brlo','brsh','brts','brtc'):
            take={'brne':not self.z,'breq':self.z,'brcs':self.c,'brlo':self.c,'brcc':not self.c,'brsh':not self.c,
                  'brts':self.t,'brtc':not self.t}[op]
            if take:nxt=target();cost=2
        elif op in ('cpse','sbrc','sbrs','sbic','sbis'):
            if op=='cpse':skip=r[reg(args[0])]==r[reg(args[1])]
            elif op in ('sbrc','sbrs'):skip=bool(r[reg(args[0])]&(1<<val(args[1])))==(op=='sbrs')
            else:skip=bool(self.mem.get(val(args[0]),0)&(1<<val(args[1])))==(op=='sbis')
            if skip:skipped=self.image.ins[nxt][0];cost=1+skipped//2;nxt+=skipped
        elif op=='rjmp':nxt=target();cost=2
        elif op=='jmp':nxt=val(args[0]);cost=3
        elif op in ('rcall','call'):
            self.push_return(nxt);nxt=target() if op=='rcall' else val(args[0]);cost=2 if op=='rcall' else 3
        elif op=='ret':
            self.cycles+=4;a=self.pop_return()
            return None if a==self.SENTINEL*2 else a
        else:raise AssertionError(f'unsupported opcode {op} at {pc:x}')
        self.cycles+=cost
        return nxt

class MainLoop(Call):
    """Run the image from main() through app_run frame by frame. hal_init is
    skipped (one-time; it reads fuses this model doesn't have) and its RAM state
    set directly. hal_boot_flash is skipped too: it is a one-time busy-wait that
    finishes before hal_init starts the scan timer, so no frame contains it. Each SLEEP is a frame boundary: the slot-0 ISR's frame
    bookkeeping is applied (one elapsed frame, PENDING -> ENABLED with buffer
    swap, an unpublished ENABLED frame -> fault), and the cycles since the
    previous wake are that frame's main-loop cost."""
    def frames(self,count):
        s=self.image.symbols;active,elapsed,frames=s['hal_active'],s['hal_elapsed_frames'],s['hal_frames']
        self.mem[0x1e]=0;self.mem[0x1f]=0;self.mem[active]=0;self.mem[elapsed]=0
        out=[];wake=0;pc=s['main'];init={s['hal_init'],s.get('hal_boot_flash',s['hal_init'])}
        for _ in range(count*20000):
            if pc in init:
                pc=self.pop_return();continue
            size,op,_=self.image.ins[pc]
            if op!='sleep':
                pc=self.exec_one(pc);continue
            self.cycles+=1;flags=self.mem.get(0x1e,0)
            assert not flags&8,('main loop latched a fault at frame',len(out))
            self.mem[elapsed]=self.mem.get(elapsed,0)+1
            if flags&2:
                self.mem[active]^=20;self.mem[0x1e]=(flags&~2)|1
            elif flags&1:
                self.mem[0x1e]=8
            a=self.mem[active];enabled=self.mem[0x1e]&1
            shown=[self.mem.get(frames+a+i,0) if enabled else 0 for i in range(20)]
            out.append((self.cycles-wake,shown));wake=self.cycles;pc+=size
            if len(out)>count:return out[1:]
        raise AssertionError('main loop stalled')

def flash_data(elf,objdump):
    """Bytes of .rodata at their data-space (memory-mapped flash) addresses."""
    out={}
    for line in subprocess.check_output([objdump,'-s','-j','.rodata',elf],text=True).splitlines():
        m=re.match(r'\s([0-9a-f]{4,8}) ((?:[0-9a-f]{2,8} ){1,4})',line)
        if m:
            data=bytes.fromhex(m[2].replace(' ',''))
            for i,b in enumerate(data):out[(int(m[1],16)+i)&0xffff]=b
    return out

def frame_budget(image,flash,frames=3600):
    """Executed proof that every frame fits: run main() for 3600 frames (18 s:
    qualification, ramp, the whole animation and its age fold, the 17 s
    diagnostic cycle) and add the ISR load of the frame shown before and after
    each frame's main-loop work, whichever is larger. Covers healthy frames at
    the starting duty tier; lower tiers only shorten pulses."""
    cost={}
    def isr(on):
        total=0
        for slot,d in enumerate(on):
            if (slot,d) not in cost:cost[slot,d]=Machine(image,slot,d).run().cycles
            total+=cost[slot,d]
        return total
    run=MainLoop(image,flash).frames(frames);worst=(0,)
    for i,(main,on) in enumerate(run):
        load=max(isr(on),isr(run[i-1][1] if i else on))
        assert main+load<5000,(i,main,load,'frame overrun')
        worst=max(worst,(main+load,main,load,i,sum(d>9 for d in on)))
    print(f'frames: {len(run)} executed; worst main {worst[1]} + ISR {worst[2]} = {worst[0]}/5000 cycles '
          f'(frame {worst[3]}, {worst[4]} lit slots); most lit slots {max(sum(d>9 for d in on) for _,on in run)}')

def check(image,flash):
    # Exercise actual publication critical sections through the instruction
    # after SREG restore. This catches a deferred four-cycle RET, not source text.
    publish_start=image.symbols['hal_publish'];publish_end=image.symbols['hal_sleep']
    healthy_mask=0
    for pc,(_,opcode,_) in image.ins.items():
        if publish_start<=pc<publish_end and opcode=='cli':
            m=Machine(image,0,62,latency=0,flags=1,stop_after_restore=True)
            m.pc=pc;m.run()
            assert m.following_cycles==1, (hex(pc),m.following_cycles,'long instruction after IRQ restore')
            if m.get('hal_flags')&1:
                healthy_mask=max(healthy_mask,m.restore_cycle+m.following_cycles)
    assert healthy_mask>0
    # Charge 6 response cycles PLUS the vector JMP3 independently, even when
    # this overcounts part of the device's documented minimum response.
    delayed_entry=healthy_mask+9
    m=Machine(image,0,62,latency=delayed_entry).run()
    assert m.pulses() and m.cycles<=247, (healthy_mask,delayed_entry,m.cycles,'publication entry margin')
    print(f'publication: mask+following {healthy_mask}, conservative entry {delayed_entry}, return {m.cycles}/250')
    worst=0;by_duration={};frame_cost=0
    for memory_cycles in (2,3):
        for slot in range(20):
            for duration in range(63):
                m=Machine(image,slot,duration,memory_cycles=memory_cycles).run()
                assert not m.get('hal_flags')&8,(slot,duration,m.cycles,'unexpected fault')
                assert (m.mem[0xa28]|m.mem[0xa29]<<8)==(m.origin+250)&65535
                assert m.get('hal_slot')==(slot+1)%20
                assert m.get('hal_elapsed_frames')==(1 if slot==0 else 0)
                for _,_,direction,level in m.trace:
                    if direction&0x3e:
                        assert direction&0x3e==m.mem[image.symbols['hal_masks']+m.leds[slot]]
                        assert level&0x3e==m.mem[levels_base(image)+m.leds[slot]]
                assert all(t<=duration for t in m.pulses()),(duration,m.pulses())
                assert bool(m.pulses())==(duration>9)
                worst=max(worst,m.cycles)
                assert m.cycles<=250,(slot,duration,m.cycles,'slot overrun')
                if slot==0:by_duration[duration]=(m.cycles,m.pulses())
    if image.symbols.get('scan_shared_slots'):
        # Shared slots: the pins driven follow the frame's LED index, not the slot.
        for leds in ([(7*k+3)%20 for k in range(20)],[7]*20,[19-k for k in range(20)]):
            for memory_cycles in (2,3):
                for slot in range(20):
                    for duration in (0,9,10,31,62):
                        m=Machine(image,slot,duration,memory_cycles=memory_cycles,leds=leds).run()
                        assert not m.get('hal_flags')&8 and m.cycles<=250
                        assert bool(m.pulses())==(duration>9) and all(t<=duration for t in m.pulses())
                        for _,_,direction,level in m.trace:
                            if direction&0x3e:
                                assert direction&0x3e==m.mem[image.symbols['hal_masks']+leds[slot]]
                                assert level&0x3e==m.mem[levels_base(image)+leds[slot]]
        print('shared slots: pins follow the per-slot LED index for permuted, repeated and reversed maps')
    for slot in range(20):
        # Maximum allowed normal scene: three62, four46, one31; field peaks23.
        duration=[62,62,62,46,46,46,46,31,23,23]+[0]*10
        frame_cost+=Machine(image,slot,duration[slot]).run().cycles
    # Latest entry that still pulses must return before the next slot; one cycle
    # later the deadline check faults dark. Fixed slots: 28 -> 249 (timing.md).
    last=max(l for l in range(11,60) if Machine(image,0,62,latency=l).run().pulses())
    m=Machine(image,0,62,latency=last).run();assert m.cycles<250 and m.pulses()
    if not image.symbols.get('scan_shared_slots'):assert (last,m.cycles)==(28,249)
    m=Machine(image,0,62,latency=last+1).run();assert not m.pulses() and m.get("hal_flags")&8
    print(f'deadline: latest pulsing entry {last} returns at {Machine(image,0,62,latency=last).run().cycles}/250')
    for latency in range(11,60):
        m=Machine(image,0,62,latency=latency).run()
        if m.pulses():assert m.cycles<250
        else:assert m.get("hal_flags")&8
    for low,edge in ((True,False),(False,True),(True,True)):
        m=Machine(image,0,62,low=low,edge=edge).run();assert not m.pulses();assert m.get('hal_flags')&4
    # MUL/libgcc may temporarily hold a nonzero r1 when interrupted.
    for zero_register in (1,127,255):
        m=Machine(image,0,62);m.r[1]=zero_register;m.original=m.r[:];m.run()
        assert m.pulses() and not m.get("hal_flags")&8
        m=Machine(image,0,62,latency=170);m.r[1]=zero_register;m.original=m.r[:];m.run()
        assert not m.pulses() and m.get("hal_flags")&8
    for origin in (65500,65530,65535):
        m=Machine(image,0,62,origin=origin).run();assert m.pulses();assert not m.get('hal_flags')&8
    m=Machine(image,0,62);m.put("hal_elapsed_frames",255);m.run();assert m.get("hal_flags")&8;assert not m.pulses()
    m=Machine(image,0,62,flags=1).run();assert m.get('hal_flags')&8;assert not m.pulses()
    m=Machine(image,0,62,latency=170).run();assert m.get('hal_flags')&8;assert not m.pulses()
    for t in range(11,250):
        m=Machine(image,0,62,warning_at=t).run();assert all(p<=62 for p in m.pulses())
    phase_bounds={'ramp':([35]*3+[0]*17,2032),
                  'belt':([62]*3+[0]*17,1832),
                  'limbs':([62]*3+[46]*4+[0]*13,1832),
                  'm42':([62]*3+[46]*4+[31]+[0]*12,1832),
                  'twinkle':([62]*3+[46]*4+[31,23,23]+[0]*10,1502),
                  'diagnostic':([31]+[0]*19,1782)}
    # Includes 24 extra cycles for warning-interval accounting and 8 for the
    # per-frame reservoir-bypass check in app_run (timing.md).
    # Main allowances are independently counted conservative final-image bounds;
    # changes to application code require the documented main recount as well.
    for phase,(durations,main_bound) in phase_bounds.items():
        irq_bound=sum(Machine(image,k,d).run().cycles for k,d in enumerate(durations))
        assert irq_bound+main_bound<5000
        print(f'{phase}: ISR {irq_bound} + main {main_bound} = {irq_bound+main_bound}/5000 cycles')
    frame_budget(image,flash)
    print(f'AVR ISR: worst {worst} cycles including11 entry/wake; scene frame ISR bound {frame_cost}')
    print('slot0 requested -> (cycles, pulse):', {d:by_duration[d] for d in (0,10,15,31,62)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('elf');p.add_argument('--objdump',default='avr-objdump');p.add_argument('--nm',default='avr-nm')
    a=p.parse_args()
    print(a.elf, "SHA256", hashlib.sha256(open(a.elf,"rb").read()).hexdigest())
    check(Image(a.elf,a.objdump,a.nm),flash_data(a.elf,a.objdump))
