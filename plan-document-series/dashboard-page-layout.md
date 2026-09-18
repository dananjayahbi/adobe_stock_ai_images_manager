# Component Specification: Dashboard Page Layout

## Status

| Attribute | Value |
|---|---|
| Component Name | DashboardPage |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Frontend - Next.js |

## Overview

The DashboardPage is the primary client component responsible for composing the application's main view. It manages global state, orchestrates data fetching and polling, handles user interactions, and structures the visual hierarchy of all child components.

## State Management

As a client component, the page maintains three core pieces of state to drive the UI.

| State Variable | Type | Purpose |
|---|---|---|
| records | Array | Holds the complete list of image record objects fetched from the backend. |
| activeFilter | String | Tracks the currently selected status tab to filter the visible records in the grid. |
| loading | Boolean | Indicates whether an initial fetch or blocking operation is currently in progress. |

## Lifecycle and Polling

The component utilizes an effect hook to manage the data lifecycle upon mounting.

| Phase | Behavior |
|---|---|
| Initialization | Immediately executes a data fetch to populate the records array. |
| Polling Interval | Establishes a recurring 3-second interval to continuously fetch updated records, ensuring the dashboard reflects backend processing progress in near real-time. |
| Cleanup | Returns a cleanup function that clears the polling interval when the component unmounts, preventing memory leaks and orphaned network requests. |

## Handler Functions

The page defines several handler functions to manage data flow and user actions.

| Function Name | Operation |
|---|---|
| fetchRecords | Executes a GET request to the `/api/records` endpoint to retrieve the latest state of all image records. |
| handleApprove | Executes a POST request to approve a single record, followed immediately by a call to `fetchRecords` to refresh the UI. |
| handleApproveAllPassed | Filters the local records array for items with a `PASSED` status, iterates through them calling the approve endpoint sequentially, and finally calls `fetchRecords` to synchronize the state. |

## Filtering Logic

The records displayed in the grid are derived from a computed array. This array is calculated by evaluating the `records` state against the `activeFilter` string. When a user selects a different tab, the `activeFilter` updates, and the computed array automatically restricts the grid to matching records.

## JSX Composition Order

The component tree is assembled in the following top-to-bottom order to create the dashboard layout:

1. **Header Section**: Contains the application title and integrates the batch approve statistics button.
2. **Dropzone Section**: Renders the drag-and-drop upload area for ingesting new files.
3. **Filter Tab Bar**: Provides the interactive tabs used to update the `activeFilter` state.
4. **ImageGrid**: Receives the computed, filtered array of records and renders the responsive card layout.

## Theme and Styling

The dashboard enforces a strict dark theme to reduce eye strain during long triage sessions.

| Element | Color Specification |
|---|---|
| Background | Zinc-950 |
| Primary Text | Zinc-100 |
