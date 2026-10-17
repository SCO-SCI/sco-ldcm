SCO-LDC v5 TEST HARNESS
  Proves, before a promotion, that the service under test returns exactly
  what production returns for everything that worked before, that the new
  velocity tables and the JWST tables serve their own rows, that what the
  service advertises is what it holds, that every refusal the tables imply
  happens and nothing else is refused, and (since Phase 3) that the page's
  dropdowns offer exactly the combinations the tables hold and explain every
  move they make.

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
                               service vs the grids loaded from the code,
                               and (Phase 3) the catalogue with xi omitted:
                               every grid at 2 km/s plus every grid held
                               at a single other velocity (the JWST modes
                               at 1), by the single-velocity rule.
  4         layer4_refusals.py refusal specification generated from the
                               tables (table reference, section 9): missing
                               cells at 4 and 8, extra cells at 0 and 1, the
                               half-step temperatures, the non-solar node
                               rule, unsupported velocities, PHOENIX-family
                               models away from 2 km/s, non-solar metallicity
                               away from 2 km/s. Phase 3 adds, per JWST
                               mode: xi omitted and xi=1 served; 0, 2, 4, 8
                               refused by name; ATLAS, PHOENIX and
                               PHOENIX-COND refused naming PHOENIX-NE;
                               non-solar refused; the four grid edges
                               refused; the 200 K steps above 7000 K
                               interpolated; PHOENIX-NE on an ordinary
                               filter refused; and, for the quadratic law
                               only, each mode refused by the exact sentence
                               decided on 10 October 2026, "<code> -- the
                               JWST modes are served under the power-2 and
                               four-parameter laws only." (the frozen route
                               is covered by layer 1 live). Exhaustive on
                               code, sampled live.
  5         layer5_derived.py  the fields Phase 2 added: h1_prime and h2_prime
                               present, finite, and equal to an independent
                               evaluation of the law at the two positions;
                               edge_point_applied true exactly when the table
                               supplied mu_cri; maxted_correction present for
                               exactly the three combinations Maxted measured
                               and absent, not null, everywhere else.
                               Layer 1 removes these fields before comparing,
                               so this layer is what checks them.
                               Since Phase 3 it enumerates every velocity,
                               not only 2 km/s, so the JWST tables are
                               covered: a spherical table's point must
                               always carry an edge point, the empirical
                               correction must appear only at 2 km/s, and
                               the two reference stars of the Phase 3 brief
                               (5800 K, log g 4.5: PRISM and SOSS2, both
                               laws) must reproduce to four decimals. Where
                               a published fit is degenerate the oracle is
                               evaluated at mu_cri +/- half a unit in the
                               sixth decimal, which is the rounding the
                               served value carries. Points whose profile no
                               real star could have (h1' >= 1, h2' <= 0 or
                               h2' > h1'), nodes included, are counted and
                               reported, not failed: most of the
                               four-parameter count is the published Claret
                               & Bloemen (2011) fits themselves in Stromgren
                               v and b, about 16 per cent of those nodes.

  6         layer6_page.py     the page's input form, without a browser. The
                               evaluator (scoEvaluate) and the note writer
                               (scoNoteAfterRefresh) are cut out of
                               static/index.html verbatim and run in V8;
                               the capability maps come from the engines in
                               the checkout. Every combination of filter,
                               model and velocity (with and without typed
                               values) is checked against the documented
                               rule written again in Python: what is offered
                               is backed by a table and nothing backed is
                               withheld; every greyed option carries the
                               tag the three-tier wording rule gives, and
                               the tag is actionable; the Teff and log g
                               blurbs are the envelope of the surviving
                               tables; [Fe/H] locks exactly when they are
                               all solar-only. Then every choice a user can
                               make from every real state is settled as the
                               page settles it: at most six passes (the
                               deepest chain is recorded), always onto a
                               combination the tables hold; a setting moves
                               only when the chosen filter has no table at
                               it (decision (d)); the note after a move has
                               the decided wording (decision (i)); every
                               combination is reachable from the default
                               state and every permitted order of entry
                               lands on it; every JWST mode is one choice
                               away from the default state and settles on
                               (mode, PHOENIX-NE, 1 km/s). Needs node on the
                               PATH or  pip install mini-racer  (Python
                               3.10+). About a minute per law. The tag
                               vocabulary is written to results/
                               layer6_tags_<law>.txt so a wording change
                               can be read in full. Added for Phase 3
                               (decision (h), 10 October 2026); on its first
                               run it found two faults in the evaluator,
                               both fixed before delivery (see the Phase 3
                               delivery notes).

  1 live    layer1_live.py     production vs test service on a deterministic
                               sample (default 300 points per law), prefixed
                               compute identical after removing xi; for the
                               quadratic law the legacy /api/compute byte for
                               byte; 18 legacy edge paths byte for byte
                               (Phase 3 added a JWST code and PHOENIX-NE on
                               the frozen route); the legacy health's stable
                               fields identical.
                               Rate-limited (8/s per service), retried and
                               checkpointed as in the original sweeps.

RUNNING
  Needs two checkouts: main (what production runs) and v5.
    git clone <repo> v4 && git -C v4 checkout f7b28aa
    git clone <repo> v5 && git -C v5 checkout v5
    pip install fastapi requests
    pip install mini-racer          (layer 6, unless node is on the PATH)
    python run_all.py --v4 ./v4 --v5 ./v5
  Layer 1 live keeps a checkpoint per law so a long sweep can resume.  That
  also means it will report a PREVIOUS run's figures if the checkpoints are
  left in place -- it once reported 300 failures for a 120-point request, which
  cost some time to understand.  Before a gate run, delete them:
    rm results/l1live_*_checkpoint.json

  Results land in results/: report.md, summary.json, one JSON per layer,
  for layer 6 the capability maps it ran on and the tag vocabularies, and
  for layer 1 local the two response dumps per law (large; delete after a
  run). Exit code 0 means zero discrepancies everywhere.
  To sweep the full enumeration against the live services as the 2025
  scripts did, raise --per-law; the checkpoint files make it resumable.

THE GATE
  A promotion of v5 to production requires a run of this harness against
  the final commit with zero discrepancies in every layer.

  KEEPING THE HARNESS HONEST
  Layers 1 local and 1 live compare a v5 response against a v4 one, so every
  field v5 adds must be removed before the comparison or every point fails.
  Those fields are named in three places that must stay in step:
      engine_dump.V5_ADDED        (layer 1 local)
      layer1_live.V5_ADDED        (layer 1 live)
      parent_app.LEGACY_WITHHELD  (the service itself)
  Add a field to a compute response and it belongs in all three at once.
  Phase 3 added no field, so the three lists are unchanged.
  Phase 2 added five and, until this was noticed, layer 1 reported 1.42
  million intended differences -- a gate that fails on everything is worse
  than no gate, because the response to a wall of known-good failures is to
  wave it through.

  Whatever is removed from the comparison must be checked somewhere else.
  That is what layer 5 is for.

  Layer 6 tests the page's code by cutting it out of static/index.html, so
  a change to the page is tested the moment it is made, with no copy to
  keep in step. What it cannot see is the DOM: how a <select> settles when
  its options are rebuilt is modelled in Python from the HTML
  specification's behaviour (checked in Chromium), and the headless page
  test in the delivery notes remains the check that the real page does the
  same.
