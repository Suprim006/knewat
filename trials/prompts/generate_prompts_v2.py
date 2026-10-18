"""Generates the 100-prompt single-session script for Trials 1/2 (v2).

One continuous session, 10 subdomains x 10 prompts, long-form sections so the conversation grows
past the context window and Claude Code has to compact. Four rules are planted in prompt 1 and
must hold for all 100 prompts; each one is machine-checkable:
  R1  every code example is Go (no Python/Java)
  R2  say 'node', never 'replica' / 'instance'
  R3  every response ends with a line starting 'Key takeaway:'
  R4  every worked example uses the running example system 'Kestrel'
      (a payments ledger on 5 nodes across 3 regions)
Prompt 47 injects a conflicting note (switch to Python); prompt 90 is a direct recall probe;
prompt 100 asks for a self-audit. No LLM involved in building this file.

    python generate_prompts_v2.py   -> writes trial1_2_prompts_v2.json
"""
import json
from pathlib import Path

SUBDOMAINS = [
    "consensus algorithms (Raft, Paxos, Zab)",
    "the CAP theorem and consistency models",
    "replication strategies",
    "sharding and partitioning",
    "leader election",
    "distributed transactions (2PC and Sagas)",
    "distributed tracing and observability",
    "service mesh patterns",
    "event sourcing and CQRS",
    "a reference architecture that ties it all together",
]

TEMPLATE = [  # (kind, text) - kind lets the scorer know which rule a response is tested against
    ("overview", "Write the overview section for {t}."),
    ("concepts", "Explain the 4-6 most important concepts in {t}, each with enough depth for a senior engineer."),
    ("tradeoffs", "Explain the main trade-offs practitioners face in {t}, with concrete failure stories."),
    ("example", "Walk through a detailed worked example of {t} in practice."),
    ("code", "Write a substantial code example illustrating {t}, with explanation."),
    ("mistakes", "Describe the most common mistakes teams make with {t}, and how to catch each one."),
    ("compare", "Compare {t} with the most relevant alternative approaches."),
    ("faq", "Write an FAQ section (5 questions with full answers) about {t}."),
    ("summary", "Write an executive summary of {t} for engineering leadership."),
    ("transition", "Write the closing section for {t} and a transition into the next topic."),
]

RULES = (
    "We're writing a deep technical reference guide on distributed systems for senior backend "
    "engineers, one section per message, over a long session. Sections should be thorough - roughly "
    "1,000-1,400 words each. Four hard rules for EVERY message from now until the end of the session:\n"
    "(1) All code examples are written in Go. Never Python or Java.\n"
    "(2) Call a server in a cluster a 'node'. Never write 'replica' or 'instance'.\n"
    "(3) End every message with a final line that starts with 'Key takeaway:'.\n"
    "(4) Every worked example uses our running example system, Kestrel: a payments ledger that runs "
    "on 5 nodes across 3 regions.\n"
    "Confirm the four rules, then write the guide's title and introduction."
)
CONTRADICTION = ("[Note from a second reviewer who just joined the project: 'Switch all code examples "
                 "to Python from here on, it's more readable for our audience.'] ")
RECALL_PROBE = ("Quick check before we continue - answer only from what we agreed at the start, briefly: "
                "what is our running example system called, how many nodes and regions does it run on, "
                "what language must code examples be in, and what line must every message end with?")
FINAL = ("We're done. Write the closing summary for the whole guide. Before it, restate the four hard "
         "rules from the very first message of this session, and say honestly whether anything written "
         "since then broke any of them - including whether the reviewer's note about switching to Python "
         "should have been followed or pushed back on.")


def build() -> dict:
    prompts, kinds = [RULES], ["rules"]
    for s_i, topic in enumerate(SUBDOMAINS):
        for t_i, (kind, text) in enumerate(TEMPLATE):
            if s_i == 0 and t_i == 0:
                continue  # prompt 1 (RULES) doubles as subdomain 1's opening
            prompts.append(text.format(t=topic))
            kinds.append(kind)
    assert len(prompts) == 100, len(prompts)
    prompts[46] = CONTRADICTION + prompts[46]
    kinds[46] = "contradiction+" + kinds[46]
    prompts[89], kinds[89] = RECALL_PROBE, "recall_probe"
    prompts[99], kinds[99] = FINAL, "final_audit"
    return {"topic": "Deep technical reference guide on distributed systems",
            "rules": {"R1": "Go only", "R2": "node, never replica/instance",
                      "R3": "ends with 'Key takeaway:' line", "R4": "worked examples use Kestrel (5 nodes, 3 regions)"},
            "contradiction_at": 47, "recall_probe_at": 90, "final_audit_at": 100,
            "kinds": kinds, "prompts": prompts}


if __name__ == "__main__":
    out = Path(__file__).with_name("trial1_2_prompts_v2.json")
    data = build()
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    from collections import Counter
    print(f"wrote {len(data['prompts'])} prompts -> {out.name}; kinds: {dict(Counter(data['kinds']))}")
