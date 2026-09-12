Planted defect: setup.cfg sets max-line-length to 120, directly contradicting CONTRIBUTING.md which mandates an 88-character limit.
Why it is objective: CONTRIBUTING.md establishes the repository authority policy of 88 characters, which setup.cfg violates.
What a reviewer must read: Cross-reference the flake8 max-line-length setting in setup.cfg with CONTRIBUTING.md.
