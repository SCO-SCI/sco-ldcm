#!/usr/bin/env python3
"""
SCO-LDC v5, Goal 1 — verification for the QUAD engine change.

Run from the repository root AFTER v5_step1_quad.py:

    cd C:\\Users\\edkmu\\Desktop\\SCO-LDC_MAIN\\SCO-LDC_V5\\sco-ldcv5
    python v5_step1_verify.py

Reads nothing but the repository. Touches no network and no service. It parses
the tables from scratch, ignoring any cache, and checks eleven things.

The important one is the first: at the default velocity the patched engine must
produce exactly what the service produces today. If that fails, nothing else
matters.
"""
import sys, os, time

if not os.path.exists(os.path.join("quad", "ldc_core.py")):
    print("ERROR: run this from the repository root.")
    sys.exit(1)

sys.path.insert(0, os.path.join(os.getcwd(), "quad"))
import ldc_core as q

fails = []
def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(label)

print("Parsing all quad tables from source, cache ignored...")
t0 = time.perf_counter()
counts = q.load_tables(os.path.join(os.getcwd(), "quad", "data"), use_cache=False)
elapsed = time.perf_counter() - t0
print(f"done in {elapsed:.2f} s\n")

T = q._TABLES

# ---- 1. nothing has changed at the default velocity -----------------------
print("1. Behaviour at the default velocity is unchanged")
REFERENCE = {
    (6000, 4.5,  0.0, "V",      "ATLAS"):        (0.4152,   0.286),
    (5150, 4.4, -0.05, "V",     "ATLAS"):        (0.606146, 0.15932),
    (3000, 3.5,  0.0, "Kp",     "PHOENIX"):      (0.5257,   0.3371),
    (6000, 4.5,  0.0, "TESS",   "PHOENIX-COND"): (0.3362,   0.2251),
}
for args, (eu1, eu2) in REFERENCE.items():
    r = q.compute_ldcs(*args)
    ok = abs(r["u1"] - eu1) < 1e-9 and abs(r["u2"] - eu2) < 1e-9
    check(f"compute{args[3:]} at Teff {args[0]}", ok,
          f"u1={r['u1']} u2={r['u2']}")

grids_at_default = {k for k in T if k[2] == q.DEFAULT_XI}
check("46 grids at the default velocity", len(grids_at_default) == 46,
      f"found {len(grids_at_default)}")
check("196,111 grid points at the default velocity",
      sum(len(T[k]["data"]) for k in grids_at_default) == 196111,
      f"found {sum(len(T[k]['data']) for k in grids_at_default):,}")
check("26 filters listed at the default velocity",
      len(q.get_available_filters()) == 26,
      f"found {len(q.get_available_filters())}")

# ---- 2. the new capability exists ----------------------------------------
print("\n2. The four new velocities are loaded")
per = {}
for (s, c, x, m) in T:
    per.setdefault(x, set()).add((s, c, m))
check("all five velocities present", sorted(per) == [0.0, 1.0, 2.0, 4.0, 8.0],
      str(sorted(per)))
check("25 ATLAS grids at each non-standard velocity",
      all(len(per[x]) == 25 for x in (0.0, 1.0, 4.0, 8.0)),
      ", ".join(f"{x:g}:{len(per[x])}" for x in (0.0, 1.0, 4.0, 8.0)))

# ---- 3. the governing rule -----------------------------------------------
print("\n3. The governing rule holds")
strays = [k for k in T if k[2] != q.DEFAULT_XI and k[3] != "ATLAS"]
check("any velocity other than 2.0 means ATLAS only", not strays,
      f"{len(strays)} stray grids" if strays else "")

# ---- 4. refusals ----------------------------------------------------------
print("\n4. Refusals fire, with a message that names the reason")
def refused(*args):
    try:
        q.compute_ldcs(*args); return None
    except ValueError as e:
        return str(e)

for args, why in [
    ((6000, 4.5,  0.0, "V",      "PHOENIX",      8.0), "PHOENIX at velocity 8"),
    ((6000, 4.5,  0.0, "TESS",   "PHOENIX-COND", 8.0), "TESS, which has no velocity axis"),
    ((6000, 4.5,  0.0, "CHEOPS", "PHOENIX-COND", 4.0), "CHEOPS PHOENIX, no velocity axis"),
    ((6000, 4.5, -0.5, "V",      "ATLAS",        8.0), "non-solar metallicity at velocity 8"),
    ((6000, 4.5,  0.0, "V",      "ATLAS",        3.0), "a velocity Claret never published"),
]:
    msg = refused(*args)
    check(why, msg is not None, (msg[:70] + "...") if msg else "NOT REFUSED")

# ---- 5. what must NOT be refused -----------------------------------------
print("\n5. New capability is reachable, not over-refused")
for xi, t, g in ((0.0, 40000, 4.0), (1.0, 8750, 1.0)):
    try:
        r = q.compute_ldcs(t, g, 0.0, "V", "ATLAS", xi)
        check(f"node at velocity {xi:g}, Teff {t}, log g {g}", True, f"u1={r['u1']:.4f}")
    except ValueError as e:
        check(f"node at velocity {xi:g}, Teff {t}, log g {g}", False, str(e)[:60])

# ---- 6. TESS disappears at non-standard velocity --------------------------
print("\n6. Filter availability changes as predicted")
f2 = {x["code"] for x in q.get_available_filters(2.0)}
f8 = {x["code"] for x in q.get_available_filters(8.0)}
check("26 filters at 2.0, 25 at 8.0", len(f2) == 26 and len(f8) == 25,
      f"{len(f2)} and {len(f8)}")
check("TESS is the only one lost", f2 - f8 == {"TESS"}, str(sorted(f2 - f8)))

# ---- 7. the cache guard ---------------------------------------------------
print("\n7. The cache version was raised")
check("CACHE_VERSION is 4", q.CACHE_VERSION == 4, f"found {q.CACHE_VERSION}")

print("\n" + "=" * 62)
if fails:
    print(f"{len(fails)} CHECK(S) FAILED. Do not commit.")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("All checks passed. Cold parse took %.2f s." % elapsed)
print("Still to do before committing: the power-2 and four-parameter engines.")
sys.exit(0)
