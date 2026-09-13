SCO-LDC v5 TEST HARNESS
  Proves, before a promotion, that the service under test returns exactly
  what production returns for everything that worked before, that the new
  velocity tables serve their own rows, that what the service advertises is
  what it holds, and that every refusal the tables imply happens and nothing
  else is refused.

POINT SETS
  Ed Mullen's enumeration from quad_equivalence_sweep.py (every populated
  node, the centre of every fully populated cell) and from
  quad_random_interior_sweep.py (one seeded random point per full cell,
  seed 20260801), generalised to the v5 table key and to all three laws.
  Solar-only grids contribute two-dimensional cells (Teff x log g), so the
  centre and random counts are slightly larger than the 2025 sweep's.

LAYERS
  1 local   layer1_local.py    v4 code (main) vs v5 code, every point, no
                               network. ~1.4 million points in ~2 minutes.
  2         layer2_velocity.py every node at xi = 0,1,2,4,8 must equal its
                               table row exactly; every interior point must
                               equal an independent trilinear oracle.
  3         layer3_catalog.py  capabilities and filters?xi=N from the test
                               service vs the grids loaded from the code.
  4         layer4_refusals.py refusal specification generated from the
                               tables (table reference, section 9): missing
                               cells at 4 and 8, extra cells at 0 and 1, the
                               half-step temperatures, the non-solar node
                               rule, unsupported velocities, PHOENIX-family
                               models away from 2 km/s, non-solar metallicity
                               away from 2 km/s. Exhaustive on code, sampled
                               live.
  1 live    layer1_live.py     production vs test service on a deterministic
                               sample (default 300 points per law), prefixed
                               compute identical after removing xi; for the
                               quadratic law the legacy /api/compute byte for
                               byte; 16 legacy edge paths byte for byte; the
                               legacy health's stable fields identical.
                               Rate-limited (8/s per service), retried and
                               checkpointed as in the original sweeps.

RUNNING
  Needs two checkouts: main (what production runs) and v5.
    git clone <repo> v4 && git -C v4 checkout f7b28aa
    git clone <repo> v5 && git -C v5 checkout v5
    pip install fastapi requests
    python run_all.py --v4 ./v4 --v5 ./v5
  Results land in results/: report.md, summary.json, one JSON per layer,
  and for layer 1 local the two response dumps per law (large; delete
  after a run). Exit code 0 means zero discrepancies everywhere.
  To sweep the full enumeration against the live services as the 2025
  scripts did, raise --per-law; the checkpoint files make it resumable.

THE GATE
  A promotion of v5 to production requires a run of this harness against
  the final commit with zero discrepancies in every layer.
