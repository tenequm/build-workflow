"""Text formatting utilities."""


def slugify(text: str) -> str:
    """Convert a string into a URL-friendly slug."""
    clean = "".join(c.lower() if c.isalnum() else "-" for c in text)
    parts = [p for p in clean.split("-") if p]
    return "-".join(parts)


def capitalize_words(text: str) -> str:
    """Capitalize each word in a string."""
    return " ".join(word.capitalize() for word in text.split())
