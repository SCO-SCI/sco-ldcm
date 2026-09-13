"""Layer 4: every refusal the tables imply happens, and nothing else is
refused. The specification is generated from the loaded grids (section 9 of
the table reference): each case is a request with an expected status and,
for refusals, a fragment of the expected message. Runs exhaustively against
the v5 code and, with --live, a rate-limited sample against a service."""
import argparse, json, os, sys, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, call_compute, table_key_parts, display_model, query_live, RateLimiter, LAWS

def cells(g, feh=0.0):
    return {(t, l) for (t, l, z) in g["data"] if z == feh}

def build_spec(core):
    spec = []
    grids = {}
    for key, g in core._TABLES.items():
        f, sm, xi = table_key_parts(key); grids[(f, sm, xi)] = g
    atlas = sorted({f for (f, sm, xi) in grids if sm == "ATLAS"})
    for f in atlas:
        g2 = grids[(f, "ATLAS", 2.0)]; c2 = cells(g2)
        for xi in (4.0, 8.0):
            gx = grids[(f, "ATLAS", xi)]; cx = cells(gx)
            for (t, l) in sorted(c2 - cx):
                spec.append(dict(case="missing_cell_at_velocity", filter=f, model="ATLAS", xi=xi, teff=t, logg=l, feh=0.0, expect=400, msg="Tables do not include data"))
                spec.append(dict(case="same_cell_at_2", filter=f, model="ATLAS", xi=2.0, teff=t, logg=l, feh=0.0, expect=200))
        for xi in (0.0, 1.0):
            gx = grids[(f, "ATLAS", xi)]
            for (t, l) in sorted(cells(gx) - c2):
                spec.append(dict(case="extra_cell_at_low_velocity", filter=f, model="ATLAS", xi=xi, teff=t, logg=l, feh=0.0, expect=200))
                spec.append(dict(case="extra_cell_absent_at_2", filter=f, model="ATLAS", xi=2.0, teff=t, logg=l, feh=0.0, expect=400, msg="Tables do not include data"))
        # half-step temperatures at the other velocities: value iff both 1000 K neighbours exist at that log g
        for xi in (0.0, 1.0, 4.0, 8.0):
            gx = grids[(f, "ATLAS", xi)]; cx = cells(gx)
            for t in (37500.0, 42500.0, 47500.0):
                for l in gx["loggs"]:
                    ok = (t - 500.0, l) in cx and (t + 500.0, l) in cx
                    spec.append(dict(case="half_step_at_velocity", filter=f, model="ATLAS", xi=xi, teff=t, logg=l, feh=0.0, expect=200 if ok else 400, msg=None if ok else "Tables do not include data"))
        # non-solar rule at 2 km/s: between non-solar nodes only exact nodes succeed
        for feh in (-0.5, 0.5):
            for l in (4.5, 5.0):
                for t in (10250.0, 10375.0, 10500.0, 10750.0, 12500.0, 12750.0, 36000.0, 37500.0, 38000.0, 38500.0, 39500.0, 40000.0, 41000.0, 42500.0, 44000.0, 45000.0):
                    have = (t, l, feh) in g2["data"]
                    spec.append(dict(case="non_solar_node_rule", filter=f, model="ATLAS", xi=2.0, teff=t, logg=l, feh=feh, expect=200 if have else 400, msg=None if have else "Tables do not include data"))
        # unsupported velocity values and non-solar at a non-default velocity
        for xi in (3.0, 2.5, -1.0, 16.0):
            spec.append(dict(case="unsupported_velocity", filter=f, model="ATLAS", xi=xi, teff=6000.0, logg=4.5, feh=0.0, expect=400, msg="published only at 0, 1, 2, 4, 8 km/s"))
        for xi in (0.0, 1.0, 4.0, 8.0):
            spec.append(dict(case="non_solar_at_velocity", filter=f, model="ATLAS", xi=xi, teff=6000.0, logg=4.5, feh=-0.5, expect=400, msg="solar metallicity only"))
    # PHOENIX-family grids away from 2 km/s
    for (f, sm, xi), g in grids.items():
        if sm == "PHOENIX" and xi == 2.0:
            label = display_model(core, f, sm); t, l = g["teffs"][len(g["teffs"])//2], g["loggs"][-1]
            for x in (0.0, 1.0, 4.0, 8.0):
                spec.append(dict(case="phoenix_family_at_velocity", filter=f, model=label, xi=x, teff=t, logg=l, feh=0.0, expect=400, msg="published only at 2 km/s"))
            spec.append(dict(case="phoenix_family_at_2", filter=f, model=label, xi=2.0, teff=t, logg=l, feh=0.0, expect=200))
    return spec

def check(status, body, c):
    if status != c["expect"]: return False
    if c["expect"] == 400 and c.get("msg") and c["msg"] not in str(body): return False
    return True

ap = argparse.ArgumentParser(); ap.add_argument("--v5", required=True); ap.add_argument("--laws", default=",".join(LAWS))
ap.add_argument("--live", default=None, help="base URL of a service to sample, e.g. https://sco-ldcm.onrender.com")
ap.add_argument("--live-per-case", type=int, default=6); ap.add_argument("--rate", type=float, default=8.0); ap.add_argument("--results", default="results")
a = ap.parse_args(); os.makedirs(a.results, exist_ok=True)
summary = {}
for law in a.laws.split(","):
    core, app = load_engine(a.v5, law); spec = build_spec(core)
    by = {}; bad = []
    for c in spec:
        status, body = call_compute(app, core, c, True)
        ok = check(status, body, c)
        d = by.setdefault(c["case"], {"cases": 0, "failures": 0}); d["cases"] += 1
        if not ok:
            d["failures"] += 1
            if len(bad) < 20: bad.append({"case": c, "status": status, "body": body if status != 200 else "value"})
    live = None
    if a.live:
        rng = random.Random(7); rl = RateLimiter(a.rate); live = {"requests": 0, "failures": 0, "examples": []}
        for case in sorted(by):
            sample = rng.sample([c for c in spec if c["case"] == case], min(a.live_per_case, by[case]["cases"]))
            for c in sample:
                rl.wait()
                code, text = query_live(f"{a.live}/{law}/api/compute", dict(filter=c["filter"], model=c["model"], xi=c["xi"], teff=c["teff"], logg=c["logg"], feh=c["feh"]))
                live["requests"] += 1
                if code is None or not check(code, text, c):
                    live["failures"] += 1
                    if len(live["examples"]) < 10: live["examples"].append({"case": c, "status": code, "body": (text or "")[:160]})
    summary[law] = {"local": by, "live": live, "examples": bad}
    tot = sum(v["cases"] for v in by.values()); fl = sum(v["failures"] for v in by.values())
    print(f"layer 4, {law}: {tot} cases in {len(by)} categories, {fl} local failures" + (f"; live sample {live['requests']} requests, {live['failures']} failures" if live else ""))
    for k, v in by.items(): print(f"     {k:28} {v['cases']:6} cases  {v['failures']} failures")
json.dump(summary, open(os.path.join(a.results, "layer4_refusals.json"), "w"), indent=1)
fails = any(v["failures"] for s in summary.values() for v in s["local"].values()) or any(s["live"] and s["live"]["failures"] for s in summary.values())
sys.exit(2 if fails else 0)
