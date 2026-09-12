"""Account data validation."""
import re


def validate_username(username: str) -> bool:
    """Check if username matches allowed alphanumeric pattern."""
    if not (3 <= len(username) <= 20):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_]+$", username))
