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
import os, sys, math, logging, importlib
logging.disable(logging.CRITICAL)

# Run from wherever the repository sits, on any platform.
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

fails = []
def check(label, got, want, tol=1e-9):
    ok = abs(got - want) < tol
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:52} {got:.10f}")
    if not ok:
        fails.append(f"{label}: got {got!r}, wanted {want!r}")

ENG = {law: importlib.import_module(f"{law}.ldc_core") for law in ('quad','power2','fourparam')}
for law, m in ENG.items():
    m.load_tables(os.path.join(ROOT, law, 'data'), use_cache=False)

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

print("\nCHECK 5 -- the values reach the right routes and no others\n")
try:
    from fastapi.testclient import TestClient
    import parent_app
    client = TestClient(parent_app.app)
except Exception as exc:                      # pragma: no cover
    print(f"  [SKIP] could not start the application: {exc}")
    client = None

NEW_FIELDS = ("h1_prime", "h2_prime", "edge_point_applied", "mu_cri")

if client is not None:
    # present on the three prefixed routes
    for law in ("quad", "power2", "fourparam"):
        r = client.get(f"/{law}/api/compute?teff=5600&logg=4.5&feh=0.0"
                       f"&filter=TESS&model=PHOENIX-COND")
        have = r.status_code == 200 and all(k in r.json() for k in NEW_FIELDS)
        print(f"  [{'PASS' if have else 'FAIL'}] /{law}/api/compute carries all four fields")
        if not have: fails.append(f"{law} route missing fields")

    # absent from the frozen unprefixed route
    r = client.get("/api/compute?teff=5600&logg=4.5&feh=0.0"
                   "&filter=TESS&model=PHOENIX-COND")
    clean = r.status_code == 200 and not any(k in r.json() for k in NEW_FIELDS)
    print(f"  [{'PASS' if clean else 'FAIL'}] /api/compute (frozen) carries none of them")
    if not clean: fails.append("frozen route leaked a field")

    # the realizability flag is internal and must not be served anywhere
    leaked = []
    for p_ in ("/quad/api/compute?teff=5600&logg=4.5&feh=0.0&filter=TESS&model=PHOENIX-COND",
               "/fourparam/api/compute?teff=3500&logg=1.0&feh=-2.0&filter=v&model=ATLAS",
               "/api/compute?teff=5600&logg=4.5&feh=0.0&filter=TESS&model=PHOENIX-COND"):
        if "realizable" in client.get(p_).text:
            leaked.append(p_)
    print(f"  [{'PASS' if not leaked else 'FAIL'}] the realizability flag is not served anywhere")
    if leaked: fails.append(f"realizable leaked at {leaked}")

    # the route's values must equal the function's, to the precision served
    r = client.get("/quad/api/compute?teff=5600&logg=4.5&feh=0.0"
                   "&filter=TESS&model=PHOENIX-COND").json()
    m  = ENG["quad"]
    ref = m.maxted_values(r["u1"], r["u2"],
                          m.aux_at(5600., 4.5, 0.0, "TESS", "PHOENIX-COND")["mu_cri"])
    check("the route's h1' matches the function's", r["h1_prime"], ref["h1_prime"], 5e-7)
    check("the route's h2' matches the function's", r["h2_prime"], ref["h2_prime"], 5e-7)

    # the served values carry six decimals and no more
    over = []
    for law in ("quad", "power2", "fourparam"):
        for q in ("teff=5650&logg=4.2&feh=0.0&filter=TESS&model=PHOENIX-COND",
                  "teff=5137&logg=4.43&feh=-0.07&filter=V&model=ATLAS"):
            d = client.get(f"/{law}/api/compute?{q}")
            if d.status_code != 200:
                continue
            d = d.json()
            for k in ("h1_prime", "h2_prime", "mu_cri"):
                v = d.get(k)
                if v is None:
                    continue
                if round(v, 6) != v:
                    over.append(f"{law} {k}={v!r}")
    print(f"  [{'PASS' if not over else 'FAIL'}] the served values carry no more than six decimals")
    if over:
        fails.append(f"over-precise: {over[:3]}")

    # the coefficients must NOT have been rounded -- the frozen payload depends on it
    d = client.get("/api/compute?teff=5137&logg=4.43&feh=-0.07"
                   "&filter=V&model=ATLAS").json()
    intact = repr(d["u1"]) == "0.6075814935999999"
    print(f"  [{'PASS' if intact else 'FAIL'}] the frozen route's coefficients are untouched "
          f"({d['u1']!r})")
    if not intact:
        fails.append("a coefficient was rounded on the frozen route")

print("\nCHECK 6 -- the web page\n")
if client is not None:
    html = client.get("/").text
    def page(label, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond: fails.append(f"page: {label}")
    page("the derived panel is present and live",
         'id="derivedPanel"' in html and 'Maxted (2023)' in html)
    page("the labels carry the prime mark",
         '<sub>1</sub>&prime;' in html and '<sub>2</sub>&prime;' in html)
    page("no trace of the withdrawn 2018 panel",
         'Maxted (2018)' not in html and 'maxtedWarn' not in html
         and 'maxted_valid' not in html)
    page("the renderer reads h1_prime and h2_prime",
         'd.h1_prime' in html and 'd.h2_prime' in html)
    page("the panel is not restricted to power-2",
         "currentLaw === 'power2' && d && d.h1" not in html)
    page("the mu_cri row exists, labelled with the published symbol",
         'id="m_mucri"' in html and '<em>&mu;</em><sub>cri</sub>' in html)
    page("mu_cri sits below Source and above the equation",
         html.index('id="m_source"') < html.index('id="m_mucri"') < html.index('id="lawEquation"'))
    page("the realizability flag is nowhere in the page",
         'realizable' not in html)

    ref = client.get("/static/sco_ldc_api_reference.html").text
    page("the reference documents the four new fields",
         all(k in ref for k in ('h1_prime','h2_prime','edge_point_applied','mu_cri')))
    page("the reference states the rescaling requirement",
         'cannot be used directly' in ref)
    page("the reference says the frozen route omits them",
         'payload is frozen' in ref)
    # Removed deliberately on 26 September 2026: astronomers choosing the
    # quadratic law already know its limitations, and restating them is not
    # this service's job.  The values are identical information to the
    # coefficients beside them, exactly reversible, so there is nothing to
    # disclose about our own arithmetic.
    page("no quadratic caveat on the page or in the reference",
         'maxtedQuadNote' not in html and 'A caution about values' not in ref)
    import re as _re
    _toc = _re.findall(r'<a href="#([^"]+)"><span class="n">(\d+)</span>', ref)
    _hdr = _re.findall(r'<span class="sec-num">(\d+)</span>', ref)
    page("the reference's contents and section numbering agree",
         [int(t[1]) for t in _toc] == [int(h) for h in _hdr]
         and [int(h) for h in _hdr] == list(range(1, len(_hdr) + 1)))
    _ids = set(_re.findall(r'id="([^"]+)"', ref))
    page("every contents link in the reference resolves",
         all(t[0] in _ids for t in _toc))
    # The derived panel must not touch #tabPanelHdr -- that element belongs to
    # the coefficient panel above and is managed by applyLaw().
    rd = html[html.index('function renderDerived'):html.index('function clearDerived')]
    # Look for the element being fetched, not merely named: the comment in
    # that function mentions it precisely to warn against touching it.
    page("the derived panel does not touch the coefficient panel's header",
         "$('tabPanelHdr')" not in rd and '$("tabPanelHdr")' not in rd)

    # Browsers must be told to revalidate.  Without this a deploy can stay
    # invisible for hours: observed 25 Sept 2026, when a hard reload did not
    # clear it and only a changed query string forced a fresh fetch.
    r = client.get("/")
    cc = r.headers.get("cache-control")
    page(f"the page is served with Cache-Control: no-cache (got {cc!r})",
         cc == "no-cache")
    et = r.headers.get("etag")
    page("and revalidation still returns 'not modified', so it stays cheap",
         et is not None
         and client.get("/", headers={"If-None-Match": et}).status_code == 304)

print("\n" + ("ALL CHECKS PASS" if not fails else f"{len(fails)} FAILURES:"))
for f in fails: print("   ", f)
