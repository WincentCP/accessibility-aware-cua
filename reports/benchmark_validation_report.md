# Benchmark Validation Report — Tahap 3

- Version: `0.4.0-task-map`
- Validation date: 2026-08-24
- Overall design status: **PASS_DESIGN**
- Cases passing spec/reset/oracle checks: **36/36**
- Near-miss evaluations rejected: **108/108**
- Public leakage findings: **0**
- Interface conditions: **2 (U0/U1)**
- Participant-study task subset: **4**

## Interpretation

PASS means the specification, deterministic reset, hidden-oracle behavior, split, and run pairing are valid. It does not mean the rendered mini-site has passed keyboard or NVDA testing. Those checks are deliberately marked pending until Tahap 5/12 so accessibility claims are not fabricated.

## Global gates

| Gate | Result |
|---|---|
| twelve final tasks | PASS |
| four domains three tasks each | PASS |
| three conditions | PASS |
| thirty six cases | PASS |
| all case checks pass | PASS |
| public oracle leakage zero | PASS |
| reset material scoring leakage zero | PASS |
| unit test suite pass | PASS |
| final runs 324 | PASS |
| final pair groups 108 | PASS |
| paired seed variant and latin order | PASS |
| pilot runs 24 | PASS |
| pilot task ids disjoint | PASS |
| pilot seeds disjoint | PASS |
| two interface conditions u0 u1 | PASS |
| interface core agent identical | PASS |
| treatment is task map and focus handoff | PASS |
| four user study tasks | PASS |
| handoff oracles complete | PASS |
| task map completed claims verified only | PASS |
| task map next action not mislabeled complete | PASS |
| participant burden bounded | PASS |
| no blindfolded substitution | PASS |

## 36 task-condition cases

| Case | Domain | Reset | Oracle correct | 3 near misses | Boundary | Status | Browser/NVDA |
|---|---|---|---|---|---|---|---|
| T01-C0 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T01-C1 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T01-C2 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T02-C0 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T02-C1 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T02-C2 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T03-C0 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T03-C1 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T03-C2 | travel | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T04-C0 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T04-C1 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T04-C2 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T05-C0 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T05-C1 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T05-C2 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T06-C0 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T06-C1 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T06-C2 | marketplace | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T07-C0 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T07-C1 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T07-C2 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T08-C0 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T08-C1 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T08-C2 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T09-C0 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T09-C1 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T09-C2 | appointment | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T10-C0 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T10-C1 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T10-C2 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T11-C0 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T11-C1 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T11-C2 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T12-C0 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T12-C1 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |
| T12-C2 | account | PASS | PASS | PASS | PASS | PASS | Pending Tahap 5/12 |

## Remaining gates

1. Supervisor approval of B0/B1/P and C0/C1/C2 protocol.
2. Stage 4 environment/repository freeze.
3. Stage 5 rendered mini-sites, double-reset integration, keyboard walkthrough, and automated accessibility scan.
4. Stage 12 runtime task-map fidelity, keyboard path, and NVDA focus-handoff validation.
5. Ethics approval and the bounded 6–8 participant study comparing U0 versus U1.
