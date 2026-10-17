# Branch review: `feature/neuro-memory-research` (main f96df06 .. e126875)

Orchestrator review of the non-Cypher changes on the scoring path (part 1 of the review task). Read-only: nothing in the
code was changed. Scope: `activation/score.py`, `activation/rank.py` (`rerank`), `activation/settings.py`, the
D-013 parts of `activation/service.py` and `engram/service.py` that feed the ranking, and the tests
`tests/activation/test_score.py`, `test_rank_d013.py`, `test_salience.py`, `test_recall_off.py` and
`tests/integration/test_recall_separation.py`. The L5/L6 harness code (`crucible/l5/*`, `crucible/l6/*_c.py`, ~2,000
lines) was only skimmed: it is benchmark code, its results are already in `docs/BASELINE.md`. The Cypher changes are
covered by `docs/research/cypher-review/` and `CYPHER_AUDIT_SUMMARY.md`.

Already documented (D-013 + amendments, BASELINE, PLEXUS_REPORT §7.5/§8/§9) and **not** repeated here as findings:
P3 not built, `add` falsified and opt-in, the 85.7% L5b ceiling from the CONTRADICTS pairs, the noise-share cost of the
§3.3 union, "beats SQL" withdrawn, the `recall(hops)` ranking defect.

## Verdict on the three "shipped default" claims

| Setting | Claimed default (D-013 + amendment) | Code today | Match |
|---|---|---|---|
| `PLEXUS_ACT_MODE` | `mult` (`add` opt-in) | `Settings.act_mode = "mult"` (settings.py L56) and `from_env` `or "mult"` (L155) | yes |
| `PLEXUS_RECALL_SEPARATION` | on | `flag()` defaults to `"on"` (L136-140, used at L147); `Settings.separation = True` (L65) | yes |
| `PLEXUS_ACT_CUES` | `entity+predicate` at `w_entity 0.03 / w_predicate 0.02 / S 5` | `cues = "entity+predicate"` (L70, L168); `W_ENTITY_DEFAULT = 0.03`, `W_PREDICATE_DEFAULT = 0.02`, `CUE_S_DEFAULT = 5.0` (score.py L31-37), read at settings L169-171; tests pin them (`test_score.py::test_d013_settings_defaults…`) | yes |

The three default values are right. But one D-013 claim about what the default **does** is not (finding 1).

## Findings

### 1. `mult` (the default) is not "byte-for-byte D-012 plus the bypass fix and separation": salience protection also applies — CONFIRMED (code + test)
D-013 decision point 2 says *"`mult` mode is byte-for-byte D-012 (plus the bypass fix and separation)"* and lists
"salience ≥ 0.5 protects from sweeps" among the P2 (`add`) features. In the code the rule is **not** gated on the mode:
`activation/service.py` L173 `if sal >= SALIENCE_PROTECT and not reasons: reasons.append(f"salience:…")` runs for both
modes, and `protected = bool(reasons)` then feeds `model.multiplier(…, protected=True)` → `max(A, A0)` in `rerank`'s
`mult` branch and the sweep's skip list. `tests/activation/test_salience.py` L95-99 pins this deliberately for
`Settings()` (mult): a fact with one VERIFIED_BY and two using agents is `protected` with reason `salience:0.86`.

Effect under the shipped default, compared with D-012: facts protected by none of D-012's rules become protected when
salience reaches 0.5 — e.g. one `verify_fact(confirmed)` alone (1.5 → 0.78), three distinct agents that *used* it
(1.0 → 0.63), or (through finding C1 of the Cypher summary) one artifact re-verified twice. They get the neutral-activation
floor in recall and are never swept.

This may well be the intended behaviour; the problem is that the decision text says otherwise. Either (a) amend D-013
point 2 / `docs/forgetting.md` to say salience protection is active in both modes, or (b) gate it with
`and st.additive` (one condition at L173, plus the test). I did not check whether the L5b fixtures have any
VERIFIED_BY / multi-agent use, so I can't say whether the measured `sep+mult` numbers include this effect. They
were produced by this code, so whatever effect it has is in them.

### 2. Two implementations of the additive score; `score.score()` is not on the production path — CONFIRMED
`score.score()` (score.py L89-135) is the documented formula, but `rank.rerank` never calls it: the `add` branch
recomputes `sc = math.log(rel) + act + sep + sal` inline (rank.py L174) from `S.act_term`/`S.sal_term`/
`S.context_term`. Only `tests/activation/test_score.py` calls `S.score()`. Today the two agree (`rel` is already clamped,
`rho = 0`, bypass zeroes `act`/`sal` in both), but they can drift: the `rel_term`/`reliability`/`rho` P3 hook exists
only in the unused function, so wiring P3 into `score()` would silently do nothing.
Proposed fix: have `rerank` call `S.score(rel, A=a, …, bypass=bypass)` for `add` mode, then derive `act`/`sal` for the
`Ranked` record from the same helpers. Alternatively, delete `score()` and point the formula test at `rerank`. Also
`RELIABILITY_PRIOR`, `rho` and `reliability` are dead until P3, which the docstring already admits. Fine to keep, but
they are only reachable from the unused function.

### 3. Two "hub" thresholds coexist in the default configuration — design note
With `cues = "entity+predicate"` (default) the context term's hub point is `S = 5` (fan ≥ e⁵ ≈ 148 gives no lift), but
the sibling expansion in `engram/recall` is still damped with `smax = settings.s_max = ln 50` (engram/service.py L593),
the single-cue P1 parameter. An entity with fan 100 gets a small entity lift (0.03 × (5 − ln 100) ≈ 0.012) while its
siblings are not expanded at all. `gamma` is unused in the default mode. The settings docstring documents both roles of
`PLEXUS_ACT_SMAX`, but the D-013 amendment doesn't say the damping kept the P1 constant. Either tie the damping to
`cue_s`, or add one line to the amendment saying the two thresholds are intentional.

### 4. Naming collisions around `S` — clarity
`rank.py` imports the module as `S` (`from plexus.activation import score as S`, L27), and `score()` takes a keyword
parameter also named `S` (the ACT-R cue strength) next to `S_max`, `s_noise` and `s_max_band`. Settings call the same
things `cue_s`, `s_max`, `s_noise`. `service.py` already uses `score as score_mod`. Suggest using `score_mod` in
`rank.py` and renaming the parameter `S` to `cue_s` (matching Settings). These are pure renames, covered by the
existing tests.

### 5. `Ranked` fields change meaning by mode — clarity
In `mult` mode `Ranked.act = ln(multiplier)` (rank.py L162), `sal = 0`, and `salience`/`in_band` are computed and
reported but unused. In `add` mode `act` is the bounded tanh term. The dataclass comment says `act` is "the activation
term (add mode)". `why_recalled`/API consumers that compare `act` across modes will compare different quantities.
Document the `mult` meaning on the field, or set `act = 0.0` in `mult` mode (the multiplier is already in `multiplier`).

### 6. Small leftovers from the multiple passes
- rank.py L139-140: `pred_match` tests `r.get("predicate") in preds` but `pred_fan` looks up
  `preds.get(str(r.get("predicate")))`. Harmless (predicates are strings) but inconsistent; drop the `str()`.
- rank.py L121-124: `lures_of` and the band/salience scan run for every row in both modes; in `mult` mode only `lures`
  is used. This is negligible at ≤ 50 rows and is mentioned only for tidiness.
- engram/service.py L756: `_fetch_candidates(..., smax: float = 1.0)` — the default is never what production passes
  (`ln 50`); `1.0` would damp any fan > e to zero if a future caller set `damp=True` without `smax`. Make it keyword-only
  with no default, or default to `S_MAX_DEFAULT`.
- activation/service.py `strength()` L279-292: `entity_lift` is reported even when `separation` is off (recall applies no
  lift then), and uses the **global** fan from `activation/entity_fan` rather than the searched-scope fan recall uses. It
  is a reporting difference only and also appears in the Cypher review.
- settings.py docstring L4-6: a broken line wrap (`[mult] (``mult``\n= D-012 multiplier,\n``add`` …`). Cosmetic.
- `activation/sweep_apply.cypher` re-checks every D-012 protection inside the write but not the D-013 salience rule
  (Python checks it before listing). A fact that became salient between listing and applying can still be swept.
  Sweeps are reversible, so this is low impact.

### 7. Tests
The default constants are pinned (`test_score.py`). The identity contract is pinned with both switches off
(`test_recall_off.py`). `test_rank_d013.py` covers the `rerank` composition in both modes, the band guard, the lures
rule and the bypass kinds. Gaps that match the findings above:
- No test asserts `rerank`'s `add` score equals `S.score()` (finding 2).
- No test states that `mult` mode with no salience inputs is still exactly D-012. Only "both off" is pinned, and finding 1
  shows the salience rule is active in `mult`.
- No test covers `artifacts_ok` with a multiply-verified artifact or an artifact on a not-done task. This is the Cypher
  semantic bug C1 in the summary, and it feeds finding 1.

## Internal consistency with the docs

Apart from finding 1, the code matches what D-013 and its amendment say was built:
- the named-entity rule;
- the two-cue context term, floored at 0, with `PLEXUS_ACT_CUES=entity` restoring the P1 form;
- `ln rel + sep` kept on bypass;
- the mode-aware sweep margin (2.0 / 0.72);
- the `pin` salience cache;
- the extra bounded reads (`recall_entities`, `recall_predicates`, `recall_hop_facts` at hop 0).

I found no unused setting: every `Settings` field is read by `rank`, `service`, `engram` or the harness.
