import json, math, numpy as np
from skyfield.api import load, EarthSatellite, wgs84
ts=load.timescale()
l=open("iss.tle").read().splitlines()
sat=EarthSatellite(l[1],l[2],l[0].strip(),ts)
SG=(1.3521,103.8198); NTU=(1.3483,103.6831)
# C2: closest subpoint to Singapore in next 48 h
t0=ts.utc(2026,10,26); mins=np.arange(0,48*60,0.25); t=ts.utc(2026,10,26,0,mins)
sp=wgs84.subpoint_of(sat.at(t)); la,lo=sp.latitude.degrees,sp.longitude.degrees
d=np.hypot(la-SG[0],(lo-SG[1])*math.cos(math.radians(SG[0]))); k=int(np.argmin(d))
tc=mins[k]; print("closest to SG", t[k].utc_strftime(), round(float(d[k]),2),"deg")
period=1440/15.4903
tm=np.arange(tc-period/2,tc+period/2,0.2); tt=ts.utc(2026,10,26,0,tm)
s2=wgs84.subpoint_of(sat.at(tt))
c2={"t_sg":t[k].utc_strftime("%Y-%m-%d %H:%M UTC"),"miss_deg":round(float(d[k]),2),
    "track":[[round(float(a),2),round(float(b),2),round(float(m-tc),1)] for a,b,m in zip(s2.longitude.degrees,s2.latitude.degrees,tm)]}
# C4: passes over NTU, next 7 days, pick highest evening pass (18:30-22:00 SGT)
obs=wgs84.latlon(*NTU)
t1=ts.utc(2026,10,26); t2=ts.utc(2026,11,2)
times,ev=sat.find_events(obs,t1,t2,altitude_degrees=10)
passes=[];cur=None
for ti,e in zip(times,ev):
    if e==0: cur={"rise":ti}
    elif e==1 and cur: cur["culm"]=ti
    elif e==2 and cur and "culm" in cur: cur["set"]=ti; passes.append(cur); cur=None
best=None
for p in passes:
    alt=(sat-obs).at(p["culm"]).altaz()[0].degrees
    h=(p["culm"].utc.hour+8+p["culm"].utc.minute/60)%24
    tag=f'{p["culm"].utc_strftime()} SGT{h:.2f} maxalt {alt:.1f}'
    if 18.5<=h<=22 or 4.5<=h<=7: print(tag)
    if (18.5<=h<=22) and (best is None or alt>best[0]): best=(alt,p)
alt,p=best; print("chosen",p["culm"].utc_strftime(),round(alt,1))
n=int((p["set"]-p["rise"])*86400/10)+1
tt=ts.tt_jd(np.linspace(p["rise"].tt,p["set"].tt,n))
a,z,_=(sat-obs).at(tt).altaz()
c4={"rise_utc":p["rise"].utc_strftime("%Y-%m-%d %H:%M:%S"),"culm_utc":p["culm"].utc_strftime("%Y-%m-%d %H:%M:%S"),"set_utc":p["set"].utc_strftime("%Y-%m-%d %H:%M:%S"),
    "maxalt":round(float(alt),1),"path":[[round(float(x),2),round(float(y),2)] for x,y in zip(z.degrees,a.degrees)]}
json.dump({"c2":c2,"c4":c4},open("sat.json","w"))
print(c4["rise_utc"],c4["set_utc"],len(c4["path"]))
