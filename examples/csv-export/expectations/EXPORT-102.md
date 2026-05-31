# EXPORT-102 — Exports can't be used to hammer or drain the system

**Type:** User Story
**Priority:** Medium

## The want
> As an operator, I want the export feature to not become a way to overload the
> database or pull the entire customer table in a loop, so that one user (or a
> leaked token) can't take the service down or exfiltrate everything.

## What "done" looks like
- The export endpoint is **rate-limited** — a single user can only trigger a
  handful of exports per minute.
- A single export is **bounded** (paginated or capped); it must not stream the
  whole table unbounded in one request.
