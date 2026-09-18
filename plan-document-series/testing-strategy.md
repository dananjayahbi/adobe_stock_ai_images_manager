# Testing Strategy Specification

## Purpose

This document defines the comprehensive testing approach for both the backend Python services and the frontend Next.js interface. It establishes coverage expectations, isolation requirements, and execution constraints to ensure deterministic and CI-compatible test runs.

## Status

PENDING

## Backend Testing

### Unit Tests for QC Engine Heuristics

The quality control engine relies on heuristic analysis of image properties. Unit tests must validate these heuristics using mock images with known characteristics.

| Test Scenario | Mock Image Properties | Expected Outcome |
|---|---|---|
| Sharpness evaluation | Image with known high sharpness score | Passes sharpness threshold |
| Sharpness evaluation | Image with known low sharpness score | Fails sharpness threshold |
| Dimension validation | Image matching Adobe Stock minimum dimensions | Passes dimension check |
| Dimension validation | Image below minimum dimensions | Fails dimension check |
| Aspect ratio validation | Image within acceptable ratio range | Passes ratio check |

### Unit Tests for Metadata Parsing

Metadata parsing logic must be tested independently of file system operations. Tests should supply raw metadata dictionaries and verify correct extraction, normalization, and mapping to internal record fields.

### Integration Tests for Upload-to-Ready Pipeline

Integration tests must exercise the full lifecycle from file upload through state transitions to final readiness. These tests must use temporary directories that are created during setup and destroyed during teardown to prevent cross-test contamination.

| Pipeline Stage | Verification Point |
|---|---|
| File ingestion | Record created with PENDING status |
| Thumbnail generation | Thumbnail file exists in temporary output directory |
| QC auditing | State transitions to PASSED or FLAGGED based on mock inputs |
| Approval | State transitions to READY after simulated human action |

### External Service Mocking

Gemini API interactions must be fully mocked to ensure deterministic test outcomes. No test should make live network calls to external AI services. Mock responses should cover success payloads, rate limit responses, and malformed return structures.

## Frontend Testing

### Component Rendering Tests

Each core UI component must have rendering tests that verify correct DOM structure given specific props.

| Component | Rendering Assertions |
|---|---|
| Dropzone | Displays upload prompt, accepts drag events, shows file count after selection |
| ImageGrid | Renders correct number of cards, displays thumbnails, shows status badges |
| InspectionModal | Opens with record details, closes on dismiss, displays metadata fields |
| StatsBar | Shows accurate counts per status category, updates when props change |

### Interaction Tests

User interactions that trigger API calls must be tested to confirm correct function invocation and payload construction.

| Interaction | Expected Behavior |
|---|---|
| Approve button click on single card | API client approve-single function called with correct record identifier |
| Bulk approve action | API client approve-multiple function called with correct array of identifiers |
| Filter dropdown selection | API client fetch-records function called with corresponding status query parameter |

### Polling Interval Lifecycle Tests

The frontend polling mechanism must be tested for proper lifecycle management. Tests should verify that polling starts when the component mounts, pauses or stops when the component unmounts, and respects configured interval durations without drift accumulation.

## Constraints

| Constraint | Implementation Requirement |
|---|---|
| Database isolation | Test database must be completely separate from the production SQLite file |
| Fixture storage | All test images stored in a dedicated test assets directory |
| CI compatibility | Test commands must execute non-interactively with standard exit codes |
| Cleanup | Temporary files and databases removed after each test session |