// name: l2/episodes
// purpose: every Episode with the agent whose Session holds it.
// params: none
// returns: agent, text
// mode: ro
MATCH (a:Agent)-[:HAD]->(:Session)-[:HAS_EPISODE]->(e:Episode)
RETURN a.id AS agent, e.text AS text
ORDER BY e.at ASC, e.id ASC
