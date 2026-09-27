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

# Fields v5 adds to a prefixed compute response that v4 never carried.  They
# are removed before the layer-1 comparison so that it keeps doing its real
# job: proving no EXISTING field changed.  Their presence is checked
# separately, by layer 5, rather than being lost from the harness entirely.
#
# Anything added to a compute response in future belongs here at the same time
# it is added to parent_app.LEGACY_WITHHELD.  Without that, layer 1 reports
# every point as a discrepancy -- as it did after Phase 2, when 1.42 million
# intended differences made the gate useless until this was fixed.
V5_ADDED = ("xi",                                    # Phase 0, the velocity work
            "h1_prime", "h2_prime",                  # Phase 2.1
            "edge_point_applied", "mu_cri",          # Phase 2.1
            "maxted_correction")                     # Phase 2.2
a = ap.parse_args()
core, app = load_engine(a.repo, a.law)
n = 0
with open(a.points) as fin, open(a.out, "w") as fout:
    for line in fin:
        p = json.loads(line)
        status, body = call_compute(app, core, p, a.has_xi)
        if status == 200 and a.has_xi:
            body = dict(body)
            for k in V5_ADDED:
                body.pop(k, None)
        fout.write(json.dumps({"s": status, "b": body}, separators=(",", ":")) + "\n")
        n += 1
print(f"{a.law} {os.path.basename(a.repo)}: {n} points")
