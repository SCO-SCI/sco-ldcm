"""Run the SCO-LDC v5 test harness and write results/report.md + summary.json.

  python run_all.py --v4 <checkout of main> --v5 <checkout of v5> [--only local|live]

Layers: 1 local (v4 vs v5 code, every point), 2 velocity (rows and oracle),
3 catalog (advertised vs held), 4 refusals (spec vs code, sampled live),
1 live (production vs test service on a sample; legacy routes byte for byte).
Exit 0 only when every layer reports zero discrepancies."""
import argparse, json, os, subprocess, sys, datetime
here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--v4", required=True); ap.add_argument("--v5", required=True)
ap.add_argument("--prod", default="https://sco-ldc.com"); ap.add_argument("--test", default="https://sco-ldcm.onrender.com")
ap.add_argument("--per-law", type=int, default=300); ap.add_argument("--only", choices=["local", "live", "all"], default="all")
ap.add_argument("--results", default=os.path.join(here, "results"))
a = ap.parse_args(); os.makedirs(a.results, exist_ok=True)
steps = []
if a.only in ("local", "all"):
    steps += [("layer1_local", ["layer1_local.py", "--v4", a.v4, "--v5", a.v5]),
              ("layer2_velocity", ["layer2_velocity.py", "--v5", a.v5])]
if a.only in ("live", "all"):
    steps += [("layer3_catalog", ["layer3_catalog.py", "--v5", a.v5, "--base", a.test]),
              ("layer4_refusals", ["layer4_refusals.py", "--v5", a.v5, "--live", a.test]),
              ("layer1_live", ["layer1_live.py", "--v5", a.v5, "--prod", a.prod, "--test", a.test, "--per-law", str(a.per_law)])]
codes = {}
for name, cmd in steps:
    r = subprocess.run([sys.executable, os.path.join(here, cmd[0])] + cmd[1:] + ["--results", a.results], capture_output=True, text=True)
    codes[name] = r.returncode
    print(f"== {name}: exit {r.returncode}"); print("\n".join(l for l in r.stdout.splitlines() if "Deprecat" not in l))
    if r.returncode not in (0, 2): print(r.stderr[-1500:])
# assemble
summary = {"run_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "v4": a.v4, "v5": a.v5, "prod": a.prod, "test": a.test, "exit_codes": codes, "layers": {}}
for name in ("layer1_local", "layer2_velocity", "layer3_catalog", "layer4_refusals", "layer1_live"):
    p = os.path.join(a.results, name + ".json")
    if os.path.exists(p): summary["layers"][name] = json.load(open(p))
json.dump(summary, open(os.path.join(a.results, "summary.json"), "w"), indent=1)
L = summary["layers"]; lines = [f"# SCO-LDC v5 harness report — {summary['run_utc']}", ""]
if "layer1_local" in L:
    lines.append("## Layer 1, local: v4 code vs v5 code, every node, cell centre and random interior point at 2 km/s")
    for law, v in L["layer1_local"].items(): lines.append(f"- {law}: {v['points']} points, {v['discrepancies']} discrepancies")
if "layer2_velocity" in L:
    lines.append("## Layer 2: velocity tables, nodes vs table rows and interior points vs independent oracle")
    for law, v in L["layer2_velocity"].items(): lines.append(f"- {law}: " + ", ".join(f"{k} {x['points']}/{x['failures']}" for k, x in v["by_velocity"].items()) + " (points/failures)")
if "layer3_catalog" in L:
    lines.append("## Layer 3: advertised catalogue vs loaded grids (live test service)")
    for law, v in L["layer3_catalog"].items(): lines.append(f"- {law}: {v['grids_in_code']} grids in code, {v['grids_advertised']} advertised, {len(v['problems'])} problems")
if "layer4_refusals" in L:
    lines.append("## Layer 4: refusal specification, exhaustive on code, sampled live")
    for law, v in L["layer4_refusals"].items():
        tot = sum(x["cases"] for x in v["local"].values()); fl = sum(x["failures"] for x in v["local"].values())
        lines.append(f"- {law}: {tot} cases, {fl} local failures" + (f"; live {v['live']['requests']} requests, {v['live']['failures']} failures" if v.get("live") else ""))
if "layer1_live" in L:
    lines.append("## Layer 1, live: production vs test service on a sample; legacy routes byte for byte")
    for law, v in L["layer1_live"].items():
        if law == "legacy": lines.append(f"- legacy: {v['edge_identical']} of {v['edge_total']} edge paths identical; health stable fields identical: {v['health_stable_fields_identical']}")
        else: lines.append(f"- {law}: {v['sampled']} of {v['of']} points, {v['pass']} pass, {v['fail']} fail")
ok = all(c == 0 for c in codes.values())
lines += ["", f"**Result: {'PASS — zero discrepancies in every layer' if ok else 'FAIL — see the layer files in results/'}**"]
open(os.path.join(a.results, "report.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines)); sys.exit(0 if ok else 2)
