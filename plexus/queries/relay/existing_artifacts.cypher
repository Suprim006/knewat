// name: relay/existing_artifacts
// purpose: Which of the given artifact ids exist (explains a rejected complete/fail/handoff).
// params: ids:list[str]
// returns: id (one row per existing artifact)
// mode: ro
MATCH (x:Artifact) WHERE x.id IN $ids
RETURN x.id AS id
