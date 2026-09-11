Planted defect: README.md claims truncate() accepts a suffix parameter and appends it, but the implementation only takes text and max_len.
Why it is objective: The signature and implementation in src/text_formatter.py take only two parameters and perform simple slicing with no suffix support.
What a reviewer must read: Compare the doc entry in README.md against the truncate function signature and body in src/text_formatter.py.
