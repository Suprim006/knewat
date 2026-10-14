// name: view/inventory_keys
// purpose: Property keys seen per label, sampled over at most $sample nodes (keeps the scan bounded).
// params: sample:int
// returns: label, keys (distinct property names, unordered)
// mode: ro
MATCH (n)
WITH n LIMIT $sample
UNWIND keys(n) AS k
RETURN labels(n)[0] AS label, collect(DISTINCT k) AS keys
ORDER BY label
