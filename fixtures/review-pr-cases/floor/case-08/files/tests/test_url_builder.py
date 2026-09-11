"""Tests for URL builder."""
from src.url_builder import build_endpoint_url, build_query_string


def test_build_query_string():
    assert build_query_string({"q": "test", "page": "1"}) == "q=test&page=1"


def test_build_endpoint_url():
    assert build_endpoint_url("https://api.example.com/", "/users") == "https://api.example.com/users"
