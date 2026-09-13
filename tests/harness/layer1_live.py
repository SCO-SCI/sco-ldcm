"""Layer 1 (live): a deterministic sample of Ed's enumeration is requested from
production and from the service under test. Prefixed compute responses must
be identical after removing the xi field the new service adds; for the
quadratic law the legacy /api/compute must be byte-identical with nothing
removed, and the legacy filters, health (stable fields) and a fixed list of
error and malformed requests must match as well. Rate-limited, retried and
checkpointed exactly as quad_equivalence_sweep.py."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, enumerate_points, query_live, Checkpoint, RateLimiter, LAWS

LEGACY_EDGE = [  # the legacy error and malformed-input paths, compared byte for byte
    "/api/compute?teff=6000&logg=4.5&filter=V", "/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=PHOENIX",
    "/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=BOGUS", "/api/compute?teff=6000&logg=4.5&feh=0.0&filter=NOPE&model=ATLAS",
    "/api/compute?logg=4.5&feh=0.0&filter=V&model=ATLAS", "/api/compute?teff=abc&logg=4.5&feh=0.0&filter=V&model=ATLAS",
    "/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS&xi=8", "/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS&xi=3",
    "/api/compute?teff=5150&logg=4.4&feh=-0.05&filter=TESS&model=ATLAS", "/api/compute?teff=6000&logg=4.5&feh=0.3&filter=V&model=ATLAS",
    "/api/compute?teff=37500&logg=4.5&feh=0.0&filter=V&model=ATLAS", "/api/compute?teff=2000&logg=4.5&feh=0.0&filter=V&model=ATLAS",
    "/api/filters", "/api/filters?xi=8", "/api/resolve?planet=NOT-A-PLANET-XYZ", "/api/nonexistent",
]

def strip_xi(text):
    try:
        d = json.loads(text)
    except Exception:
        return text
    if isinstance(d, dict): d.pop("xi", None)
    return json.dumps(d, separators=(",", ":"), sort_keys=False)

ap = argparse.ArgumentParser()
ap.add_argument("--v5", required=True); ap.add_argument("--prod", default="https://sco-ldc.com"); ap.add_argument("--test", default="https://sco-ldcm.onrender.com")
ap.add_argument("--laws", default=",".join(LAWS)); ap.add_argument("--per-law", type=int, default=600); ap.add_argument("--rate", type=float, default=8.0)
ap.add_argument("--results", default="results")
a = ap.parse_args(); os.makedirs(a.results, exist_ok=True)
rl_p, rl_t = RateLimiter(a.rate), RateLimiter(a.rate)
summary = {}
for law in a.laws.split(","):
    core, _ = load_engine(a.v5, law)
    pts = list(enumerate_points(core, xi_filter=2.0))
    stride = max(1, len(pts) // a.per_law); sample = pts[::stride][:a.per_law]
    ck = Checkpoint(os.path.join(a.results, f"l1live_{law}_checkpoint.json")); st = ck.state
    fails = []
    for idx in range(st["next_index"], len(sample)):
        p = sample[idx]; q = dict(teff=p["teff"], logg=p["logg"], feh=p["feh"], filter=p["filter"], model=p["model"])
        rl_p.wait(); cp, tp = query_live(f"{a.prod}/{law}/api/compute", q)
        rl_t.wait(); ct, tt = query_live(f"{a.test}/{law}/api/compute", q)
        ok = cp == ct and cp is not None and strip_xi(tp) == strip_xi(tt)
        if law == "quad" and ok:   # the frozen route: byte for byte, nothing removed
            rl_p.wait(); lp = query_live(f"{a.prod}/api/compute", q)
            rl_t.wait(); lt = query_live(f"{a.test}/api/compute", q)
            ok = lp == lt and lp[0] is not None and lp[1] == tp  # legacy == prod prefixed too
        st["n_pass" if ok else "n_fail"] += 1
        if not ok and len(fails) < 20: fails.append({"point": p, "prod": (cp, (tp or "")[:120]), "test": (ct, (tt or "")[:120])})
        st["next_index"] = idx + 1
        if (idx + 1) % 50 == 0: ck.save()
    ck.save()
    summary[law] = {"sampled": len(sample), "of": len(pts), "pass": st["n_pass"], "fail": st["n_fail"], "examples": fails}
    print(f"layer 1 live, {law}: {len(sample)} of {len(pts)} points, {st['n_pass']} pass, {st['n_fail']} fail")
# legacy edge paths, byte for byte
edge = []
for path in LEGACY_EDGE:
    rl_p.wait(); cp, tp = query_live(a.prod + path, {}); rl_t.wait(); ct, tt = query_live(a.test + path, {})
    same = (cp == ct and tp == tt)
    edge.append({"path": path, "identical": same, "prod": cp, "test": ct} if not same else {"path": path, "identical": True})
ph = json.loads(query_live(a.prod + "/api/health", {})[1]); th = json.loads(query_live(a.test + "/api/health", {})[1])
stable = lambda d: {k: d[k] for k in ("status", "version", "tables", "filter_count") if k in d}
health_ok = stable(ph) == stable(th) and list(ph.keys()) == list(th.keys())
summary["legacy"] = {"edge_paths": edge, "edge_identical": sum(1 for e in edge if e["identical"]), "edge_total": len(edge), "health_stable_fields_identical": health_ok}
print(f"legacy edge paths: {summary['legacy']['edge_identical']} of {len(edge)} identical; health stable fields identical: {health_ok}")
json.dump(summary, open(os.path.join(a.results, "layer1_live.json"), "w"), indent=1)
sys.exit(2 if any(v.get("fail") for k, v in summary.items() if k != "legacy") or summary["legacy"]["edge_identical"] != len(edge) or not health_ok else 0)
