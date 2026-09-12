# Add path sanitization helper

Adds `sanitize_path` to `src/url_builder.py` to normalize URL path segments.

All unit tests in `tests/test_url_builder.py` pass, including new coverage for `sanitize_path` edge cases.
