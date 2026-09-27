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
    examples = []

    def fail(point, why, detail=None):
        global n_diff
        n_diff += 1
        if len(examples) < a.examples:
            examples.append({"point": point, "why": why, "detail": detail})

    for p in enumerate_points(core, xi_filter=DEFAULT_XI,
                              kinds=tuple(a.kinds.split(","))):
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
        # The served value is rounded to six decimals, so it may differ from an
        # independent evaluation by up to one unit in that place.  Two earlier
        # attempts at this comparison were wrong and are recorded so they are
        # not repeated: a tolerance of exactly half a unit failed on points
        # landing on the boundary, and requiring the rounded oracle to match
        # exactly failed where floating-point noise of order 1e-16 pushed the
        # two sides of a half-way point in opposite directions.  One unit in
        # the last served place is the honest bound, and it is still four
        # orders of magnitude finer than the 0.005 these values are measured to.
        if abs(h1 - want1) > 1e-6 or abs(h2 - want2) > 1e-6:
            fail(p, "a derived value disagrees with a direct evaluation",
                 {"served": [h1, h2], "direct": [want1, want2]})
            continue

        # --- the empirical correction must appear only where it was measured
        key = (law, p["filter"], p["model"])
        want_corr = key in EXPECT_CORRECTION
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
                    "seconds": round(time.time() - t0, 1), "examples": examples}
    print(f"layer 5, {law}: {n} points, {n_diff} discrepancies, "
          f"{with_edge} carried an edge point, {with_corr} carried a correction, "
          f"{summary[law]['seconds']} s")
    for e in examples[:3]:
        print("   e.g.", e)

json.dump(summary, open(os.path.join(a.results, "layer5_derived.json"), "w"), indent=1)
sys.exit(2 if any(v["discrepancies"] for v in summary.values()) else 0)
