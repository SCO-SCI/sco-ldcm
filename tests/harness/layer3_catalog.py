"""Layer 3: what the live service advertises equals what the code holds.
The capabilities map and the filters catalog at every velocity, fetched from
the service under test, are compared with the grids loaded from the v5 code."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, table_key_parts, display_model, query_live, LAWS

ap = argparse.ArgumentParser(); ap.add_argument("--v5", required=True); ap.add_argument("--base", default="https://sco-ldcm.onrender.com")
ap.add_argument("--laws", default=",".join(LAWS)); ap.add_argument("--results", default="results")
a = ap.parse_args(); os.makedirs(a.results, exist_ok=True)
summary = {}
for law in a.laws.split(","):
    core, _ = load_engine(a.v5, law)
    expected = {}
    for key, g in core._TABLES.items():
        f, sm, xi = table_key_parts(key)
        expected[(f, display_model(core, f, sm), xi)] = dict(teff_min=g["teffs"][0], teff_max=g["teffs"][-1], logg_min=g["loggs"][0], logg_max=g["loggs"][-1],
                                                            feh_min=g["fehs"][0], feh_max=g["fehs"][-1], feh_fixed=(len(g["fehs"])==1), n_points=len(g["data"]), model_key=sm)
    problems = []
    code, text = query_live(f"{a.base}/{law}/api/capabilities", {})
    if code != 200: problems.append(f"capabilities HTTP {code}"); caps = []
    else: caps = json.loads(text)["capabilities"]
    seen = {}
    for f in caps:
        for g in f["grids"]:
            seen[(f["code"], g["model"], float(g["xi"]))] = g
    for k in set(expected) - set(seen): problems.append(f"missing from capabilities: {k}")
    for k in set(seen) - set(expected): problems.append(f"unexpected in capabilities: {k}")
    for k in set(expected) & set(seen):
        e, s = expected[k], seen[k]
        for fld in ("teff_min","teff_max","logg_min","logg_max","feh_min","feh_max","feh_fixed","n_points","model_key"):
            if s.get(fld) != e[fld]: problems.append(f"{k} {fld}: service {s.get(fld)} vs code {e[fld]}")
    # filters catalog at each velocity must be the capabilities restricted to that velocity
    for xi in (0,1,2,4,8):
        code, text = query_live(f"{a.base}/{law}/api/filters", {"xi": xi} if xi != 2 else {})
        if code != 200: problems.append(f"filters?xi={xi} HTTP {code}"); continue
        fl = json.loads(text)["filters"]
        got = {(f["code"], m["model"]): m for f in fl for m in f["models"]}
        want = {(k[0], k[1]): v for k, v in expected.items() if k[2] == float(xi)}
        if set(got) != set(want): problems.append(f"filters?xi={xi}: entries differ: only-service {sorted(set(got)-set(want))[:5]} only-code {sorted(set(want)-set(got))[:5]}")
        for k in set(got) & set(want):
            if got[k]["n_points"] != want[k]["n_points"] or got[k]["teff_min"] != want[k]["teff_min"] or bool(got[k]["feh_fixed"]) != want[k]["feh_fixed"]:
                problems.append(f"filters?xi={xi} {k}: {got[k]['n_points']}/{got[k]['teff_min']}/{got[k]['feh_fixed']} vs {want[k]['n_points']}/{want[k]['teff_min']}/{want[k]['feh_fixed']}")
    summary[law] = {"grids_in_code": len(expected), "grids_advertised": len(seen), "problems": problems}
    print(f"layer 3, {law}: {len(expected)} grids in code, {len(seen)} advertised, {len(problems)} problems" + (f"  e.g. {problems[:2]}" if problems else ""))
json.dump(summary, open(os.path.join(a.results, "layer3_catalog.json"), "w"), indent=1)
sys.exit(2 if any(v["problems"] for v in summary.values()) else 0)
