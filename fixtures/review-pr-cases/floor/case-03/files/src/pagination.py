"""Pagination helpers."""
from typing import Any, List, Sequence


def paginate_items(items: Sequence[Any], page: int, per_page: int) -> List[Any]:
    """Return a slice of items for the given 1-based page index."""
    if page < 1:
        raise ValueError("page must be >= 1")
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    start = (page - 1) * per_page
    end = start + per_page
    return list(items[start:end])
