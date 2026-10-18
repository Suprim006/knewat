"""A stand-in for ``claude -p`` for the L6 tests (no LLM, no subscription).

Reads the prompt on stdin, finds ``Question <id>:`` and answers from the JSON file in ``FAKE_ANSWERS`` (``{id: answer}``).
``FAKE_TOOLS`` (comma list) makes it emit tool_use blocks; ``FAKE_PROSE`` puts a sentence before the JSON; ``FAKE_COST``
sets total_cost_usd; ``FAKE_SUBTYPE`` the result subtype; ``FAKE_ARGS`` / ``FAKE_COUNT`` name files that get the argv /
one line per call.
"""

import json
import os
import re
import sys


def emit(obj):
    print(json.dumps(obj), flush=True)


def main():
    prompt = sys.stdin.read()
    if os.environ.get("FAKE_COUNT"):
        with open(os.environ["FAKE_COUNT"], "a", encoding="utf-8") as f:
            f.write("x\n")
    if os.environ.get("FAKE_ARGS"):
        with open(os.environ["FAKE_ARGS"], "a", encoding="utf-8") as f:
            f.write(json.dumps(sys.argv[1:]) + "\n")
    m = re.search(r"Question (\w+):", prompt)
    qid = m.group(1) if m else "?"
    answers = {}
    if os.environ.get("FAKE_ANSWERS"):
        with open(os.environ["FAKE_ANSWERS"], encoding="utf-8") as f:
            answers = json.load(f)
    emit({"type": "system", "subtype": "init", "session_id": "fake"})
    for t in filter(None, os.environ.get("FAKE_TOOLS", "").split(",")):
        emit(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "t", "name": t, "input": {}}]},
            }
        )
    reply = json.dumps({"answer": answers.get(qid, "unknown")})
    if os.environ.get("FAKE_PROSE"):
        reply = "Let me think about it. " + reply
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}})
    emit(
        {
            "type": "result",
            "subtype": os.environ.get("FAKE_SUBTYPE", "success"),
            "is_error": False,
            "result": reply,
            "num_turns": 2,
            "total_cost_usd": float(os.environ.get("FAKE_COST", "0.05")),
            "duration_api_ms": 5,
            "usage": {
                "input_tokens": 3,
                "output_tokens": 7,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": len(prompt) // 4,
            },
            "modelUsage": {"claude-sonnet-5-5": {}},
            "permission_denials": [],
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
