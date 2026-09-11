"""Price calculation and rounding helpers."""


def apply_discount(price: float, discount_percent: float) -> float:
    """Apply discount percentage to price."""
    if not (0.0 <= discount_percent <= 100.0):
        raise ValueError("discount_percent must be between 0 and 100")
    return price * (1.0 - discount_percent / 100.0)
