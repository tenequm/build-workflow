"""URL query string formatting helpers."""
from typing import Dict
from urllib.parse import urlencode


def build_query_string(params: Dict[str, str]) -> str:
    """Format dictionary into URL encoded query string."""
    return urlencode(params)


def build_endpoint_url(base_url: str, endpoint: str) -> str:
    """Join base url and endpoint path."""
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
