"""Metric computation helpers."""
from typing import Sequence


def calculate_mean(values: Sequence[float]) -> float:
    """Compute arithmetic mean."""
    if not values:
        raise ValueError("values cannot be empty")
    return sum(values) / len(values)


def calculate_median(values: Sequence[float]) -> float:
    """Compute median value."""
    if not values:
        raise ValueError("values cannot be empty")
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
