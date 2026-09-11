Planted defect: pr.md asserts new unit tests cover sanitize_path edge cases, but the patch adds no tests to test_url_builder.py.
Why it is objective: The patch modifies only src/url_builder.py and makes zero changes to tests/test_url_builder.py.
What a reviewer must read: Compare the test coverage claim in pr.md against the actual diff contents.
