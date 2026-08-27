# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Primary: blind and low-vision research participants who use a keyboard and screen reader to complete controlled web tasks with an AI agent.
- Secondary: the researcher who launches deterministic benchmark sessions, monitors run state, and evaluates recorded outcomes.

## Product Purpose

Accessibility-Aware CUA helps a participant state or receive a web goal, understand what an agent is doing, and retain control while the agent completes the task. The research environment exists to evaluate whether accessibility-tree observation, verified actions, bounded recovery, and shared control produce reliable, understandable assistance.

## Positioning

The product exposes an accessible, verified task map rather than presenting computer-use automation as an opaque sequence of clicks. Only post-action-verified progress is presented as complete, and the participant can approve, pause, reject, take over, resume, or cancel.

## Operating Context

- A local FastAPI service hosts four synthetic benchmark domains and deterministic task sessions.
- A Manifest V3 Chromium side panel presents the participant controls, Indonesian guidance, agent activity, task-map evidence, and shared-control actions.
- Twelve synthetic tasks cover travel, marketplace, appointment, and account-settings scenarios across C0, C1, and C2 conditions.
- All task data is dummy data. The environment stops before real booking, payment, checkout, account deletion, or other external transactions.

## Capabilities and Constraints

- Preserve the existing benchmark contracts, element IDs, event wiring, keyboard commands, API boundaries, and hidden-oracle separation.
- Input is available through text and push-to-talk; speech transcripts must be reviewed before use.
- Indonesian voice guidance supplements, but never replaces, semantic text and ARIA live regions.
- The current system is a research prototype. Automated gates do not substitute for the pending Windows NVDA evaluation.
- The attached scheduler image is a visual reference only; its content, feature set, and information architecture must not be copied.

## Brand Commitments

- Product name: Accessibility-Aware CUA.
- Voice: concise, calm, respectful, transparent, and native Indonesian for participant-facing guidance.
- Visual direction confirmed by the user: clean, modern, premium, minimal, generous spacing, consistent geometry, and Plus Jakarta Sans throughout.

## Evidence on Hand

- The repository contains the benchmark catalog, deterministic reset and oracle logic, accessibility-tree observer, semantic executor, verification and recovery flow, side-panel UI, automated gates, and research documentation.
- Existing claims and limitations are documented in `README.md`; future UI work must not invent participants, success rates, testimonials, or external deployment claims.

## Product Principles

1. Make the current task, agent state, and participant control obvious at every moment.
2. Treat verified evidence as progress; never imply success from an attempted action alone.
3. Reduce participant effort without hiding safety boundaries or research conditions.
4. Keep participant-facing language plain while preserving auditable technical detail for the researcher.
5. Prefer deterministic, recoverable flows over decorative complexity.

## Accessibility & Inclusion

- Keyboard operation and screen-reader comprehension are primary product requirements, not fallback modes.
- Maintain logical DOM order, semantic landmarks and headings, visible high-contrast focus, textual status/error feedback, target sizes suitable for touch, reduced-motion behavior, forced-colors support, and zoom/reflow without horizontal scrolling.
- Avoid overlapping spoken guidance; participants must be able to repeat or disable AI voice without losing textual status.
