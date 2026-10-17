"""Layer 5: the fields Phase 2 added must be present, correct, and confined.

Layer 1 removes these fields before comparing v4 with v5, because its job is to
prove that no EXISTING field changed.  That leaves nobody checking the new ones,
so this layer does it, over the same enumeration of points.

Three things are asserted for every point:

  * h1_prime and h2_prime are present, finite, and equal an independent
    evaluation of the law at the two measurement positions.  The oracle here
    evaluates the law directly rather than using the closed forms the service
    uses, so an error in those forms cannot hide.

  * edge_point_applied is true exactly when the table supplied mu_cri, and the
    positions used follow from it.  Testing the flag against the table rather
    than against a model name is deliberate: the JWST tables arriving in Phase 3
    are spherical under a different name, and a name test would silently skip
    the correction for them.

  * maxted_correction is present for exactly the three law-and-filter
    combinations Maxted measured, at the default velocity only, and absent
    everywhere else -- absent, not null, so a caller can test for the key.

Since Phase 3 the enumeration covers every velocity, not just 2 km/s, so that
the JWST tables (PHOENIX-NE, 1 km/s only) are checked: they carry an edge
point, so the correction flag must be true for every one of their points, and
Maxted's empirical correction must be absent for all of them.  Two reference
stars from the Phase 3 brief, read directly from the published tables and
worked through the arithmetic specification by hand, are asserted exactly.

Run as part of run_all.py.  Exit code 0 means no discrepancies.
"""
import argparse, json, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_engine, enumerate_points, call_compute, LAWS

ap = argparse.ArgumentParser()
ap.add_argument("--v5", required=True)
ap.add_argument("--laws", default=",".join(LAWS))
ap.add_argument("--kinds", default="node,center,random")
ap.add_argument("--results", default="results")
ap.add_argument("--examples", type=int, default=20)
a = ap.parse_args()
os.makedirs(a.results, exist_ok=True)

# The three combinations Maxted measured, keyed as the service keys them.
# Kepler comes from Claret & Bloemen (2011) ATLAS, which the quadratic and
# four-parameter engines both draw on; TESS from Claret (2018) PHOENIX-COND,
# which only the quadratic engine uses.
EXPECT_CORRECTION = {
    ("quad", "Kp", "ATLAS"), ("fourparam", "Kp", "ATLAS"),
    ("quad", "TESS", "PHOENIX-COND"),
}
DEFAULT_XI = 2.0
ALL_XI = (0.0, 1.0, 2.0, 4.0, 8.0)

# Reference values from "Phase 3 Brief: JWST Coverage" (4 October 2026): a
# Sun-like star at 5800 K, log g 4.5, read directly from the published tables
# and converted by hand through the Maxted specification, with the edge-point
# correction applied.  Four decimals, as the brief quotes them.
REFERENCE = {
    ("power2",    "PRISM"): (0.9115, 0.1138),
    ("fourparam", "PRISM"): (0.9123, 0.1170),
    ("power2",    "SOSS2"): (0.8598, 0.1655),
    ("fourparam", "SOSS2"): (0.8605, 0.1685),
}


def profile(law, body, mu):
    """Evaluate the law itself at one position -- the independent route."""
    if law == "quad":
        return 1.0 - body["u1"] * (1 - mu) - body["u2"] * (1 - mu) ** 2
    if law == "power2":
        return 1.0 - body["g"] * (1 - mu ** body["h"])
    c = (body["a1"], body["a2"], body["a3"], body["a4"])
    return 1.0 - sum(v * (1 - mu ** ((j + 1) / 2.0)) for j, v in enumerate(c))


summary = {}
for law in a.laws.split(","):
    t0 = time.time()
    core, app = load_engine(a.v5, law)
    n = n_diff = 0
    with_corr = with_edge = 0
    non_realizable = 0          # points (nodes included) whose profile no real star could have
    non_realizable_examples = []
    examples = []

    def fail(point, why, detail=None):
        global n_diff
        n_diff += 1
        if len(examples) < a.examples:
            examples.append({"point": point, "why": why, "detail": detail})

    # --- the reference stars, exact to the four decimals the brief quotes
    for (rlaw, code), (want1, want2) in REFERENCE.items():
        if rlaw != law:
            continue
        status, body = call_compute(app, core, dict(teff=5800.0, logg=4.5, feh=0.0, filter=code, model="PHOENIX-NE", xi=1.0), True)
        if status != 200 or round(body["h1_prime"], 4) != want1 or round(body["h2_prime"], 4) != want2:
            fail({"reference": code}, "a reference star from the Phase 3 brief does not reproduce",
                 {"status": status, "served": None if status != 200 else [body["h1_prime"], body["h2_prime"]], "brief": [want1, want2]})

    for p in (q for xi in ALL_XI
                for q in enumerate_points(core, xi_filter=xi, kinds=tuple(a.kinds.split(",")))):
        status, body = call_compute(app, core, p, True)
        if status != 200:
            continue
        n += 1

        # --- the two values must be present and finite
        if "h1_prime" not in body or "h2_prime" not in body:
            fail(p, "a derived value is missing"); continue
        h1, h2 = body["h1_prime"], body["h2_prime"]
        if not (isinstance(h1, float) and math.isfinite(h1)
                and isinstance(h2, float) and math.isfinite(h2)):
            fail(p, "a derived value is not a finite number", {"h1": h1, "h2": h2})
            continue

        # --- the flag must follow the table, not the model's name
        mc = body.get("mu_cri")
        applied = body.get("edge_point_applied")
        if applied is not (mc is not None):
            fail(p, "the correction flag disagrees with the edge point",
                 {"edge_point_applied": applied, "mu_cri": mc})
            continue
        with_edge += 1 if applied else 0

        # --- and the values must equal a direct evaluation of the law
        k = 1.0 - (mc or 0.0)
        mu1, mu2 = 1.0 - k / 3.0, 1.0 - 2.0 * k / 3.0
        want1 = profile(law, body, mu1)
        want2 = want1 - profile(law, body, mu2)
        # The served mu_cri is rounded to six decimals, so the oracle sees it
        # with an error of up to half a unit in that place.  For an ordinary
        # star that moves the result by less than 1e-7 and is invisible under
        # the tolerance below.  Where the published power-2 fit is degenerate
        # (g in the hundreds with h near zero, which the JWST F322W2 table has
        # at 2700-2900 K, log g 3.0) the interpolated profile is wildly steep
        # and the same half unit moves the result by several 1e-6.  So the
        # oracle is evaluated at mu_cri plus and minus that half unit and the
        # served value must lie within the band they span.  This is a check
        # on the arithmetic only; whether such a profile means anything is
        # reported separately below, not failed.
        if mc is not None:
            band1, band2 = [want1], [want2]
            for m in (mc - 5e-7, mc + 5e-7):
                kk = 1.0 - m
                w1 = profile(law, body, 1.0 - kk / 3.0)
                band1.append(w1); band2.append(w1 - profile(law, body, 1.0 - 2.0 * kk / 3.0))
            lo1, hi1, lo2, hi2 = min(band1), max(band1), min(band2), max(band2)
        else:
            lo1 = hi1 = want1; lo2 = hi2 = want2
        # The served value is rounded to six decimals, so it may differ from an
        # independent evaluation by up to one unit in that place.  Two earlier
        # attempts at this comparison were wrong and are recorded so they are
        # not repeated: a tolerance of exactly half a unit failed on points
        # landing on the boundary, and requiring the rounded oracle to match
        # exactly failed where floating-point noise of order 1e-16 pushed the
        # two sides of a half-way point in opposite directions.  One unit in
        # the last served place is the honest bound, and it is still four
        # orders of magnitude finer than the 0.005 these values are measured to.
        if not (lo1 - 1e-6 <= h1 <= hi1 + 1e-6) or not (lo2 - 1e-6 <= h2 <= hi2 + 1e-6):
            fail(p, "a derived value disagrees with a direct evaluation",
                 {"served": [h1, h2], "direct": [want1, want2]})
            continue

        # --- information, not a failure: a profile no real star could have
        #     (Short et al. 2019: h1' < 1 and 0 < h2' <= h1'), at a node or an
        #     interpolated point.  The service reports it without comment
        #     (decision, 24 Sept 2026); this layer counts the cases so that a
        #     table's behaviour is seen.  Most of the four-parameter count is
        #     the published Claret & Bloemen (2011) fits themselves, in the
        #     Stromgren v and b bands (about 16 per cent of those nodes); the
        #     power-2 count is a few cells next to degenerate fits.
        if not (h1 < 1.0 and 0.0 < h2 <= h1):
            non_realizable += 1
            if len(non_realizable_examples) < 10:
                non_realizable_examples.append({"point": p, "h1_prime": h1, "h2_prime": h2})

        # --- a spherical table must always have applied the correction
        if p["model"] in ("PHOENIX-COND", "PHOENIX-NE") and not applied:
            fail(p, "a spherical table's point carries no edge point"); continue

        # --- the empirical correction must appear only where it was measured,
        #     and only at the default velocity
        key = (law, p["filter"], p["model"])
        want_corr = key in EXPECT_CORRECTION and p["xi"] == DEFAULT_XI
        has_corr = "maxted_correction" in body
        if has_corr != want_corr:
            fail(p, "the empirical correction is served where it was not measured"
                 if has_corr else "the empirical correction is missing where it was measured")
            continue
        if has_corr:
            with_corr += 1
            c = body["maxted_correction"]
            need = ("h1_prime", "h1_prime_err", "h2_prime", "h2_prime_err",
                    "offset_h1_prime", "offset_h2_prime", "table", "band",
                    "n_systems", "source")
            if any(f not in c for f in need):
                fail(p, "the correction object is missing a field",
                     {"has": sorted(c)}); continue
            # the corrected value must be the served value plus the offset
            # Two independent roundings are involved and the bound follows from
            # that rather than from experiment.  The served value is
            # round(true, 6), in error by at most half a unit in the sixth
            # decimal.  The corrected value is round(true + offset, 6), in error
            # by at most another half unit.  So the two sides of this comparison
            # can legitimately differ by a full unit, 1e-6, and a little more
            # once floating-point representation is allowed for.
            if abs(c["h1_prime"] - (h1 + c["offset_h1_prime"])) > 1.5e-6 \
               or abs(c["h2_prime"] - (h2 + c["offset_h2_prime"])) > 1.5e-6:
                fail(p, "the corrected value is not the served value plus the offset",
                     {"served": [h1, h2], "corrected": [c["h1_prime"], c["h2_prime"]]})

    summary[law] = {"points": n, "discrepancies": n_diff,
                    "with_edge_point": with_edge, "with_correction": with_corr,
                    "non_realizable": non_realizable,
                    "non_realizable_examples": non_realizable_examples,
                    "seconds": round(time.time() - t0, 1), "examples": examples}
    print(f"layer 5, {law}: {n} points, {n_diff} discrepancies, "
          f"{with_edge} carried an edge point, {with_corr} carried a correction, "
          f"{non_realizable} profiles no real star could have, nodes included (reported, not failed), "
          f"{summary[law]['seconds']} s")
    for e in examples[:3]:
        print("   e.g.", e)

json.dump(summary, open(os.path.join(a.results, "layer5_derived.json"), "w"), indent=1)
sys.exit(2 if any(v["discrepancies"] for v in summary.values()) else 0)
