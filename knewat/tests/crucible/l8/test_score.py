"""Scorer unit tests on hand-made transcripts (no DB, no model): every count below is computed by hand."""

from __future__ import annotations

import json
from pathlib import Path

from knewat.crucible.l8.score import Truth, perm_test, score_run, wilson

OLD, NEW, OTHER, X2OLD = "AX-11111", "AX-22222", "AX-33333", "AX-30001"


def _sentinels() -> dict:
    return {
        "functions": {
            "auth.token_ttl": [{"token": OLD, "from_turn": 0}, {"token": NEW, "from_turn": 3, "change": 1}],
            "api.base_path": [{"token": OTHER, "from_turn": 0}],
            "ratelimit.window": [{"token": X2OLD, "from_turn": -1}, {"token": "AX-44444", "from_turn": 0}],
        }
    }


def _use(i: str, name: str, inp: dict) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]},
        }
    )


def _res(i: str, content: object, err: bool = False) -> str:
    c = content if isinstance(content, str) else json.dumps(content)
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": i, "content": c, "is_error": err}]
            },
        }
    )


def _text(t: str) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}})


def _write_run(tmp: Path) -> tuple[Path, Path]:
    seed = tmp / "seeds" / "1"
    seed.mkdir(parents=True)
    (seed / "sentinels.json").write_text(json.dumps(_sentinels()))
    (seed / "schedule.json").write_text(json.dumps({"x2_old_token": X2OLD, "commits": []}))
    run = tmp / "runs" / "1" / "P"
    (run / "transcripts").mkdir(parents=True)
    P = "mcp__knewat__"
    art = "<workdir>/artifacts/t07-implement-crud-spec/crud-spec.md"
    t = {
        # turn 2: assert the old value (current then) -> scored, current
        "02-researcher-t04-survey-infra-security": [
            _use("a", P + "assert_fact", {"subject": "S", "predicate": "auth.token_ttl", "value": OLD}),
            _res("a", {"fact_id": "f1"}),
        ],
        # turn 3 (after the commit landed before turn 3)
        "03-builder-t07-implement-crud-spec": [
            _use("b", P + "claim_next_task", {"lease_ms": 1}),
            _res("b", {"task": {"id": "t07-implement-crud-spec", "version": 1}}),
            _text(f"The code now says {NEW}."),
            # stale artifact write (old only) right after the agent wrote the new token in its text -> stale + M1
            _use(
                "c", "Write", {"file_path": art, "content": f"auth.token_ttl: {OLD}\napi.base_path: {OTHER}"}
            ),
            _res("c", "ok"),
            # both old and new -> current
            _use(
                "d",
                "Write",
                {"file_path": art, "content": f"auth.token_ttl: {NEW} (was {OLD})\napi.base_path: {OTHER}"},
            ),
            _res("d", "ok"),
            # completion while the file lacks auth.session_cookie / notes.max_length (not tracked here -> ignored): not C2
            _use(
                "e",
                P + "complete_task",
                {
                    "task_id": "t07-implement-crud-spec",
                    "expected_version": 1,
                    "artifacts": [{"summary": f"ttl {NEW}"}],
                },
            ),
            _res("e", {"task_id": "t07-implement-crud-spec"}),
            # second completion of the same task -> R1
            _use(
                "g",
                P + "complete_task",
                {
                    "task_id": "t07-implement-crud-spec",
                    "expected_version": 1,
                    "artifacts": [{"summary": f"ttl {NEW}"}],
                },
            ),
            _res("g", {"task_id": "t07-implement-crud-spec"}),
            # duplicate assert of the same triple -> R2 (current, scored)
            _use("h", P + "assert_fact", {"subject": "S", "predicate": "auth.token_ttl", "value": OLD}),
            _res("h", {"fact_id": "f1", "duplicate_of": "f1"}),
            # handoff with a token and no fact ids -> M3 (stale: OLD after the commit, NEW absent)
            _use(
                "i",
                P + "handoff",
                {"to_agent": "planner", "task_id": "t07", "note": f"ttl is {OLD}", "fact_ids": []},
            ),
            _res("i", {"handoff_id": "h1"}),
            # an errored write is not scored
            _use("j", P + "assert_fact", {"subject": "S", "predicate": "x", "value": OLD}),
            _res("j", "boom", err=True),
        ],
    }
    for name, lines in t.items():
        (run / "transcripts" / f"{name}.jsonl").write_text("\n".join(lines) + "\n")
    rec = {"seed": 1, "arm": "P", "status": "completed",
           "turns": [{"turn": 1, "agent": "planner", "name": "init", "kind": "init"},
                     {"turn": 2, "agent": "researcher", "name": "t04-survey-infra-security", "kind": "task", "start_ms": 1000, "end_ms": 2000},
                     {"turn": 3, "agent": "builder", "name": "t07-implement-crud-spec", "kind": "task", "start_ms": 3000, "end_ms": 4000}],
           "commits_landed": [{"k": 1, "kind": "value", "funcs": ["auth.token_ttl"], "landed_before_turn": 3, "sha": "s1"}],
           "events": [], "kills_fired": {},
           "claude": {"tokens": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 1000,
                                 "cache_creation_input_tokens": 200}, "total_cost_usd": 0.5}}  # fmt: skip
    (run / "run.json").write_text(json.dumps(rec))
    (run / "store_dump.json").write_text(json.dumps({"facts": [{"id": "f1", "value": OLD, "status": "active"}],
                                                    "wrote": [{"node": "f1", "agent": "researcher", "at": 1500}, {"node": "h1", "agent": "planner", "at": 3500}], "tasks": [], "changes": []}))  # fmt: skip
    return run, seed


def test_truth_current_and_stale() -> None:
    run = {"commits_landed": [{"k": 1, "landed_before_turn": 3}], "turns": [{"turn": 3}]}
    T = Truth.build(run, {}, _sentinels())
    assert T.current("auth.token_ttl", 2) == OLD and T.current("auth.token_ttl", 3) == NEW
    assert T.stale_tokens(f"x {OLD}", 2) == [] and T.stale_tokens(f"x {OLD}", 3) == [OLD]
    assert T.stale_tokens(f"{OLD} -> {NEW}", 3) == []
    assert T.stale_tokens(X2OLD, 1) == [X2OLD]  # the S03 note's value is stale from the start


def test_score_hand_counts(tmp_path: Path) -> None:
    run, seed = _write_run(tmp_path)
    m = score_run(run, seed)
    sa = m["stale_act"]
    # scored: a(cur) c(stale) d(cur) e(cur) g(cur) h(STALE: OLD after commit) i(stale); j errored -> 7 actions
    assert sa["scored_actions"] == 7
    assert sa["stale"] == 3
    assert m["mast"]["R1"] == 1 and m["mast"]["R2"] == 1 and m["mast"]["R3"] == 0
    assert m["mast"]["M1"] >= 1  # c (and h, i) follow the text naming NEW
    assert m["mast"]["M3"] == 1
    # correct = scored - stale - repetition(g; h is both) = 7 - 3 - 1 = 3
    assert m["tokens"]["correct_actions"] == 3
    assert m["tokens"]["total"] == 1350 and m["tokens"]["billing_weighted"] == round(150 + 100 + 250)
    # f1 written by the researcher inside turn 2 -> has a record; the duplicate ack (h) is skipped; the handoff's
    # WROTE row is by another agent -> no record (amendment 3 rule)
    assert m["provenance"]["by_tool"]["assert_fact"] == {"with_record": 1, "acknowledged": 1, "rate": 1.0}
    assert m["provenance"]["by_tool"]["handoff"] == {"with_record": 0, "acknowledged": 1, "rate": 0.0}
    assert m["provenance"]["duplicate_acks_skipped"] == 1


def test_stats() -> None:
    assert perm_test([0.1] * 5, [0.5] * 5) == round(2 / 252, 4)
    assert perm_test([0.1, 0.2], [0.1, 0.2]) == 1.0
    assert wilson(0, 10)[0] == 0.0
