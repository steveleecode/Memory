def normalize_filename(name: str) -> str:
    """Return a stable filename label for indexing."""
    return " ".join(name.strip().split())
