"""Catalog service for product lookup."""
from typing import Any, Optional
from src.item_cache import ItemCache


def get_product(cache: ItemCache, product_id: str) -> Optional[Any]:
    """Lookup product from cache. Returns item if found, None otherwise."""
    item = cache.get_item(product_id)
    if item is None:
        return None
    return item
