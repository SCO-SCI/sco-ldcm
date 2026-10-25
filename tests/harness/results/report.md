# SCO-LDC v5 harness report — 2026-10-15 11:01 UTC (local layers, on Ed's computer) and 2026-10-18 10:14 UTC (live layers, against staging)

## Layer 1, local: v4 code vs v5 code, every node, cell centre and random interior point at 2 km/s
- quad: 467659 points, 0 discrepancies
- power2: 474122 points, 0 discrepancies
- fourparam: 474466 points, 0 discrepancies
## Layer 5 — the fields Phase 2 added, at every velocity, plus the Phase 3 reference stars

- quad: 592234 points, 0 discrepancies, 2898 with an edge point, 19885 with a correction, 0 profiles no real star could have, nodes included (reported, not failed)
- power2: 597597 points, 0 discrepancies, 61421 with an edge point, 0 with a correction, 20 profiles no real star could have, nodes included (reported, not failed)
- fourparam: 597941 points, 0 discrepancies, 61421 with an edge point, 18329 with a correction, 7309 profiles no real star could have, nodes included (reported, not failed)

## Layer 6 — the page's dropdown evaluator, exhaustively, without a browser

- quad: 16848 states, 212154 tags (1081 distinct), 5749 transitions, deepest settle 3, 146 of 146 combinations reachable from the default state, 0 failures
- power2: 22464 states, 392306 tags (1912 distinct), 7321 transitions, deepest settle 3, 149 of 149 combinations reachable from the default state, 0 failures
- fourparam: 31200 states, 642340 tags (2898 distinct), 8056 transitions, deepest settle 3, 150 of 150 combinations reachable from the default state, 0 failures
  (engine: mini-racer; scoEvaluate md5 da1d1d456941983267985d9bd74e5613)

## Layer 2: velocity tables, nodes vs table rows and interior points vs independent oracle
- quad: xi=0 32075/0, xi=1 32025/0, xi=2 467659/0, xi=4 30575/0, xi=8 29900/0 (points/failures)
- power2: xi=0 29509/0, xi=1 38329/0, xi=2 474122/0, xi=4 28129/0, xi=8 27508/0 (points/failures)
- fourparam: xi=0 29509/0, xi=1 38329/0, xi=2 474466/0, xi=4 28129/0, xi=8 27508/0 (points/failures)
## Layer 3: advertised catalogue vs loaded grids (live test service)
- quad: 146 grids in code, 146 advertised, 0 problems
- power2: 149 grids in code, 149 advertised, 0 problems
- fourparam: 150 grids in code, 150 advertised, 0 problems
## Layer 4: refusal specification, exhaustive on code, sampled live
- quad: 7669 cases, 0 local failures; live 69 requests, 0 failures
- power2: 7273 cases, 0 local failures; live 105 requests, 0 failures
- fourparam: 7278 cases, 0 local failures; live 105 requests, 0 failures
## Layer 1, live: production vs test service on a sample; legacy routes byte for byte
- quad: 300 of 467659 points, 300 pass, 0 fail
- power2: 300 of 474122 points, 300 pass, 0 fail
- fourparam: 300 of 474466 points, 300 pass, 0 fail
- legacy: 18 of 18 edge paths identical; health stable fields identical: True

**Result: PASS — zero discrepancies in every layer**
