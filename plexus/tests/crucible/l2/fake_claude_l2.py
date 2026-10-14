"""A stand-in for ``claude -p`` for the L2 tests (no LLM, no subscription).

Speaks the ``--output-format stream-json`` protocol: reads the whole prompt on stdin, finds ``Question Qnn:`` and
answers from the JSON file named by ``FAKE_ANSWERS`` (``{"Q05": <answer>}``); a question missing from the file gets
``{"answer": "unknown"}``. ``FAKE_MODE``: ``deny`` (permission_denials in the result), ``tool`` (a tool_use block),
``garbage`` (a reply that is not JSON), ``fail`` (exit 1 without a result). ``FAKE_COUNT`` names a file that gets one
line appended per invocation, so tests can count real calls.
"""

from __future__ import annotations

import json
import os
import re
import sys


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def main() -> int:
    prompt = sys.stdin.read()
    if os.environ.get("FAKE_COUNT"):
        with open(os.environ["FAKE_COUNT"], "a", encoding="utf-8") as f:
            f.write(f"{len(prompt)}\n")
    mode = os.environ.get("FAKE_MODE", "")
    if mode == "fail":
        print("boom", file=sys.stderr)
        return 1
    m = re.search(r"Question (Q\d+):", prompt)
    qid = m.group(1) if m else "?"
    answers = {}
    if os.environ.get("FAKE_ANSWERS"):
        with open(os.environ["FAKE_ANSWERS"], encoding="utf-8") as f:
            answers = json.load(f)
    emit({"type": "system", "subtype": "init", "session_id": "fake", "tools": []})
    if mode == "tool":
        emit(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]},
            }
        )
    reply = "no idea" if mode == "garbage" else json.dumps({"answer": answers.get(qid, "unknown")})
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}})
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": reply,
            "num_turns": 1,
            "total_cost_usd": 0.01,
            "duration_api_ms": 5,
            "usage": {
                "input_tokens": 3,
                "output_tokens": 7,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": len(prompt) // 4,
            },
            "modelUsage": {"claude-fake": {}},
            "permission_denials": [{"tool_name": "Read"}] if mode == "deny" else [],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
