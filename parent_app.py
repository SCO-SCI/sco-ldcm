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

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from shared import nea_resolver
from shared import exofop_resolver

from quad.app import app as quad_app
from power2.app import app as power2_app
from fourparam.app import app as fourparam_app

# Legacy alias (Option 2): the unprefixed /api/... endpoints must keep serving
# the QUADRATIC law unchanged, because NASA/TESS depend on sco-ldc.com/api/...
# returning u1/u2. We import the quad sub-app's actual route handlers and
# re-register them on the parent at the unprefixed paths, so the legacy API is
# the SAME code path as /quad/api/... (zero drift) and is permanently quadratic.
from quad.app import (
    health as _quad_health,
    filters as _quad_filters,
    compute as _quad_compute,
    resolve as _quad_resolve,
)

logger = logging.getLogger("scoldc-merged")
logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DATA = os.path.join(BASE_DIR, "shared", "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
NEA_FALLBACK_PATH = os.path.join(SHARED_DATA, "nea_parameters_fallback.tsv")
EXOFOP_FALLBACK_PATH = os.path.join(SHARED_DATA, "exofop_toi_fallback.tsv")

REFRESH_HOUR_UTC = 17
REFRESH_MINUTE_UTC = 0
REFRESH_MAX_ATTEMPTS = 4
REFRESH_RETRY_INTERVAL_SECONDS = 300

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
    if candidate <= now + timedelta(hours=1):
        candidate += timedelta(days=1)
    return candidate


def _refresh_scheduler():
    while True:
        now = datetime.now(timezone.utc)
        target = _next_refresh_time_utc(now)
        wait_seconds = (target - now).total_seconds()
        logger.info("Shared refresh scheduler sleeping until %s (%.0f min)",
                    target.strftime("%Y-%m-%d %H:%M UTC"), wait_seconds / 60.0)
        time.sleep(wait_seconds)
        nea_done = False
        exofop_done = False
        for attempt in range(1, REFRESH_MAX_ATTEMPTS + 1):
            if not nea_done:
                nea_done = nea_resolver.refresh_cache_from_live()
            if not exofop_done:
                exofop_done = exofop_resolver.refresh_cache_from_live()
            if nea_done and exofop_done:
                logger.info("Shared refresh succeeded (both caches updated)")
                break
            if attempt < REFRESH_MAX_ATTEMPTS:
                time.sleep(REFRESH_RETRY_INTERVAL_SECONDS)
            else:
                logger.warning("Shared refresh exhausted retries: nea=%s exofop=%s",
                               nea_done, exofop_done)


_refresh_thread = threading.Thread(
    target=_refresh_scheduler, name="shared-refresh-scheduler", daemon=True,
)
_refresh_thread.start()
logger.info("Shared refresh scheduler thread started")


app = FastAPI(title="SCO-LDC merged (quadratic + power-2)", version="merge-step3")

app.mount("/quad", quad_app)
app.mount("/power2", power2_app)
app.mount("/fourparam", fourparam_app)

# --- Legacy quadratic alias (Option 2): unprefixed /api/... -> quadratic ---
# These reuse the quad sub-app's own handler functions, so behavior is
# byte-identical to /quad/api/... . This preserves the contract that
# sco-ldc.com/api/compute returns quadratic u1/u2 for existing callers
# (NASA/TESS). The legacy path is permanently quadratic; new laws are reached
# only via their own prefixes (/power2, later /fourparam).
app.add_api_route("/api/health", _quad_health, methods=["GET", "HEAD"])
app.add_api_route("/api/filters", _quad_filters, methods=["GET"])
app.add_api_route("/api/compute", _quad_compute, methods=["GET"])
app.add_api_route("/api/resolve", _quad_resolve, methods=["GET"])

if os.path.isdir(STATIC_DIR) and os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
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
