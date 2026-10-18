# The graph didn't fix what I thought it would fix

*Second post in a series about Plexus, a graph-backed memory and coordination layer for AI agent teams, built for
the FalkorDB Graph Hacks Track 02. The first post asked whether a graph beats SQL on raw correctness and speed
(short answer: mostly a tie). This one asked a harder question and got an answer I didn't want.*

I went into this benchmark round with a hypothesis I was pretty attached to: a graph gives you query
expressiveness, easy multi-tenancy, and easy traversal. SQL gives you atomic writes. Four clean buckets, each
backend wins its own. I spent a day designing the tests to prove it. Then I spent a few more days finding out
two of those four buckets don't hold up, and that none of it mattered as much as I thought anyway.

## Round one: hunting for the real mechanism-level differences

The first benchmark (L6, in the earlier post) tied SQLite and FalkorDB on almost everything, because the test
questions were things any competent store can answer. So I built a second round, specifically designed to find
places where the designs should differ: multi-tenancy at scale (1 to 2,000 tenants), traversal-shaped queries
SQL is supposedly bad at, atomic writes under real crash injection, and a concurrent-session load test from 2
sessions up to a thousand.

**Traversal: SQL won, and not narrowly.** On every unbounded traversal cell, hand-written SQL beat Cypher,
25x to 900x at 50,000 facts. The constrained-shortest-path query timed out on 6 of 12 questions in Cypher. All
three Cypher forms of a closure query timed out completely, while the recursive SQL version answered in 7.4
seconds. The reason is almost boring once you see it: FalkorDB enumerates whole paths and filters afterward,
while a recursive CTE prunes and deduplicates at every step. Cypher won exactly one motif question, 5.9x faster
at the largest scale. I expected the opposite of this result going in.

**Multi-tenancy: real but narrower than the pitch.** Isolation was a tie: zero cross-tenant leaks on the
product path from 1 to 2,000 tenants in either backend. A SQLite file per tenant locks down just as easily as
a FalkorDB graph per tenant. Where FalkorDB actually wins is that per-operation latency stays flat as tenant
count grows (0.9x to 1.1x ratio from N=1 to N=2,000), while SQLite's gets 14x to 40x worse over the same range,
even though it's still faster in absolute terms the whole way. That's a real win. It comes at a real cost
though: FalkorDB creates a tenant 9x slower, uses 4x to 15x more memory per tenant, and at 1,000 concurrent
sessions over 200 tenants it rejected about 90% of calls with a queue-limit error. SQLite rejected none.

**Atomic writes: confirmed, and then immediately complicated.** I killed a process mid-write 200 times on a
6-entity close-out operation. SQLite's transaction: zero partial writes. Plexus's actual product code, which
spreads that same write across four separate tool calls: 86 partial writes out of 200. That's the result I
expected. Then I tested a single Cypher statement doing the same work in one shot, and it matched SQLite's
guarantee exactly, in every crash scenario, with one network round trip instead of thirteen and 26 lines of
code instead of 39. So "SQL wins atomic writes" turned into "SQL wins atomic writes when your own code doesn't
use the atomicity you already have." That's a bug in my product, not a limit of the database.

Somewhere in the middle of the crash tests I also reproduced a nondeterministic FalkorDB segfault on log replay,
10 times out of 11 attempts, tied to a race between graph deletion and async memory freeing. I kept the crashed
container as evidence instead of deleting it. That one's going in a bug report, not a slide.

## Round two: does any of this matter to an actual agent?

All of that was still mechanism-level. Multi-tenant latency curves and traversal timing are things a database
nerd cares about. They're not what a team of AI agents cares about. An agent doesn't care whether the query
took 4 milliseconds or 400. It cares whether it just acted on a fact that stopped being true an hour ago and
nobody told it.

So I built a third round that measures outcomes instead of mechanisms: stale-act rate (how often an agent acted
on a fact already invalidated by a code or spec change), step repetition and the other MAST failure signatures,
time-to-notice a change, contradiction-detection latency, and tokens spent per correct action rather than per
question. Everything scored deterministically against a known fault-injection schedule, no LLM judge. Three
real Claude Code agents, five seeded runs each, a 20-sprint history that doesn't fit in context, with ten code
and spec changes, three crashes, and three planted contradictions landing on an identical timeline for every
backend.

I expected Plexus to win this one. It didn't.

Ordered worst to best across the pooled metrics: unmodified Claude Code managing its own memory files, no tools
at all, came in at or below Plexus. SQLite came out ahead of both. Plexus matched SQLite on catching
contradictions at write time, which is the one place the design should obviously help and it did. Everywhere
else it lost. It missed more stale facts than either baseline (11 of 41 changes never noticed, against 4 for
SQLite and 2 for the plain-files agent). It found only 3 of 15 history facts it needed, against 5 for SQLite
and all 15 for the agent that just grepped its own files. In four of five runs, that recall failure directly
caused a task to fail. And it cost 2x to 2.7x more tokens per correct action, for worse outcomes, not better
ones.

The reasons aren't mysterious once you look. The staleness-detection tools exist in Plexus specifically to
solve this problem, and the agents never called a single one, across all five runs, because the test never
told them those tools existed. So the one feature built for exactly this situation was never exercised. And
separately, the agents read raw files far less than the baselines (72 times versus 106 for SQLite and 277 for
the plain-files agent) and leaned on semantic recall instead, and that recall just isn't finding the right
facts. That's an embedding and ranking problem. It has nothing to do with whether the backend is a graph.

## What I actually believe now

The headline I wanted to write was "Plexus cut stale actions by X% and step repetition by Y%, at Z times the
tokens." The headline the data supports is: not in this configuration, and here's exactly why not. I'd rather
publish that than quietly rerun it until the number looks better, which is the whole point of writing the
prediction down before the test instead of after.

None of this means the graph model is wrong. The write-time contradiction detection worked. The crash-atomicity
story is fine once the product code actually uses one statement instead of four. What it means is that the
part of the pitch I was most confident about, long-horizon memory actually changing agent behavior for the
better, is the part I had the least evidence for, and now that I've gone looking, the evidence says the
bottleneck is retrieval quality, not the data model underneath it. Fixing that, and rerunning this exact test
with the staleness tools actually in the agents' hands, is the next thing on the list. Not a new feature. A
retry of the test that just told me I was wrong.

Source and full result files: `<REPO_URL>`, `docs/research/P10_GRAPH_VS_SQL.md` and
`docs/research/L8_LONG_HORIZON_OUTCOMES.md`. Every run is seeded, every prediction was written before the run
that tested it, and every number in this post came out of a committed results file, not a screenshot.
