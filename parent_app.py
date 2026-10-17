"""
parent_app.py — Phase 3 merge.

Mounts the two verified standalone apps as isolated sub-applications and owns
the shared resolver subsystem:
    /quad    -> quadratic (v3) app   (its own ldc_core / _TABLES)
    /power2  -> power-2  (v4) app     (its own ldc_core / _TABLES)
    /        -> shared frontend (placeholder until Step 4/5)

Step 3: the NEA/ExoFOP resolvers live in `shared/` and are imported by both
sub-apps. The parent loads their caches ONCE at startup and runs ONE refresh
scheduler. The sub-apps no longer load caches or start schedulers.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from shared import nea_resolver
from shared import exofop_resolver

from quad.app import app as quad_app
from power2.app import app as power2_app
from fourparam.app import app as fourparam_app


from quad.app import (
    health as _quad_health,
    filters as _quad_filters,
    compute_legacy as _quad_compute_legacy,
    resolve as _quad_resolve,
)
from quad import ldc_core as _quad_ldc_core

logger = logging.getLogger("scoldc-merged")
logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DATA = os.path.join(BASE_DIR, "shared", "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
NEA_FALLBACK_PATH = os.path.join(SHARED_DATA, "nea_parameters_fallback.tsv")
EXOFOP_FALLBACK_PATH = os.path.join(SHARED_DATA, "exofop_toi_fallback.tsv")

REFRESH_HOUR_UTC = 17
REFRESH_MINUTE_UTC = 0
# Retry policy. The previous policy was four attempts five minutes apart and
# then nothing until the next day, so a half-hour outage at 17:00 UTC cost a
# whole day's data.
REFRESH_RETRY_INTERVAL_SECONDS = 900          # 15 minutes between attempts
REFRESH_RETRY_WINDOW_SECONDS = 6 * 3600       # keep trying for six hours
# If the process starts without live data it should not wait until 17:00 for a
# first attempt, or the service runs a whole day on the bundled fallback.
STARTUP_RETRY_DELAY_SECONDS = 600
# How long after a crash the supervisor restarts the scheduler.
SUPERVISOR_RESTART_DELAY_SECONDS = 60

# Load the shared caches ONCE.
NEA_STATUS = nea_resolver.load_cache_at_startup(fallback_path=NEA_FALLBACK_PATH)
logger.info("Loaded SHARED NEA cache: source=%s count=%d",
            NEA_STATUS["source"], NEA_STATUS["count"])

EXOFOP_STATUS = exofop_resolver.load_cache_at_startup(fallback_path=EXOFOP_FALLBACK_PATH)
logger.info("Loaded SHARED ExoFOP cache: source=%s count=%d",
            EXOFOP_STATUS["source"], EXOFOP_STATUS["count"])


def _next_refresh_time_utc(now):
    candidate = now.replace(hour=REFRESH_HOUR_UTC, minute=REFRESH_MINUTE_UTC,
                            second=0, microsecond=0)
    # Previously this compared against now + 1 hour, which made a process that
    # started between 16:00 and 17:00 UTC skip that day's refresh entirely.
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _refresh_until_done(deadline) -> bool:
    """Keep attempting both caches until each has succeeded or the deadline
    passes. A cache that has already succeeded is not fetched again."""
    nea_done = False
    exofop_done = False
    while True:
        if not nea_done:
            nea_done = nea_resolver.refresh_cache_from_live()
        if not exofop_done:
            exofop_done = exofop_resolver.refresh_cache_from_live()
        if nea_done and exofop_done:
            logger.info("Shared refresh succeeded (both caches updated)")
            return True
        if datetime.now(timezone.utc) >= deadline:
            logger.error(
                "Shared refresh gave up for today: nea=%s exofop=%s | "
                "nea_error=%s | exofop_error=%s",
                nea_done, exofop_done,
                nea_resolver.refresh_diagnostics().get("last_error"),
                exofop_resolver.refresh_diagnostics().get("last_error"),
            )
            return False
        logger.warning("Shared refresh incomplete (nea=%s exofop=%s); "
                       "retrying in %d s", nea_done, exofop_done,
                       REFRESH_RETRY_INTERVAL_SECONDS)
        time.sleep(REFRESH_RETRY_INTERVAL_SECONDS)


def _retry_window_from_now():
    return datetime.now(timezone.utc) + timedelta(seconds=REFRESH_RETRY_WINDOW_SECONDS)


def _refresh_scheduler():
    # If startup could not reach the services, try again shortly instead of
    # waiting until 17:00 with the bundled fallback in place.
    if NEA_STATUS.get("source") != "nea" or EXOFOP_STATUS.get("source") != "exofop":
        logger.warning("Startup did not obtain live data (nea=%s exofop=%s); "
                       "first refresh attempt in %d s",
                       NEA_STATUS.get("source"), EXOFOP_STATUS.get("source"),
                       STARTUP_RETRY_DELAY_SECONDS)
        time.sleep(STARTUP_RETRY_DELAY_SECONDS)
        _refresh_until_done(_retry_window_from_now())

    while True:
        now = datetime.now(timezone.utc)
        target = _next_refresh_time_utc(now)
        wait_seconds = (target - now).total_seconds()
        logger.info("Shared refresh scheduler sleeping until %s (%.0f min)",
                    target.strftime("%Y-%m-%d %H:%M UTC"), wait_seconds / 60.0)
        time.sleep(wait_seconds)
        _refresh_until_done(_retry_window_from_now())


def _refresh_supervisor():
    """The thread body, and nothing escapes it.

    A scheduler thread that dies is a service that stops updating with no
    restart and no message -- which is what happened between 9 September and
    13 October 2026. The resolvers are now exception-safe in their own right;
    this is the second line of defence.
    """
    while True:
        try:
            _refresh_scheduler()
            return                      # the scheduler loops forever; a clean
                                        # return means deliberate shutdown
        except Exception:
            logger.exception("Shared refresh scheduler crashed; restarting in %d s",
                             SUPERVISOR_RESTART_DELAY_SECONDS)
            time.sleep(SUPERVISOR_RESTART_DELAY_SECONDS)


# The scheduler thread MUST be created inside the process that serves requests.
#
# Starting it here, at import time, put it in whichever process imported this
# module. Under gunicorn that import happens before the worker is forked, and
# threads do not survive fork(): the worker inherits the Thread OBJECT, which
# honestly reports itself as not alive, and no running thread. The worker then
# answers every request from caches that nothing will ever refresh. That is why
# nothing refreshed between 9 September and 13 October 2026 -- not an exception
# killing the thread, but a thread that was never in the serving process.
#
# A startup hook runs inside the worker, after the fork, so the thread lives
# where it is needed.
_refresh_thread = None
_refresh_thread_pid = None
_refresh_thread_lock = threading.Lock()


def _start_refresh_thread() -> None:
    """Create the scheduler thread in this process. Safe to call more than once."""
    global _refresh_thread, _refresh_thread_pid
    with _refresh_thread_lock:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            return
        _refresh_thread = threading.Thread(
            target=_refresh_supervisor, name="shared-refresh-scheduler", daemon=True,
        )
        _refresh_thread.start()
        _refresh_thread_pid = os.getpid()
        logger.info("Shared refresh scheduler thread started in pid %d",
                    _refresh_thread_pid)


app = FastAPI(title="SCO-LDC general (quadratic + power-2 + four-parameter)", version="5.0.0")


@app.on_event("startup")
def _start_background_work() -> None:
    # Runs in the worker process, after any fork. See the note above.
    _start_refresh_thread()

app.mount("/quad", quad_app)
app.mount("/power2", power2_app)
app.mount("/fourparam", fourparam_app)


# ---------------------------------------------------------------------------
# The legacy unprefixed routes. These are a permanent contract with NASA/TESS
# and AstroImageJ: same bytes, forever.
#
# health and resolve are still bound directly to the quadratic handlers, so
# there is exactly one implementation and no possibility of drift.
#
# filters and compute cannot be, from v5 onward. Their quadratic handlers now
# accept a microturbulent velocity, and the legacy routes must not. So each is
# wrapped in a forwarder that takes the pre-v5 parameters only and calls the
# quadratic app's implementation. The wrappers add no logic of their own: they
# forward, and compute additionally removes the "xi" key the prefixed route
# reports, because the legacy response must gain no new fields. Anyone sending
# ?xi= to an unprefixed route gets it ignored, which is the intended behaviour.
#
# Since Phase 3 (October 2026) the quadratic app's compute() names the laws
# that serve a filter this law does not hold -- the JWST modes -- instead of
# saying "Unknown filter". The frozen route must keep saying "Unknown filter",
# so its wrapper calls compute_legacy(), the same implementation with that one
# message left as it has always been. There is still exactly one code path for
# the numbers.
# ---------------------------------------------------------------------------

def _legacy_filters() -> dict:
    # The velocity must be passed explicitly. Calling a FastAPI handler as an
    # ordinary function bypasses parameter resolution, so its default would
    # arrive as a Query object rather than a number.
    return _quad_filters(xi=_quad_ldc_core.DEFAULT_XI)


# Fields that the newer prefixed routes carry but the four original, frozen
# routes must not.  Anything added to a compute response from now on belongs
# here unless it has been decided that the legacy consumers should see it.
# AstroImageJ and the TFOP tooling read the unprefixed route; its payload is
# frozen.
LEGACY_WITHHELD = ("xi", "h1_prime", "h2_prime", "edge_point_applied",
                   "mu_cri", "maxted_correction")


def _legacy_compute(
    teff: float = Query(..., description="Effective temperature in K"),
    logg: float = Query(..., description="Surface gravity log g in cgs dex"),
    feh:  float = Query(0.0, description="Metallicity [Fe/H] in dex (solar=0.0)"),
    filter: str = Query(..., alias="filter", description="Filter code (e.g. 'V', 'Kp', 'TESS', 'CBB')"),
    model:  str = Query("ATLAS", description="Stellar atmosphere model: ATLAS, PHOENIX, or PHOENIX-COND"),
) -> dict:
    result = _quad_compute_legacy(teff=teff, logg=logg, feh=feh, filter=filter,
                                  model=model, xi=_quad_ldc_core.DEFAULT_XI)
    for key in LEGACY_WITHHELD:
        result.pop(key, None)
    return result


def _legacy_health() -> dict:
    # Same principle as the two wrappers above: the legacy payload must not
    # change. The quadratic engine's own health reports the rows it loaded,
    # which from v5 onward span all five velocities, so the numbers grew.
    # The frozen route keeps reporting the 2 km/s counts, recomputed from the
    # loaded grids rather than hard-coded, so they stay right if a table is
    # ever replaced. Every other field is passed through untouched.
    result = dict(_quad_health())
    result["tables"] = _quad_ldc_core.row_counts_at_xi(_quad_ldc_core.DEFAULT_XI)
    # The version field is part of the frozen payload too. The quadratic
    # engine now reports 5.0.0 on its prefixed route; the legacy route keeps
    # the string it has always carried.
    result["version"] = "3.1.0"
    return result


app.add_api_route("/api/health", _legacy_health, methods=["GET", "HEAD"])
app.add_api_route("/api/filters", _legacy_filters, methods=["GET"])
app.add_api_route("/api/compute", _legacy_compute, methods=["GET"])
app.add_api_route("/api/resolve", _quad_resolve, methods=["GET"])


@app.get("/api/refresh-status")
def _refresh_status():
    """Why the planet caches are as old as they are.

    A new path, deliberately: the four frozen routes above must answer byte for
    byte as they always have, so none of this could be added to /api/health.
    """
    nea = nea_resolver.refresh_diagnostics()
    exofop = exofop_resolver.refresh_diagnostics()
    ages = [d["age_hours"] for d in (nea, exofop) if d["age_hours"] is not None]
    return JSONResponse({
        "scheduler_thread_alive": bool(_refresh_thread is not None
                                       and _refresh_thread.is_alive()),
        # If these two differ, the thread was started in a process that is not
        # the one answering this request, and it will never do any work here.
        "scheduler_pid": _refresh_thread_pid,
        "serving_pid": os.getpid(),
        "refresh_hour_utc": REFRESH_HOUR_UTC,
        "worst_age_hours": max(ages) if ages else None,
        "nea": nea,
        "exofop": exofop,
    })

# ---------------------------------------------------------------------------
# Static files, with an explicit instruction to revalidate.
#
# Without a Cache-Control header a browser is left to invent its own freshness
# lifetime, and may serve a stored copy of the page without asking the server
# whether anything has changed.  That produced a real fault on 25 September
# 2026: after a deploy the page kept showing the previous version, a hard
# reload did not help, and it corrected itself hours later when the browser's
# guessed lifetime expired.  Only a changed query string forced a fresh fetch.
#
# "no-cache" does not forbid caching.  It tells the browser to check with the
# server before reusing what it holds.  Because these responses already carry
# an ETag, that check is cheap: unchanged files come back as a short "not
# modified" reply and the browser reuses its copy.  The effect is that a deploy
# becomes visible immediately, to everyone, every time.
# ---------------------------------------------------------------------------

class _RevalidatingStatic(StaticFiles):
    """StaticFiles that asks browsers to revalidate rather than guess."""

    def file_response(self, *args, **kwargs):          # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


if os.path.isdir(STATIC_DIR) and os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/static", _RevalidatingStatic(directory=STATIC_DIR), name="static_legacy")
    app.mount("/", _RevalidatingStatic(directory=STATIC_DIR, html=True), name="static") 
    
else:
    @app.get("/")
    def _placeholder():
        return JSONResponse({
            "service": "SCO-LDC merged",
            "laws": {"quadratic": "/quad", "power-2": "/power2",
                     "four-parameter": "/fourparam"},
            "shared_caches": {"nea": NEA_STATUS, "exofop": EXOFOP_STATUS},
            "note": "shared frontend arrives in Step 4/5",
        })
