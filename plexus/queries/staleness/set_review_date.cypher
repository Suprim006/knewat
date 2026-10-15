// name: staleness/set_review_date
// purpose: Set (or clear, with open_to) the review date of a fact that is not about code (a deployed URL, an account, a client request): once it has passed the fact is suspect.
// params: fact_id:str, verify_after:int
// returns: fact_id, verify_after. Zero rows = no such fact.
// mode: rw
MATCH (f:Fact {id: $fact_id})
SET f.verify_after = $verify_after
RETURN f.id AS fact_id, f.verify_after AS verify_after
