# SCO-LDC v5 harness report — 2026-09-11 05:12 UTC

## Layer 1, local: v4 code vs v5 code, every node, cell centre and random interior point at 2 km/s
- quad: 467659 points, 0 discrepancies
- power2: 474122 points, 0 discrepancies
- fourparam: 474466 points, 0 discrepancies
## Layer 2: velocity tables, nodes vs table rows and interior points vs independent oracle
- quad: xi=0 32075/0, xi=1 32025/0, xi=2 467659/0, xi=4 30575/0, xi=8 29900/0 (points/failures)
- power2: xi=0 29509/0, xi=1 29463/0, xi=2 474122/0, xi=4 28129/0, xi=8 27508/0 (points/failures)
- fourparam: xi=0 29509/0, xi=1 29463/0, xi=2 474466/0, xi=4 28129/0, xi=8 27508/0 (points/failures)
## Layer 3: advertised catalogue vs loaded grids (live test service)
- quad: 146 grids in code, 146 advertised, 0 problems
- power2: 138 grids in code, 138 advertised, 0 problems
- fourparam: 139 grids in code, 139 advertised, 0 problems
## Layer 4: refusal specification, exhaustive on code, sampled live
- quad: 7655 cases, 0 local failures; live 60 requests, 0 failures
- power2: 7061 cases, 0 local failures; live 60 requests, 0 failures
- fourparam: 7066 cases, 0 local failures; live 60 requests, 0 failures
## Layer 1, live: production vs test service on a sample; legacy routes byte for byte
- quad: 150 of 467659 points, 150 pass, 0 fail
- power2: 150 of 474122 points, 150 pass, 0 fail
- fourparam: 150 of 474466 points, 150 pass, 0 fail
- legacy: 16 of 16 edge paths identical; health stable fields identical: True

**Result: PASS — zero discrepancies in every layer**
