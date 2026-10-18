-- S-txn / S-auto: the close-out, one statement per entity or edge row (11), inside BEGIN IMMEDIATE ... COMMIT for S-txn.
-- The statements are separated by a line with only ';;'. The task UPDATE is the version guard (0 rows changed = miss).
INSERT INTO steps (id, co, agent_id, at) VALUES (:step, :co, :agent, :now)
;;
INSERT INTO facts (id, co, value, status, created_at) VALUES (:fact, :co, :value, 'active', :now)
;;
INSERT INTO fact_derived (fact_id, source_id) VALUES (:fact, :src)
;;
INSERT INTO fact_asserted (fact_id, agent_id) VALUES (:fact, :agent)
;;
INSERT INTO step_wrote (step_id, node_id) VALUES (:step, :fact)
;;
INSERT INTO decisions (id, co, text, agent_id, task_id, created_at) VALUES (:dec, :co, :text, :agent, :task, :now)
;;
INSERT INTO decision_based_on (decision_id, fact_id) VALUES (:dec, :fact)
;;
UPDATE tasks SET status = 'done', done_at = :now, version = version + 1, co = :co
 WHERE id = :task AND status = 'claimed' AND claimed_by = :agent AND version = :v
;;
INSERT INTO artifacts (id, co, summary, agent_id, task_id, created_at) VALUES (:art, :co, :summary, :agent, :task, :now)
;;
INSERT INTO handoffs (id, co, note, from_agent, to_agent, task_id, created_at) VALUES (:ho, :co, :note, :agent, :to, :task, :now)
;;
INSERT INTO handoff_carries (handoff_id, fact_id) VALUES (:ho, :fact)
