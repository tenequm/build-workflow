"""Text helpers. Slug and title handling lives here and nowhere else."""

from __future__ import annotations

import re

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def slugify(value: str, limit: int = 48) -> str:
    """Lowercase, collapse every non-alphanumeric run to a single hyphen, trim, cut."""
    collapsed = _NON_ALPHANUMERIC.sub("-", value.strip().lower())
    return collapsed.strip("-")[:limit].strip("-")
