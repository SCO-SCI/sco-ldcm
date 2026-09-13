"""Layer 2: the velocity tables serve their own rows. For xi in 0, 1, 2, 4, 8
every node must return exactly the table cell with on_grid true and xi
echoed; every cell centre and random interior point must equal an
independent trilinear interpolation of the eight corner cells."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, enumerate_points, call_compute, table_key_parts, display_model, COEF_KEYS, LAWS

def bracket(axis, x):
    if x <= axis[0]: return 0, 0, 0.0
    if x >= axis[-1]: return len(axis)-1, len(axis)-1, 0.0
    for i in range(len(axis)-1):
        if axis[i] <= x <= axis[i+1]:
            if x == axis[i]: return i, i, 0.0
            if x == axis[i+1]: return i+1, i+1, 0.0
            return i, i+1, (x-axis[i])/(axis[i+1]-axis[i])
    raise ValueError

def oracle(g, teff, logg, feh):
    te, lg, fe = g["teffs"], g["loggs"], g["fehs"]
    i0,i1,tT = bracket(te, teff); j0,j1,tG = bracket(lg, logg)
    if len(fe) == 1:
        k0=k1=0; tZ=0.0
    else:
        k0,k1,tZ = bracket(fe, feh)
    corners = {}
    for a,i in ((0,i0),(1,i1)):
        for b,j in ((0,j0),(1,j1)):
            for c,k in ((0,k0),(1,k1)):
                key = (round(te[i],2), round(lg[j],3), round(fe[k],3))
                if key not in g["data"]: return None
                corners[(a,b,c)] = g["data"][key]
    w = {(0,0,0):(1-tT)*(1-tG)*(1-tZ),(0,0,1):(1-tT)*(1-tG)*tZ,(0,1,0):(1-tT)*tG*(1-tZ),(0,1,1):(1-tT)*tG*tZ,
         (1,0,0):tT*(1-tG)*(1-tZ),(1,0,1):tT*(1-tG)*tZ,(1,1,0):tT*tG*(1-tZ),(1,1,1):tT*tG*tZ}
    n = len(next(iter(corners.values())))
    out = [0.0]*n
    for i in (0,1):
        for j in (0,1):
            for k in (0,1):
                for m in range(n): out[m] += w[(i,j,k)]*corners[(i,j,k)][m]
    return out

ap = argparse.ArgumentParser(); ap.add_argument("--v5", required=True); ap.add_argument("--laws", default=",".join(LAWS)); ap.add_argument("--results", default="results")
a = ap.parse_args(); os.makedirs(a.results, exist_ok=True)
summary = {}
for law in a.laws.split(","):
    t0=time.time(); core, app = load_engine(a.v5, law); keys = COEF_KEYS[law]
    grids = {}
    for key, g in core._TABLES.items():
        f, sm, xi = table_key_parts(key); grids[(f, display_model(core, f, sm), xi)] = g
    stats = {}; bad = []
    for xi in (0.0, 1.0, 2.0, 4.0, 8.0):
        n=nn=0
        for p in enumerate_points(core, xi_filter=xi):
            status, body = call_compute(app, core, p, True); n += 1
            g = grids[(p["filter"], p["model"], xi)]
            expect = g["data"].get((p["teff"], p["logg"], p["feh"])) if p["kind"]=="node" else oracle(g, p["teff"], p["logg"], p["feh"])
            ok = status == 200 and body.get("xi") == xi and all(abs(body[k]-e) <= (0.0 if p["kind"]=="node" else 1e-12) for k,e in zip(keys, expect)) \
                 and (body["grid"]["on_grid"] is (p["kind"]=="node"))
            if not ok:
                nn += 1
                if len(bad) < 20: bad.append({"law": law, "point": p, "status": status, "body": body if status!=200 else {k: body[k] for k in keys}, "expected": expect})
        stats[f"xi={xi:g}"] = {"points": n, "failures": nn}
    summary[law] = {"by_velocity": stats, "seconds": round(time.time()-t0,1), "examples": bad}
    print(f"layer 2, {law}: " + ", ".join(f"{k} {v['points']} pts/{v['failures']} fail" for k,v in stats.items()) + f"  ({summary[law]['seconds']} s)")
json.dump(summary, open(os.path.join(a.results, "layer2_velocity.json"), "w"), indent=1)
sys.exit(2 if any(v["failures"] for s in summary.values() for v in s["by_velocity"].values()) else 0)
