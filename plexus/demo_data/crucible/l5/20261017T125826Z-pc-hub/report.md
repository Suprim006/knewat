# Crucible L5 results

Run 2026-10-17T12:58:26Z, code 468601e, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

# L5b hub variant (plan §5.3): one entity, 200 facts of distinct predicates

Seed 20261016, embedder FastEmbedder, hub `Atlas Core Platform` with 200 facts (resolved fan 200), 40 ordinary entities x 5 facts, 400 facts; predicate fan mean 2.00 (max 6). LLM calls: 0.

| Arm | recall@1 | recall@5 | other hub fact above target | other hub fact in top 5 | entity facts added (mean) | probe ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|
| off | 97.5% | 100.0% | 2.5% | 100.0% | 0.0 | 15.5 | 2.0 |
| sep-entity | 97.5% | 100.0% | 2.5% | 100.0% | 0.0 | 29.5 | 5.0 |
| sep-flat | 97.5% | 100.0% | 2.5% | 100.0% | 0.0 | 29.2 | 5.0 |
| sep | 100.0% | 100.0% | 0.0% | 100.0% | 0.0 | 29.8 | 5.0 |

| Criterion | hard | ok | value |
|---|---|---|---|
| hub: sep recall@1 >= 0.90 (plan §5.3) | no | PASS | [1.0] |
| hub: sep recall@1 >= 0.80 (falsification floor) | yes | PASS | [1.0] |
| hub: sep other hub fact above the target <= 10% | no | PASS | [0.0] |
| hub: flat boost puts another hub fact above the target >= 30% (plan §5.3) | no | FAIL | [0.025] |
| hub: flat boost has another hub fact in the top 5 >= 30% (plan §5.3 as written) | no | PASS | [1.0] |
| hub: sep recall@1 - sep-entity recall@1 >= 0.10 (the predicate cue is what helps) | no | FAIL | [0.975, 1.0] |
| hub: sep-entity recall@1 within 2 probes (0.01) of off (zero lift at fan 200) | no | PASS | [0.975, 0.975] |


## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| hub: sep recall@1 >= 0.90 (plan §5.3) | no | PASS | [1.0] |
| hub: sep recall@1 >= 0.80 (falsification floor) | yes | PASS | [1.0] |
| hub: sep other hub fact above the target <= 10% | no | PASS | [0.0] |
| hub: flat boost puts another hub fact above the target >= 30% (plan §5.3) | no | FAIL | [0.025] |
| hub: flat boost has another hub fact in the top 5 >= 30% (plan §5.3 as written) | no | PASS | [1.0] |
| hub: sep recall@1 - sep-entity recall@1 >= 0.10 (the predicate cue is what helps) | no | FAIL | [0.975, 1.0] |
| hub: sep-entity recall@1 within 2 probes (0.01) of off (zero lift at fan 200) | no | PASS | [0.975, 0.975] |
