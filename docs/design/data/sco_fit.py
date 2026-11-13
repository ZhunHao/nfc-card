# Search rotations of the (true-shape) Scorpius projection for the largest LED layout on the card.
import json, math
exec(open("layout.py").read().split("L={}")[0])
by={s["id"]:s for s in D["sco"]}
leds=["bet1 Sco","del Sco","pi Sco","rho Sco","sig Sco","alf Sco","tau Sco","eps Sco","mu1 Sco","zet2 Sco","eta Sco","tet Sco","iot1 Sco","kap Sco","lam Sco","G Sco"]
dots=["nu Sco","ups Sco","M4"]
ids=leds+dots; st=[by[i] for i in ids]
ra0=sum(s["ra"] for s in st)/len(st); dec0=sum(s["dec"] for s in st)/len(st)
P=[gnom(s["ra"],s["dec"],ra0,dec0) for s in st]; base=[(-x,-y) for x,y in P]   # east left, north up
NAME=(8.5,8.0,31,21.5)
MCUS={"BL":[8.5,33.6],"BR":[57,33.6],"TR":[57,8.3]}
def inside(p,r,pad): return r[0]-pad<p[0]<r[2]+pad and r[1]-pad<p[1]<r[3]+pad
best=None
import sys
ANGLES=[int(sys.argv[1])] if len(sys.argv)>1 else range(-180,180,2)  # pass 0 for north-up
for a in ANGLES:
  t=math.radians(a); R=[(x*math.cos(t)-y*math.sin(t),x*math.sin(t)+y*math.cos(t)) for x,y in base]
  xs=[p[0] for p in R]; ys=[p[1] for p in R]
  for mk,m in MCUS.items():
    mr=(m[0],m[1],m[0]+21,m[1]+13.2)
    for k in range(100,40,-2):
      s=min(69/(max(xs)-min(xs)),37.3/(max(ys)-min(ys)))*k/100
      for ox in [8.6+i*0.5 for i in range(0,int(70-(max(xs)-min(xs))*s)*2+1)]:
        for oy in [8.5+j*0.5 for j in range(0,int(38-(max(ys)-min(ys))*s)*2+1)]:
          pts=[(ox+(x-min(xs))*s,oy+(y-min(ys))*s) for x,y in R]
          if any(inside(p,NAME,1.5) or inside(p,mr,1.4) for p in pts): continue
          if pts and all(clash_ok for clash_ok in [not clash(pts[:len(leds)])]):
            if best is None or s>best[0]: best=(s,a,mk,pts)
          break_ok=True
        else: continue
      if best and best[0]>=s: break
print("scale",round(best[0],2),"rot",best[1],"mcu",best[2])
s,a,mk,pts=best
labels={"alf Sco":"ANTARES"}
out={"leds":[{"x":round(x,2),"y":round(y,2),"id":ids[i],"V":st[i]["V"],"label":labels.get(ids[i])} for i,(x,y) in enumerate(pts[:len(leds)])],
     "dots":[{"x":round(x,2),"y":round(y,2),"id":ids[len(leds)+i],"V":st[len(leds)+i]["V"],"label":None} for i,(x,y) in enumerate(pts[len(leds):])],
     "lines":[[ids.index(p),ids.index(q)] for p,q in [("nu Sco","bet1 Sco"),("bet1 Sco","del Sco"),("del Sco","pi Sco"),("pi Sco","rho Sco"),("del Sco","sig Sco"),("sig Sco","alf Sco"),("alf Sco","tau Sco"),("tau Sco","eps Sco"),("eps Sco","mu1 Sco"),("mu1 Sco","zet2 Sco"),("zet2 Sco","eta Sco"),("eta Sco","tet Sco"),("tet Sco","iot1 Sco"),("iot1 Sco","kap Sco"),("kap Sco","lam Sco"),("lam Sco","ups Sco")]],
     "mcu":MCUS[mk],"scale":round(s,3),"rot":a}
d=json.load(open("data.json")); d["sco"]=out; json.dump(d,open("data.json","w"),separators=(",",":"))
