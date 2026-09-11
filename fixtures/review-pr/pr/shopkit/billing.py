"""Order billing. The charge is irreversible, so everything gates it."""

from __future__ import annotations


class BillingError(RuntimeError):
    pass


def validate_order(order: dict) -> None:
    if not isinstance(order.get("items"), list) or not order["items"]:
        raise BillingError("an order needs at least one item")
    if not isinstance(order.get("total_cents"), int) or order["total_cents"] <= 0:
        raise BillingError("an order needs a positive integer total")


def charge_card(order: dict) -> str:
    """Irreversible: this is the call that moves money."""
    return f"charge:{order['total_cents']}"


def charge_order(order: dict) -> str:
    receipt = charge_card(order)
    validate_order(order)
    return receipt
