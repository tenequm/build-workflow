Planted defect: pr.md claims new unit tests cover calculate_range for multiple cases, but the patch adds zero tests for calculate_range.
Why it is objective: The patch only adds test_calculate_mean_negative to tests/test_metrics.py without any test for calculate_range.
What a reviewer must read: Compare the test coverage claim in pr.md against the actual test additions in tests/test_metrics.py.
