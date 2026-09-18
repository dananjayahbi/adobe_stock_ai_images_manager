# Component Specification: Drag-and-Drop File Upload (Dropzone)

## Status

| Attribute | Value |
|---|---|
| Component Name | Dropzone |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Frontend - Next.js |

## Overview

The Dropzone component provides the primary ingestion interface for the Adobe Stock AI Image Studio. It allows operators to upload batches of JPEG images via drag-and-drop or a traditional click-to-browse file picker. Upon successful transmission to the backend, it notifies the parent component through a callback so the dashboard can refresh its record list.

## Props Interface

| Prop Name | Type | Required | Description |
|---|---|---|---|
| onUploadComplete | Callback Function | Yes | Invoked after one or more files have been successfully uploaded and acknowledged by the backend. The parent component uses this trigger to refresh the image records grid. |

## Behavioral Specification

### File Acceptance

The component renders a designated drop area that strictly accepts JPEG files. When files are selected—either by dropping them into the zone or by using the click-to-browse fallback—the component constructs a FormData payload containing all selected files. Multiple file selection is fully supported in both interaction modes.

### Network Transmission

The FormData payload is transmitted via an HTTP POST request to the `/upload` endpoint. During this transmission, the component enters a loading state to prevent duplicate submissions and provide visual feedback to the operator. Once the server responds with a success status, the `onUploadComplete` callback is triggered.

### Validation Strategy

The component performs minimal client-side validation. It checks the file type to ensure only JPEGs are processed before constructing the FormData. It does not perform any other client-side validation such as file size limits, dimension checks, or corruption detection. All advanced validation is deferred to the backend pipeline.

### Interaction States

| State | Trigger | Behavior |
|---|---|---|
| Idle | Default state | Renders the standard drop area prompt. |
| Drag-Over | User drags valid files over the zone | Applies visual feedback indicating the drop target is active. |
| Drag-Leave | User drags files out of the zone without dropping | Reverts visual feedback to the idle state. |
| Loading | Upload POST request is in flight | Disables further drops, displays a loading indicator. |
| Success | Server acknowledges upload | Triggers the `onUploadComplete` callback, reverts to idle. |

## Visual Design

| Element | Design Specification |
|---|---|
| Border | Dashed border to clearly delineate the interactive drop region. |
| Content Alignment | Centered icon accompanied by a text prompt instructing the user to drag files or click to browse. |
| Hover / Active State | Visual style changes when the user hovers over the zone or when a drag-over event occurs, providing clear affordance. |
| Loading Indicator | Displayed during upload transmission to communicate progress and block further interaction. |
