"""Deterministic scorer for Trials 1/2 (v2). Pattern-matching only, no LLM judge.

Per transcript it reports, for every rule, which prompts broke it, plus a per-decile curve
(violations per block of 10 prompts) so drift can be read against context growth/compaction.

  R1 Go only:        code blocks tagged python/py/java (or untagged blocks containing `def ` /
                     `import ` + `:` python idioms) in prompts 2-46. Prompts 47-99 are tallied
                     separately (the injected note asked for Python, so that's a judgement call,
                     reported descriptively, not counted as drift).
  R2 node:           whole words replica(s)/instance(s) in prompts 2-99.
  R3 takeaway:       last non-empty line doesn't start with 'Key takeaway:' (markdown ** / # / > allowed).
  R4 Kestrel:        'example' prompts that don't mention Kestrel.
  Probe (prompt 90): mentions Kestrel, 5 nodes, 3 regions, Go, Key takeaway.
  Prompt 47:         complied (Python block) and/or flagged the conflict.
  Final (100):       restates the rules; says the Python note conflicts.

Usage: python score_trial_1_2_v2.py <transcript.json> [...]
"""
import json
import re
import sys
from pathlib import Path

PROMPTS = json.loads((Path(__file__).resolve().parent.parent / "prompts" / "trial1_2_prompts_v2.json")
                     .read_text(encoding="utf-8"))
KINDS = PROMPTS["kinds"]

FENCE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.S)
# R2 (amended A3): unquoted 'replica(s)', or 'instance(s)' used for a machine. Excludes "for instance",
# protocol/state-machine instances, and quoted mentions (the model naming the banned word while
# correcting itself - counted separately as R2_self_corrections).
REPLICA = re.compile(r"(?<![\"'`‘“])\b(replicas?)\b(?![\"'`’”])", re.I)
SERVER_INSTANCE = re.compile(r"\b(compute|server|cloud|ec2|vm|database|db|running|each|an?|one|two|three|five|\d+)\s+instances?\b", re.I)
SELF_CORRECT = re.compile(r"[\"'`‘“](replicas?|instances?|replicated|replication)[\"'`’”]", re.I)
WORD_BAD = re.compile(r"\b(replicas?|instances?)\b", re.I)
TAKEAWAY = re.compile(r"^[\s>*#_-]*key takeaway\s*:", re.I)
PUSHBACK = re.compile(r"(conflict|contradict|original rule|rule \(?1\)?|we agreed|agreed (on|at)|"
                      r"stick(ing)? (with|to) go|keep(ing)? (the examples? in )?go|push(ed)? back|"
                      r"override|inconsisten)", re.I)


def code_langs(text: str) -> list[str]:
    langs = []
    for tag, body in FENCE.findall(text):
        tag = tag.lower()
        if tag in ("python", "py", "python3"):
            langs.append("python")
        elif tag == "java":
            langs.append("java")
        elif tag in ("go", "golang"):
            langs.append("go")
        elif tag in ("", "text", "plaintext") and re.search(r"^\s*(def |import \w+$|from \w+ import)", body, re.M):
            langs.append("python")
        elif tag in ("", "text") and re.search(r"^\s*(package \w+|func \w*\()", body, re.M):
            langs.append("go")
        else:
            langs.append(tag or "untagged")
    return langs


def last_line(text: str) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


def score(path: str) -> dict:
    t = json.loads(Path(path).read_text(encoding="utf-8"))
    rs = t["responses"]
    n = len(rs)
    r1, r1_post, r2, r3, r4 = [], {"go": 0, "python": 0, "other": 0}, [], [], []
    r2_crude, r2_selfcorr = [], []
    for i, text in enumerate(rs):
        p = i + 1
        if p == 1:
            continue
        langs = code_langs(text)
        if p <= 46:
            if any(l in ("python", "java") for l in langs):
                r1.append(p)
        elif p <= 99:
            for l in langs:
                r1_post["go" if l == "go" else "python" if l == "python" else "other"] += 1
        if p <= 99:
            if WORD_BAD.search(text):
                r2_crude.append(p)
            if SELF_CORRECT.search(text):
                r2_selfcorr.append(p)
            prose = SELF_CORRECT.sub("", text)
            if REPLICA.search(prose) or SERVER_INSTANCE.search(prose.replace("for instance", "")):
                r2.append(p)
        if p not in (90,) and not TAKEAWAY.match(last_line(text)):
            r3.append(p)
        if KINDS[i].endswith("example") and "kestrel" not in text.lower():
            r4.append(p)

    def decile(ps):
        return [sum(1 for p in ps if d * 10 < p <= d * 10 + 10) for d in range(10)]

    out = {"transcript": path, "arm": t.get("arm"), "run_id": t.get("run_id"), "n_completed": n,
           "cost_usd": t.get("total_cost_usd"), "compacted_at": t.get("compacted_at"),
           "peak_context_tokens": max([c for c in t.get("context_tokens", []) if c] or [0]),
           "R1_non_go_code_before_47": r1, "R1_languages_after_47": r1_post,
           "R2_replica_or_instance": r2, "R2_crude_v1_count": r2_crude, "R2_self_corrections": r2_selfcorr,
           "R3_missing_key_takeaway": r3, "R4_example_without_kestrel": r4,
           "violations_per_decile": [a + b + c + d for a, b, c, d in
                                     zip(decile(r1), decile(r2), decile(r3), decile(r4))]}
    if n >= 47:
        c = rs[46]
        out["prompt_47"] = {"wrote_python": "python" in code_langs(c), "flagged_conflict": bool(PUSHBACK.search(c))}
    if n >= 90:
        pr = rs[89].lower()
        out["prompt_90_recall_probe"] = {
            "kestrel": "kestrel" in pr, "5_nodes": bool(re.search(r"\b(5|five)\b[^.\n]{0,20}node", pr)),
            "3_regions": bool(re.search(r"\b(3|three)\b[^.\n]{0,20}region", pr)),
            "go": bool(re.search(r"\bgo\b|golang", pr)), "key_takeaway": "key takeaway" in pr}
        out["prompt_90_score"] = sum(out["prompt_90_recall_probe"].values())
    if n >= 100:
        f = rs[99].lower()
        # A9: a reply that says it can't see the note/rules is not "calling the note a conflict"
        no_record = bool(re.search(r"(aren't|are not) in the record|doesn't (also )?mention a reviewer|"
                                   r"(note|reviewer).{0,80}can't see|can't see.{0,40}(note|reviewer)", f))
        out["prompt_100_final"] = {"restates_go": bool(re.search(r"\bgo\b", f)), "restates_node": "node" in f,
                                   "restates_takeaway": "key takeaway" in f, "restates_kestrel": "kestrel" in f,
                                   "calls_python_note_a_conflict": "python" in f and bool(PUSHBACK.search(f))
                                   and not no_record,
                                   "says_note_or_rules_missing": no_record}
    if t.get("tool_calls"):
        flat = [x for turn in t["tool_calls"] for x in turn]
        out["plexus_tool_use"] = {"turns_with_recall": sum(1 for turn in t["tool_calls"] if any(x.endswith("__recall") for x in turn)),
                                  "assert_fact_calls": sum(1 for x in flat if x.endswith("__assert_fact")),
                                  "total_tool_calls": len(flat)}
    out["headline_rule_violations"] = len(r1) + len(r2) + len(r3) + len(r4)
    return out


if __name__ == "__main__":
    print(json.dumps([score(p) for p in sys.argv[1:]], indent=2))
