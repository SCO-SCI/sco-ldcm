"""The eleven JWST observing modes of Claret, Hauschildt & Torres (2025).

WHAT THIS IS
------------
One definition, shared by the three engines, of the JWST tables added in
Phase 3 (October 2026): which modes exist, what they are called, which
atmosphere model and microturbulent velocity they were computed with, and how
the two published files are laid out.  The power-2 and four-parameter engines
register these modes and parse the files through this module; the quadratic
engine, which holds no JWST table, uses the list of codes to tell a caller
where the modes ARE served.  Keeping the list here means the three engines
cannot disagree about it.

THE SOURCE
----------
Claret, Hauschildt & Torres (2025, A&A 699, A97), CDS catalogue J/A+A/699/A97.
Two plain fixed-width text files:

    table2.dat   four-parameter law   logg  Teff  mode  a1 a2 a3 a4  mu_crit  chi2
    table3.dat   power-2 law          logg  Teff  mode  g  h         mu_crit  chi2

One row per (log g, Teff, mode): the observing mode is a COLUMN, where every
other table the service reads gives each band its own file or its own block
of columns.  3,366 rows in each file: 51 temperatures x 6 gravities x 11
modes, with no cell missing.

The grid.  Teff 2400 to 7800 K: every 100 K up to 7000 K, then every 200 K
(7200, 7400, 7600, 7800), so 51 nodes.  log g 3.0 to 5.5 in steps of 0.5.
Solar composition only.  Microturbulent velocity 1.0 km/s only, where every
other table the service holds is published at 2.0 km/s (and the ATLAS tables
at 0, 1, 2, 4 and 8).

THE MODEL
---------
Spherically symmetric PHOENIX models of the NewEra generation (Hauschildt et
al. 2025, A&A 698, A47), labelled PHOENIX-NE throughout the service.  They are
a different vintage from the PHOENIX-COND tables already held -- the model-grid
paper reports updated molecular line lists as the main source of the
differences from earlier generations, and these tables were computed at a
different microturbulent velocity -- so they are NOT merged with the existing
PHOENIX/PHOENIX-COND storage key.  Decision, E. Mullen, 4 October 2026.

Edge point.  The paper (section 3) fixes the limb at the point where dI/dr is
largest (Wittkowski et al. 2004), which it notes corresponds to a Rosseland
mean optical depth of about 1.  Claret & Southworth (2023), the source of the
PHOENIX-COND tables, called that convention M1 and the service holds their M2
tables (the midpoint between that point and the adjacent mu-grid point), so
the two sets of tables do not fix the edge point in exactly the same way.

Because the models are spherical, each row carries an edge point (mu_crit),
and the Maxted h1'/h2' derivation applies the edge-point correction to these
tables exactly as it does to the PHOENIX-COND ones: Phase 2 tests for the
presence of an edge point, not for a model name.

THE CODES
---------
The filter codes are Claret's own, exactly as the published file has them, so
that anyone comparing an answer against the table sees the same string.  The
instrument is carried in the display name, and for the four NIRSpec gratings
so is the blocking filter they are used with (G235H/F170LP and so on), which
is how the CDS ReadMe and JWST observers name those modes (decision,
E. Mullen, 10 October 2026).  Note that F277W exists on both NIRCam and
NIRISS; in this table it is the NIRISS one.
"""

from typing import Callable, Dict, List, Optional, Tuple

SOURCE = "CHT25"
MODEL = "PHOENIX-NE"
XI = 1.0
FEH = 0.0
CATEGORY = "JWST"
CITATION = "Claret, Hauschildt & Torres (2025, A&A 699, A97)"
CATALOGUE = "J/A+A/699/A97"

# (code, display name, mean wavelength in microns), in the order of the CDS
# ReadMe, which is the order of Table 1 of the paper: NIRCam, NIRISS, NIRSpec.
MODES: Tuple[Tuple[str, str, float], ...] = (
    ("F210M",  "NIRCam F210M",        2.10),
    ("F322W2", "NIRCam F322W2",       3.34),
    ("F444W",  "NIRCam F444W",        4.44),
    ("SOSS1",  "NIRISS SOSS Order 1", 1.80),
    ("SOSS2",  "NIRISS SOSS Order 2", 0.80),
    ("F277W",  "NIRISS F277W",        2.80),
    ("G235H",  "NIRSpec G235H/F170LP", 2.44),
    ("G235M",  "NIRSpec G235M/F170LP", 2.45),
    ("G395H",  "NIRSpec G395H/F290LP", 4.04),
    ("G395M",  "NIRSpec G395M/F290LP", 4.03),
    ("PRISM",  "NIRSpec PRISM",        3.65),
)

CODES: Tuple[str, ...] = tuple(m[0] for m in MODES)
DISPLAY_NAMES: Dict[str, str] = {m[0]: m[1] for m in MODES}

# The laws under which these modes are served, named in the refusal the
# quadratic engine gives.  Claret published no quadratic table for JWST,
# deliberately: his section 4 argues the quadratic law fits poorly and does
# not conserve flux.  The wording of that refusal is E. Mullen's (10 October
# 2026): "<code> — the JWST modes are served under the power-2 and
# four-parameter laws only."
SERVED_UNDER = "the power-2 and four-parameter laws"


def registry_entries() -> List[Dict]:
    """The FILTER_REGISTRY rows for the eleven modes, in published order."""
    return [{"code": code, "name": name, "category": CATEGORY, "source": SOURCE}
            for code, name, _ in MODES]


# Fixed-width column positions from the CDS ReadMe (1-based byte ranges,
# converted to Python slices).  Both files share the first three columns.
_LOGG = slice(0, 4)      # bytes  1-  4  F4.2
_TEFF = slice(5, 9)      # bytes  6-  9  I4
_MODE = slice(10, 16)    # bytes 11- 16  A6

# table3.dat (power-2): g 18-28, h 30-40, mu_crit 42-51, chi2 53-62
_P2_COEFFS = (slice(17, 28), slice(29, 40))
_P2_MU = slice(41, 51)
_P2_CHI = slice(52, 62)

# table2.dat (four-parameter): a1 18-27, a2 29-38, a3 40-49, a4 51-60,
# mu_crit 62-71, chi2 73-82
_4P_COEFFS = (slice(17, 27), slice(28, 38), slice(39, 49), slice(50, 60))
_4P_MU = slice(61, 71)
_4P_CHI = slice(72, 82)


def parse(path: str, n_coefficients: int,
          add_point: Callable[..., None]) -> int:
    """Read one of the two files and hand every row to the engine.

    ``n_coefficients`` is 2 for table3.dat (power-2) or 4 for table2.dat
    (four-parameter).  ``add_point`` is called as

        add_point(code, teff, logg, coefficients, mu_crit, chi2)

    once per row whose mode is one of the eleven and whose fields are all
    present.  Rows with a mode this module does not know are skipped rather
    than stored under an unregistered code; rows with a blank field are
    skipped too.  Returns the number of rows stored, which the health route
    reports as the table's row count.
    """
    if n_coefficients == 2:
        coeff_slices, mu_slice, chi_slice = _P2_COEFFS, _P2_MU, _P2_CHI
    elif n_coefficients == 4:
        coeff_slices, mu_slice, chi_slice = _4P_COEFFS, _4P_MU, _4P_CHI
    else:
        raise ValueError("n_coefficients must be 2 or 4")

    known = set(CODES)
    count = 0
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if len(line) < chi_slice.stop - 1:
                continue
            code = line[_MODE].strip()
            if code not in known:
                continue
            try:
                logg = float(line[_LOGG])
                teff = float(line[_TEFF])
                coeffs = tuple(float(line[s]) for s in coeff_slices)
                mu_crit = float(line[mu_slice])
                chi2 = float(line[chi_slice])
            except ValueError:
                # A blank or malformed field.  The ReadMe marks g as possibly
                # null; no such row exists in the published file, but if one
                # ever did it must not become a stored zero.
                continue
            add_point(code, teff, logg, coeffs, mu_crit, chi2)
            count += 1
    return count
