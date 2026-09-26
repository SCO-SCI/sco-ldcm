"""Maxted's empirically measured corrections to published limb-darkening tables.

WHAT THIS IS
------------
Everything else SCO-LDC serves is arithmetic on published tables.  This is not:
it is a measurement of how far a particular published table sits from real
stars.

Maxted (2023, MNRAS 519, 3723) took 43 systems observed by Kepler and TESS,
determined their actual limb darkening from the light curves, and compared the
result against nine published tabulations.  For each he recorded an offset, its
uncertainty, and how much the individual stars scattered around it.  Table 3 of
that paper holds the results.

Only three of our filter/model/law combinations use a table he actually tested,
so a correction is available for those three and for nothing else.  Where none
exists the service says so rather than borrowing one measured elsewhere:
different tables give different values for the same star, so a borrowed
correction would introduce an error of the same order as the correction itself.

WHY IT IS SHOWN SEPARATELY RATHER THAN APPLIED
----------------------------------------------
Decision, E. Mullen, 26 September 2026.  The corrected values are displayed
beside the table values, never folded into them.  Three reasons:

  * Durability.  This is one team's measurement of 43 stars.  Kostogryz and
    colleagues already publish tables that model the same physics directly, and
    better constraints will follow.  Applying the correction to what we serve
    would make every such paper a maintenance obligation and would silently
    change answers users had already recorded.  Shown as an attributed line, a
    future revision changes one line rather than the meaning of the service.

  * Honesty about size.  The correction is barely larger than its own
    uncertainty -- the ratios are 1.2, 0.3, 1.1 and 1.0.  Serving a shifted
    central value alone would present a barely significant result as a fact and
    would discard the width, which is the part Maxted's recipe is about.  His
    recommendation is not "add 0.006" but "use 0.880 +/- 0.006 as a prior".

  * It cannot be done for the four-parameter law anyway.  The correction is to
    h1' and h2', two numbers, and that law has four coefficients.  Two equations
    cannot determine four unknowns: sets of coefficients as different as
    (0.413, 0.481, -0.150, -0.019) and (-2.172, 2.204, 1.172, -1.284) give
    identical h1' and h2'.  There is no single corrected set to serve.

SCOPE
-----
Applied only at the default microturbulent velocity.  Maxted interpolated
Claret's standard tables; the other velocity variants would carry a different
offset from reality, and extrapolating his measurement onto them is not
supported by anything he published.
"""

from typing import Dict, Optional

DEFAULT_XI = 2.0

# Keyed by (source key as used by the engine, filter code, display model name).
# Values are Maxted (2023) Table 3: the offset, its uncertainty, and the
# external scatter of individual stars about it.  The sign convention is
# observed minus calculated, so a positive offset means real stars are brighter
# than the table predicts and the offset is ADDED.
_TABLE3 = {
    # Kepler band, Claret & Bloemen (2011) ATLAS.
    # Used by the quadratic engine (source "CB2011") and the four-parameter
    # engine, whose "CB_CS" source takes its ATLAS tables from the same paper.
    ("CB2011", "Kp", "ATLAS"): dict(
        dh1=+0.006, e1=0.002, s1=0.005,
        dh2=-0.013, e2=0.004, s2=0.013,
        table="Claret & Bloemen (2011) ATLAS", band="Kepler", n=24),
    ("CB_CS", "Kp", "ATLAS"): dict(
        dh1=+0.006, e1=0.002, s1=0.005,
        dh2=-0.013, e2=0.004, s2=0.013,
        table="Claret & Bloemen (2011) ATLAS", band="Kepler", n=24),

    # TESS band, Claret (2018) PHOENIX-COND.  Quadratic engine only: the
    # power-2 and four-parameter engines take their TESS spherical tables from
    # Claret & Southworth (2023), which Maxted did not test.
    ("C2018", "TESS", "PHOENIX-COND"): dict(
        dh1=+0.011, e1=0.004, s1=0.008,
        dh2=-0.002, e2=0.006, s2=0.005,
        table="Claret (2018) PHOENIX-COND", band="TESS", n=10),
}

SOURCE = "Maxted (2023), MNRAS 519, 3723, Table 3"


def correction(source: str, filter_code: str, model: str,
               h1_prime: float, h2_prime: float,
               xi: float = DEFAULT_XI) -> Optional[Dict[str, object]]:
    """The corrected values for this star, or None if no measurement exists.

    Returns the corrected h1' and h2' with the width a user should attach to
    them.  The width combines the uncertainty on the correction itself with the
    scatter of real stars about it, added in quadrature, which is how Maxted
    builds the prior he recommends.
    """
    row = _TABLE3.get((source, filter_code, model))
    if row is None or abs(xi - DEFAULT_XI) > 1e-9:
        return None
    w1 = (row["e1"] ** 2 + row["s1"] ** 2) ** 0.5
    w2 = (row["e2"] ** 2 + row["s2"] ** 2) ** 0.5
    return {
        "h1_prime": round(h1_prime + row["dh1"], 6),
        "h1_prime_err": round(w1, 6),
        "h2_prime": round(h2_prime + row["dh2"], 6),
        "h2_prime_err": round(w2, 6),
        "offset_h1_prime": row["dh1"],
        "offset_h2_prime": row["dh2"],
        "table": row["table"],
        "band": row["band"],
        "n_systems": row["n"],
        "source": SOURCE,
    }
