# 53 — Accessibility and Inclusive Operation

## Purpose
Make the studio usable by operators with varied vision, motor, hearing, and cognitive needs while treating accessibility as a reliability property for a local production tool.

## Scope
The plan covers semantic structure, keyboard operation, focus management, screen-reader announcements, contrast, zoom, motion, forms, errors, image alternatives, timing, and accessibility verification. It applies to the Next.js interface and does not replace the backend’s file and security controls.

## Decisions / requirements
Every page has one clear heading, logical landmarks, and a predictable reading order. Interactive elements use native controls where possible. All actions are keyboard reachable, with visible focus that is not obscured by dialogs, sticky headers, or image viewers. Modal dialogs trap focus only while open, return focus to the launching control on close, and provide an accessible name and description.

Status badges and charts use text and icons in addition to color. Contrast must meet the selected WCAG target for normal text, large text, controls, borders, and focus indicators. The interface must remain usable at browser zoom and operating-system text scaling without loss of action access. Long labels and filenames must reflow rather than relying on horizontal scrolling in ordinary layouts.

Dynamic processing updates are announced appropriately without flooding assistive technology. A polite live region summarizes meaningful batch changes, while detailed progress remains available in the page. Errors identify the affected field or image, explain how to recover, and retain safe user input. Upload controls expose accepted formats and limits before selection. The image viewer supplies useful alt text from filename and metadata where available, while decorative thumbnails remain nonredundant; 100% inspection controls must have descriptive labels.

Animation is optional and never required to understand status. Users who prefer reduced motion receive an equivalent static state. Color-blind-safe palettes and nonvisual status cues are mandatory. Timeouts, provider retries, and background work must not erase context. Keyboard shortcuts, if introduced, are discoverable and must not conflict with browser or assistive-technology commands.

Accessibility testing combines automated checks, keyboard-only walkthroughs, screen-reader smoke tests, contrast inspection, zoom testing, and manual review of error and dynamic states. Findings are tracked by severity and block release when core upload, review, or approval cannot be completed accessibly.

## Affected blueprint areas
This governs the Next.js layout and components, review workflow, API error presentation, thumbnail and inspection behavior, and release quality gates.

## Dependencies
It depends on the design system, supported browser matrix, image metadata availability, and the final action/status vocabulary. Accessibility acceptance must be included in E2E and release testing.

## Acceptance criteria
- Upload, inspection, decision, metadata review, and finalization work keyboard-only.
- Focus order and restoration are correct for menus, dialogs, and route changes.
- Status and errors remain understandable without color or sound.
- Zoom and reduced-motion modes preserve all core functionality.
- Automated and manual checks are recorded for each release.
- No critical accessibility defect remains in the core workflow.

## Risks / open questions
Screen-reader behavior can differ across Windows browsers and products. The team must choose the supported browser and screen-reader combinations, define the target WCAG conformance level, and recruit at least one representative accessibility reviewer. Complex image pan and zoom controls require particular manual validation.