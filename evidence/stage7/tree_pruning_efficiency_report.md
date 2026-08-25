# Stage 7 Tree-Pruning Efficiency

Generated from the pinned Playwright Chromium observer gate over all 36 public cases.

- Cases: 36
- Mean raw ARIA size: 2207.9 characters
- Mean compact size: 1986.7 characters
- Mean reduction: 10.09%
- Maximum compact size: 2482 characters
- Context budget: 12000 characters
- Cases within budget: 36/36
- Mean capture latency: 40.1 ms
- P95 capture latency: 129 ms
- Coordinates, task-specific CSS selectors, test IDs, and private oracle fields in planner snapshot: none

The compact snapshot preserves landmarks, headings, form controls, status/error semantics,
dialog/note content, values, states, focus, and observation-scoped references. App chrome,
extension namespace content, generic wrappers, and duplicate non-actionable text are pruned.
