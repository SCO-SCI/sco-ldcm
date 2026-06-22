SCO-LDC MERGED (Quadratic + Power-2) — Phase 3, Steps 1-5
==========================================================

STRUCTURE
  parent_app.py          Mounts both sub-apps + serves frontend + owns resolvers/scheduler
  quad/                  Quadratic (v3) sub-app
    app.py               MODIFIED: package-relative imports; resolver-load & scheduler removed; root route
    ldc_core.py          UNCHANGED (your v3 engine)
    build_cache.py       UNCHANGED
    __init__.py          NEW (empty; makes it a package)
    data/                Your v3 data (tableab, table5, CBBQUADRATIC, table2, table8, tables.pkl)
  power2/                Power-2 (v4) sub-app
    app.py               MODIFIED: same changes as quad/app.py
    ldc_core.py          UNCHANGED (your v4 engine)
    build_cache.py       UNCHANGED
    __init__.py          NEW
    data/c22 c23 cbb     Your v4 data + tables.pkl
  shared/                Shared resolver subsystem (one copy each)
    nea_resolver.py      UNCHANGED (identical in v3 and v4)
    exofop_resolver.py   UNCHANGED
    __init__.py          NEW
    data/                Shared fallback TSVs
  static/
    index.html           NEW: merged law-switcher frontend
  requirements.txt       (same deps as standalone)
  Procfile               NOTE: entry point is parent_app:app (NOT app:app)

RUN LOCALLY
  pip install -r requirements.txt
  uvicorn parent_app:app --reload
  Then open http://127.0.0.1:8000/

  - Default law is Quadratic. Use the "Limb-darkening law" dropdown to switch.
  - Quadratic backend: /quad/api/...   Power-2 backend: /power2/api/...

WHAT CHANGED IN app.py (both):
  1. imports: `import ldc_core` -> `from quad import ldc_core` (resp. power2)
     and resolvers now `from shared import ...`
  2. Removed module-level resolver load_cache_at_startup() calls
  3. Removed the refresh-scheduler thread start
     (parent_app.py now does these ONCE for both laws)
  4. Root "/" route returns a small JSON pointer instead of serving a frontend
  Everything else (routes, compute logic, health) is unchanged.

DEPLOY (Step 7, when ready):
  Start command must use parent_app:app (the Procfile here already does).
  Keep --workers 1 (single process holds both engines + shared cache).
