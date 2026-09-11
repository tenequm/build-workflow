"""Unit tests for metric tracker."""
import pytest
from src.metric_tracker import calculate_mean, calculate_median


def test_calculate_mean():
    assert calculate_mean([1.0, 2.0, 3.0]) == 2.0
    assert calculate_mean([4.0]) == 4.0


def test_calculate_mean_empty():
    with pytest.raises(ValueError):
        calculate_mean([])


def test_calculate_median_odd():
    assert calculate_median([3.0, 1.0, 2.0]) == 2.0


def test_calculate_median_even():
    assert calculate_median([1.0, 2.0, 3.0, 4.0]) == 2.5
