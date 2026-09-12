"""Tests for pagination."""
import pytest
from src.pagination import paginate_items


def test_paginate_items():
    data = [1, 2, 3, 4, 5]
    assert paginate_items(data, 1, 2) == [1, 2]
    assert paginate_items(data, 2, 2) == [3, 4]
    assert paginate_items(data, 3, 2) == [5]
