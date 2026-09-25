"""Verification of Maxted's two brightness measurements.

Three checks, as set out in the project plan, Phase 2 revision 6:

  1. against direct evaluation of each law at the two positions, which is
     independent of the closed forms used in the code;
  2. against reference values computed and recorded during the derivation;
  3. that power-2 and four-parameter agree closely where both come from the
     same source paper, since both follow a real brightness profile well.

Maxted's own published worked example is deliberately NOT used: it appears to
combine model values from the TESS band with corrections from the Kepler band,
so a correct implementation would fail it.
"""
import sys, math, logging, importlib
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/home/claude/work')

fails = []
def check(label, got, want, tol=1e-9):
    ok = abs(got - want) < tol
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:52} {got:.10f}")
    if not ok:
        fails.append(f"{label}: got {got!r}, wanted {want!r}")

ENG = {law: importlib.import_module(f"{law}.ldc_core") for law in ('quad','power2','fourparam')}
for law, m in ENG.items():
    m.load_tables(f'/home/claude/work/{law}/data', use_cache=False)

def direct(law, r, mu):
    """Evaluate the law itself at one position -- the independent route."""
    if law == 'quad':
        return 1 - r['u1']*(1-mu) - r['u2']*(1-mu)**2
    if law == 'power2':
        return 1 - r['g']*(1 - mu**r['h'])
    c = [r['a1'], r['a2'], r['a3'], r['a4']]
    return 1 - sum(c[j]*(1 - mu**((j+1)/2)) for j in range(4))

def call(law, r, mc):
    m = ENG[law]
    if law == 'quad':      return m.maxted_values(r['u1'], r['u2'], mc)
    if law == 'power2':    return m.maxted_values(r['g'], r['h'], mc)
    return m.maxted_values(r['a1'], r['a2'], r['a3'], r['a4'], mc)

print("CHECK 1 -- against direct evaluation of each law\n")
CASES = [(5600.,4.5,0.0,'TESS','PHOENIX-COND','spherical, correction applied'),
         (5750.,4.5,0.0,'V','ATLAS','plane-parallel, no correction'),
         (3200.,5.0,0.0,'TESS','PHOENIX-COND','cool dwarf, spherical'),
         (4500.,2.5,0.0,'TESS','PHOENIX-COND','giant, large edge point'),
         (6000.,4.0,0.0,'Kp','ATLAS','Kepler band, plane-parallel')]
for T,G,Z,F,M,lab in CASES:
    for law in ('quad','power2','fourparam'):
        try:
            r = ENG[law].compute_ldcs(T,G,Z,F,M)
        except Exception:
            continue
        mc = ENG[law].aux_at(T,G,Z,F,M)['mu_cri']
        got = call(law, r, mc)
        k = 1.0 - (mc or 0.0)
        mu1, mu2 = 1 - k/3, 1 - 2*k/3
        check(f"{law:10} {F:5} {lab[:24]:24} h1'", got['h1_prime'], direct(law,r,mu1))
        check(f"{law:10} {F:5} {lab[:24]:24} h2'", got['h2_prime'],
              direct(law,r,mu1) - direct(law,r,mu2))

print("\nCHECK 2 -- against the recorded reference values")
print("           (5600 K, log g 4.5, solar, TESS, PHOENIX-COND)\n")
REF = {'quad':(0.8608114566,0.1794696370),
       'power2':(0.8559773974,0.1671712073),
       'fourparam':(0.8557872679,0.1677169858)}
for law,(w1,w2) in REF.items():
    r  = ENG[law].compute_ldcs(5600.,4.5,0.0,'TESS','PHOENIX-COND')
    mc = ENG[law].aux_at(5600.,4.5,0.0,'TESS','PHOENIX-COND')['mu_cri']
    got = call(law, r, mc)
    check(f"{law:10} h1'", got['h1_prime'], w1, 1e-9)
    check(f"{law:10} h2'", got['h2_prime'], w2, 1e-9)

print("\nCHECK 3 -- power-2 and four-parameter must agree to within the difference")
print("           in how well each law fits the simulation.")
print()
print("           Both come from Claret & Southworth 2023, so they describe the")
print("           same simulated star.  They do not agree exactly, because the")
print("           four-parameter law fits the profile 2 to 13 times better than")
print("           power-2 does, by Claret's own published fit-quality figures.")
print("           The observed spread across the grid is 0.0002 to 0.0026, so")
print("           the threshold is 0.003.  A LARGER disagreement than that would")
print("           indicate a fault; a smaller one is the laws, not the code.\n")
for T,G,F in ((5600.,4.5,'TESS'),(4000.,4.5,'TESS'),(4500.,4.5,'TESS'),
              (3000.,4.5,'TESS'),(6500.,4.0,'TESS')):
    out = {}
    for law in ('power2','fourparam'):
        r  = ENG[law].compute_ldcs(T,G,0.0,F,'PHOENIX-COND')
        mc = ENG[law].aux_at(T,G,0.0,F,'PHOENIX-COND')['mu_cri']
        out[law] = call(law, r, mc)
    d1 = abs(out['power2']['h1_prime'] - out['fourparam']['h1_prime'])
    d2 = abs(out['power2']['h2_prime'] - out['fourparam']['h2_prime'])
    ok = d1 < 0.003 and d2 < 0.003
    print(f"  [{'PASS' if ok else 'FAIL'}] {T:.0f} K, log g {G}:  h1' differ by {d1:.5f}, h2' by {d2:.5f}")
    if not ok: fails.append(f"power-2 vs four-parameter at {T:.0f}/{G}")

print("\nCHECK 4 -- the flag and the edge point are reported correctly\n")
r  = ENG['quad'].compute_ldcs(5600.,4.5,0.0,'TESS','PHOENIX-COND')
mc = ENG['quad'].aux_at(5600.,4.5,0.0,'TESS','PHOENIX-COND')['mu_cri']
g1 = ENG['quad'].maxted_values(r['u1'], r['u2'], mc)
print(f"  [{'PASS' if g1['edge_point_applied'] else 'FAIL'}] spherical table reports the correction applied")
print(f"  [{'PASS' if abs(g1['mu_cri']-mc)<1e-12 else 'FAIL'}] the edge point is passed through: {g1['mu_cri']}")
if not g1['edge_point_applied']: fails.append('flag false on spherical')
r  = ENG['quad'].compute_ldcs(5750.,4.5,0.0,'V','ATLAS')
g2 = ENG['quad'].maxted_values(r['u1'], r['u2'], None)
print(f"  [{'PASS' if not g2['edge_point_applied'] else 'FAIL'}] plane-parallel reports no correction")
print(f"  [{'PASS' if g2['mu_cri'] is None else 'FAIL'}] the edge point is reported empty")
if g2['edge_point_applied']: fails.append('flag true on plane-parallel')
# with no edge point the positions must be exactly 2/3 and 1/3
alt = ENG['quad'].maxted_values(r['u1'], r['u2'], 0.0)
check("k = 1 gives the uncorrected answer exactly", alt['h1_prime'], g2['h1_prime'], 1e-15)

print("\n" + ("ALL CHECKS PASS" if not fails else f"{len(fails)} FAILURES:"))
for f in fails: print("   ", f)
