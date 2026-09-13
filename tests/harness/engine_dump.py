"""Run one code base's compute handler over a points file and write the
responses, one JSON line per point, in the same order. Used twice per law by
layer 1: once for the v4 code (production), once for v5."""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, call_compute

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True); ap.add_argument("--law", required=True)
ap.add_argument("--points", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--has-xi", action="store_true", help="the compute handler takes xi (v5)")
a = ap.parse_args()
core, app = load_engine(a.repo, a.law)
n = 0
with open(a.points) as fin, open(a.out, "w") as fout:
    for line in fin:
        p = json.loads(line)
        status, body = call_compute(app, core, p, a.has_xi)
        if status == 200 and a.has_xi:
            body = dict(body); body.pop("xi", None)        # the one field v5 adds
        fout.write(json.dumps({"s": status, "b": body}, separators=(",", ":")) + "\n")
        n += 1
print(f"{a.law} {os.path.basename(a.repo)}: {n} points")
