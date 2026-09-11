"""Data processing pipeline."""
from typing import List


def process_records(records: List[str]) -> List[str]:
    """Strip whitespace and filter empty records."""
    return [record.strip() for record in records if record.strip()]
