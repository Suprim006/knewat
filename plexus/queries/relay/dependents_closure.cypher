// name: relay/dependents_closure
// purpose: ONE read statement (one snapshot, D-014): every task that depends on $id directly or transitively, up to $depth DEPENDS_ON hops, with its hop distance.
// params: id:str, depth:int, limit:int
// returns: id, status, lv (one row per distinct dependent at its nearest hop distance lv; nearest first, then id; done tasks are walked through but not returned; at most $limit rows). Zero rows = no such task, or nothing depends on it.
// mode: ro
// Level-wise expansion: 50 fixed one-hop steps, each skipped once $depth is reached or the frontier is empty; a level is the DISTINCT dependents of the previous one (`DEPENDS_ON*1..N` is exponential on a layered DAG). The frontier is not pruned by tasks already seen, so a task reached at several distances is expanded at each (bounded by $depth x edges); min(lv) keeps the nearest. Carried lists are aggregated with head(collect(...)), not used as grouping keys.
MATCH (root:Task {id: $id})
OPTIONAL MATCH (root)<-[:DEPENDS_ON]-(x1:Task)
WITH collect(DISTINCT x1) AS fr
WITH fr, [y IN fr | {t: y, lv: 1}] AS el
UNWIND CASE WHEN size(fr) = 0 OR $depth < 2 THEN [null] ELSE fr END AS p2
OPTIONAL MATCH (p2)<-[:DEPENDS_ON]-(x2:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x2) AS fr
WITH el + [y IN fr | {t: y, lv: 2}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 3 THEN [null] ELSE fr END AS p3
OPTIONAL MATCH (p3)<-[:DEPENDS_ON]-(x3:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x3) AS fr
WITH el + [y IN fr | {t: y, lv: 3}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 4 THEN [null] ELSE fr END AS p4
OPTIONAL MATCH (p4)<-[:DEPENDS_ON]-(x4:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x4) AS fr
WITH el + [y IN fr | {t: y, lv: 4}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 5 THEN [null] ELSE fr END AS p5
OPTIONAL MATCH (p5)<-[:DEPENDS_ON]-(x5:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x5) AS fr
WITH el + [y IN fr | {t: y, lv: 5}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 6 THEN [null] ELSE fr END AS p6
OPTIONAL MATCH (p6)<-[:DEPENDS_ON]-(x6:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x6) AS fr
WITH el + [y IN fr | {t: y, lv: 6}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 7 THEN [null] ELSE fr END AS p7
OPTIONAL MATCH (p7)<-[:DEPENDS_ON]-(x7:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x7) AS fr
WITH el + [y IN fr | {t: y, lv: 7}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 8 THEN [null] ELSE fr END AS p8
OPTIONAL MATCH (p8)<-[:DEPENDS_ON]-(x8:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x8) AS fr
WITH el + [y IN fr | {t: y, lv: 8}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 9 THEN [null] ELSE fr END AS p9
OPTIONAL MATCH (p9)<-[:DEPENDS_ON]-(x9:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x9) AS fr
WITH el + [y IN fr | {t: y, lv: 9}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 10 THEN [null] ELSE fr END AS p10
OPTIONAL MATCH (p10)<-[:DEPENDS_ON]-(x10:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x10) AS fr
WITH el + [y IN fr | {t: y, lv: 10}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 11 THEN [null] ELSE fr END AS p11
OPTIONAL MATCH (p11)<-[:DEPENDS_ON]-(x11:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x11) AS fr
WITH el + [y IN fr | {t: y, lv: 11}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 12 THEN [null] ELSE fr END AS p12
OPTIONAL MATCH (p12)<-[:DEPENDS_ON]-(x12:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x12) AS fr
WITH el + [y IN fr | {t: y, lv: 12}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 13 THEN [null] ELSE fr END AS p13
OPTIONAL MATCH (p13)<-[:DEPENDS_ON]-(x13:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x13) AS fr
WITH el + [y IN fr | {t: y, lv: 13}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 14 THEN [null] ELSE fr END AS p14
OPTIONAL MATCH (p14)<-[:DEPENDS_ON]-(x14:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x14) AS fr
WITH el + [y IN fr | {t: y, lv: 14}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 15 THEN [null] ELSE fr END AS p15
OPTIONAL MATCH (p15)<-[:DEPENDS_ON]-(x15:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x15) AS fr
WITH el + [y IN fr | {t: y, lv: 15}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 16 THEN [null] ELSE fr END AS p16
OPTIONAL MATCH (p16)<-[:DEPENDS_ON]-(x16:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x16) AS fr
WITH el + [y IN fr | {t: y, lv: 16}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 17 THEN [null] ELSE fr END AS p17
OPTIONAL MATCH (p17)<-[:DEPENDS_ON]-(x17:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x17) AS fr
WITH el + [y IN fr | {t: y, lv: 17}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 18 THEN [null] ELSE fr END AS p18
OPTIONAL MATCH (p18)<-[:DEPENDS_ON]-(x18:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x18) AS fr
WITH el + [y IN fr | {t: y, lv: 18}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 19 THEN [null] ELSE fr END AS p19
OPTIONAL MATCH (p19)<-[:DEPENDS_ON]-(x19:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x19) AS fr
WITH el + [y IN fr | {t: y, lv: 19}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 20 THEN [null] ELSE fr END AS p20
OPTIONAL MATCH (p20)<-[:DEPENDS_ON]-(x20:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x20) AS fr
WITH el + [y IN fr | {t: y, lv: 20}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 21 THEN [null] ELSE fr END AS p21
OPTIONAL MATCH (p21)<-[:DEPENDS_ON]-(x21:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x21) AS fr
WITH el + [y IN fr | {t: y, lv: 21}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 22 THEN [null] ELSE fr END AS p22
OPTIONAL MATCH (p22)<-[:DEPENDS_ON]-(x22:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x22) AS fr
WITH el + [y IN fr | {t: y, lv: 22}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 23 THEN [null] ELSE fr END AS p23
OPTIONAL MATCH (p23)<-[:DEPENDS_ON]-(x23:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x23) AS fr
WITH el + [y IN fr | {t: y, lv: 23}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 24 THEN [null] ELSE fr END AS p24
OPTIONAL MATCH (p24)<-[:DEPENDS_ON]-(x24:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x24) AS fr
WITH el + [y IN fr | {t: y, lv: 24}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 25 THEN [null] ELSE fr END AS p25
OPTIONAL MATCH (p25)<-[:DEPENDS_ON]-(x25:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x25) AS fr
WITH el + [y IN fr | {t: y, lv: 25}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 26 THEN [null] ELSE fr END AS p26
OPTIONAL MATCH (p26)<-[:DEPENDS_ON]-(x26:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x26) AS fr
WITH el + [y IN fr | {t: y, lv: 26}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 27 THEN [null] ELSE fr END AS p27
OPTIONAL MATCH (p27)<-[:DEPENDS_ON]-(x27:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x27) AS fr
WITH el + [y IN fr | {t: y, lv: 27}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 28 THEN [null] ELSE fr END AS p28
OPTIONAL MATCH (p28)<-[:DEPENDS_ON]-(x28:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x28) AS fr
WITH el + [y IN fr | {t: y, lv: 28}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 29 THEN [null] ELSE fr END AS p29
OPTIONAL MATCH (p29)<-[:DEPENDS_ON]-(x29:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x29) AS fr
WITH el + [y IN fr | {t: y, lv: 29}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 30 THEN [null] ELSE fr END AS p30
OPTIONAL MATCH (p30)<-[:DEPENDS_ON]-(x30:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x30) AS fr
WITH el + [y IN fr | {t: y, lv: 30}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 31 THEN [null] ELSE fr END AS p31
OPTIONAL MATCH (p31)<-[:DEPENDS_ON]-(x31:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x31) AS fr
WITH el + [y IN fr | {t: y, lv: 31}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 32 THEN [null] ELSE fr END AS p32
OPTIONAL MATCH (p32)<-[:DEPENDS_ON]-(x32:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x32) AS fr
WITH el + [y IN fr | {t: y, lv: 32}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 33 THEN [null] ELSE fr END AS p33
OPTIONAL MATCH (p33)<-[:DEPENDS_ON]-(x33:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x33) AS fr
WITH el + [y IN fr | {t: y, lv: 33}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 34 THEN [null] ELSE fr END AS p34
OPTIONAL MATCH (p34)<-[:DEPENDS_ON]-(x34:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x34) AS fr
WITH el + [y IN fr | {t: y, lv: 34}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 35 THEN [null] ELSE fr END AS p35
OPTIONAL MATCH (p35)<-[:DEPENDS_ON]-(x35:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x35) AS fr
WITH el + [y IN fr | {t: y, lv: 35}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 36 THEN [null] ELSE fr END AS p36
OPTIONAL MATCH (p36)<-[:DEPENDS_ON]-(x36:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x36) AS fr
WITH el + [y IN fr | {t: y, lv: 36}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 37 THEN [null] ELSE fr END AS p37
OPTIONAL MATCH (p37)<-[:DEPENDS_ON]-(x37:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x37) AS fr
WITH el + [y IN fr | {t: y, lv: 37}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 38 THEN [null] ELSE fr END AS p38
OPTIONAL MATCH (p38)<-[:DEPENDS_ON]-(x38:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x38) AS fr
WITH el + [y IN fr | {t: y, lv: 38}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 39 THEN [null] ELSE fr END AS p39
OPTIONAL MATCH (p39)<-[:DEPENDS_ON]-(x39:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x39) AS fr
WITH el + [y IN fr | {t: y, lv: 39}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 40 THEN [null] ELSE fr END AS p40
OPTIONAL MATCH (p40)<-[:DEPENDS_ON]-(x40:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x40) AS fr
WITH el + [y IN fr | {t: y, lv: 40}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 41 THEN [null] ELSE fr END AS p41
OPTIONAL MATCH (p41)<-[:DEPENDS_ON]-(x41:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x41) AS fr
WITH el + [y IN fr | {t: y, lv: 41}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 42 THEN [null] ELSE fr END AS p42
OPTIONAL MATCH (p42)<-[:DEPENDS_ON]-(x42:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x42) AS fr
WITH el + [y IN fr | {t: y, lv: 42}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 43 THEN [null] ELSE fr END AS p43
OPTIONAL MATCH (p43)<-[:DEPENDS_ON]-(x43:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x43) AS fr
WITH el + [y IN fr | {t: y, lv: 43}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 44 THEN [null] ELSE fr END AS p44
OPTIONAL MATCH (p44)<-[:DEPENDS_ON]-(x44:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x44) AS fr
WITH el + [y IN fr | {t: y, lv: 44}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 45 THEN [null] ELSE fr END AS p45
OPTIONAL MATCH (p45)<-[:DEPENDS_ON]-(x45:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x45) AS fr
WITH el + [y IN fr | {t: y, lv: 45}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 46 THEN [null] ELSE fr END AS p46
OPTIONAL MATCH (p46)<-[:DEPENDS_ON]-(x46:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x46) AS fr
WITH el + [y IN fr | {t: y, lv: 46}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 47 THEN [null] ELSE fr END AS p47
OPTIONAL MATCH (p47)<-[:DEPENDS_ON]-(x47:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x47) AS fr
WITH el + [y IN fr | {t: y, lv: 47}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 48 THEN [null] ELSE fr END AS p48
OPTIONAL MATCH (p48)<-[:DEPENDS_ON]-(x48:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x48) AS fr
WITH el + [y IN fr | {t: y, lv: 48}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 49 THEN [null] ELSE fr END AS p49
OPTIONAL MATCH (p49)<-[:DEPENDS_ON]-(x49:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x49) AS fr
WITH el + [y IN fr | {t: y, lv: 49}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 50 THEN [null] ELSE fr END AS p50
OPTIONAL MATCH (p50)<-[:DEPENDS_ON]-(x50:Task)
WITH head(collect(el)) AS el, collect(DISTINCT x50) AS fr
WITH el + [y IN fr | {t: y, lv: 50}] AS el, fr
UNWIND el AS e
WITH e.t AS t, min(e.lv) AS lv
WITH t, lv WHERE coalesce(t.status, '') <> 'done'
WITH t, lv ORDER BY lv ASC, t.id ASC LIMIT $limit
RETURN t.id AS id, t.status AS status, lv
