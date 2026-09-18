# Component Specification: Filterable Image Card Grid

## Status

| Attribute | Value |
|---|---|
| Component Name | ImageGrid |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Frontend - Next.js |

## Overview

The ImageGrid component renders a filterable, responsive card layout displaying image records processed by the backend. Each card surfaces critical metadata, quality control status, and contextual actions, allowing operators to quickly triage large batches of AI-generated images.

## Props Interface

| Prop Name | Type | Required | Description |
|---|---|---|---|
| records | Array | Yes | The collection of image record objects to be rendered as cards. |
| activeFilter | String | Yes | The currently selected status filter used to determine which records are visible in the grid. |

## Responsive Layout

The grid utilizes a responsive CSS grid layout that adapts to the viewport width to optimize screen real estate across devices.

| Viewport Category | Column Count |
|---|---|
| Mobile | 1 column |
| Tablet | 2 columns |
| Laptop | 3 columns |
| Desktop | 4 columns |

## Card Anatomy

Each card within the grid represents a single image record and contains the following elements:

### Thumbnail

The primary visual element is a thumbnail image loaded from the backend's static `/thumbnails/` path. This ensures fast rendering even when processing high-resolution source files.

### Confidence Badge Overlay

Positioned in the top-right corner of the card, this badge overlays the thumbnail. It displays a percentage value representing the confidence score alongside a corresponding status icon.

### Metadata Text

Below the thumbnail, the card displays the filename in a monospace font. To prevent layout breaking on long filenames, the text is truncated. Additionally, megapixel count and variance metrics are displayed to give the operator immediate technical context.

### Failure Reasons List

This section is conditionally rendered. It appears exclusively for records with a `FLAGGED` status. When present, it is enclosed in an amber warning box and lists the specific reasons the image failed automated quality control.

### Action Button

The action button at the bottom of the card changes based on the record's current status.

| Record Status | Button Label / Behavior |
|---|---|
| Any status except READY | Displays "Approve & Tag", allowing the operator to manually advance the record. |
| READY | Displays a staged label indicating the image has been approved, tagged, and is awaiting final upload. |

## Status Border Color Mapping

Cards feature a colored border that provides immediate visual identification of the record's lifecycle status.

| Status | Border Color |
|---|---|
| FLAGGED | Amber |
| PASSED | Emerald |
| READY | Blue |
| PENDING | Zinc |
| AUDITING | Zinc |
