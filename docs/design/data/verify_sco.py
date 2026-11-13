# Independent check of the A1 layout: re-project SIMBAD positions with astropy's WCS (TAN)
# and compare every pairwise distance on the card against true angular separation.
import json, itertools, numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
S={s["id"]:s for s in json.load(open("stars.json"))["sco"]}
L=json.load(open("data.json"))["sco"]; pts=L["leds"]+L["dots"]
ids=[p["id"] for p in pts]
c=SkyCoord([S[i]["ra"] for i in ids],[S[i]["dec"] for i in ids],unit="deg")
w=WCS(naxis=2); w.wcs.ctype=["RA---TAN","DEC--TAN"]; w.wcs.crval=[np.mean(c.ra.deg),np.mean(c.dec.deg)]; w.wcs.cdelt=[-1,1]; w.wcs.crpix=[0,0]
x,y=w.world_to_pixel(c); ref=np.c_[x,-y]                       # degrees on the tangent plane, east left, north up
card=np.array([[p["x"],p["y"]] for p in pts])
r=[];ang=[]
for i,j in itertools.combinations(range(len(pts)),2):
    r.append(np.linalg.norm(card[i]-card[j])/np.linalg.norm(ref[i]-ref[j]))
    ang.append(c[i].separation(c[j]).deg)
r=np.array(r); print(f"card mm per tangent-plane degree: mean {r.mean():.4f}, spread {100*(r.max()-r.min())/r.mean():.3f}%")
# best-fit rotation between reference and card
A=ref-ref.mean(0); B=card-card.mean(0); U,_,Vt=np.linalg.svd(A.T@B); R=U@Vt
print("rotation applied:",round(np.degrees(np.arctan2(R[0,1],R[0,0])),2),"deg; mirrored:",bool(np.linalg.det(R)<0))
res=np.linalg.norm(A@R*r.mean()-B,axis=1); print("max position residual on card (mm):",round(res.max(),3))
for a,b in [("alf Sco","lam Sco"),("bet1 Sco","alf Sco"),("alf Sco","tet Sco")]:
    i,j=ids.index(a),ids.index(b); print(f"{a}–{b}: true {c[i].separation(c[j]).deg:.2f}°, card {np.linalg.norm(card[i]-card[j]):.1f} mm")
