// name: relay/verify_artifact
// purpose: Record that an agent verified an artifact ((Artifact)-[:VERIFIED_BY {at, independent}]->(Agent)); idempotent per pair. `independent` = false when the verifier produced the artifact, so self-verification stays distinguishable.
// params: agent:str, artifact:str, now:int
// returns: artifact, agent, independent (true when the verifier is not the artifact's producer).
//   Zero rows = unknown agent or artifact.
// mode: rw
MATCH (x:Artifact {id: $artifact}), (a:Agent {id: $agent})
OPTIONAL MATCH (x)-[p:PRODUCED_BY]->(a)
WITH x, a, count(p) AS own
MERGE (x)-[v:VERIFIED_BY]->(a)
ON CREATE SET v.at = $now, v.independent = (own = 0)
RETURN x.id AS artifact, a.id AS agent, own = 0 AS independent
