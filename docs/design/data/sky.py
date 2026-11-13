import json, warnings
warnings.filterwarnings("ignore")
from astropy.utils import iers; iers.conf.auto_download=False
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
import astropy.units as u
from astroquery.simbad import Simbad
names=["Sirius","Canopus","Arcturus","Vega","Capella","Rigel","Procyon","Achernar","Betelgeuse","Altair","Aldebaran","Antares","Spica","Pollux","Fomalhaut","Deneb","Regulus","Mimosa","Acrux","Hadar","alf Cen","Peacock","alf Gru","Mirfak","Hamal","Diphda","Nunki","Kaus Australis","Enif","Alpheratz"]
S=Simbad(); S.add_votable_fields("V")
r=S.query_objects(names)
d=json.load(open("sat.json")); t=Time(d["c4"]["culm_utc"].replace(" ","T"),scale="utc")
loc=EarthLocation(lat=1.3483*u.deg,lon=103.6831*u.deg,height=20*u.m)
c=SkyCoord(r["ra"],r["dec"],unit="deg").transform_to(AltAz(obstime=t,location=loc))
out=[]
for n,row,al,az in zip(names,r,c.alt.deg,c.az.deg):
    if al>12: out.append({"name":n,"V":float(row["V"]),"alt":round(float(al),1),"az":round(float(az),1)})
out.sort(key=lambda s:s["V"])
for s in out: print(s)
d["c4"]["stars"]=out; json.dump(d,open("sat.json","w"))
