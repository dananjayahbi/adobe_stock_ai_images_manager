# Backend Model - Image Record Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - ORM Entity |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Define the SQLAlchemy ORM entity that persists image metadata and pipeline state for every uploaded file. This model is the central data structure around which the entire audit, approval, and upload pipeline revolves.

## Responsibilities

### Column Definitions

The ImageRecord table must contain the following columns:

| Column Name | Type | Constraints | Default | Description |
|---|---|---|---|---|
| id | Integer | Primary key, auto-increment | None | Unique identifier for each record |
| filename | String | Unique, indexed | None | Original filename as provided during upload |
| original_path | String | Not null | None | Absolute filesystem path to the image in the inbox directory |
| thumbnail_path | String | Not null | None | Absolute filesystem path to the generated thumbnail |
| status | String | Indexed | PENDING | Current pipeline state of the image |
| megapixels | Float | None | 0.0 | Computed resolution in megapixels |
| laplacian_variance | Float | None | 0.0 | Sharpness metric computed during audit |
| semantic_confidence | Float | None | 0.0 | AI-generated confidence score for metadata quality |
| heuristic_breakdown | JSON | None | Empty dict | Detailed breakdown of individual audit check results |
| failure_reasons | JSON | None | Empty list | List of human-readable strings explaining why an image was flagged |
| title | String | Nullable | None | Generated or approved title for Adobe Stock submission |
| keywords | JSON | Nullable | None | List of generated or approved keywords for Adobe Stock submission |
| created_at | DateTime (UTC) | Not null | Current UTC time | Timestamp when the record was first created |
| updated_at | DateTime (UTC) | Not null | Auto-updated on change | Timestamp of the most recent modification |

### Index Strategy

Two indexes are required for efficient querying:

| Index Target | Rationale |
|---|---|
| filename (unique) | Prevents duplicate entries and enables fast lookups by name |
| status | Supports filtered listing queries where users view images by pipeline stage |

### State Machine

The status field follows a strict directed state machine. Invalid transitions must be rejected at the application layer:

| Source State | Allowed Destination States | Trigger |
|---|---|---|
| PENDING | AUDITING | Background audit task begins processing |
| AUDITING | PASSED | All automated quality checks succeed |
| AUDITING | FLAGGED | One or more quality checks fail |
| PASSED | READY | Human approves the record |
| FLAGGED | READY | Human overrides the flag and approves the record |

Terminal state: READY. Records in the READY state have been fully processed, embedded with metadata, and moved to the upload directory. No further state transitions occur.

### Timestamp Behavior

| Column | Behavior |
|---|---|
| created_at | Set once at insertion time using UTC. Must never be modified afterward. |
| updated_at | Automatically refreshed to the current UTC time whenever any column on the record is modified and committed. |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| JSON column serialization | The heuristic_breakdown, failure_reasons, and keywords columns must use the JSON type to ensure proper serialization and deserialization without manual string handling |
| UTC timestamps | All datetime values must be stored in UTC; no local timezone offsets are permitted |
| Nullable metadata fields | Title and keywords remain null until the metadata generation service populates them during the approval phase |
| Default numeric values | Megapixels, laplacian_variance, and semantic_confidence default to 0.0 to indicate that auditing has not yet occurred |
| Immutable ID | The primary key must never be reassigned or modified after creation |