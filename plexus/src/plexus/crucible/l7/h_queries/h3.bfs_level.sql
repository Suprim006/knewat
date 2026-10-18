-- H3 app-side BFS, one statement per level: the parents of the frontier with their status
SELECT fp.child AS p, fp.parent AS q, f.status AS status
FROM fact_parent fp JOIN facts f ON f.id = fp.parent
WHERE fp.child IN (SELECT value FROM json_each(:frontier))
