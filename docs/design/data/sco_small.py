# North-up Scorpius at a chosen scale, centred in the free area right of the name block.
# Fainter stars that collide with a brighter LED become printed dots. Usage: sco_small.py <mm_per_deg>
import json, sys, math
exec(open("layout.py").read().split("L={}")[0])
scale=float(sys.argv[1])
by={s["id"]:s for s in D["sco"]}
cand=["bet1 Sco","del Sco","pi Sco","rho Sco","sig Sco","alf Sco","tau Sco","eps Sco","mu1 Sco","zet2 Sco","eta Sco","tet Sco","iot1 Sco","kap Sco","lam Sco","G Sco"]
dots=["nu Sco","ups Sco","M4"]
ids=cand+dots; st=[by[i] for i in ids]
ra0=sum(s["ra"] for s in st)/len(st); dec0=sum(s["dec"] for s in st)/len(st)
P=[gnom(s["ra"],s["dec"],ra0,dec0) for s in st]; xs=[-p[0] for p in P]; ys=[-p[1] for p in P]
w=(max(xs)-min(xs))*scale; h=(max(ys)-min(ys))*scale
ox=54-w/2; oy=27-h/2        # centre of the area right of the name block
pts=[(ox+(x-min(xs))*scale, oy+(y-min(ys))*scale) for x,y in zip(xs,ys)]
pos=dict(zip(ids,pts)); leds=list(cand)
while True:   # demote the fainter star of each clashing pair
    bad=[(a,b) for i,a in enumerate(leds) for b in leds[i+1:] if abs(pos[a][0]-pos[b][0])<2.7 and abs(pos[a][1]-pos[b][1])<1.8]
    if not bad: break
    a,b=bad[0]; f=a if by[a]["V"]>by[b]["V"] else b; leds.remove(f); dots.append(f)
mcu=[8.5,33.6]
hits=[i for i in leds if mcu[0]-1.2<pos[i][0]<mcu[0]+22.2 and mcu[1]-1.2<pos[i][1]<mcu[1]+14.4]
print("figure",round(w,1),"x",round(h,1),"mm  LEDs",len(leds),"dots",dots,"mcu hits",hits,"edge",[i for i in leds if not(7.6<pos[i][0]<78 and 7.3<pos[i][1]<46.7)])
allids=leds+dots
lines=[("nu Sco","bet1 Sco"),("bet1 Sco","del Sco"),("del Sco","pi Sco"),("pi Sco","rho Sco"),("del Sco","sig Sco"),("sig Sco","alf Sco"),("alf Sco","tau Sco"),("tau Sco","eps Sco"),("eps Sco","mu1 Sco"),("mu1 Sco","zet2 Sco"),("zet2 Sco","eta Sco"),("eta Sco","tet Sco"),("tet Sco","iot1 Sco"),("iot1 Sco","kap Sco"),("kap Sco","lam Sco"),("lam Sco","ups Sco")]
E=lambda i:{"x":round(pos[i][0],2),"y":round(pos[i][1],2),"id":i,"V":by[i]["V"],"label":"ANTARES" if i=="alf Sco" else None}
out={"leds":[E(i) for i in leds],"dots":[E(i) for i in dots],"lines":[[allids.index(a),allids.index(b)] for a,b in lines],"mcu":mcu,"scale":scale,"rot":0}
d=json.load(open("data.json")); d["sco"]=out; json.dump(d,open("data.json","w"),separators=(",",":"))
