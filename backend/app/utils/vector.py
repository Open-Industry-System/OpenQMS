"""Shared utilities for pgvector dimension handling."""


def parse_vector_dimensions(raw: str | None, default: int = 1536) -> int:
    """Parse and validate vector dimensions from a string argument.

    Args:
        raw: Raw string value (e.g. from Alembic -x dimensions=768).
        default: Default value when raw is None or empty.

    Returns:
        Validated integer dimensions.

    Raises:
        ValueError: If raw is provided but not a valid integer, or out of range (1-2000).
    """
    if raw is None or raw.strip() == "":
        return default
    try:
        dim = int(raw)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid vector dimensions: '{raw}'. Must be an integer.")
    if not (1 <= dim <= 2000):
        raise ValueError(f"Invalid vector dimensions: {dim}. Must be 1-2000.")
    return dim
