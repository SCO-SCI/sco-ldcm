#!/usr/bin/env python3
"""SCO-LDC v5 Goal 1, step 2 verification: the API routes.

Run from the repository root AFTER replacing the four files:

    cd C:\\Users\\edkmu\\Desktop\\SCO-LDC_MAIN\\SCO-LDC_V5\\sco-ldcv5
    python v5_verify_routes.py

Starts the whole service in memory and exercises it. No network, no deploy.
Section 1 is the important one: it proves the frozen unprefixed routes still
behave exactly as before and cannot be influenced by a velocity parameter.
"""
import sys, logging, warnings; sys.path.insert(0, ".")
logging.disable(logging.CRITICAL); warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient
import parent_app
c = TestClient(parent_app.app)
fails=[]
def ck(label, ok, det=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"   {det}" if det else ""))
    if not ok: fails.append(label)

print("1. THE FROZEN ROUTES STAY FROZEN")
base="/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS"
r0=c.get(base)
ck("legacy compute works", r0.status_code==200)
ck("legacy compute has NO xi field", "xi" not in r0.json(), str(sorted(r0.json().keys())))
for xi in ("8","0","3","abc"):
    r=c.get(base+f"&xi={xi}")
    ck(f"legacy compute ignores ?xi={xi}", r.status_code==200 and r.text==r0.text,
       f"status {r.status_code}")
f0=c.get("/api/filters"); f8=c.get("/api/filters?xi=8")
ck("legacy filters ignores ?xi=8", f0.status_code==200 and f0.text==f8.text,
   f"{len(f0.json()['filters'])} filters")
h=c.get("/api/health")
ck("legacy health unchanged", h.status_code==200 and h.json()["filter_count"]==26)

print("\n2. PREFIXED ROUTES ACCEPT A VELOCITY")
for law, keys in (("quad",("u1","u2")), ("power2",("g","h")),
                  ("fourparam",("a1","a2","a3","a4"))):
    q=f"/{law}/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS"
    d2=c.get(q).json(); d8=c.get(q+"&xi=8").json()
    ck(f"{law}: default reports xi 2", d2.get("xi")==2.0, str(d2.get("xi")))
    ck(f"{law}: xi=8 reports xi 8", d8.get("xi")==8.0, str(d8.get("xi")))
    ck(f"{law}: xi=8 changes the coefficients", any(d2[k]!=d8[k] for k in keys),
       "  ".join(f"{k} {d2[k]} -> {d8[k]}" for k in keys[:2]))

print("\n3. PREFIXED FILTERS RESPOND TO VELOCITY")
for law,n2,n8 in (("quad",26,25),("power2",24,23),("fourparam",28,23)):
    a=len(c.get(f"/{law}/api/filters").json()["filters"])
    b=len(c.get(f"/{law}/api/filters?xi=8").json()["filters"])
    ck(f"{law}: {n2} filters at 2, {n8} at 8", a==n2 and b==n8, f"got {a} and {b}")

print("\n4. REFUSALS RETURN 400 WITH A REASON")
for q,why in [("/quad/api/compute?teff=6000&logg=4.5&feh=0.0&filter=TESS&model=PHOENIX-COND&xi=8","quad TESS at 8"),
              ("/quad/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=PHOENIX&xi=8","quad PHOENIX at 8"),
              ("/quad/api/compute?teff=6000&logg=4.5&feh=-0.5&filter=V&model=ATLAS&xi=8","non-solar at 8"),
              ("/quad/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS&xi=3","unpublished velocity"),
              ("/power2/api/compute?teff=6000&logg=4.5&feh=0.0&filter=CHEOPS&model=PHOENIX-COND&xi=4","power2 CHEOPS at 4"),
              ("/fourparam/api/compute?teff=6000&logg=4.5&feh=0.0&filter=TESS&model=PHOENIX-COND&xi=8","4p TESS at 8")]:
    r=c.get(q)
    ck(why, r.status_code==400, f"{r.status_code}: {str(r.json().get('detail'))[:58]}")

print("\n" + "="*60)
print("ALL PASS" if not fails else f"{len(fails)} FAILURE(S)")
for f in fails: print("  ", f)
sys.exit(1 if fails else 0)
