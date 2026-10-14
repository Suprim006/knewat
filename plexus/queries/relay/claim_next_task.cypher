// name: relay/claim_next_task
// purpose: Atomically claim the best ready task for an agent: dependency-aware, lease-aware, one statement.
// params: agent:str, lease_ms:int, now:int
// returns: id, title, priority, version, lease_until, claimed_by, reclaimed_from ('' unless an expired lease was
//   taken over; then the previous claimer). Zero rows = nothing claimable (or unknown agent).
// mode: rw
// Candidates: status 'open', or status 'claimed' whose lease expired (lease_until < now). A candidate is ready
// only when it has no DEPENDS_ON target whose status is not 'done' (a failed dependency blocks it forever).
// Writes are serialised per graph and this is a single statement, so two agents can never win the same task.
// The ORDER BY ... LIMIT 1 happens BEFORE any write (LIMIT does not stop eager writes). The dependency check
// uses OPTIONAL MATCH + count(), not a pattern-comprehension size([...]) (reference section 2, item 13).
MATCH (a:Agent {id: $agent})
MATCH (t:Task)
WHERE t.status IN ['open', 'claimed'] AND (t.status = 'open' OR t.lease_until < $now)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH a, t, count(d) AS open_deps
WHERE open_deps = 0
WITH a, t ORDER BY t.priority DESC, t.created_at ASC, t.id ASC LIMIT 1
WITH a, t, t.claimed_by AS previous
SET t.status = 'claimed', t.claimed_by = $agent, t.lease_until = $now + $lease_ms, t.version = t.version + 1
CREATE (a)-[:CLAIMED {at: $now, lease_until: $now + $lease_ms, reclaimed_from: previous}]->(t)
RETURN t.id AS id, t.title AS title, t.priority AS priority, t.version AS version,
       t.lease_until AS lease_until, t.claimed_by AS claimed_by, previous AS reclaimed_from
