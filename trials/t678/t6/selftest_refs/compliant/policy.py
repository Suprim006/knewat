def visible(tasks):
    """X1: archived tasks never leave."""
    return [t for t in tasks if not t.get("archived")]
