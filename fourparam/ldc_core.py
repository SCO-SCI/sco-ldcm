from __future__ import annotations

import os
import pickle
from bisect import bisect_left
from typing import Dict, List, Optional, Tuple



_CB_CS   = "CB_CS"
_CS_ONLY = "CS_ONLY"
_CB_ONLY = "CB_ONLY"

FILTER_REGISTRY: List[Dict] = [
    # Johnson-Cousins (ATLAS from CB2011 tableeq5, PHOENIX-COND from CS2023 table12)
    {"code": "U",  "name": "Johnson U",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "B",  "name": "Johnson B",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "V",  "name": "Johnson V",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "R",  "name": "Cousins R",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "I",  "name": "Cousins I",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "J",  "name": "Johnson J",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "H",  "name": "Johnson H",  "category": "Johnson-Cousins", "source": _CB_CS},
    {"code": "K",  "name": "Johnson K",  "category": "Johnson-Cousins", "source": _CB_CS},
    # Sloan / SDSS (ATLAS from CB2011, PHOENIX-COND from CS2023 table8)
    {"code": "u*", "name": "SDSS u'",    "category": "Sloan/SDSS",      "source": _CB_CS},
    {"code": "g*", "name": "SDSS g'",    "category": "Sloan/SDSS",      "source": _CB_CS},
    {"code": "r*", "name": "SDSS r'",    "category": "Sloan/SDSS",      "source": _CB_CS},
    {"code": "i*", "name": "SDSS i'",    "category": "Sloan/SDSS",      "source": _CB_CS},
    {"code": "z*", "name": "SDSS z'",    "category": "Sloan/SDSS",      "source": _CB_CS},
    # Stromgren (ATLAS from CB2011, PHOENIX-COND from CS2023 table12)
    {"code": "u",  "name": "Strömgren u", "category": "Strömgren",      "source": _CB_CS},
    {"code": "v",  "name": "Strömgren v", "category": "Strömgren",      "source": _CB_CS},
    {"code": "b",  "name": "Strömgren b", "category": "Strömgren",      "source": _CB_CS},
    {"code": "y",  "name": "Strömgren y", "category": "Strömgren",      "source": _CB_CS},
    # Gaia -- PHOENIX-COND only (CS2023 table4); CB2011 predates Gaia
    {"code": "G_BP", "name": "Gaia G_BP", "category": "Gaia",           "source": _CS_ONLY},
    {"code": "G",    "name": "Gaia G",    "category": "Gaia",           "source": _CS_ONLY},
    {"code": "G_RP", "name": "Gaia G_RP", "category": "Gaia",           "source": _CS_ONLY},
    # Space-based
    {"code": "Kp",   "name": "Kepler",    "category": "Space-based",    "source": _CB_CS},
    {"code": "TESS", "name": "TESS",      "category": "Space-based",    "source": _CS_ONLY},
    {"code": "CHEOPS", "name": "CHEOPS",  "category": "Space-based",    "source": _CS_ONLY},
    # CoRoT / Spitzer -- CB2011 only (ATLAS + 2011 PHOENIX via Option B)
    {"code": "C",  "name": "CoRoT",           "category": "Space-based", "source": _CB_ONLY},
    {"code": "S1", "name": "Spitzer 3.6 μm",  "category": "Space-based", "source": _CB_ONLY},
    {"code": "S2", "name": "Spitzer 4.5 μm",  "category": "Space-based", "source": _CB_ONLY},
    {"code": "S3", "name": "Spitzer 5.8 μm",  "category": "Space-based", "source": _CB_ONLY},
    {"code": "S4", "name": "Spitzer 8.0 μm",  "category": "Space-based", "source": _CB_ONLY},
]


SOURCE_CITATIONS: Dict[str, str] = {
    _CB_CS:   "Claret & Bloemen (2011, A&A 529, A75); Claret & Southworth (2023, A&A 674, A63)",
    _CS_ONLY: "Claret & Southworth (2023, A&A 674, A63)",
    _CB_ONLY: "Claret & Bloemen (2011, A&A 529, A75)",
}


# Which atmosphere models (storage names) each source tag provides.
EXPECTED_MODELS: Dict[str, List[str]] = {
    _CB_CS:   ["ATLAS", "PHOENIX"],   # ATLAS from CB2011, PHOENIX(-COND) from CS2023
    _CS_ONLY: ["PHOENIX"],            # PHOENIX-COND from CS2023 only
    _CB_ONLY: ["ATLAS", "PHOENIX"],   # ATLAS + 2011 PHOENIX (CoRoT/Spitzer), both CB2011
}



_CS23_COND_FILTERS = [
    "U", "B", "V", "R", "I", "J", "H", "K",
    "u*", "g*", "r*", "i*", "z*",
    "u", "v", "b", "y",
    "G_BP", "G", "G_RP",
    "Kp", "TESS", "CHEOPS",
]
MODEL_DISPLAY_NAMES: Dict[Tuple[str, str], str] = {
    (code, "PHOENIX"): "PHOENIX-COND" for code in _CS23_COND_FILTERS
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

Coef4 = Tuple[float, float, float, float]


def _add_point(table_key: Tuple[str, str, float, str],
               teff: float, logg: float, feh: float,
               a1: float, a2: float, a3: float, a4: float) -> None:

    grid = _TABLES.setdefault(table_key, {
        "teffs": set(), "loggs": set(), "fehs": set(), "data": {}
    })

    t = round(float(teff), 2)
    gg = round(float(logg), 3)
    z = round(float(feh), 3)
    grid["teffs"].add(t)     # type: ignore[union-attr]
    grid["loggs"].add(gg)    # type: ignore[union-attr]
    grid["fehs"].add(z)      # type: ignore[union-attr]
    grid["data"][(t, gg, z)] = (   # type: ignore[index]
        float(a1), float(a2), float(a3), float(a4))


def _finalize_tables() -> None:
    for grid in _TABLES.values():
        grid["teffs"] = sorted(grid["teffs"])   # type: ignore[arg-type]
        grid["loggs"] = sorted(grid["loggs"])   # type: ignore[arg-type]
        grid["fehs"]  = sorted(grid["fehs"])    # type: ignore[arg-type]





_CB_SDSS_CODE_MAP = {
    "u,": "u*", "g,": "g*", "r,": "r*", "i,": "i*", "z,": "z*",
}


_CB_PHOENIX_KEEP = {"C", "S1", "S2", "S3", "S4"}

# Map a CB2011 in-file filter code to the registry source tag.
# CoRoT/Spitzer are CB_ONLY; all others that exist in the registry are CB_CS.
_CB_SOURCE_BY_CODE: Dict[str, str] = {}
for _f in FILTER_REGISTRY:
    if _f["source"] in (_CB_CS, _CB_ONLY):
        _CB_SOURCE_BY_CODE[_f["code"]] = _f["source"]


def _parse_tableeq5(path: str) -> int:
    count = 0
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            # Model field starts at byte 61 (index 60); the value ("ATLAS"=5 /
            # "PHOENIX"=7) may be the last token, so rows are ~65-67 chars.
            # Guard only on reaching the model field, not the ReadMe Lrecl.
            if len(line) < 61:
                continue
            try:
                logg = float(line[0:5])
                teff = float(line[6:12])
                feh  = float(line[13:17])
                xi   = float(line[18:22])
                a1   = float(line[23:30])
                a2   = float(line[31:38])
                a3   = float(line[39:46])
                a4   = float(line[47:54])
            except ValueError:
                continue

            raw_code = line[55:57]
            # Normalize SDSS prime-as-comma codes to registry codes; other
            # codes are recovered by stripping trailing spaces.
            code = _CB_SDSS_CODE_MAP.get(raw_code, raw_code.rstrip())
            met  = line[58:59].strip()
            mod  = line[60:67].strip()

            if met != "L":
                continue

            # Only ingest CB2011 filters that appear in this registry.
            source = _CB_SOURCE_BY_CODE.get(code)
            if source is None:
                continue

            v = _norm_xi(xi)
            if mod == "ATLAS":
                _add_point((source, code, v, "ATLAS"), teff, logg, feh, a1, a2, a3, a4)
                count += 1
            elif mod == "PHOENIX":
                # Option B: keep CB2011 PHOENIX only for CoRoT/Spitzer.
                if code in _CB_PHOENIX_KEEP:
                    _add_point((source, code, v, "PHOENIX"), teff, logg, feh, a1, a2, a3, a4)
                    count += 1
                # else: drop -- CS2023 supplies PHOENIX-COND for this band.
    return count





def _parse_cs23_4p(path: str, bands: List[Tuple[str, str]]) -> int:
    nb = len(bands)
    expected = 4 + 6 * nb
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
                    a1 = float(parts[4 + bi])
                    a2 = float(parts[4 + nb + bi])
                    a3 = float(parts[4 + 2 * nb + bi])
                    a4 = float(parts[4 + 3 * nb + bi])
                    _add_point((source, code, xi, "PHOENIX"), teff, logg, feh,
                               a1, a2, a3, a4)
            except (ValueError, IndexError):
                continue
            count += 1
    return count





CACHE_FILENAME = "tables.pkl"
CACHE_VERSION = 2

# CS2023 band orders (on-file column order), each (filter_code, source_tag).
# Gaia/TESS/CHEOPS are CS_ONLY; Kepler is CB_CS (its ATLAS comes from CB2011).
_CS23_TABLE4_BANDS = [
    ("G_BP", _CS_ONLY), ("G", _CS_ONLY), ("G_RP", _CS_ONLY),
    ("Kp", _CB_CS), ("TESS", _CS_ONLY), ("CHEOPS", _CS_ONLY),
]
_CS23_TABLE8_BANDS = [
    ("u*", _CB_CS), ("g*", _CB_CS), ("r*", _CB_CS), ("i*", _CB_CS), ("z*", _CB_CS),
]
_CS23_TABLE12_BANDS = [
    ("u", _CB_CS), ("v", _CB_CS), ("b", _CB_CS), ("y", _CB_CS),
    ("U", _CB_CS), ("B", _CB_CS), ("V", _CB_CS), ("R", _CB_CS),
    ("I", _CB_CS), ("J", _CB_CS), ("H", _CB_CS), ("K", _CB_CS),
]

SOURCE_FILES = (
    os.path.join("c11", "tableeq5.dat"),
    os.path.join("c23", "table4.dat"),
    os.path.join("c23", "table8.dat"),
    os.path.join("c23", "table12.dat"),
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
    counts["c11/tableeq5.dat"] = _parse_tableeq5(j(data_dir, "c11", "tableeq5.dat"))
    counts["c23/table4.dat"]   = _parse_cs23_4p(j(data_dir, "c23", "table4.dat"),  _CS23_TABLE4_BANDS)
    counts["c23/table8.dat"]   = _parse_cs23_4p(j(data_dir, "c23", "table8.dat"),  _CS23_TABLE8_BANDS)
    counts["c23/table12.dat"]  = _parse_cs23_4p(j(data_dir, "c23", "table12.dat"), _CS23_TABLE12_BANDS)
    _finalize_tables()
    return counts


def _save_cache(cache_path: str, counts: Dict[str, int]) -> None:
    payload = {"version": CACHE_VERSION, "tables": _TABLES, "counts": counts}
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




# ---------------------------------------------------------------------------
# Lookup / interpolation. Identical trilinear scheme as the quadratic and
# power-2 systems, extended to interpolate four coefficients (a1..a4).
# ---------------------------------------------------------------------------
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


def _nearest_available(data: Dict[Tuple[float, float, float], Coef4],
                       teff_vals: Tuple[float, float],
                       logg_vals: Tuple[float, float],
                       feh_vals: Tuple[float, float]
                       ) -> Optional[List[List[List[Coef4]]]]:
    cube: List[List[List[Coef4]]] = [
        [[(0.0, 0.0, 0.0, 0.0)] * 2 for _ in range(2)] for _ in range(2)]
    for i, te in enumerate(teff_vals):
        for j, lg in enumerate(logg_vals):
            for k, fe in enumerate(feh_vals):
                key = (round(te, 2), round(lg, 3), round(fe, 3))
                if key not in data:
                    return None
                cube[i][j][k] = data[key]
    return cube


def _filter_has_model(filter_code: str, storage_model: str) -> bool:
    for f in FILTER_REGISTRY:
        if f["code"] == filter_code:
            return storage_model in EXPECTED_MODELS.get(f["source"], [])
    return False


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
            suggestion = " Use the PHOENIX-COND model instead." if storage_model == "ATLAS" and _filter_has_model(filter_code, "PHOENIX") else ""
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

    cube = _nearest_available(data, teff_vals, logg_vals, feh_vals)  # type: ignore[arg-type]
    if cube is None:
        model_name = _display_model(filter_code, storage_model)
        raise ValueError(
            f"Invalid Input: Tables do not include data for this combination of "
            f"Teff = {teff}, log g = {logg}, and [Fe/H] = {feh} "
            f"with the {model_name} model."
        )

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

    a1 = a2 = a3 = a4 = 0.0
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                c1, c2, c3, c4 = cube[i][j][k]
                weight = w[i][j][k]
                a1 += weight * c1
                a2 += weight * c2
                a3 += weight * c3
                a4 += weight * c4

    return {
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "a4": a4,
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
