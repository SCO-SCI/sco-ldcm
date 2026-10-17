import os
import time
import sys

# The engine imports from the repository's shared/ package, so the repository
# root must be importable when this script is run from inside quad/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ldc_core


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    cache_path = os.path.join(data_dir, ldc_core.CACHE_FILENAME)
    if os.path.exists(cache_path):
        os.remove(cache_path)
        print(f"removed old cache: {cache_path}")

    t0 = time.perf_counter()
    counts = ldc_core.load_tables(data_dir, use_cache=False)
    parse_ms = (time.perf_counter() - t0) * 1000

    if not os.path.exists(cache_path):
        print("ERROR: cache file was not written. Is data/ writable?",
              file=sys.stderr)
        return 1

    size_kb = os.path.getsize(cache_path) / 1024
    print(f"parsed sources in {parse_ms:.0f} ms:")
    for name, n in counts.items():
        print(f"  {name:20s} {n:>7d} rows")
    print(f"wrote {cache_path} ({size_kb:.0f} KB)")

    
    # Rows at every velocity the parsers keep (the ATLAS files at all five
    # velocities since v5, 9,586 = 7,695 at 2 km/s plus the solar rows at
    # 0, 1, 4 and 8; the PHOENIX-COND file at 2 km/s only).
    expected = {"table2.dat": 502, "table8.dat": 9586}
    for fname, want in expected.items():
        got = counts.get(fname)
        if got != want:
            print(f"ERROR: {fname} parsed {got} rows, expected {want} "
                  f"(check the source file and the xi=2 km/s filter).",
                  file=sys.stderr)
            return 1
    print("CHEOPS row counts verified (table2=502, table8=9586 at all velocities)")

    
    t0 = time.perf_counter()
    counts2 = ldc_core.load_tables(data_dir, use_cache=True)
    load_ms = (time.perf_counter() - t0) * 1000
    assert counts == counts2, "cache round-trip mismatch"
    print(f"cache load verified in {load_ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
