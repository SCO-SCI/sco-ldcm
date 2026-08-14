SCO-LDC GENERAL (Quadratic + Power-2 + Four-parameter)
======================================================

A single FastAPI service that serves stellar limb-darkening coefficients for
three laws, by trilinear interpolation of published Claret tables. Each law is
an isolated sub-application with its own engine and data; a parent app mounts
them, owns the shared resolver subsystem, and serves the law-switcher frontend.

  Quadratic       u1, u2          (production law; see LEGACY API CONTRACT)
  Power-2         g, h
  Four-parameter  a1, a2, a3, a4


STRUCTURE
  parent_app.py          Mounts all three sub-apps, owns resolvers/scheduler,
                         registers the legacy /api/... alias, serves frontend
  quad/                  Quadratic sub-app          (app version 3.1.0)
    app.py               package-relative imports; no resolver load/scheduler
    ldc_core.py          quadratic engine
    build_cache.py       builds data/tables.pkl
    __init__.py
    data/                tableab.dat, table5.dat, table8.dat, table2.dat,
                         CBBQUADRATIC.txt, tables.pkl
  power2/                Power-2 sub-app            (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          power-2 engine
    build_cache.py
    __init__.py
    data/c22/            table1.dat, table2.dat, table3.dat   (ATLAS, CS22)
    data/c23/            table2.dat, table6.dat, table10.dat  (PHOENIX-COND, CS23)
    data/cbb/            cbbpower2.txt                        (CBB, CMG2022)
    data/tables.pkl
  fourparam/             Four-parameter sub-app     (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          four-parameter engine
    build_cache.py
    __init__.py
    data/c11/            tableeq5.dat                         (ATLAS + PHOENIX, CB2011)
    data/c23/            table4.dat, table8.dat, table12.dat  (PHOENIX-COND, CS2023)
    data/tables.pkl
  shared/                Shared resolver subsystem (one copy, used by all three)
    nea_resolver.py
    exofop_resolver.py
    __init__.py
    data/                nea_parameters_fallback.tsv, exofop_toi_fallback.tsv
  static/
    index.html           merged law-switcher frontend
    sco_ldc_api_reference.html
    favicon.ico, icons/
  requirements.txt       fastapi, uvicorn[standard], gunicorn, httpx
  Procfile               entry point is parent_app:app  (NOT app:app)


ROUTES
  Parent (legacy alias, permanently QUADRATIC):
    /api/health      GET, HEAD
    /api/filters     GET
    /api/compute     GET
    /api/resolve     GET

  Per-law prefixes -- each sub-app exposes the same route set:
    /quad/api/...        quadratic
    /power2/api/...      power-2
    /fourparam/api/...   four-parameter

    api/health           GET, HEAD
    api/filters          GET
    api/compute          GET
    api/resolve          GET
    admin/cache-status   GET
    /                    small JSON pointer (frontend is served by the parent)

  /                  law-switcher frontend (static/, html=True)


LEGACY API CONTRACT  (important)
  The unprefixed /api/... routes MUST keep serving the quadratic law
  unchanged: NASA/TESS and other callers depend on sco-ldc.com/api/compute
  returning u1/u2. parent_app.py implements this by importing the quad
  sub-app's own handler functions and re-registering them at the unprefixed
  paths, so the legacy API is the SAME code path as /quad/api/... (zero
  drift) and is permanently quadratic. New laws are reached only via their
  own prefixes. Do not repoint /api/... at another law.


RUN LOCALLY
  pip install -r requirements.txt
  uvicorn parent_app:app --reload
  Then open http://127.0.0.1:8000/

  - Default law is Quadratic. Use the "Limb-darkening law" dropdown to switch.
  - Backends: /quad/api/...  /power2/api/...  /fourparam/api/...

  Quick checks:
    curl "http://127.0.0.1:8000/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS"
    curl "http://127.0.0.1:8000/power2/api/compute?teff=6000&logg=4.5&feh=0.0&filter=Kp&model=ATLAS"
    curl "http://127.0.0.1:8000/fourparam/api/compute?teff=6000&logg=4.5&feh=0.0&filter=V&model=ATLAS"


ARCHITECTURE NOTES
  1. Each sub-app has its own ldc_core and its own _TABLES store. The three
     engines are independent; a filter/model present in one law is not
     necessarily present in another.
  2. Sub-app imports are package-relative:
       from quad import ldc_core        (resp. power2, fourparam)
       from shared import nea_resolver / exofop_resolver
  3. Sub-apps do NOT load resolver caches and do NOT start a refresh
     scheduler. parent_app.py loads the shared NEA/ExoFOP caches once at
     startup and runs a single refresh scheduler (17:00 UTC) for all three.
  4. Each sub-app's root "/" returns a small JSON pointer rather than a
     frontend; the parent serves the single merged frontend at "/".
  5. All three sub-apps enable permissive CORS for GET.
  6. Data caching: each law's data/tables.pkl is a prebuilt cache produced by
     that law's build_cache.py. Rebuild it after changing any .dat/.txt.


MAXTED (2018) REPARAMETERIZATION -- CURRENTLY DISABLED
  The power-2 engine implements the Maxted h1/h2 reparameterization in
  power2/ldc_core.py :: maxted_params(), including the Short et al. (2019)
  realizable-region test. The function is intact and fully working, but its
  output is NOT exposed anywhere:
    - power2/ldc_core.py   call site and the three response keys
                           ("h1", "h2", "maxted_valid") are commented out
    - static/index.html    the derived-values panel is commented out and
                           renderDerived() is forced off; the clipboard text
                           no longer appends h1/h2
    - static/sco_ldc_api_reference.html
                           all Maxted documentation removed
  Reason: Will update to Maxted (2023, MNRAS 519, 3723)  


KNOWN VESTIGIAL FILES  (safe to delete; not imported by anything)
  quad/nea_resolver.py         superseded by shared/nea_resolver.py
  quad/exofop_resolver.py      superseded by shared/exofop_resolver.py
  power2/nea_resolver.py       superseded by shared/nea_resolver.py
  power2/exofop_resolver.py    superseded by shared/exofop_resolver.py
  quad/data/*_fallback.tsv     superseded by shared/data/
  power2/data/*_fallback.tsv   superseded by shared/data/
  (fourparam/ was added after the shared/ refactor and has no such leftovers.)


DEPLOY
  Start command must use parent_app:app (the Procfile here already does).
  Keep --workers 1 -- a single process holds all three engines plus the
  shared resolver cache; multiple workers would duplicate the tables in
  memory and run redundant refresh schedulers.

  Verify after deploy:
    - /api/compute still returns u1/u2 (legacy contract)
    - each /LAW/api/health reports its expected table counts
    - the frontend law switcher reaches all three backends
