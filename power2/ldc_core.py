from __future__ import annotations

import os
from bisect import bisect_left
from typing import Dict, List, Optional, Tuple



FILTER_REGISTRY: List[Dict] = [
    # Johnson-Cousins (ATLAS from CS22 table3, PHOENIX from CS23 table10)
    {"code": "U",  "name": "Johnson U",      "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "B",  "name": "Johnson B",      "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "V",  "name": "Johnson V",      "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "R",  "name": "Cousins R",      "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "I",  "name": "Cousins I",      "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "J",  "name": "2MASS J",        "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "H",  "name": "2MASS H",        "category": "Johnson-Cousins", "source": "CS22_CS23"},
    {"code": "K",  "name": "2MASS K",        "category": "Johnson-Cousins", "source": "CS22_CS23"},
    # Sloan / SDSS (ATLAS from CS22 table2, PHOENIX from CS23 table6)
    {"code": "u*", "name": "SDSS u'",        "category": "Sloan/SDSS",      "source": "CS22_CS23"},
    {"code": "g*", "name": "SDSS g'",        "category": "Sloan/SDSS",      "source": "CS22_CS23"},
    {"code": "r*", "name": "SDSS r'",        "category": "Sloan/SDSS",      "source": "CS22_CS23"},
    {"code": "i*", "name": "SDSS i'",        "category": "Sloan/SDSS",      "source": "CS22_CS23"},
    {"code": "z*", "name": "SDSS z'",        "category": "Sloan/SDSS",      "source": "CS22_CS23"},
    # Stromgren (ATLAS from CS22 table3, PHOENIX from CS23 table10)
    {"code": "u",  "name": "Strömgren u",    "category": "Strömgren",       "source": "CS22_CS23"},
    {"code": "v",  "name": "Strömgren v",    "category": "Strömgren",       "source": "CS22_CS23"},
    {"code": "b",  "name": "Strömgren b",    "category": "Strömgren",       "source": "CS22_CS23"},
    {"code": "y",  "name": "Strömgren y",    "category": "Strömgren",       "source": "CS22_CS23"},
    # Gaia (ATLAS from CS22 table1, PHOENIX from CS23 table2) -- new in power-2
    {"code": "G_BP", "name": "Gaia G_BP",    "category": "Gaia",            "source": "CS22_CS23"},
    {"code": "G",    "name": "Gaia G",       "category": "Gaia",            "source": "CS22_CS23"},
    {"code": "G_RP", "name": "Gaia G_RP",    "category": "Gaia",            "source": "CS22_CS23"},
    # Space-based (ATLAS from CS22 table1, PHOENIX from CS23 table2)
    {"code": "Kp",   "name": "Kepler",       "category": "Space-based",     "source": "CS22_CS23"},
    {"code": "TESS", "name": "TESS",         "category": "Space-based",     "source": "CS22_CS23"},
    # CHEOPS -- PHOENIX (CS23 table2) only; CS22 has no CHEOPS
    {"code": "CHEOPS", "name": "CHEOPS",     "category": "Space-based",     "source": "CS23_ONLY"},
    # CBB (Blue Blocking Exoplanet) -- ATLAS only, SCO power-2 table
    {"code": "CBB", "name": "CBB (Blue Blocking Exoplanet)",
                                             "category": "Exoplanet",       "source": "CBBP2"},
]


SOURCE_CITATIONS: Dict[str, str] = {
    "CS22_CS23": "Claret & Southworth (2022, A&A 664, A128; 2023, A&A 674, A63)",
    "CS23_ONLY": "Claret & Southworth (2023, A&A 674, A63)",
    "CBBP2":     "Claret, Mullen & Gary CBB power-2 table",
}


# Which atmosphere models each source tag provides.
EXPECTED_MODELS: Dict[str, List[str]] = {
    "CS22_CS23": ["ATLAS", "PHOENIX"],   # ATLAS from CS22, PHOENIX from CS23
    "CS23_ONLY": ["PHOENIX"],            # CHEOPS: CS23 PHOENIX only
    "CBBP2":     ["ATLAS"],              # CBB: ATLAS only
}


# CS23 PHOENIX-COND grids display as "PHOENIX-COND" but store under "PHOENIX".
MODEL_DISPLAY_NAMES: Dict[Tuple[str, str], str] = {
    ("CHEOPS", "PHOENIX"): "PHOENIX-COND",
    ("U", "PHOENIX"): "PHOENIX-COND",  ("B", "PHOENIX"): "PHOENIX-COND",
    ("V", "PHOENIX"): "PHOENIX-COND",  ("R", "PHOENIX"): "PHOENIX-COND",
    ("I", "PHOENIX"): "PHOENIX-COND",  ("J", "PHOENIX"): "PHOENIX-COND",
    ("H", "PHOENIX"): "PHOENIX-COND",  ("K", "PHOENIX"): "PHOENIX-COND",
    ("u", "PHOENIX"): "PHOENIX-COND",  ("v", "PHOENIX"): "PHOENIX-COND",
    ("b", "PHOENIX"): "PHOENIX-COND",  ("y", "PHOENIX"): "PHOENIX-COND",
    ("u*", "PHOENIX"): "PHOENIX-COND", ("g*", "PHOENIX"): "PHOENIX-COND",
    ("r*", "PHOENIX"): "PHOENIX-COND", ("i*", "PHOENIX"): "PHOENIX-COND",
    ("z*", "PHOENIX"): "PHOENIX-COND",
    ("G_BP", "PHOENIX"): "PHOENIX-COND", ("G", "PHOENIX"): "PHOENIX-COND",
    ("G_RP", "PHOENIX"): "PHOENIX-COND",
    ("Kp", "PHOENIX"): "PHOENIX-COND", ("TESS", "PHOENIX"): "PHOENIX-COND",
}


def _display_model(filter_code: str, model: str) -> str:

    return MODEL_DISPLAY_NAMES.get((filter_code, model), model)





Grid = Dict[str, object]

# Microturbulent velocity, km/s. Claret publishes coefficients at these five
# values; 2.0 is what every table has and what the service served before v5.
SUPPORTED_XI: Tuple[float, ...] = (0.0, 1.0, 2.0, 4.0, 8.0)
DEFAULT_XI: float = 2.0


def _norm_xi(xi: float) -> float:
    """Canonical form of a velocity, so keys compare reliably."""
    return round(float(xi), 3)


# Key is (source, filter code, velocity, storage model). Velocity sits ahead of
# the model deliberately: the sweep scripts read the filter from position 1 and
# the model from the last position, and this ordering keeps both valid.
_TABLES: Dict[Tuple[str, str, float, str], Grid] = {}


def _add_point(table_key: Tuple[str, str, float, str],
               teff: float, logg: float, feh: float,
               g: float, h: float) -> None:

    grid = _TABLES.setdefault(table_key, {
        "teffs": set(), "loggs": set(), "fehs": set(), "data": {}
    })

    t = round(float(teff), 2)
    gg = round(float(logg), 3)
    z = round(float(feh), 3)
    grid["teffs"].add(t)         # type: ignore[union-attr]
    grid["loggs"].add(gg)        # type: ignore[union-attr]
    grid["fehs"].add(z)          # type: ignore[union-attr]
    grid["data"][(t, gg, z)] = (float(g), float(h))   # type: ignore[index]


def _finalize_tables() -> None:

    for grid in _TABLES.values():
        grid["teffs"] = sorted(grid["teffs"])   # type: ignore[arg-type]
        grid["loggs"] = sorted(grid["loggs"])   # type: ignore[arg-type]
        grid["fehs"]  = sorted(grid["fehs"])    # type: ignore[arg-type]







def _parse_cs22(path: str, bands: List[Tuple[str, str]]) -> int:
    
    nb = len(bands)
    expected = 4 + 3 * nb
    count = 0
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != expected:
                continue
            try:
                logg = float(parts[0])
                teff = float(parts[1])
                feh  = float(parts[2])
                xi   = float(parts[3])
            except ValueError:
                continue
            try:
                for bi, (code, source) in enumerate(bands):
                    g = float(parts[4 + bi])
                    h = float(parts[4 + nb + bi])
                    _add_point((source, code, _norm_xi(xi), "ATLAS"),
                               teff, logg, feh, g, h)
            except ValueError:
                continue
            count += 1
    return count


def _parse_cs23(path: str, bands: List[Tuple[str, str]]) -> int:
    
    nb = len(bands)
    expected = 4 + 4 * nb
    count = 0
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != expected:
                continue
            try:
                logg = float(parts[0])
                teff = float(parts[1])
                feh  = float(parts[2])
                # Bytes 19-22 are the Vel column (CDS J/A+A/674/A63). Every row
                # of these PHOENIX-COND files carries 2.0, so this grid ends up
                # at 2.0 and nowhere else, which is what the refusal rule wants.
                xi   = _norm_xi(float(parts[3]))
            except ValueError:
                continue
            try:
                for bi, (code, source) in enumerate(bands):
                    g = float(parts[4 + bi])
                    h = float(parts[4 + nb + bi])
                    _add_point((source, code, xi, "PHOENIX"),
                               teff, logg, feh, g, h)
            except ValueError:
                continue
            count += 1
    return count


def _parse_cbb_power2(path: str, source: str) -> int:
    
    count = 0
    buf: List[Tuple[float, float, float, float, float]] = []  # (logg, teff, feh, xi, coeff)
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                # skips the 3 header lines (which have a text label, not a float)
                continue
            try:
                logg = float(parts[0])
                teff = float(parts[1])
                feh  = float(parts[2])
                vel  = float(parts[3])
                coef = float(parts[4])
            except ValueError:
                continue
            buf.append((logg, teff, feh, vel, coef))

            if len(buf) == 3:
                (lg1, te1, fe1, xi1, c_g) = buf[0]
                (lg2, te2, fe2, xi2, c_h) = buf[1]
                (lg3, te3, fe3, xi3, c_x) = buf[2]
                buf = []
                if not (lg1 == lg2 == lg3 and te1 == te2 == te3 and fe1 == fe2 == fe3):
                    continue
                if not (xi1 == xi2 == xi3):
                    continue
                _add_point((source, "CBB", _norm_xi(xi1), "ATLAS"),
                           te1, lg1, fe1, c_g, c_h)
                count += 1
    return count





import pickle

CACHE_FILENAME = "tables.pkl"
CACHE_VERSION = 2

# (filter_code, source_tag) per band, in on-file column order.
_T = "CS22_CS23"   # both ATLAS (CS22) and PHOENIX (CS23)
_P = "CS23_ONLY"   # PHOENIX only (CHEOPS)

_CS22_TABLE1_BANDS = [("G_BP", _T), ("G", _T), ("G_RP", _T), ("Kp", _T), ("TESS", _T)]
_CS22_TABLE2_BANDS = [("u*", _T), ("g*", _T), ("r*", _T), ("i*", _T), ("z*", _T)]
_CS22_TABLE3_BANDS = [("u", _T), ("v", _T), ("b", _T), ("y", _T), ("U", _T), ("B", _T),
                      ("V", _T), ("R", _T), ("I", _T), ("J", _T), ("H", _T), ("K", _T)]

# CS23 table2 carries CHEOPS, which has no ATLAS source -> tag it CS23_ONLY here,
# its file-mates CS22_CS23. This is why CHEOPS lands under the PHOENIX-only tag
# directly, with no re-keying.
_CS23_TABLE2_BANDS = [("G_BP", _T), ("G", _T), ("G_RP", _T), ("Kp", _T), ("TESS", _T), ("CHEOPS", _P)]
_CS23_TABLE6_BANDS = [("u*", _T), ("g*", _T), ("r*", _T), ("i*", _T), ("z*", _T)]
_CS23_TABLE10_BANDS = [("u", _T), ("v", _T), ("b", _T), ("y", _T), ("U", _T), ("B", _T),
                       ("V", _T), ("R", _T), ("I", _T), ("J", _T), ("H", _T), ("K", _T)]

SOURCE_FILES = (
    os.path.join("c22", "table1.dat"),
    os.path.join("c22", "table2.dat"),
    os.path.join("c22", "table3.dat"),
    os.path.join("c23", "table2.dat"),
    os.path.join("c23", "table6.dat"),
    os.path.join("c23", "table10.dat"),
    os.path.join("cbb", "cbbpower2.txt"),
)


def _cache_is_fresh(cache_path: str, source_paths: List[str]) -> bool:

    if not os.path.exists(cache_path):
        return False
    cache_mtime = os.path.getmtime(cache_path)
    for p in source_paths:
        if not os.path.exists(p):
            return False
        if os.path.getmtime(p) > cache_mtime:
            return False
    return True


def _parse_all(data_dir: str) -> Dict[str, int]:

    counts: Dict[str, int] = {}
    j = os.path.join
    counts["c22/table1.dat"]  = _parse_cs22(j(data_dir, "c22", "table1.dat"),  _CS22_TABLE1_BANDS)
    counts["c22/table2.dat"]  = _parse_cs22(j(data_dir, "c22", "table2.dat"),  _CS22_TABLE2_BANDS)
    counts["c22/table3.dat"]  = _parse_cs22(j(data_dir, "c22", "table3.dat"),  _CS22_TABLE3_BANDS)
    counts["c23/table2.dat"]  = _parse_cs23(j(data_dir, "c23", "table2.dat"),  _CS23_TABLE2_BANDS)
    counts["c23/table6.dat"]  = _parse_cs23(j(data_dir, "c23", "table6.dat"),  _CS23_TABLE6_BANDS)
    counts["c23/table10.dat"] = _parse_cs23(j(data_dir, "c23", "table10.dat"), _CS23_TABLE10_BANDS)
    counts["cbb/cbbpower2.txt"] = _parse_cbb_power2(j(data_dir, "cbb", "cbbpower2.txt"), "CBBP2")
    _finalize_tables()
    return counts


def _save_cache(cache_path: str, counts: Dict[str, int]) -> None:

    payload = {
        "version": CACHE_VERSION,
        "tables":  _TABLES,
        "counts":  counts,
    }
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp_path, cache_path)


def _load_cache(cache_path: str) -> Optional[Dict[str, int]]:

    try:
        with open(cache_path, "rb") as fh:
            payload = pickle.load(fh)
    except (pickle.UnpicklingError, EOFError, AttributeError, OSError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return None
    tables = payload.get("tables")
    counts = payload.get("counts")
    if not isinstance(tables, dict) or not isinstance(counts, dict):
        return None
    _TABLES.clear()
    _TABLES.update(tables)
    return counts


def load_tables(data_dir: str, use_cache: bool = True) -> Dict[str, int]:

    _TABLES.clear()

    cache_path = os.path.join(data_dir, CACHE_FILENAME)
    source_paths = [os.path.join(data_dir, f) for f in SOURCE_FILES]

    if use_cache and _cache_is_fresh(cache_path, source_paths):
        counts = _load_cache(cache_path)
        if counts is not None:
            return counts

    counts = _parse_all(data_dir)

    try:
        _save_cache(cache_path, counts)
    except OSError:
        pass

    return counts







def _resolve_table_key(filter_code: str, model: str,
                       xi: float = DEFAULT_XI) -> Tuple[str, str, float, str]:

    entry = None
    for f in FILTER_REGISTRY:
        if f["code"] == filter_code:
            entry = f
            break
    if entry is None:
        raise ValueError(f"Unknown filter: {filter_code!r}")
    source = entry["source"]

    if model.upper() == "PHOENIX-COND":
        storage_model = "PHOENIX"
    else:
        storage_model = model.upper()

    return (source, filter_code, _norm_xi(xi), storage_model)


def get_available_filters(xi: float = DEFAULT_XI) -> List[Dict]:

    out: List[Dict] = []
    for f in FILTER_REGISTRY:
        code = f["code"]
        source = f["source"]
        models_present: List[Dict] = []
        for storage_model in EXPECTED_MODELS[source]:
            grid = _TABLES.get((source, code, _norm_xi(xi), storage_model))
            if grid is None:
                continue
            teffs = grid["teffs"]   # type: ignore[index]
            loggs = grid["loggs"]   # type: ignore[index]
            fehs  = grid["fehs"]    # type: ignore[index]
            models_present.append({
                "model": _display_model(code, storage_model),
                "model_key": storage_model,
                "teff_min": teffs[0],  "teff_max": teffs[-1],
                "logg_min": loggs[0],  "logg_max": loggs[-1],
                "feh_min":  fehs[0],   "feh_max":  fehs[-1],
                "feh_fixed": (len(fehs) == 1),
                "n_points": len(grid["data"]),   # type: ignore[arg-type]
            })
        if not models_present:
            continue
        out.append({
            "code": code,
            "name": f["name"],
            "category": f["category"],
            "source": source,
            "citation": SOURCE_CITATIONS[source],
            "models": models_present,
        })
    return out




def _bracket(axis: List[float], x: float) -> Tuple[int, int, float]:

    lo = axis[0]
    hi = axis[-1]
    if x < lo - 1e-9 or x > hi + 1e-9:
        raise ValueError(f"value {x} outside grid [{lo}, {hi}]")

    if x <= lo:
        return 0, 0, 0.0
    if x >= hi:
        n = len(axis) - 1
        return n, n, 0.0

    idx = bisect_left(axis, x)
    if idx < len(axis) and axis[idx] == x:
        return idx, idx, 0.0
    i_hi = idx
    i_lo = idx - 1
    span = axis[i_hi] - axis[i_lo]
    t = (x - axis[i_lo]) / span if span > 0 else 0.0
    return i_lo, i_hi, t


def _nearest_available(data: Dict[Tuple[float, float, float], Tuple[float, float]],
                       teff_vals: Tuple[float, float],
                       logg_vals: Tuple[float, float],
                       feh_vals: Tuple[float, float]
                       ) -> Optional[Tuple[List[List[List[Tuple[float, float]]]],
                                            Tuple[float, float],
                                            Tuple[float, float],
                                            Tuple[float, float]]]:

    cube: List[List[List[Tuple[float, float]]]] = [[[(0.0, 0.0)] * 2 for _ in range(2)] for _ in range(2)]
    for i, te in enumerate(teff_vals):
        for j, lg in enumerate(logg_vals):
            for k, fe in enumerate(feh_vals):
                key = (round(te, 2), round(lg, 3), round(fe, 3))
                if key not in data:
                    return None
                cube[i][j][k] = data[key]
    return cube, teff_vals, logg_vals, feh_vals


def _filter_has_model(filter_code: str, storage_model: str) -> bool:

    for f in FILTER_REGISTRY:
        if f["code"] == filter_code:
            return storage_model in EXPECTED_MODELS.get(f["source"], [])
    return False


def maxted_params(g: float, h: float) -> Tuple[float, float, bool]:
    
    two_pow = 2.0 ** (-h)
    h1 = 1.0 - g * (1.0 - two_pow)
    h2 = g * two_pow
    valid = (h1 < 1.0) and (0.0 < h2 <= h1)
    return h1, h2, valid


def compute_ldcs(teff: float, logg: float, feh: float,
                 filter_code: str, model: str,
                 xi: float = DEFAULT_XI
                 ) -> Dict[str, object]:

    xi = _norm_xi(xi)
    if xi not in SUPPORTED_XI:
        allowed = ", ".join(f"{v:g}" for v in SUPPORTED_XI)
        raise ValueError(
            f"Invalid Input (microturbulent velocity = {xi:g} km/s): "
            f"coefficients are published only at {allowed} km/s.")

    table_key = _resolve_table_key(filter_code, model, xi)
    source, code, _xi, storage_model = table_key
    grid = _TABLES.get(table_key)
    if grid is None:
        model_name = _display_model(filter_code, storage_model)
        if xi != DEFAULT_XI and _TABLES.get(
                (source, code, DEFAULT_XI, storage_model)) is not None:
            raise ValueError(
                f"Invalid Input (microturbulent velocity = {xi:g} km/s): "
                f"the {model_name} table for filter {filter_code} is published "
                f"only at {DEFAULT_XI:g} km/s.")
        raise ValueError(
            f"no data for filter {filter_code!r} with model {model!r}")

    teffs: List[float] = grid["teffs"]   # type: ignore[assignment]
    loggs: List[float] = grid["loggs"]   # type: ignore[assignment]
    fehs:  List[float] = grid["fehs"]    # type: ignore[assignment]
    data = grid["data"]                  # type: ignore[assignment]

    try:
        i0, i1, tT = _bracket(teffs, float(teff))
    except ValueError as e:
        model_name = _display_model(filter_code, storage_model)
        if float(teff) < teffs[0]:
            suggestion = " Use the PHOENIX model instead." if storage_model == "ATLAS" and _filter_has_model(filter_code, "PHOENIX") else ""
            raise ValueError(
                f"Invalid Input (Teff = {teff} K): "
                f"The {model_name} model does not support values of Teff "
                f"below {teffs[0]:.0f} K.{suggestion}"
            ) from e
        else:
            suggestion = " Use the ATLAS model instead." if storage_model == "PHOENIX" and _filter_has_model(filter_code, "ATLAS") else ""
            raise ValueError(
                f"Invalid Input (Teff = {teff} K): "
                f"The {model_name} model does not support values of Teff "
                f"above {teffs[-1]:.0f} K.{suggestion}"
            ) from e
    try:
        j0, j1, tG = _bracket(loggs, float(logg))
    except ValueError as e:
        model_name = _display_model(filter_code, storage_model)
        if float(logg) < loggs[0]:
            suggestion = " Use the ATLAS model instead." if storage_model == "PHOENIX" and _filter_has_model(filter_code, "ATLAS") else ""
            raise ValueError(
                f"Invalid Input (log g = {logg}): "
                f"The {model_name} model does not support values of log g "
                f"below {loggs[0]:.1f}.{suggestion}"
            ) from e
        else:
            raise ValueError(
                f"Invalid Input (log g = {logg}): "
                f"The {model_name} model does not support values of log g "
                f"above {loggs[-1]:.1f}."
            ) from e

    if len(fehs) == 1:
        if abs(float(feh) - fehs[0]) > 1e-6:
            raise ValueError(
                f"[Fe/H] {feh} not available for {filter_code}/"
                f"{_display_model(filter_code, storage_model)} "
                f"(solar metallicity only: {fehs[0]:+.1f})")
        k0, k1, tZ = 0, 0, 0.0
    else:
        try:
            k0, k1, tZ = _bracket(fehs, float(feh))
        except ValueError as e:
            model_name = _display_model(filter_code, storage_model)
            if float(feh) < fehs[0]:
                raise ValueError(
                    f"Invalid Input ([Fe/H] = {feh}): "
                    f"The {model_name} model does not support values of [Fe/H] "
                    f"below {fehs[0]:+.1f}."
                ) from e
            else:
                raise ValueError(
                    f"Invalid Input ([Fe/H] = {feh}): "
                    f"The {model_name} model does not support values of [Fe/H] "
                    f"above {fehs[-1]:+.1f}."
                ) from e

    teff_vals = (teffs[i0], teffs[i1])
    logg_vals = (loggs[j0], loggs[j1])
    feh_vals  = (fehs[k0],  fehs[k1])

    corners = _nearest_available(data, teff_vals, logg_vals, feh_vals)  # type: ignore[arg-type]
    if corners is None:
        model_name = _display_model(filter_code, storage_model)
        raise ValueError(
            f"Invalid Input: Tables do not include data for this combination of "
            f"Teff = {teff}, log g = {logg}, and [Fe/H] = {feh} "
            f"with the {model_name} model."
        )

    cube, _, _, _ = corners

    w = [
        [(1.0 - tT) * (1.0 - tG) * (1.0 - tZ),
         (1.0 - tT) * (1.0 - tG) * tZ],
        [(1.0 - tT) * tG * (1.0 - tZ),
         (1.0 - tT) * tG * tZ],
    ], [
        [tT * (1.0 - tG) * (1.0 - tZ),
         tT * (1.0 - tG) * tZ],
        [tT * tG * (1.0 - tZ),
         tT * tG * tZ],
    ]

    g_coef = 0.0
    h_coef = 0.0
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                c1, c2 = cube[i][j][k]
                weight = w[i][j][k]
                g_coef += weight * c1
                h_coef += weight * c2

    

    return {
        "g": g_coef,
        "h": h_coef,
        
        "filter_code": filter_code,
        "filter_name": next(f["name"] for f in FILTER_REGISTRY if f["code"] == filter_code),
        "model": _display_model(filter_code, storage_model),
        "citation": SOURCE_CITATIONS[source],
        "grid": {
            "teff_bracket": [teff_vals[0], teff_vals[1]],
            "logg_bracket": [logg_vals[0], logg_vals[1]],
            "feh_bracket":  [feh_vals[0],  feh_vals[1]],
            "fractions":    {"teff": tT, "logg": tG, "feh": tZ},
            "on_grid":      (tT == 0.0 and tG == 0.0 and tZ == 0.0),
        },
    }
