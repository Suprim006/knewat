// name: view/inventory_memory
// purpose: The memory-health counts of the View's inventory (P7): active facts that are suspect now, dormant facts, pinned facts, and the Change / CodeAnchor nodes.
// params: now:int
// returns: one row: suspect_facts, dormant_facts, pinned_facts, changes, code_anchors
// mode: ro
// suspect_facts follows the contract rule (verify_state = 'suspect' OR verify_after <= now) over ACTIVE facts, as staleness/suspect_ids does: two index-backed
// branches, the second excluding facts the first already counted, so nothing is counted twice. dormant_facts uses the Fact(status) index and pinned_facts the
// Fact(pinned) index; the two label counts are O(1). Facts written before P7 have none of these properties and count as 0.
CALL { MATCH (f:Fact {verify_state: 'suspect', status: 'active'}) RETURN count(f) AS marked }
CALL { MATCH (f:Fact) WHERE f.verify_after <= $now AND f.status = 'active' AND coalesce(f.verify_state, 'verified') <> 'suspect' RETURN count(f) AS due }
CALL { MATCH (f:Fact {status: 'dormant'}) RETURN count(f) AS dormant }
CALL { MATCH (f:Fact {pinned: true}) RETURN count(f) AS pinned }
CALL { MATCH (c:Change) RETURN count(c) AS changes }
CALL { MATCH (a:CodeAnchor) RETURN count(a) AS anchors }
RETURN marked + due AS suspect_facts, dormant AS dormant_facts, pinned AS pinned_facts, changes, anchors AS code_anchors
