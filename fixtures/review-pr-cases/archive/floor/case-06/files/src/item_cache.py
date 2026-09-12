"""Item cache implementation."""
from typing import Any, Dict, Optional


class ItemCache:
    def __init__(self) -> None:
        self._entries: Dict[str, Any] = {}

    def set_item(self, key: str, value: Any) -> None:
        self._entries[key] = value

    def get_item(self, key: str) -> Optional[Any]:
        """Retrieve cached item, returning None if key is absent."""
        return self._entries.get(key, None)
