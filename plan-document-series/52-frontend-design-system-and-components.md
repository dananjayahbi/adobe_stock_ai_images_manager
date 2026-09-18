# 52 — Frontend Design System and Components

## Purpose
Establish a coherent visual and interaction system for the Next.js application so status, risk, evidence, and actions remain recognizable across dashboard, queue, inspection, and packaging surfaces.

## Scope
This document covers design tokens, layout primitives, status indicators, cards, tables, dialogs, forms, progress displays, notifications, image inspection controls, responsive rules, and component ownership. It does not define backend behavior or choose a third-party component library by itself.

## Decisions / requirements
The visual language should prioritize clarity over decoration. A neutral canvas, strong typography hierarchy, generous grouping, and restrained accent colors should support long review sessions. Tokens must define spacing, type scale, border radius, shadows, focus rings, semantic colors, and motion durations. Semantic colors cannot be the only status channel: every status includes text, iconography, and accessible labels. Red is reserved for blocking or destructive conditions; amber indicates review attention; blue or neutral indicates in progress; green indicates verified success only.

Core primitives include AppShell, navigation, page header, filter bar, status badge, evidence section, image card, data table, empty state, error state, loading state, confirmation dialog, toast, form field, pagination control, and progress summary. Components must have predictable keyboard behavior and a documented loading, disabled, error, and no-data state. The image viewer must keep controls discoverable at both fit and 100% zoom and must not trap scrolling unexpectedly.

Forms for metadata and review notes show constraints near the field, preserve user input after validation errors, and distinguish generated text from human edits. Dialogs are reserved for decisions requiring confirmation; routine details belong in the page. Notifications must identify the affected batch or image and provide a route back to it. Long filenames and generated titles must wrap or truncate with an accessible full value.

The design system should be implemented as reusable frontend components with API types sourced from the wire contract. Visual snapshots or equivalent review artifacts should cover the most important states, including provider unavailable, stale revision, empty queue, partial upload, and package failure.

## Affected blueprint areas
This refines the Next.js layout, Dropzone, ImageGrid, InspectionModal, StatsBar, API client, and all frontend surfaces implied by documents 50, 51, 53, and 54.

## Dependencies
Tokens depend on accessibility contrast requirements, supported viewport sizes, API status semantics, and the selected styling/component technology. Image controls depend on thumbnail and source-preview routes with safe access control.

## Acceptance criteria
- Shared components cover all MVP states without ad hoc status styling.
- Semantic meaning remains understandable without color.
- Focus, error, disabled, and loading states are designed and tested.
- Components behave consistently at the minimum supported window size.
- Copy and icons distinguish advisory findings from hard blockers.
- New screens consume tokens and shared primitives rather than duplicating patterns.

## Risks / open questions
A heavy component library may add bundle cost or constrain the inspection experience. The team must decide whether to build primitives with native elements, adopt a maintained library, and how visual regression will run on Windows. User testing is needed to calibrate density for operators reviewing hundreds of images.