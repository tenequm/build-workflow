"""Tests for account validator."""
from src.account_validator import validate_username


def test_validate_username():
    assert validate_username("alice_01") is True
    assert validate_username("ab") is False
    assert validate_username("invalid space") is False
