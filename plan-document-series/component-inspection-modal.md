# Component Specification: Image Inspection Modal

## Status

| Attribute | Value |
|---|---|
| Component Name | InspectionModal |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Frontend - Next.js |

## Overview

The InspectionModal is a full-screen or large-format modal dialog designed for detailed human review of image records. It serves as the critical intervention point in the human-in-the-loop workflow, enabling operators to inspect flagged images at full resolution before deciding whether to override automated quality control failures.

## Trigger Conditions

The modal is triggered when an operator needs to inspect a `FLAGGED` image at 100% zoom. Automated quality control pipelines may flag images for issues like soft focus or blur; however, in AI-generated art, these traits are sometimes intentional artistic choices. The modal provides the workspace necessary for a human to make that distinction and override the system if appropriate.

## Display Elements

Upon opening, the modal presents the following components to the operator:

### Full-Resolution Viewer

The primary element is a viewer displaying the full-resolution source image. This viewer must support pan and zoom capabilities, allowing the operator to inspect fine details, textures, and artifacts at 100% magnification or higher.

### Failure Reasons List

A comprehensive list detailing exactly why the automated pipeline flagged the image. This list aggregates failure reasons from both stages of the quality control process:

| QC Stage | Description |
|---|---|
| Deterministic | Rule-based failures such as incorrect dimensions, unsupported color profiles, or excessive file size. |
| Semantic | AI-evaluated failures such as perceived blurriness, anatomical anomalies, or composition defects. |

### Confidence Score Breakdown

A detailed view of the confidence scores generated during the auditing phase, providing mathematical context behind the automated decision to flag the image.

## Actions

| Action | Description |
|---|---|
| Manual Override | A dedicated button that allows the operator to approve the image despite the automated flags. Clicking this advances the record's status, bypassing the failure reasons. |
| Close | A close button that dismisses the modal and returns the operator's focus to the underlying grid view without altering the record's status. |

## Workflow Purpose

This component directly supports the human-in-the-loop operational philosophy. Because AI generation tools frequently produce stylized outputs (e.g., intentional soft focus, artistic motion blur, surreal compositions), strict automated thresholds will inevitably generate false positives. The InspectionModal empowers the operator to rescue visually acceptable assets that would otherwise be discarded automatically.
