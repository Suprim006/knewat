// name: lineage/existing_ids
// purpose: Which of the given ids exist as a Step, Fact, Decision, Handoff or Task (explains a rejected link_step).
// params: ids:list[str]
// returns: id, label (one row per existing id)
// mode: ro
MATCH (n:Step) WHERE n.id IN $ids RETURN n.id AS id, 'Step' AS label
UNION
MATCH (n:Fact) WHERE n.id IN $ids RETURN n.id AS id, 'Fact' AS label
UNION
MATCH (n:Decision) WHERE n.id IN $ids RETURN n.id AS id, 'Decision' AS label
UNION
MATCH (n:Handoff) WHERE n.id IN $ids RETURN n.id AS id, 'Handoff' AS label
UNION
MATCH (n:Task) WHERE n.id IN $ids RETURN n.id AS id, 'Task' AS label
