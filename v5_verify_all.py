#!/usr/bin/env python3
"""
SCO-LDC v5, Goal 1 — verification for ALL THREE engines.

Run from the repository root after replacing the three ldc_core.py files:

    cd C:\\Users\\edkmu\\Desktop\\SCO-LDC_MAIN\\SCO-LDC_V5\\sco-ldcv5
    del quad\\data\\tables.pkl
    del power2\\data\\tables.pkl
    del fourparam\\data\\tables.pkl
    python v5_verify_all.py

Touches no network and no service. It reads the repository, parses every table
from scratch ignoring any cache, and prints PASS or FAIL for each check.

The first section is the one that matters. It proves the service still gives
exactly the answers it gives today.
"""
import sys, os, time, collections

for law in ("quad", "power2", "fourparam"):
    if not os.path.exists(os.path.join(law, "ldc_core.py")):
        print(f"ERROR: {law}/ldc_core.py not found. Run this from the repository root.")
        sys.exit(1)

fails = []
def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(label)

def load(law):
    import importlib.util
    for m in list(sys.modules):
        if m == "ldc_core":
            del sys.modules[m]
    base = os.path.join(os.getcwd(), law)
    spec = importlib.util.spec_from_file_location("ldc_core", os.path.join(base, "ldc_core.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ldc_core"] = mod
    sys.path.insert(0, base)
    spec.loader.exec_module(mod)
    t0 = time.perf_counter()
    mod.load_tables(os.path.join(base, "data"), use_cache=False)
    dt = time.perf_counter() - t0
    sys.path.remove(base)
    return mod, dt

# What the service returns today. If any of these move, stop.
REFERENCE = {
    "quad": [((6000, 4.5,  0.0, "V",    "ATLAS"),        ("u1","u2"), (0.4152, 0.286)),
             ((5150, 4.4, -0.05, "V",   "ATLAS"),        ("u1","u2"), (0.606146, 0.15932)),
             ((3000, 3.5,  0.0, "Kp",   "PHOENIX"),      ("u1","u2"), (0.5257, 0.3371)),
             ((6000, 4.5,  0.0, "TESS", "PHOENIX-COND"), ("u1","u2"), (0.3362, 0.2251))],
    "power2": [((6000, 4.5, 0.0, "Kp",  "ATLAS"),        ("g","h"),   (0.7402, 0.6292))],
    "fourparam": [((3000, 3.5, 0.0, "Kp","PHOENIX-COND"),
                   ("a1","a2","a3","a4"),
                   (0.28775211, 1.77747108, -1.90014251, 0.7223791))],
}

EXPECT = {   # law: (grids at 2.0, points at 2.0, filters at 2.0, cache ver, filters lost at 8.0)
    "quad":      (46, 196111, 26, 4, {"TESS"}),
    "power2":    (46, 195914, 24, 2, {"CHEOPS"}),
    "fourparam": (47, 196054, 28, 2, {"CHEOPS", "G", "G_BP", "G_RP", "TESS"}),
}

total_time = 0.0
for law in ("quad", "power2", "fourparam"):
    print(f"\n{'='*64}\n{law.upper()}\n{'='*64}")
    m, dt = load(law)
    total_time += dt
    T = m._TABLES
    n_grids, n_points, n_filters, cache_ver, lost = EXPECT[law]

    print(f"parsed in {dt:.2f} s")

    print("\n1. Answers are unchanged")
    for args, keys, expected in REFERENCE[law]:
        r = m.compute_ldcs(*args)
        ok = all(abs(r[k] - e) < 1e-9 for k, e in zip(keys, expected))
        check(f"{args[3]} / {args[4]} at Teff {args[0]}", ok,
              "  ".join(f"{k}={r[k]}" for k in keys))
    at2 = {k for k in T if k[2] == m.DEFAULT_XI}
    check(f"{n_grids} grids at the default velocity", len(at2) == n_grids, f"found {len(at2)}")
    pts = sum(len(T[k]["data"]) for k in at2)
    check(f"{n_points:,} grid points at the default velocity", pts == n_points, f"found {pts:,}")
    check(f"{n_filters} filters at the default velocity",
          len(m.get_available_filters()) == n_filters,
          f"found {len(m.get_available_filters())}")

    print("\n2. The four new velocities are loaded")
    per = collections.defaultdict(set)
    for (s, c, x, mod) in T:
        per[x].add((s, c, mod))
    check("all five velocities present", sorted(per) == [0.0, 1.0, 2.0, 4.0, 8.0], str(sorted(per)))
    counts = {x: len(per[x]) for x in sorted(per)}
    check("equal grid counts at the four non-standard velocities",
          len({counts[x] for x in (0.0, 1.0, 4.0, 8.0)}) == 1,
          "  ".join(f"{x:g}:{counts[x]}" for x in sorted(counts)))

    print("\n3. The governing rule holds")
    strays = [k for k in T if k[2] != m.DEFAULT_XI and k[3] != "ATLAS"]
    check("any velocity other than 2.0 means ATLAS only", not strays,
          f"{len(strays)} stray grids" if strays else "")

    print("\n4. Filter availability changes as predicted")
    f2 = {x["code"] for x in m.get_available_filters(2.0)}
    f8 = {x["code"] for x in m.get_available_filters(8.0)}
    check("the right filters are lost at a non-standard velocity",
          f2 - f8 == lost, f"{len(f2)} -> {len(f8)}, lost {sorted(f2 - f8)}")

    print("\n5. Refusals fire")
    def refused(*a):
        try:
            m.compute_ldcs(*a); return None
        except ValueError as e:
            return str(e)
    any_phx = sorted(c for (s, c, x, mo) in T if x == 2.0 and mo == "PHOENIX")
    if any_phx:
        msg = refused(6000, 4.5, 0.0, any_phx[0], "PHOENIX", 8.0)
        check(f"PHOENIX ({any_phx[0]}) at velocity 8", msg is not None,
              (msg[:64] + "...") if msg else "NOT REFUSED")
    any_atl = sorted(c for (s, c, x, mo) in T if x == 8.0 and mo == "ATLAS")
    msg = refused(6000, 4.5, 0.0, any_atl[0], "ATLAS", 3.0)
    check("a velocity Claret never published", msg is not None,
          (msg[:64] + "...") if msg else "NOT REFUSED")
    msg = refused(6000, 4.5, -0.5, any_atl[0], "ATLAS", 8.0)
    check("non-solar metallicity at velocity 8", msg is not None,
          (msg[:64] + "...") if msg else "NOT REFUSED")

    print("\n6. The cache guard was raised")
    check(f"CACHE_VERSION is {cache_ver}", m.CACHE_VERSION == cache_ver,
          f"found {m.CACHE_VERSION}")

print("\n" + "=" * 64)
if fails:
    print(f"{len(fails)} CHECK(S) FAILED. Do not commit.")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print(f"All checks passed in all three engines.")
print(f"Total cold parse time for all three: {total_time:.2f} s.")
print("Safe to commit. It still has to be tested on staging before production.")
sys.exit(0)
