"""Shared pieces of the SCO-LDC v5 test harness.

Point enumeration follows Ed Mullen's quad_equivalence_sweep.py (nodes and
cell centres) and quad_random_interior_sweep.py (one seeded random point per
full cell), generalised to the v5 table key (source, filter, xi, storage
model) and to all three laws. Checkpointing, rate limiting and the retry
policy for live services are his as well.
"""
import importlib, json, os, random, sys, time, hashlib, logging

LAWS = ("quad", "power2", "fourparam")
COEF_KEYS = {"quad": ("u1", "u2"), "power2": ("g", "h"), "fourparam": ("a1", "a2", "a3", "a4")}

# ---------------------------------------------------------------- engines
def load_engine(repo, law):
    """Import <repo>/<law>/ldc_core.py and app.py and load the tables exactly
    as the service does. One repo per process: module names collide."""
    logging.disable(logging.CRITICAL)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    core = importlib.import_module(f"{law}.ldc_core")
    app = importlib.import_module(f"{law}.app")
    core.load_tables(os.path.join(repo, law, "data"))
    return core, app

def table_key_parts(key):
    """(source, filter, xi, storage_model) for v5 keys, (source, filter, model)
    for v4 keys. Returns (filter, model, xi)."""
    if len(key) == 4:
        return key[1], key[3], float(key[2])
    return key[1], key[2], 2.0

def display_model(core, filt, storage_model):
    return core._display_model(filt, storage_model) if hasattr(core, "_display_model") else storage_model

# ---------------------------------------------------------------- points
def _stable_seed(base, cell_id):
    h = hashlib.sha256(f"{base}|{cell_id}".encode()).hexdigest()
    return int(h[:16], 16)

def enumerate_points(core, xi_filter=2.0, kinds=("node", "center", "random"), seed=20260801):
    """Yield dicts {filter, model, xi, teff, logg, feh, kind} in a deterministic
    order: sorted keys; per grid all nodes, then all full-cell centres, then
    one seeded random interior point per full cell (Ed's schemes)."""
    for key in sorted(core._TABLES.keys(), key=lambda k: tuple(str(x) for x in k)):
        filt, smodel, xi = table_key_parts(key)
        if xi_filter is not None and xi != xi_filter:
            continue
        model = display_model(core, filt, smodel)
        g = core._TABLES[key]
        te, lg, fe = list(g["teffs"]), list(g["loggs"]), list(g["fehs"])
        nodes = set(g["data"].keys())
        if "node" in kinds:
            for t in te:
                for l in lg:
                    for z in fe:
                        if (t, l, z) in nodes:
                            yield dict(filter=filt, model=model, xi=xi, teff=t, logg=l, feh=z, kind="node")
        if "center" in kinds or "random" in kinds:
            for i in range(len(te) - 1):
                for j in range(len(lg) - 1):
                    for k in range(max(len(fe) - 1, 1)):
                        k1 = k + 1 if len(fe) > 1 else k
                        corners = [(te[a], lg[b], fe[c]) for a in (i, i + 1) for b in (j, j + 1) for c in (k, k1)]
                        if not all(c in nodes for c in corners):
                            continue
                        if "center" in kinds:
                            yield dict(filter=filt, model=model, xi=xi, kind="center",
                                       teff=round((te[i] + te[i + 1]) / 2.0, 4), logg=round((lg[j] + lg[j + 1]) / 2.0, 4),
                                       feh=round((fe[k] + fe[k1]) / 2.0, 4))
                        if "random" in kinds:
                            rng = random.Random(_stable_seed(seed, f"{filt}|{model}|{xi}|{i}|{j}|{k}"))
                            fx, fy, fz = rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.95)
                            yield dict(filter=filt, model=model, xi=xi, kind="random",
                                       teff=round(te[i] + fx * (te[i + 1] - te[i]), 4), logg=round(lg[j] + fy * (lg[j + 1] - lg[j]), 4),
                                       feh=round(fe[k] + fz * (fe[k1] - fe[k]), 4) if len(fe) > 1 else fe[k])

# ---------------------------------------------------------------- direct calls
def call_compute(app, core, p, has_xi):
    """Call the compute route handler directly (no HTTP). Returns
    (status, body_dict_or_detail)."""
    from fastapi import HTTPException
    kw = dict(teff=p["teff"], logg=p["logg"], feh=p["feh"], filter=p["filter"], model=p["model"])
    if has_xi:
        kw["xi"] = p.get("xi", 2.0)
    try:
        return 200, app.compute(**kw)
    except HTTPException as e:
        return e.status_code, e.detail

# ---------------------------------------------------------------- live HTTP (Ed's machinery)
try:
    import requests
    _SESSION = requests.Session()
    def _get(url, params, timeout):
        r = _SESSION.get(url, params=params, timeout=timeout)
        return r.status_code, r.text
except ImportError:
    import urllib.parse, urllib.request, urllib.error
    def _get(url, params, timeout):
        req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

def query_live(url, params, timeout=30, retries=4, backoff=1.5):
    """(status, body_text) with Ed's retry policy: transient failures are
    retried; definitive answers, including 400s, are returned at once."""
    last = "unknown"
    for attempt in range(retries + 1):
        try:
            code, text = _get(url, params, timeout)
        except Exception as e:
            last = f"exception:{type(e).__name__}"
        else:
            if code in (429, 500, 502, 503, 504):
                last = f"http{code}"
            else:
                return code, text
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    return None, last

class Checkpoint:
    def __init__(self, path):
        self.path = path
        self.state = {"next_index": 0, "n_pass": 0, "n_fail": 0}
        if os.path.exists(path):
            try:
                self.state = json.load(open(path))
            except Exception:
                pass
    def save(self):
        tmp = self.path + ".tmp"
        json.dump(self.state, open(tmp, "w"))
        os.replace(tmp, self.path)

class RateLimiter:
    def __init__(self, per_second):
        self.min_gap = 1.0 / per_second if per_second > 0 else 0.0
        self.last = 0.0
    def wait(self):
        now = time.time()
        gap = self.min_gap - (now - self.last)
        if gap > 0:
            time.sleep(gap)
        self.last = time.time()
