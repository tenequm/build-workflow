Planted defect: calculate_total_pages uses (total_items + per_page) // per_page instead of (total_items + per_page - 1) // per_page.
Why it is objective: Exact multiples of per_page (such as 10 items with 10 per page) produce 2 pages instead of 1.
What a reviewer must read: Check the arithmetic ceiling division formula in calculate_total_pages in src/pagination.py.
