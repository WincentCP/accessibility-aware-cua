# Reset material boundary

`reset_material.json` is mounted only by the benchmark web server. It contains
synthetic records and clean initial states required to rebuild a case from
`task_id + condition_id + seed`.

It intentionally excludes success patches, predicates, invariants, near-miss
labels, target annotations, and oracle results. The browser receives only the
specific public fixture and UI state for its active case.

Stage 5 must load this material in the benchmark server process and deploy the
oracle evaluator separately. The agent/planner container may not mount this
directory, `benchmark/private/`, or `a11y_benchmark/oracles/`.
