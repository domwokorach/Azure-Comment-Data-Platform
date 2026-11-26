# ADR-0002: One metadata-driven ingestion pipeline instead of one pipeline per source

**Status:** Accepted · **Date:** 2026-11-26

## Context
We expect 30+ sources over the next two years. Building a new pipeline for each one means copy-paste code, different behaviours, and a backlog that grows faster than the team.

## Decision
A single generic ingestion pipeline reads a **source registry** (control table) and loops over each enabled source. Adding a source means adding a row (format, path, key, owner, classification, load type), not writing code. Only silver transformations are source-specific.

## Consequences
- New sources are onboarded in hours, not weeks.
- The registry doubles as the inventory of data assets, so owners and classifications are always known.
- Unusual sources (APIs with paging, CDC) may need an extra pattern, added as a new `format` handler, not a one-off pipeline.
- The registry becomes critical: it is version-controlled and changes go through pull-request review.
