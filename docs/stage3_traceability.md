# Stage 3 Traceability to the Locked Research Protocol

## Research boundary preserved

- Browser target remains desktop web in Playwright-bundled headed Chromium.
- Technical comparison remains B0 visual, B1 semantic, and P proposed.
- Participant-facing comparison adds U0 basic accessible interface versus U1
  Shared Accessible Task View while keeping the core agent identical.
- Conditions remain C0 normal, C1 accessibility/layout, and C2 dynamic/safety.
- The runtime verifier and the final hidden oracle remain separate components.
- A minimal Manifest V3 extension is now core because it renders the accessible
  task view and performs focus handoff. No RAG, multi-agent, mobile/native app,
  live-site dependency, real transaction, or premature user-impact claim was introduced.

## Requirement-to-evidence map

| Locked requirement | Stage 3 artifact | Verification |
|---|---|---|
| 4 workflow domains × 3 tasks | `benchmark/public/task_specs.json` | Catalog count/domain unit test |
| 12 tasks × 3 conditions | `benchmark/public/case_matrix.json` | 36-case validator |
| Public goal separated from scoring truth | `benchmark/public/` vs `benchmark/private/` | Recursive leakage checks |
| Idempotent reset | `a11y_benchmark/reset/engine.py` | Double-reset equality for 36 cases |
| Seeded replay | Private final/pilot manifests | Replay key and stable snapshot hash |
| Hidden deterministic oracle | `a11y_benchmark/oracles/engine.py` | Correct-state and near-miss tests |
| ≥3 near misses per task | `benchmark/private/task_oracles.json` | 108/108 rejected evaluations |
| Fair B0/B1/P pairing | `benchmark/private/manifests/final_runs.json` | Same seed/variant per pair |
| Balanced run order | Final manifest | Latin order test per repetition |
| 324 final runs | Final manifest | Exact row-count test |
| 24 separate pilot runs | Pilot manifest | Task-ID and seed disjointness test |
| Keyboard-only feasibility declared | Public task keyboard paths | Static contract check; rendered test pending Stage 5 |
| Synthetic, no live dependency | Task data policy and local routes | Static URL/data audit |
| U0/U1 fair interface comparison | `benchmark/public/interface_conditions.json` | Treatment isolation tests |
| Verified-only task-map claims | Task-map snapshot schema | Const/evidence-ref contract test |
| Four bounded participant tasks | Public study plan | Count, session, and burden checks |
| Focus targets hidden from agent | Private collaboration oracle | Recursive leakage checks |

## Evidence interpretation

`PASS_DESIGN` proves that the benchmark contract, split, reset simulation,
oracle, and experiment manifest are internally consistent and reproducible. It
does not prove browser accessibility, NVDA usability, or agent performance. Those
claims require the later rendered mini-sites and experimental runs. It also does
not prove task-map fidelity, NVDA focus handoff, or user benefit; those gates
remain explicitly pending.
