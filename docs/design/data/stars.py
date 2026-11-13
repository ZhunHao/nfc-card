import json
from astroquery.simbad import Simbad
S=Simbad(); S.add_votable_fields("V")
sets={
 "sco":["bet1 Sco","nu Sco","del Sco","pi Sco","rho Sco","sig Sco","alf Sco","tau Sco","eps Sco","mu1 Sco","zet2 Sco","eta Sco","tet Sco","iot1 Sco","kap Sco","lam Sco","ups Sco","M4","ome1 Sco","G Sco"],
 "cru":["alf Cru","bet Cru","gam Cru","del Cru","eps Cru","alf Cen","bet Cen","gam Cen","eps Cen","zet Cen","del Cen","alf Mus","bet Mus","NGC 4755","lam Cen","rho Cen","mu Cen","eta Cen","tet Cen","gam Mus"],
 "sgr":["gam2 Sgr","del Sgr","eps Sgr","lam Sgr","phi Sgr","sig Sgr","zet Sgr","tau Sgr","mu Sgr","eta Sgr","xi2 Sgr","omi Sgr","pi Sgr","M8","M20","M22","M17","M28","M25"],
}
out={}
for k,names in sets.items():
    r=S.query_objects(names)
    cols=r.colnames
    out[k]=[{"id":n,"main":str(row["main_id"]),"ra":float(row["ra"]),"dec":float(row["dec"]),"V":(None if hasattr(row["V"],"mask") and row["V"] is None else (float(row["V"]) if str(row["V"])!="--" else None))} for n,row in zip(names,r)]
# Pleiades: brightest members by region
r=Simbad.query_tap("SELECT b.main_id, b.ra, b.dec, f.flux AS vmag FROM basic AS b JOIN flux AS f ON f.oidref=b.oid WHERE f.filter='V' AND f.flux<7.6 AND CONTAINS(POINT('ICRS',b.ra,b.dec),CIRCLE('ICRS',56.75,24.12,1.25))=1 ORDER BY vmag")
out["pleiades"]=[{"id":str(x["main_id"]),"main":str(x["main_id"]),"ra":float(x["ra"]),"dec":float(x["dec"]),"V":float(x["vmag"])} for x in r]
json.dump(out,open("stars.json","w"),indent=1)
for k,v in out.items():
    print(k,len(v))
    for s in v: print("  ",s["id"],"|",s["main"],round(s["ra"],3),round(s["dec"],3),s["V"])
