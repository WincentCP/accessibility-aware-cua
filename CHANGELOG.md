# Changelog

## Unreleased

- Separated participant UI and Chromium integration into `frontend/`, and moved
  FastAPI plus the agent core into `backend/` without changing runtime behavior.
- Updated Python imports, npm workspace links, launchers, validators, CI, tests,
  and asset resolution for the new repository boundaries.
- Added a current system-architecture guide covering the participant, agent,
  benchmark, evaluation, recording, and report flows.

## Stage 12

- Added a versioned verified-only accessible task-map compiler with evidence provenance and stale-reference invalidation.
- Rebuilt the MV3 side panel and in-page landmark bridge for task progress, uncertainty, planning, and shared control.
- Added a bounded push-to-talk Whisper adapter with transcript review, cancellation, text fallback, and zero raw-audio persistence.
- Added semantic focus bridge, keyboard shortcuts, axe/reflow tests, microphone-denial tests, schema, and auditable automated gates.
- Kept the real Windows + NVDA walkthrough explicitly pending; automated tests do not substitute for it.

## Stage 11

- Added versioned deterministic risk taxonomy and policy gate before execution.
- Added explicit accessible approval contract, voice phrase validation, and one-shot consumption.
- Added atomic pause/takeover gate, verified semantic focus handoff, fresh-observation resume, and state delta.
- Added versioned conversation corrections and idempotent intervention outcome persistence.
- Added automated safety recall, race, double-execution, and four-task focus/resume gates.

## 0.6.0-stage6 — 2026-08-25

- Added closed, versioned Pydantic contracts and strict TypeScript mirrors for
  command, goal, accessibility observation, action, verification, task map,
  focus handoff, agent state, and run result.
- Added PostgreSQL migration v1 plus rollback, typed metric columns, structured
  audit reconstruction, and correlation IDs for reproducible experiments.
- Integrated the official LangGraph PostgreSQL checkpointer with strict msgpack
  and a state-only graph that preserves pending approval across process restart.
- Added recursive privacy redaction, zero-retention raw-audio policy, ERD, data
  dictionary, retention policy, quickstart, DoD, and CI integration gates.
- Kept planner, observer, executor, and verifier behavior out of this stage so
  data contracts are tested before browser autonomy is introduced.

## 0.5.0-stage4-5 — 2026-08-25

- Initialized the Git monorepo and separated API, extension, future agent,
  benchmark, evaluation, tests, docs, and evidence boundaries.
- Added exact Python/Node dependency locks, safe environment validation,
  PostgreSQL compose/health checks, pre-commit, and CI gates.
- Added a Manifest V3 TypeScript/Vite accessible side-panel shell with text and
  browser-supported voice input affordances.
- Implemented four FastAPI mini-sites covering T01–T12 and C0/C1/C2 without
  external services or real transaction controls.
- Added deterministic public reset/session APIs, server-only mutable state, and
  an evaluator-only hook compatible with the Stage 3 hidden oracle.
- Added 100-reset stale-state stress testing, 36/36 success-state verification,
  recursive HTTP oracle-leakage checks, deterministic C1/C2 validation, and
  safety-control audits.
- Added Playwright, axe-core, external-request, persistent Chromium, and
  keyboard tests. Windows headed extension/NVDA and second-machine clean-clone
  gates remain explicitly pending.

## 0.4.0-task-map — 2026-08-24

- Reframed the primary contribution around a Shared Accessible Task View and
  focus-synchronized shared control; verify-after-action remains the evidence
  foundation for displayed progress.
- Added U0/U1 interface-condition contracts with an identical core agent.
- Added a machine-readable task-map schema that forbids unverified completion
  claims and distinguishes planned actions from completed actions.
- Added a bounded 6–8 participant study plan: four tasks, 45–60 minutes, no
  blindfolded sighted substitutes, and synthetic data only.
- Added four private handoff oracles and public/private leakage checks.
- Preserved the original 12 tasks, 36 cases, 324 final runs, and 24 pilot runs.

## 0.3.0-draft — 2026-08-23

- Added 12 final task specifications across four domains.
- Added C0/C1/C2 condition contracts and fairness constraints.
- Added 36-case matrix, deterministic reset engine, replay keys, and seeded
  order/label/price/schedule/delay variants.
- Added hidden deterministic predicate oracle with safety invariants.
- Added three labelled near-miss states per final task.
- Added paired 324-run final manifest with balanced Latin order.
- Added 24-run pilot split with disjoint task IDs and seeds.
- Added public/private/reset deployment boundaries and leakage validation.
- Added 10-test standard-library validation suite and auditable report.
