"""Stock bookkeeping. Deliberately clean: not every file in a pull request is a defect."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockLevel:
    sku: str
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return max(self.on_hand - self.reserved, 0)


def reserve(level: StockLevel, count: int) -> StockLevel:
    if count < 0:
        raise ValueError("cannot reserve a negative count")
    if count > level.available:
        raise ValueError(f"only {level.available} of {level.sku} are available")
    return StockLevel(sku=level.sku, on_hand=level.on_hand, reserved=level.reserved + count)


def release(level: StockLevel, count: int) -> StockLevel:
    if count < 0:
        raise ValueError("cannot release a negative count")
    return StockLevel(sku=level.sku, on_hand=level.on_hand, reserved=max(level.reserved - count, 0))
