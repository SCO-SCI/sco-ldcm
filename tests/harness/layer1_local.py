"""Layer 1 (local): for every point of Ed's enumeration at 2 km/s, the v4 code
and the v5 code must produce identical compute responses (v5's xi field
removed). Runs the two code bases in separate processes and compares."""
import argparse, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, enumerate_points, LAWS

ap = argparse.ArgumentParser()
ap.add_argument("--v4", required=True); ap.add_argument("--v5", required=True)
ap.add_argument("--laws", default=",".join(LAWS)); ap.add_argument("--kinds", default="node,center,random")
ap.add_argument("--results", default="results")
a = ap.parse_args()
os.makedirs(a.results, exist_ok=True)
here = os.path.dirname(os.path.abspath(__file__))
summary = {}
for law in a.laws.split(","):
    t0 = time.time()
    core, _ = load_engine(a.v5, law)          # v5 tables define the point set
    pts = os.path.join(a.results, f"points_{law}.jsonl")
    counts = {}
    with open(pts, "w") as f:
        for p in enumerate_points(core, xi_filter=2.0, kinds=tuple(a.kinds.split(","))):
            f.write(json.dumps(p, separators=(",", ":")) + "\n"); counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    out4, out5 = os.path.join(a.results, f"l1_{law}_v4.jsonl"), os.path.join(a.results, f"l1_{law}_v5.jsonl")
    for repo, out, flag in ((a.v4, out4, []), (a.v5, out5, ["--has-xi"])):
        r = subprocess.run([sys.executable, os.path.join(here, "engine_dump.py"), "--repo", repo, "--law", law, "--points", pts, "--out", out] + flag,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-2000:]); sys.exit(1)
    # compare line by line
    n = n_diff = 0; examples = []
    with open(pts) as fp, open(out4) as f4, open(out5) as f5:
        for p, l4, l5 in zip(fp, f4, f5):
            n += 1
            if l4 != l5:
                n_diff += 1
                if len(examples) < 20:
                    examples.append({"point": json.loads(p), "v4": json.loads(l4), "v5": json.loads(l5)})
    summary[law] = {"points": n, "by_kind": counts, "discrepancies": n_diff, "seconds": round(time.time() - t0, 1), "examples": examples}
    print(f"layer 1 local, {law}: {n} points ({counts}), {n_diff} discrepancies, {summary[law]['seconds']} s")
    for e in examples[:3]:
        print("   e.g.", e)
json.dump(summary, open(os.path.join(a.results, "layer1_local.json"), "w"), indent=1)
sys.exit(2 if any(v["discrepancies"] for v in summary.values()) else 0)
