import os
import time
import sys

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
        print(f"  {name:24s} {n:>8d} rows")
    print(f"wrote {cache_path} ({size_kb:.0f} KB)")

    
    expected = {
        "c11/tableeq5.dat": 177125,
        "c23/table4.dat":      823,
        "c23/table8.dat":      823,
        "c23/table12.dat":     823,
    }
    for fname, want in expected.items():
        got = counts.get(fname)
        if got != want:
            print(f"ERROR: {fname} parsed {got} rows, expected {want} "
                  f"(check the source file, the xi=2 km/s filter, and the "
                  f"Option B keep-rule).",
                  file=sys.stderr)
            return 1
    print("Four-parameter row counts verified "
          "(CB2011 Option B = 177125; CS2023 Eq.3/M2 = 823 each).")

    t0 = time.perf_counter()
    counts2 = ldc_core.load_tables(data_dir, use_cache=True)
    load_ms = (time.perf_counter() - t0) * 1000
    assert counts == counts2, "cache round-trip mismatch"
    print(f"cache load verified in {load_ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
