"""Catalog listing."""

from __future__ import annotations

from .text import slugify


def catalog_entry(name: str) -> dict:
    return {"name": name, "slug": slugify(name)}
