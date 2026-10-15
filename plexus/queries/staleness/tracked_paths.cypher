// name: staleness/tracked_paths
// purpose: The paths the graph already tracks: uris of Sources and paths of CodeAnchors. `plexus code baseline` hashes the ones inside a repository.
// params: limit:int
// returns: path (distinct; Source uris may also be URLs or note ids, the caller keeps only absolute file paths)
// mode: ro
MATCH (s:Source) RETURN DISTINCT s.uri AS path LIMIT $limit
UNION
MATCH (a:CodeAnchor) RETURN DISTINCT a.path AS path LIMIT $limit
