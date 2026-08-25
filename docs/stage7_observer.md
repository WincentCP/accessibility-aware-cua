# Stage 7 Accessibility Observer

## Boundary

Stage 7 only observes and resolves browser semantics. It does not plan a task,
click, type, select, submit, verify an action, or access the private benchmark
oracle. Those execution responsibilities begin in Stage 8.

The primary source is Playwright `locator.aria_snapshot()` on the page body. A
documented Chromium-only fallback uses a Playwright `CDPSession` and
`Accessibility.getFullAXTree` when the primary API fails. The snapshot never
contains pixel coordinates, task-specific CSS selectors, test IDs, or private
oracle values.

## Data flow

1. Capture the browser ARIA YAML and a semantic focus signature.
2. Parse role, accessible name, value, state, level, and hierarchy.
3. Remove application chrome, extension namespace content, generic wrappers,
   and duplicate non-actionable text while preserving controls, landmarks,
   headings, errors, dialogs, status, notes, and necessary prose.
4. Assign refs such as `v12:ax0042`, hash the semantic content, and produce a
   compact planner-facing representation.
5. Match a target by exact role + accessible name + requested state.
6. Return `TARGET_NOT_FOUND`, `AMBIGUOUS_TARGET`, or `STALE_OBSERVATION`
   explicitly when a unique current target cannot be established.

Every capture creates a new observation version, including after navigation or
re-render. Therefore, all references and relevant items from the previous
version are invalid. This deliberately prevents a later executor from acting on
an element that has changed underneath it.

## Reproducible gate

```bash
python -m playwright install chromium
python -m pytest -q
python scripts/validate_stage7.py
```

The gate opens all 36 public T01–T12 × C0–C2 cases with fixed seeds. It checks
108 oracle-independent semantic targets, the strict semantic locator for every
actionable target, 35 cross-observation stale references, golden ARIA snapshots,
context budget, and forbidden-token leakage.

Golden baselines and measurement evidence may only be changed deliberately:

```bash
python scripts/validate_stage7.py --update-assets
```

Review the ARIA diffs before committing an update. Do not update golden files to
silence an unexplained regression.
