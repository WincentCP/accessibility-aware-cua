---
name: Accessibility-Aware CUA
description: A calm, accessible control room for transparent benchmark tasks and shared-control agent assistance.
colors:
  primary-navy: "#173b63"
  primary-navy-hover: "#0f2d4d"
  primary-navy-soft: "#e9f0f7"
  amber-signal: "#c47a12"
  amber-soft: "#fff3d6"
  focus-amber: "#8a4f00"
  success-green: "#177245"
  success-soft: "#eaf7f0"
  danger-red: "#b42318"
  danger-soft: "#fff0ee"
  ink: "#101828"
  ink-secondary: "#475467"
  ink-tertiary: "#667085"
  surface: "#ffffff"
  extension-canvas: "#eef2f6"
  benchmark-canvas: "#f4f7fa"
  surface-strong: "#e8eef5"
  border: "#d4dde7"
  border-strong: "#aebdcd"
typography:
  display:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "clamp(2rem, 5vw, 4rem)"
    fontWeight: 720
    lineHeight: 1.06
    letterSpacing: "-0.045em"
  headline:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3.2rem)"
    fontWeight: 720
    lineHeight: 1.1
    letterSpacing: "-0.04em"
  title:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 720
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.58
  label:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 720
    lineHeight: 1.35
rounded:
  control: "0.75rem"
  card: "1rem"
  hero: "1.25rem"
  pill: "999px"
spacing:
  xs: "0.55rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.25rem"
components:
  button-primary:
    backgroundColor: "{colors.primary-navy}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0.72rem 1.05rem"
    height: "3rem"
  button-primary-hover:
    backgroundColor: "{colors.primary-navy-hover}"
  button-secondary:
    backgroundColor: "{colors.primary-navy-soft}"
    textColor: "{colors.primary-navy}"
    rounded: "{rounded.control}"
    padding: "0.7rem 0.9rem"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "1.25rem"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0.7rem 0.8rem"
    height: "3rem"
---

# Design System: Accessibility-Aware CUA

## Overview

**Creative North Star: "The Calm Control Room"**

The design makes agent assistance and benchmark state inspectable rather than theatrical. Deep navy establishes identity and the primary action path; cool white and slate surfaces separate work without visual noise; restrained amber calls attention to pending or contextual information. The result is clean, premium, minimal, and deliberately operational.

The system spans two coordinated surfaces. The Chromium side panel is participant-first: task input, live activity, verified evidence, then shared controls in that order. The benchmark mini-site is researcher-and-participant facing: global domain navigation, task and safety context, live status, work area, then reproducibility details. Both use the same typeface, palette roles, geometry, state language, and accessible interaction behavior.

**Key Characteristics:**

- One Plus Jakarta Sans voice across display, body, labels, controls, and keyboard hints.
- Navy identity blocks and primary actions over cool neutral canvases.
- Amber for attention and planned/pending context; green and red only for semantic outcomes.
- Soft, consistent geometry; borders and restrained shadows clarify hierarchy.
- Text and semantic state always carry meaning; motion and color only reinforce it.

**The Verified-Progress Rule.** Attempted or planned actions never receive completed styling or language; only post-action-verified evidence does.

**Finish review:** SHIP. Seed key: `brief-pinned-cua-20260826`. The desktop and mobile screenshots under `.impeccable/review/` are review evidence, not shipping assets or design-system inputs.

## Colors

The palette is primary navy plus cool neutrals, with a restrained amber signal and explicit green/red outcome states. Token values in the frontmatter are normative.

### Primary

- **Control Navy:** Identity panels, site header, task goal blocks, primary buttons, links, and selected controls.
- **Soft Navy:** Secondary actions and selected record backgrounds.

### Secondary

- **Signal Amber:** Phase/prototype signals and the activity scanner; its soft tint carries condition, next-action, warning, and task metadata surfaces.

### Tertiary

- **Verified Green:** Completed progress and successful status.
- **Intervention Red:** Errors, rejected or destructive actions, and assertive approval alerts.

### Neutral

- **Cool Canvas:** The side panel uses a slightly deeper cool slate canvas; the benchmark uses a lighter cool slate canvas.
- **White Surface:** Cards, workspaces, fields, and quiet buttons.
- **Slate Ink:** Primary, secondary, and tertiary text form a three-step hierarchy.
- **Cool Borders:** Default and strong strokes separate surfaces and controls.

**The Semantic Color Rule.** Amber means attention or pending context, green means verified success, and red means error or intervention. Never use these roles interchangeably or as decoration.

**The Contrast Preference Rule.** Under `prefers-contrast: more`, strengthen borders and secondary ink; do not rearrange the palette or remove textual status.

## Typography

**Display Font:** Plus Jakarta Sans (with `system-ui`, `sans-serif` fallback)
**Body Font:** Plus Jakarta Sans (with `system-ui`, `sans-serif` fallback)
**Label Font:** Plus Jakarta Sans (with `system-ui`, `sans-serif` fallback)

**Character:** A single variable sans family keeps Indonesian guidance, research context, and controls contemporary and calm. Tight tracking belongs to large headings; body and control text remain straightforward and highly legible.

### Hierarchy

- **Display:** Large benchmark hero only; fluid size, heavy-but-not-black weight, compact leading, and balanced wrapping.
- **Headline:** Page and task titles; fluid down to mobile and usually constrained to about 18 characters per line.
- **Title:** Section and card headings; compact, semibold-to-bold, and slightly tightened.
- **Body:** Default reading copy with generous leading; explanatory text is generally constrained to 59–65 characters.
- **Label:** Dense interface labels, metadata, chips, and key/value terms; never all-caps and never a substitute for a real heading.

**The One-Family Rule.** Plus Jakarta Sans is required throughout. Local variable font files serve the benchmark, and the extension imports the variable package. The detector's generic font warning is explicitly overridden by this product requirement.

## Layout

The benchmark uses a centered fluid shell capped at 74rem. Its home grid is two columns, domain task cards use three columns, and forms and record collections use two columns. Task pages use a named-area grid with a flexible workspace and a minimum 17rem context rail. At 58rem the task layout and task-card collection become one column; at 44rem all content grids become one column, the metadata moves before the title, buttons stretch full width, and navigation remains horizontally scrollable without forcing page-level overflow.

The extension uses a single-column shell capped at 31rem with a compact 0.875rem rhythm. Internal button and shared-control groups use two equal columns. Below 22rem, shell gaps and padding tighten, cards use the smaller corner, nonessential prototype metadata hides, controls stack, and the voice-guide actions remain a two-column row.

The recurring spatial rhythm is 0.55rem for compact gaps, 0.75–1rem for control and section spacing, and 1.25rem for primary surface padding. Preserve semantic DOM order when grid areas reflow. A minimum side-panel width of 18rem and `overflow-wrap: anywhere` protect zoom and long localized strings from horizontal scrolling.

**The Two-Surface Rule.** Keep participant control progressive in the side panel and benchmark context explicit in the mini-site; share tokens and behavior, not page composition.

## Elevation & Depth

The system uses a restrained hybrid of borders, tonal layering, and low-chroma navy shadows. Most containers remain flat with a one-pixel cool border. Shadows are reserved for the identity hero, the primary task/work surface, primary buttons, selected records, and hoverable domain panels; they indicate hierarchy or response, never decoration.

### Shadow Vocabulary

- **Card lift** (`0 12px 32px rgba(30, 58, 95, 0.08)` in the panel; `0 14px 36px rgba(30, 58, 95, 0.08)` on the site): Primary work and task surfaces.
- **Hero lift** (`0 18px 42px rgba(23, 59, 99, 0.16)`): Benchmark hero only.
- **Primary-action lift** (`0 7px 16px rgba(23, 59, 99, 0.14)`): Enabled primary buttons.

**The Flat-by-Default Rule.** A standard card earns separation through surface tone and border. Add shadow only for primary hierarchy, selection, or interactive lift.

## Shapes

Controls and inset notices use gently rounded 0.75rem corners; cards use 1rem; dominant navy identity surfaces may use 1.25rem. Chips and progress tracks are pills. Brand marks are compact rounded squares containing three circular amber points. One-pixel borders remain visible on light surfaces, while navy blocks use tonal contrast.

**The Consistent-Geometry Rule.** Reuse the control, card, hero, and pill radii. Do not introduce sharp cards, unrelated corner scales, or decorative edge treatments.

## Components

### Buttons

- **Shape:** Rounded controls with at least 2.75rem height in the side panel and 3rem on the benchmark; touch manipulation is enabled.
- **Primary:** White on navy, semibold, with restrained action lift. Hover darkens navy and lifts 1px; active moves down 1px and scales to 0.99.
- **Secondary / Quiet:** Navy-on-soft-navy for supportive actions; slate-on-white with a cool border for low-emphasis actions.
- **Danger:** Red text on soft red at rest, reversing to white on red at hover.
- **Disabled:** Muted slate on cool gray with no shadow or transform and a non-action cursor. Disabled state must remain a real `disabled` or `aria-disabled` state, not a visual simulation.

### Inputs / Fields

- **Style:** White fields, strong cool border, control radius, inherited Plus Jakarta Sans, and primary-navy caret.
- **Sizing:** Benchmark text inputs and selects are at least 3rem high; side-panel textarea is resizable with a 5.75rem minimum height.
- **Hover / Focus:** Hover strengthens the border. Focus uses the shared high-contrast treatment below.
- **Choice controls:** Native checkbox and radio controls remain visible at 1.3rem with navy `accent-color`; selected record cards gain soft navy tone, stronger border, and a subtle two-pixel ring.

### Cards / Containers

- **Style:** White surface, cool one-pixel border, card radius, and approximately 1–1.35rem internal padding.
- **Context states:** Amber-soft condition and warning cards, green-soft successful status, and red-soft error/approval cards always include visible text.
- **Interactive cards:** Domain cards may lift 2px and gain the card shadow on hover; reduced-motion mode removes the transform.

### Chips and Status

- Chips are compact pill labels with explicit text. Navy-on-soft-navy denotes context; brown-on-soft-amber denotes phase or metadata.
- Running, queued, starting, and loading states animate the amber indicator and scanner. Completed fills the track green; failed/error fills it red. Reduced motion replaces scanning with a static 58% amber bar.
- Status updates use `role="status"` and polite live regions; approval alerts use `role="alert"` and assertive announcement.

### Navigation

The benchmark header is a navy band with white brand text, pale navigation links, and a small research-environment chip. Links gain a translucent white background on hover. On mobile, navigation remains a single horizontally scrollable row while the rest of the page reflows vertically.

### Shared Controls

- **Idle:** All command buttons are disabled and helper text states that controls activate after a goal is confirmed or a task starts.
- **Ready / Active:** Loading an active benchmark task or rendering a task map enables the command set. During a nonterminal live run, controls remain enabled and helper text advertises pause, correction, takeover, and keyboard shortcuts.
- **Terminal / Missing:** Completed, failed, cancelled, or missing runs disable all shared controls; goal submission becomes available again.
- **Command integrity:** Keyboard shortcuts trigger only enabled matching buttons. Live approve/edit limitations remain announced in text and do not imply an action occurred.

### Accessibility Behavior

Links, buttons, fields, and disclosures receive a 3px focus-amber outline offset by 3px plus a 6px pale-amber halo. Skip links move into view on focus. Forced-colors mode returns key shapes and status indicators to system color adjustment and adds a system-text border to dot indicators. Reduced-motion mode collapses animations and transitions to effectively zero and removes hover/active transforms. Never remove semantic text, live regions, native form behavior, or logical source order when adapting visuals.

## Do's and Don'ts

### Do:

- **Do** preserve the two-surface information architecture and keep current task, state, verified evidence, and participant control easy to scan.
- **Do** use Plus Jakarta Sans everywhere and retain its variable weights, balanced headings, and generous body leading.
- **Do** pair every status color or animation with concise visible text and the appropriate semantic announcement.
- **Do** retain the exact focus, high-contrast, forced-colors, reduced-motion, zoom, and mobile reflow behavior when adding components.
- **Do** keep controls at least 2.75rem high and allow long Indonesian strings to wrap.
- **Do** preserve all existing IDs, event wiring, ARIA contracts, keyboard commands, benchmark conditions, and deterministic state boundaries.

### Don't:

- **Don't** present attempted, planned, or pending actions as completed or verified.
- **Don't** use amber, green, or red as interchangeable decoration; their semantic roles are fixed.
- **Don't** add decorative accent stripes. They were removed from the shipped visual system.
- **Don't** add dense dashboards, copied scheduler content, invented claims, imagery, glyph icons, or ornamental motion.
- **Don't** hide safety, approval, synthetic-data, research-condition, or shared-control limitations.
- **Don't** treat the review screenshots as product assets or provenance-bearing shipping rasters.
