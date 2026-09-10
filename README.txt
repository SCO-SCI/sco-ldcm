SCO-LDC GENERAL (Quadratic + Power-2 + Four-parameter)
======================================================

A single FastAPI service that serves stellar limb-darkening coefficients for
three laws, by trilinear interpolation of published Claret tables. Each law is
an isolated sub-application with its own engine and data; a parent app mounts
them, owns the shared resolver subsystem, and serves the law-switcher frontend.

  Quadratic       u1, u2          (production law; see LEGACY API CONTRACT)
  Power-2         g, h
  Four-parameter  a1, a2, a3, a4

Since v5 (September 2026) the ATLAS tables are held at all five published
microturbulent velocities (ξ = 0, 1, 2, 4, 8 km/s) and the prefixed routes
accept ξ as a parameter. The legacy /api/... routes are untouched by this;
see MICROTURBULENT VELOCITY below.


STRUCTURE
  parent_app.py          Mounts all three sub-apps, owns resolvers/scheduler,
                         registers the legacy /api/... alias, serves frontend
  quad/                  Quadratic sub-app          (app version 3.1.0)
    app.py               package-relative imports; no resolver load/scheduler
    ldc_core.py          quadratic engine
    build_cache.py       builds data/tables.pkl
    __init__.py
    data/                tableab.dat, table5.dat, table8.dat, table2.dat,
                         CBBQUADRATIC.txt, tables.pkl (cache version 4)
  power2/                Power-2 sub-app            (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          power-2 engine
    build_cache.py
    __init__.py
    data/c22/            table1.dat, table2.dat, table3.dat   (ATLAS, CS22)
    data/c23/            table2.dat, table6.dat, table10.dat  (PHOENIX-COND, CS23)
    data/cbb/            cbbpower2.txt                        (CBB, CMG2022)
    data/tables.pkl      (cache version 2)
  fourparam/             Four-parameter sub-app     (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          four-parameter engine
    build_cache.py
    __init__.py
    data/c11/            tableeq5.dat                         (ATLAS + PHOENIX, CB2011)
    data/c23/            table4.dat, table8.dat, table12.dat  (PHOENIX-COND, CS2023)
    data/tables.pkl      (cache version 2)
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
    api/filters          GET      optional ξ (query parameter xi)
    api/capabilities     GET      every filter x model x ξ grid, with ranges
    api/compute          GET      optional ξ (query parameter xi)
    api/resolve          GET
    admin/cache-status   GET
    /                    small JSON pointer (frontend is served by the parent)

  The legacy alias has no capabilities route, and ξ is ignored on it.

  /                  law-switcher frontend (static/, html=True)


LEGACY API CONTRACT  (important)
  The unprefixed /api/... routes MUST keep serving the quadratic law
  unchanged: NASA/TESS and other callers depend on sco-ldc.com/api/compute
  returning u1/u2. Nothing done in this repository may change what those
  four routes return, in content, shape or wording.

  parent_app.py implements this by re-registering the quad sub-app's own
  handlers at the unprefixed paths, so the legacy API runs the same engine
  as /quad/api/... and is permanently quadratic. Since the velocity work
  three of the four are registered through thin wrappers that pin the
  pre-velocity behaviour:
    _legacy_filters   takes no parameters; returns the 2 km/s catalog
    _legacy_compute   takes only teff, logg, feh, filter, model; computes
                      at ξ = 2 and drops the xi field from the response
    _legacy_health    reports the 2 km/s table row counts (179,645 for
                      tableab.dat, 7,695 for CBBQUADRATIC.txt and table8.dat,
                      574 and 502 for table5.dat and table2.dat) while
                      /quad/api/health reports all rows loaded
  /api/resolve is bound directly. Before any deploy, byte-compare all four
  legacy routes between production and staging, including error paths.
  New laws and new features are reached only via the prefixes. Do not
  repoint /api/... at another law.


MICROTURBULENT VELOCITY ξ  (v5, September 2026)
  What is loaded
    Every ATLAS table, in every law, at ξ = 0, 1, 2, 4 and 8 km/s. The
    tables at 0, 1, 4 and 8 exist for ATLAS at solar metallicity only.
    Every PHOENIX and PHOENIX-COND table exists at ξ = 2 only. Table keys
    in each engine's _TABLES are (source, filter, ξ, storage model).
    Grid counts: quad 146, power2 138, fourparam 139 (46/46/47 at ξ = 2,
    then one per ATLAS filter at each other velocity).

  Request rules (prefixed compute routes)
    xi omitted            -> ξ = 2, identical to pre-velocity behaviour
    xi not in {0,1,2,4,8} -> 400 "coefficients are published only at
                             0, 1, 2, 4, 8 km/s"
    xi != 2 with a PHOENIX-family model
                          -> 400 "the PHOENIX table for filter X is
                             published only at 2 km/s"
    xi != 2 with feh != 0 -> 400 by the existing solar-only metallicity
                             rule
    Every prefixed compute response carries "xi": <velocity used>.
    Prefixed api/filters?xi=N lists only the models with a table at N.

  How the velocity tables differ from ξ = 2
    Same envelope (3500-50000 K, log g 0-5), same temperature nodes except
    that the half-step nodes 37500, 42500 and 47500 K do not exist at
    ξ != 2. Populated solar cells: ξ=2 476, ξ=0 and 1 485, ξ=4 465,
    ξ=8 456. ξ = 0 and 1 add nine low-gravity cells the 2 km/s grid lacks;
    ξ = 4 lacks eleven cells and ξ = 8 twenty, all at the low-gravity edge
    of the hot stars (e.g. 38000 K at log g 4.0 is refused at 4 and 8).

  The ATLAS grid itself  (applies at every velocity, unchanged since v4)
    The solar and non-solar metallicities have different temperature
    nodes: solar every 250 K to 13000 K then every 1000 K; non-solar every
    250 K to 10000 K, every 500 K to 13000 K, every 1000 K to 35000 K,
    then every 2500 K to 50000 K. Interpolation brackets on the union, so
    for a non-solar metallicity between 10000 and 13000 K and above
    35000 K only requests exactly on a non-solar node succeed. The lowest
    available log g rises with temperature (0.0 to 6000 K ... 5.0 only at
    50000 K). The full node lists, gravity floors and holes of every grid
    are in the document "SCO-LDC v5: Reference to the Loaded Tables" and
    in the API reference, compute section.

  Where the code is
    <law>/ldc_core.py     SUPPORTED_XI, DEFAULT_XI, _norm_xi, the ξ-keyed
                          parsers, get_available_filters(xi),
                          get_capabilities(), row_counts_at_xi() (quad)
    <law>/app.py          xi parameter on filters and compute; the
                          capabilities route
    parent_app.py         the three legacy wrappers
    static/index.html     reads api/capabilities; the dropdown tags and
                          the message-area notes are driven from it


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
    - /api/compute still returns u1/u2 (legacy contract) and carries no
      xi field; /api/filters and /api/compute byte-identical to the
      previous deploy for a fixed set of requests, error paths included
    - /api/health reports the 2 km/s counts (tableab.dat 179645); the
      prefixed /quad/api/health reports all rows loaded (223138)
    - each /LAW/api/health reports its expected table counts
    - /LAW/api/capabilities responds under all three prefixes
    - a prefixed compute with xi=8 returns a different value from xi=2
      for an ATLAS filter and is refused for a PHOENIX-family model
    - the frontend law switcher reaches all three backends
