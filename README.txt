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

Since Phase 3 (October 2026) the power-2 and four-parameter engines also
hold the eleven JWST observing modes of Claret, Hauschildt & Torres (2025),
computed with the NewEra PHOENIX models and served under the model label
PHOENIX-NE at ξ = 1 km/s. The quadratic law has no JWST table, and the
legacy /api/... routes are untouched by this as well; see THE JWST TABLES
below.


STRUCTURE
  parent_app.py          Mounts all three sub-apps, owns resolvers/scheduler,
                         registers the legacy /api/... alias, serves frontend
  quad/                  Quadratic sub-app          (app version 3.1.0)
    app.py               package-relative imports; no resolver load/scheduler
    ldc_core.py          quadratic engine
    build_cache.py       builds data/tables.pkl
    __init__.py
    data/                tableab.dat, table5.dat, table8.dat, table2.dat,
                         CBBQUADRATIC.txt, tables.pkl (cache version 5)
  power2/                Power-2 sub-app            (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          power-2 engine
    build_cache.py
    __init__.py
    data/c22/            table1.dat, table2.dat, table3.dat   (ATLAS, CS22)
    data/c23/            table2.dat, table6.dat, table10.dat  (PHOENIX-COND, CS23)
    data/cbb/            cbbpower2.txt                        (CBB, CMG2022)
    data/c25/            table3.dat                (PHOENIX-NE, CHT25; the JWST modes)
    data/tables.pkl      (cache version 4)
  fourparam/             Four-parameter sub-app     (app version 4.0.0)
    app.py               same pattern as quad/app.py
    ldc_core.py          four-parameter engine
    build_cache.py
    __init__.py
    data/c11/            tableeq5.dat                         (ATLAS + PHOENIX, CB2011)
    data/c23/            table4.dat, table8.dat, table12.dat  (PHOENIX-COND, CS2023)
    data/c25/            table2.dat                (PHOENIX-NE, CHT25; the JWST modes)
    data/tables.pkl      (cache version 4)
  shared/                Code used by all three sub-apps (one copy)
    nea_resolver.py      the resolver subsystem
    exofop_resolver.py
    maxted_correction.py Maxted's (2023) empirical correction (Phase 2)
    jwst_modes.py        the eleven JWST modes: codes, display names, and the
                         parser for the two CHT25 files (Phase 3)
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
                      at ξ = 2 and drops the Phase 2 and Phase 3 fields
                      (parent_app.LEGACY_WITHHELD) from the response.
                      Since Phase 3 it calls quad/app.py :: compute_legacy,
                      the same implementation as the prefixed route except
                      that a filter the quadratic law does not hold is
                      still reported as "Unknown filter: 'X'", where the
                      prefixed /quad/api/compute names the laws that serve
                      a JWST mode instead
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
    Every PHOENIX and PHOENIX-COND table exists at ξ = 2 only, and the
    JWST (PHOENIX-NE) tables at ξ = 1 only. Table keys in each engine's
    _TABLES are (source, filter, ξ, storage model).
    Grid counts: quad 146, power2 149, fourparam 150 (46/46/47 at ξ = 2,
    then one per ATLAS filter at each other velocity, then the eleven
    JWST modes at ξ = 1 in power2 and fourparam).

  Request rules (prefixed compute routes)
    xi omitted            -> ξ = 2 when the chosen table has a 2 km/s
                             grid, identical to pre-velocity behaviour;
                             otherwise the one velocity the chosen table
                             has (the JWST modes: 1 km/s). The response's
                             xi field says which. This is the single-
                             velocity rule of Phase 3; it is a general
                             rule, not a JWST special case.
    xi not in {0,1,2,4,8} -> 400 "coefficients are published only at
                             0, 1, 2, 4, 8 km/s"
    xi != 2 with a PHOENIX-family model
                          -> 400 "the PHOENIX-COND table for filter X is
                             published only at 2 km/s" (the display model
                             name is used)
    xi != 1 with a JWST mode
                          -> 400 "the PHOENIX-NE table for filter X is
                             published only at 1 km/s"
    xi != 2 with feh != 0 -> 400 by the existing solar-only metallicity
                             rule
    Every prefixed compute response carries "xi": <velocity used>.
    Prefixed api/filters?xi=N lists only the models with a table at N.
    Prefixed api/filters with xi omitted lists what a compute request
    omitting xi can reach: every model at 2 km/s plus the single-velocity
    tables (the JWST modes), so it is a superset of api/filters?xi=2.

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
                          get_capabilities(), row_counts_at_xi() (quad),
                          and since Phase 3 _velocities_held() and
                          _resolve_xi() (the single-velocity rule)
    <law>/app.py          xi parameter on filters and compute; the
                          capabilities route
    parent_app.py         the three legacy wrappers
    static/index.html     reads api/capabilities; the dropdown tags and
                          the message-area notes are driven from it


THE JWST TABLES  (Phase 3, October 2026)
  What is loaded
    The eleven JWST observing modes of Claret, Hauschildt & Torres (2025,
    A&A 699, A97; CDS J/A+A/699/A97): NIRCam F210M, F322W2, F444W; NIRISS
    SOSS order 1 (SOSS1), SOSS order 2 (SOSS2), F277W; NIRSpec G235H,
    G235M, G395H, G395M, PRISM. Filter codes are exactly the strings of
    the published file; the instrument is in the display name (F277W is
    the NIRISS one), and the four NIRSpec gratings are shown with their
    blocking filter, as JWST names them (G235H/F170LP, G235M/F170LP,
    G395H/F290LP, G395M/F290LP). Power-2 (c25/table3.dat) and four-parameter
    (c25/table2.dat) only: the paper published no quadratic table for
    these modes, deliberately. 3,366 rows in each file, a complete grid
    of 51 temperatures x 6 gravities x 11 modes.
    Model label PHOENIX-NE: spherical PHOENIX models of the NewEra
    generation (Hauschildt et al. 2025), a different vintage from the
    PHOENIX-COND tables, so they are a separate storage key ("PHOENIX-NE",
    source "CHT25") and are never merged with PHOENIX/PHOENIX-COND.
    Grid: Teff 2400-7800 K (every 100 K to 7000 K, then every 200 K),
    log g 3.0-5.5 in steps of 0.5, solar composition, ξ = 1 km/s only.
    Every row carries an edge point (mu_cri), so the Phase 2 edge-point
    correction applies to every JWST point automatically; the code tests
    for the presence of an edge point, not for a model name. No Maxted
    (2023) empirical correction exists for any JWST mode.

  Request rules
    xi omitted, or xi=1   -> served at ξ = 1 (single-velocity rule)
    any other xi          -> 400 "the PHOENIX-NE table for filter X is
                             published only at 1 km/s"
    another model         -> 400 "filter X is available only with the
                             PHOENIX-NE model"
    PHOENIX-NE on an ordinary filter
                          -> 400 "filter X is available only with the
                             ... models" (power2, fourparam); the quad
                             engine keeps "no data for filter ..."
    feh != 0              -> 400 by the existing solar-only rule
    quadratic law, prefixed /quad/api/compute
                          -> 400 "X -- the JWST modes are served under the
                             power-2 and four-parameter laws only."
    quadratic law, legacy /api/compute
                          -> 400 "Unknown filter: 'X'", unchanged

  A hazard to know about (documented in the API reference, JWST section)
    The published power-2 fits are degenerate at a few cool, low-gravity
    nodes (F322W2 at log g 3.0, 2700-2900 K; G235H and G235M at log g 3.0,
    2500-2800 K: g in the tens to thousands with h near zero). The service
    interpolates the coefficients faithfully, as it does everywhere, and
    inside the cells next to those nodes the interpolated profile is one
    no real star could have (h1' far below zero for F322W2). The
    four-parameter table has no such nodes. The harness (layer 5) counts
    these cases and reports them without failing.

  Where the code is
    shared/jwst_modes.py          the modes, names, source tag, parser
    power2/ldc_core.py            _parse_cht25, the registry entries,
    fourparam/ldc_core.py         _resolve_xi, the refusal wording
    quad/ldc_core.py              served_by_another_law(), UnknownFilter
    quad/app.py                   _compute(), compute_legacy()
    static/index.html             PHOENIX-NE in LAW_CONFIG, the JWST
                                  category, resolveModelEntry()
    tests/harness/                layer 3 (xi-omitted catalogue), layer 4
                                  (the JWST refusal cases, the cross-law
                                  case), layer 5 (all velocities, the two
                                  reference stars), layer 1 live (two more
                                  legacy edge paths)


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
    curl "http://127.0.0.1:8000/power2/api/compute?teff=5800&logg=4.5&feh=0.0&filter=PRISM&model=PHOENIX-NE"
      (served at xi = 1; h1_prime 0.9115, h2_prime 0.1138 to four decimals)


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
  6. Data caching: each law's data/tables.pkl is a cache of the parsed
     tables, stamped with the engine's CACHE_VERSION. It is no longer
     committed (see .gitignore): a missing or stale cache is rebuilt by the
     service itself on its first start, in a few seconds. Each law's
     build_cache.py rebuilds it by hand and checks the row counts; run it
     from inside the law's directory (python build_cache.py). Phase 3 bumped
     CACHE_VERSION to 4 in power2 and fourparam, so the first start after
     the JWST tables arrive re-parses everything once.


MAXTED (2023) h1', h2'  (Phase 2, September 2026)
  Every prefixed compute response, in every law, carries two quantities
  derived from the served coefficients (Maxted 2023, MNRAS 519, 3723):
    h1_prime, h2_prime    the law evaluated at mu = 2/3, and the drop from
                          there to mu = 1/3
    edge_point_applied    true when the table supplied an edge point
    mu_cri                the interpolated edge point of a spherical model
                          (PHOENIX-COND, PHOENIX-NE), or null for a
                          plane-parallel table; when present, the two
                          positions are rescaled by k = 1 - mu_cri before
                          the law is evaluated (1 - k/3 and 1 - 2k/3)
    maxted_correction     present only for the three combinations Maxted
                          measured (quad Kp/ATLAS, fourparam Kp/ATLAS,
                          quad TESS/PHOENIX-COND), only at ξ = 2; shown
                          beside the table values, never applied to them
  Code: <law>/ldc_core.py :: maxted_values(), shared/maxted_correction.py.
  The legacy /api/... routes withhold all of these fields
  (parent_app.LEGACY_WITHHELD); the frontend shows them in the derived
  panel (renderDerived); the API reference documents them.
  This replaced the Maxted (2018) h1/h2 reparameterization that was carried
  in the power-2 engine but disabled until September 2026.


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
    - /power2/api/health reports c25/table3.dat 3366 and
      /fourparam/api/health reports c25/table2.dat 3366; filter_count
      26 / 35 / 39 for quad / power2 / fourparam
    - a prefixed power-2 or four-parameter compute for PRISM with
      model=PHOENIX-NE and no xi returns "xi": 1.0; with xi=2 it is
      refused; /quad/api/compute for PRISM names the two laws; the legacy
      /api/compute for PRISM still says "Unknown filter: 'PRISM'"
    - the frontend law switcher reaches all three backends, and the JWST
      category appears under power-2 and four-parameter after choosing
      1 km/s and PHOENIX-NE
