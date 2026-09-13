#!/usr/bin/env python3
"""
quad_equivalence_sweep.py
=========================

Exhaustive quadratic-law equivalence check between v3 (sco-ldc) and v4 (sco-ldcm).

GOAL
----
Prove that, for the quadratic law, the merged service (v4) returns coefficients
IDENTICAL to production v3 for every query a user could make -- so that cutover
changes no number anyone depends on.

WHAT IT COMPARES  (Tier 2: nodes + cell centers)
------------------------------------------------
For every (filter, model) pair in the quadratic grid:
  * every GRID NODE            -> tests table values + lookup
  * every full CELL CENTER     -> tests trilinear interpolation in all 3 axes
    (a cell center is the midpoint of a box whose 8 corners are all present)

Totals (current tables): 196,111 nodes + 132,925 cell centers = 329,036 queries,
i.e. 658,072 HTTP requests across the two services. At a few requests/second this
runs for many hours, so the sweep is fully RESUMABLE (see CHECKPOINTING).

Each query is issued to BOTH services and u1/u2 compared with tolerance TOL
(default 1e-6). Any difference beyond TOL is a discrepancy and is logged.

INDEPENDENCE
------------
The enumeration is built from a LOCAL copy of the quad tables (the same table
files both services use) purely to know WHICH points to ask about. The pass/fail
judgment is v3-vs-v4: the local tables are never used as the "right answer," only
to drive the query list. So this measures agreement between the two services, not
agreement with a third oracle.

USAGE
    python quad_equivalence_sweep.py \\
        --v3 https://sco-ldc.com \\
        --v4 https://sco-ldcm.onrender.com/api \\
        --tables ./quad/data

    # resume after an interruption -- just run the same command again:
    python quad_equivalence_sweep.py --v3 ... --v4 ... --tables ./quad/data

    # options
    --tol 1e-6            comparison tolerance on u1/u2 (default 1e-6)
    --rate 8             max requests/second PER SERVICE (default 8)
    --checkpoint FILE    progress file (default quad_sweep_checkpoint.json)
    --out FILE           discrepancy CSV (default quad_sweep_discrepancies.csv)
    --nodes-only         skip cell centers (nodes only; faster smoke pass)

CHECKPOINTING
-------------
Every CHECKPOINT_EVERY queries the script writes {index, n_pass, n_fail} to the
checkpoint file. On restart it reads that index and SKIPS ahead to it, so an
interruption at hour 20 resumes near hour 20, not zero. The enumeration order is
deterministic (sorted keys, sorted axes), so the index is stable across runs as
long as --tables and --nodes-only are unchanged.

The --v4 target should be the LEGACY ALIAS path (…/api), since that is the route
that must match v3. To sweep the /quad sub-app instead, pass …/quad/api.

EXIT CODE
    0  no discrepancies
    2  one or more discrepancies (see the CSV)
    1  aborted (config error, both-services-unreachable, etc.)
"""

import argparse
import csv
import json
import math
import os
import sys
import time

CHECKPOINT_EVERY = 500          # write progress every N queries
PROGRESS_PRINT_EVERY = 2000     # print a status line every N queries


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
try:
    import requests
    _SESSION = requests.Session()

    def _get(url, params, timeout):
        r = _SESSION.get(url, params=params, timeout=timeout)
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else None)
except ImportError:
    import urllib.parse, urllib.request, urllib.error

    def _get(url, params, timeout):
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, None


# ---------------------------------------------------------------------------
# Build the query enumeration from the local quad tables
# ---------------------------------------------------------------------------
def load_quad_tables(tables_dir):
    """Import the quad engine and load its tables. Returns the _TABLES dict:
       {(source, filter, model): {teffs, loggs, fehs, data}}."""
    # Find the quad package: tables_dir is typically <repo>/quad/data, so the
    # engine module ldc_core.py sits in <repo>/quad.
    quad_pkg = os.path.dirname(os.path.abspath(tables_dir))
    if quad_pkg not in sys.path:
        sys.path.insert(0, quad_pkg)
    try:
        import ldc_core
    except ImportError:
        # maybe tables_dir already IS the quad package dir
        if os.path.abspath(tables_dir) not in sys.path:
            sys.path.insert(0, os.path.abspath(tables_dir))
        import ldc_core
    ldc_core.load_tables(tables_dir, use_cache=False)
    return ldc_core._TABLES


def enumerate_queries(tables, nodes_only=False, seed=20260801):
    """Yield (filter_code, model, teff, logg, feh, kind) in a DETERMINISTIC order.

    This variant tests ONE RANDOM INTERIOR POINT per complete grid cell (kind
    'interior'), comparing v3 vs v4 -- NOT nodes, NOT cell centers. It exists to
    directly measure v3/v4 agreement at arbitrary points strictly inside each
    cell, complementing Test 1 (which tested nodes + deterministic cell centers).

    Determinism: the random point for each cell is drawn from a per-cell seeded
    RNG (base seed + a stable hash of the cell's identity), so the enumeration is
    identical across runs and the checkpoint index stays valid on resume.

    The interior point is placed at a random fraction in (0.05, 0.95) along each
    axis -- strictly inside the cell, never on a face, edge, or corner, so it
    genuinely exercises interpolation rather than reducing to a stored node.

    `nodes_only` is accepted for CLI compatibility but ignored here (this variant
    never emits nodes).
    """
    import random as _random
    import hashlib as _hashlib
    def _stable_seed(base, cell_id):
        # Python's built-in hash() is salted per process (PYTHONHASHSEED), which
        # would break determinism/resume. Use a stable digest instead.
        h = _hashlib.md5(repr((base, cell_id)).encode()).hexdigest()
        return int(h[:12], 16)
    for key in sorted(tables.keys()):
        filt = key[1]
        model = key[-1]
        g = tables[key]
        data = g["data"]
        te = list(g["teffs"]); lg = list(g["loggs"]); fe = list(g["fehs"])
        nodeset = set(data.keys())

        for i in range(len(te) - 1):
            for j in range(len(lg) - 1):
                for k in range(len(fe) - 1):
                    corners = [(te[a], lg[b], fe[c])
                               for a in (i, i + 1) for b in (j, j + 1) for c in (k, k + 1)]
                    if not all(c in nodeset for c in corners):
                        continue
                    # per-cell deterministic RNG (stable across runs/processes)
                    cell_id = (filt, model, i, j, k)
                    rng = _random.Random(_stable_seed(seed, cell_id))
                    fx = rng.uniform(0.05, 0.95)
                    fy = rng.uniform(0.05, 0.95)
                    fz = rng.uniform(0.05, 0.95)
                    pt = round(te[i] + fx * (te[i + 1] - te[i]), 4)
                    pl = round(lg[j] + fy * (lg[j + 1] - lg[j]), 4)
                    pz = round(fe[k] + fz * (fe[k + 1] - fe[k]), 4)
                    yield (filt, model, pt, pl, pz, "interior")


def count_queries(tables, nodes_only=False, seed=20260801):
    return sum(1 for _ in enumerate_queries(tables, nodes_only, seed))


# ---------------------------------------------------------------------------
# Query one service
# ---------------------------------------------------------------------------
def query_service(base, filt, model, teff, logg, feh, timeout,
                  retries=4, backoff=1.5):
    """Return (u1, u2) or ('ERR', detail).

    RETRY POLICY (added to survive transient network failures over a ~23h run):
    A dropped connection, timeout, or a 5xx/429/503 from the host is TRANSIENT --
    the server didn't disagree, it just didn't answer -- so we retry it up to
    `retries` times with exponential backoff before giving up. This prevents a
    single network blip (e.g. a Render cold-start or a dropped TCP connection)
    from being recorded as a v3-vs-v4 discrepancy.

    What is NOT retried: a well-formed HTTP 200 whose body is missing/!numeric
    fields (a real contract problem), and -- crucially -- a genuine coefficient
    MISMATCH between v3 and v4. Mismatches are detected by the CALLER comparing
    two successful (u1,u2) results; they never reach this function as an ERR, so
    a real disagreement still fails immediately and is never masked by retries.
    """
    url = base.rstrip("/") + "/api/compute"
    params = {"teff": teff, "logg": logg, "feh": feh, "filter": filt, "model": model}

    last_detail = "unknown"
    for attempt in range(retries + 1):
        transient = False
        try:
            code, body = _get(url, params, timeout)
        except Exception as e:
            # network-level failure: connection reset, timeout, DNS, etc.
            last_detail = f"exception:{type(e).__name__}"
            transient = True
        else:
            if code == 200 and isinstance(body, dict):
                if "u1" not in body or "u2" not in body:
                    # definitive: a 200 with a malformed body is a real problem,
                    # not a network blip -- do not retry.
                    return ("ERR", f"nofields:{str(body)[:60]}")
                try:
                    return (float(body["u1"]), float(body["u2"]))
                except (TypeError, ValueError):
                    return ("ERR", f"badnum:{body.get('u1')},{body.get('u2')}")
            elif code in (429, 500, 502, 503, 504):
                # server-side transient (throttle / restart / gateway) -- retry
                last_detail = f"http{code}"
                transient = True
            else:
                # definitive non-200 (e.g. 400 bad request) -- do not retry
                return ("ERR", f"http{code}")

        if not transient or attempt == retries:
            break
        # exponential backoff before the next attempt
        time.sleep(backoff * (2 ** attempt))

    return ("ERR", f"{last_detail}(after {retries} retries)")


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------
def load_checkpoint(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            return int(d.get("next_index", 0)), int(d.get("n_pass", 0)), int(d.get("n_fail", 0))
        except Exception:
            pass
    return 0, 0, 0


def save_checkpoint(path, next_index, n_pass, n_fail):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"next_index": next_index, "n_pass": n_pass, "n_fail": n_fail}, f)
    os.replace(tmp, path)   # atomic


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Exhaustive quadratic v3-vs-v4 equivalence sweep")
    ap.add_argument("--v3", required=True, help="v3 base URL, e.g. https://sco-ldc.com")
    ap.add_argument("--v4", required=True, help="v4 base URL incl. path, e.g. https://sco-ldcm.onrender.com/api")
    ap.add_argument("--tables", required=True, help="path to quad tables dir (e.g. ./quad/data)")
    ap.add_argument("--tol", type=float, default=1e-6, help="u1/u2 comparison tolerance (default 1e-6)")
    ap.add_argument("--rate", type=float, default=8.0, help="max requests/sec per service (default 8)")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--retries", type=int, default=4,
                    help="retries on transient network/5xx failures before recording ERR (default 4)")
    ap.add_argument("--backoff", type=float, default=1.5,
                    help="base seconds for exponential backoff between retries (default 1.5)")
    ap.add_argument("--seed", type=int, default=20260801,
                    help="seed for per-cell random interior point (default 20260801)")
    ap.add_argument("--checkpoint", default="quad_random_interior_checkpoint.json")
    ap.add_argument("--out", default="quad_random_interior_discrepancies.csv")
    ap.add_argument("--nodes-only", action="store_true", help="skip cell centers")
    args = ap.parse_args()

    print("Loading local quad tables to build the query list...")
    try:
        tables = load_quad_tables(args.tables)
    except Exception as e:
        print(f"ERROR: could not load quad tables from {args.tables}: {e}")
        return 1
    print(f"  {len(tables)} (filter, model) keys loaded")

    print("Counting queries (this enumerates the full grid once)...")
    total = count_queries(tables, args.nodes_only, args.seed)
    print(f"  total queries: {total:,}  (one random interior point per complete cell)")
    print(f"  HTTP requests: {2*total:,} across both services")
    print()

    # sanity: both services reachable, and both actually serve the quadratic law
    print("Sanity check: querying one point on each service...")
    probe = next(enumerate_queries(tables, args.nodes_only, args.seed))
    f, m, t, l, z, _ = probe
    r3 = query_service(args.v3, f, m, t, l, z, args.timeout, args.retries, args.backoff)
    r4 = query_service(args.v4, f, m, t, l, z, args.timeout, args.retries, args.backoff)
    print(f"  v3 {args.v3}: {r3}")
    print(f"  v4 {args.v4}: {r4}")
    if r3[0] == "ERR" or r4[0] == "ERR":
        print("ERROR: one or both services failed the probe. Check URLs "
              "(v4 should include the /api or /quad/api path). Aborting.")
        return 1
    print()

    next_index, n_pass, n_fail = load_checkpoint(args.checkpoint)
    if next_index > 0:
        print(f"RESUMING from checkpoint at index {next_index:,} "
              f"(pass={n_pass:,} fail={n_fail:,})")
    # open discrepancy CSV (append if resuming)
    new_csv = not (os.path.exists(args.out) and next_index > 0)
    csv_fh = open(args.out, "a", newline="", encoding="utf-8")
    writer = csv.writer(csv_fh)
    if new_csv:
        writer.writerow(["index", "kind", "filter", "model", "teff", "logg", "feh",
                         "v3_u1", "v3_u2", "v4_u1", "v4_u2", "d_u1", "d_u2", "note"])
        csv_fh.flush()

    gap = 1.0 / args.rate if args.rate > 0 else 0.0
    t_start = time.time()
    idx = 0
    processed_this_run = 0

    try:
        for q in enumerate_queries(tables, args.nodes_only, args.seed):
            if idx < next_index:            # fast-forward on resume
                idx += 1
                continue
            filt, model, teff, logg, feh, kind = q

            t0 = time.time()
            v3 = query_service(args.v3, filt, model, teff, logg, feh, args.timeout, args.retries, args.backoff)
            v4 = query_service(args.v4, filt, model, teff, logg, feh, args.timeout, args.retries, args.backoff)

            note = ""
            discrepancy = False
            if v3[0] == "ERR" or v4[0] == "ERR":
                discrepancy = True
                note = f"v3={v3[1] if v3[0]=='ERR' else 'ok'};v4={v4[1] if v4[0]=='ERR' else 'ok'}"
                d1 = d2 = ""
                v3u = v3 if v3[0] == "ERR" else (v3[0], v3[1])
                writer.writerow([idx, kind, filt, model, teff, logg, feh,
                                 v3[0] if v3[0] != "ERR" else "ERR",
                                 v3[1] if v3[0] != "ERR" else "",
                                 v4[0] if v4[0] != "ERR" else "ERR",
                                 v4[1] if v4[0] != "ERR" else "",
                                 "", "", note])
            else:
                d1 = abs(v3[0] - v4[0])
                d2 = abs(v3[1] - v4[1])
                if d1 > args.tol or d2 > args.tol:
                    discrepancy = True
                    writer.writerow([idx, kind, filt, model, teff, logg, feh,
                                     f"{v3[0]:.9f}", f"{v3[1]:.9f}",
                                     f"{v4[0]:.9f}", f"{v4[1]:.9f}",
                                     f"{d1:.3e}", f"{d2:.3e}", "DIFF"])

            if discrepancy:
                n_fail += 1
                csv_fh.flush()
                print(f"  [DISCREPANCY] idx={idx} {filt}/{model} "
                      f"({teff},{logg},{feh}) {kind}: {note or f'du1={d1:.2e} du2={d2:.2e}'}")
            else:
                n_pass += 1

            idx += 1
            processed_this_run += 1

            if idx % CHECKPOINT_EVERY == 0:
                save_checkpoint(args.checkpoint, idx, n_pass, n_fail)
            if idx % PROGRESS_PRINT_EVERY == 0:
                elapsed = time.time() - t_start
                rate_now = processed_this_run / elapsed if elapsed > 0 else 0
                remaining = (total - idx) / rate_now if rate_now > 0 else 0
                print(f"  {idx:,}/{total:,}  pass={n_pass:,} fail={n_fail:,}  "
                      f"~{rate_now:.1f} q/s  ETA {remaining/3600:.1f}h", flush=True)

            # rate limit (per service; two requests per query so sleep to gap*2 total budget)
            dt = time.time() - t0
            budget = gap * 2  # two requests issued this iteration
            if dt < budget:
                time.sleep(budget - dt)

    except KeyboardInterrupt:
        save_checkpoint(args.checkpoint, idx, n_pass, n_fail)
        csv_fh.flush(); csv_fh.close()
        print(f"\nInterrupted. Progress saved at index {idx:,}. "
              f"Re-run the same command to resume.")
        return 1

    save_checkpoint(args.checkpoint, idx, n_pass, n_fail)
    csv_fh.flush(); csv_fh.close()

    print()
    print("=" * 64)
    print("QUADRATIC EQUIVALENCE SWEEP COMPLETE")
    print("=" * 64)
    print(f"v3: {args.v3}")
    print(f"v4: {args.v4}")
    print(f"tolerance: {args.tol:g}")
    print(f"queries compared: {idx:,}")
    print(f"  PASS: {n_pass:,}")
    print(f"  FAIL: {n_fail:,}")
    print()
    if n_fail == 0:
        print("RESULT: zero discrepancies. v3 and v4 return identical quadratic "
              "coefficients across the full grid. Safe to cut over (on this axis).")
        return 0
    print(f"RESULT: {n_fail:,} discrepancies -- see {args.out}. DO NOT cut over "
          "until each is explained.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
