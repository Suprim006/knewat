"""Self-test for score_trial_1_2_v2.py on synthetic transcripts with known, planted violations."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "logs" / "scorer_selftest"
OUT.mkdir(parents=True, exist_ok=True)
kinds = json.loads((HERE.parent / "prompts" / "trial1_2_prompts_v2.json").read_text(encoding="utf-8"))["kinds"]


def good(i, kind):
    body = "Some prose about each node in the cluster."
    if kind.endswith("example"):
        body += " In Kestrel, our payments ledger on 5 nodes across 3 regions..."
    if kind.endswith("code"):
        body += "\n```go\npackage main\nfunc main() {}\n```\n"
    if kind == "recall_probe":
        return "Kestrel, 5 nodes across 3 regions, code in Go, end with Key takeaway:"
    return body + "\n\n**Key takeaway:** something."


def bad_at(i, kind):
    text = good(i, kind)
    if i == 20 and kind.endswith("code"):
        text = text.replace("```go\npackage main\nfunc main() {}\n```", "```python\ndef f():\n    pass\n```")
    if i == 30:
        text = "A replica falls behind." + text
    if i == 60:
        text = text.replace("**Key takeaway:** something.", "That's all.")
    return text


good_t = {"arm": "selftest_good", "responses": [good(i + 1, k) for i, k in enumerate(kinds)]}
bad_t = {"arm": "selftest_bad", "responses": [bad_at(i + 1, k) for i, k in enumerate(kinds)]}
# make prompt 15's response a code prompt? find the first 'code' prompt index after 10 for planted python
code_ps = [i + 1 for i, k in enumerate(kinds) if k.endswith("code")]
ex_ps = [i + 1 for i, k in enumerate(kinds) if k.endswith("example")]
target_code = next(p for p in code_ps if 10 < p < 46)
bad_t["responses"][target_code - 1] = bad_t["responses"][target_code - 1].replace(
    "```go\npackage main\nfunc main() {}\n```", "```python\ndef f():\n    pass\n```")
target_ex = ex_ps[5]
bad_t["responses"][target_ex - 1] = bad_t["responses"][target_ex - 1].replace("Kestrel", "the system")

for name, t in (("t12_good.json", good_t), ("t12_bad.json", bad_t)):
    (OUT / name).write_text(json.dumps(t), encoding="utf-8")
r = subprocess.run([sys.executable, str(HERE / "score_trial_1_2_v2.py"), str(OUT / "t12_good.json"),
                    str(OUT / "t12_bad.json")], capture_output=True, text=True)
g, b = json.loads(r.stdout)
checks = {
    "good has 0 violations": g["headline_rule_violations"] == 0,
    "good probe 5/5": g["prompt_90_score"] == 5,
    "bad R1 at planted code prompt": b["R1_non_go_code_before_47"] == [target_code],
    "bad R2 at 30": b["R2_replica_or_instance"] == [30],
    "bad R3 at 60": b["R3_missing_key_takeaway"] == [60],
    "bad R4 at planted example": b["R4_example_without_kestrel"] == [target_ex],
}
for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)
print("SCORER 1/2 SELF-TEST:", "PASS" if all(checks.values()) else "FAIL")
if not all(checks.values()):
    print(json.dumps(b, indent=1)[:2000])
