import json, math
D=json.load(open("stars.json"))
MCU_W,MCU_H=21,13.2
def gnom(ra,dec,ra0,dec0):
    r=math.radians; a,d,a0,d0=r(ra),r(dec),r(ra0),r(dec0)
    c=math.sin(d0)*math.sin(d)+math.cos(d0)*math.cos(d)*math.cos(a-a0)
    xi=math.cos(d)*math.sin(a-a0)/c; eta=(math.cos(d0)*math.sin(d)-math.sin(d0)*math.cos(d)*math.cos(a-a0))/c
    return math.degrees(xi),math.degrees(eta)
def fit(stars,box,pad=0):
    ra0=sum(s["ra"] for s in stars)/len(stars); dec0=sum(s["dec"] for s in stars)/len(stars)
    P=[gnom(s["ra"],s["dec"],ra0,dec0) for s in stars]
    xs=[-p[0] for p in P]; ys=[-p[1] for p in P]
    x0,y0,x1,y1=box; s=min((x1-x0)/(max(xs)-min(xs)),(y1-y0)/(max(ys)-min(ys)))
    ox=x0+((x1-x0)-(max(xs)-min(xs))*s)/2; oy=y0+((y1-y0)-(max(ys)-min(ys))*s)/2
    return [(ox+(x-min(xs))*s, oy+(y-min(ys))*s) for x,y in zip(xs,ys)], s
def clash(pts):
    bad=[]
    for i,(x,y) in enumerate(pts):
        if x<7.6 or x>78 or y<7.3 or y>46.7: bad.append(f"{i} edge")
        for j,(u,v) in enumerate(pts):
            if j>i and abs(x-u)<2.7 and abs(y-v)<1.8: bad.append(f"{i}/{j}")
    return bad
def mcu_hits(pts,m,pad=1.2): return [i for i,(x,y) in enumerate(pts) if m[0]-pad<x<m[0]+MCU_W+pad and m[1]-pad<y<m[1]+MCU_H+pad]
def pick(name,ids,box,mcu,lines,labels={},dots=()):
    by={s["id"]:s for s in D[name]}; allids=list(ids)+list(dots); st=[by[i] for i in allids]
    allpts,s=fit(st,box); n=len(ids); pts=allpts[:n]
    print(name,len(ids),"LEDs scale mm/deg",round(s,2),"clash",clash(pts),"mcu",mcu_hits(pts,mcu))
    P=lambda k,x,y:{"x":round(x,2),"y":round(y,2),"id":st[k]["id"],"V":st[k]["V"],"label":labels.get(st[k]["id"])}
    return {"leds":[P(k,x,y) for k,(x,y) in enumerate(pts)],"dots":[P(n+k,x,y) for k,(x,y) in enumerate(allpts[n:])],
            "lines":[[allids.index(a),allids.index(b)] for a,b in lines],"mcu":mcu,"scale":round(s,3)}
L={}
sco=["bet1 Sco","del Sco","pi Sco","rho Sco","sig Sco","alf Sco","tau Sco","eps Sco","mu1 Sco","zet2 Sco","eta Sco","tet Sco","iot1 Sco","kap Sco","lam Sco","G Sco"]
L["sco"]=pick("sco",sco,(30,8.3,76,45.8),[8.5,33.6],
 [("nu Sco","bet1 Sco"),("bet1 Sco","del Sco"),("del Sco","pi Sco"),("pi Sco","rho Sco"),("del Sco","sig Sco"),("sig Sco","alf Sco"),("alf Sco","tau Sco"),("tau Sco","eps Sco"),("eps Sco","mu1 Sco"),("mu1 Sco","zet2 Sco"),("zet2 Sco","eta Sco"),("eta Sco","tet Sco"),("tet Sco","iot1 Sco"),("iot1 Sco","kap Sco"),("kap Sco","lam Sco"),("lam Sco","ups Sco"),("nu Sco","bet1 Sco")],
 {"alf Sco":"ANTARES","lam Sco":"SHAULA","tet Sco":"SARGAS","bet1 Sco":"ACRAB","del Sco":"DSCHUBBA","M4":"M4"},dots=["nu Sco","ups Sco","M4"])
cru=["alf Cru","bet Cru","gam Cru","del Cru","eps Cru","alf Cen","bet Cen","lam Cen","alf Mus","gam Mus"]
L["cru"]=pick("cru",cru,(30,9,77,45),[8.5,33.6],
 [("alf Cru","gam Cru"),("bet Cru","del Cru"),("alf Cen","bet Cen"),("alf Mus","bet Mus"),("alf Mus","gam Mus")],
 {"alf Cru":"ACRUX","gam Cru":"GACRUX","alf Cen":"RIGIL KENT.","bet Cen":"HADAR","bet Cru":"MIMOSA","NGC 4755":"JEWEL BOX"},dots=["bet Mus","NGC 4755"])
sgr=["gam2 Sgr","del Sgr","eps Sgr","lam Sgr","phi Sgr","sig Sgr","zet Sgr","tau Sgr","mu Sgr","eta Sgr","xi2 Sgr","pi Sgr","M8","M20","M22","M17","M25"]
L["sgr"]=pick("sgr",sgr,(30,8.3,76,45.8),[8.5,33.6],
 [("gam2 Sgr","del Sgr"),("del Sgr","eps Sgr"),("eps Sgr","gam2 Sgr"),("del Sgr","lam Sgr"),("lam Sgr","phi Sgr"),("del Sgr","phi Sgr"),("phi Sgr","zet Sgr"),("zet Sgr","eps Sgr"),("phi Sgr","sig Sgr"),("sig Sgr","tau Sgr"),("tau Sgr","zet Sgr")],
 {"M8":"LAGOON","M20":"TRIFID","M22":"M22","M17":"OMEGA","sig Sgr":"NUNKI","eps Sgr":"KAUS AUS.","M25":"M25","M28":"M28"},dots=["M28"])
pl=D["pleiades"]
names={"* eta Tau":"ALCYONE","*  27 Tau":"ATLAS","*  17 Tau":"ELECTRA","*  20 Tau":"MAIA","*  23 Tau":"MEROPE","* q Tau":"TAYGETA","*  28 Tau":"PLEIONE","*  16 Tau":"CELAENO","*  21 Tau":"ASTEROPE"}
drop={"*  24 Tau","*  28 Tau","*  22 Tau"}
ids=[s["id"] for s in pl if s["V"]<7.0 and s["id"] not in drop][:20]
L["ple"]=pick("pleiades",ids,(24,8.3,78,45.8),[8.5,33.6],[],names,dots=["*  28 Tau","*  22 Tau","*  24 Tau"])
json.dump(L,open("layout.json","w"))
