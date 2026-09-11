# Project Governance

## Overview
This document defines roles, responsibilities, and review requirements
for the metrics-collector repository.

## Roles and Responsibilities

### Core Maintainers
Core Maintainers are responsible for the core ingestion pipeline,
architecture decisions, and overall repository stability.

Requirements:
- Maintain active participation in pipeline architecture discussions.
- Review pull requests modifying core collector pipelines.

### Plugin Reviewers
Plugin Reviewers oversee external metrics integrations and exporter
plugins.

Requirements:
- Review third-party plugin integrations for protocol adherence.
- Ensure integration tests pass for new exporters.

## Review Quorums

### Core Pipeline Changes
Any PR touching core collector pipelines requires at least 2 approvals
from Core Maintainers before merging into the main branch.

### Plugin Submissions
Plugin updates require consensus among active Plugin Reviewers (no fixed
quorum count, but must include at least one domain reviewer).

## Escalation
Disagreements regarding architecture changes are resolved by a majority
vote of Core Maintainers during monthly sync meetings.
