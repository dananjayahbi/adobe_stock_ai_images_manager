# Component Specification: Dashboard Statistics Bar

## Status

| Attribute | Value |
|---|---|
| Component Name | StatsBar |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Frontend - Next.js |

## Overview

The StatsBar component acts as the dashboard header, providing operators with an at-a-glance summary of the current batch's processing state. It displays aggregate metrics and houses the primary batch action button used to finalize approved images.

## Metrics Display

The component calculates and displays the total number of records in the current dataset, alongside a breakdown of counts per status category. These metrics update reactively as the background polling mechanism refreshes the record data.

| Metric | Description |
|---|---|
| Total Records | The absolute count of all image records currently loaded in the dashboard. |
| Pending Count | Number of records waiting to enter the processing pipeline. |
| Auditing Count | Number of records currently undergoing automated quality control. |
| Passed Count | Number of records that have successfully cleared all automated checks. |
| Flagged Count | Number of records that failed one or more quality control checks. |
| Ready Count | Number of records that have been approved, tagged, and prepared for upload. |

## Batch Approve Action

The StatsBar contains a prominent action button labeled "Batch Approve Passed". 

| Attribute | Behavior |
|---|---|
| Dynamic Label | The button displays the current count of `PASSED` records, updating dynamically as new images clear the audit stage. |
| Execution Logic | When clicked, the button triggers a routine that iterates through all records currently holding a `PASSED` status. It calls the approval endpoint sequentially for each record. |

## Visual Design

The layout is constructed using a flexbox row to align metrics and actions horizontally across the top of the dashboard.

| Element | Visual Specification |
|---|---|
| Counter Badges | Each status count is presented inside a badge utilizing the status-appropriate color (amber for Flagged, emerald for Passed, blue for Ready, zinc for Pending/Auditing). |
| Batch Approve Button | Styled as a prominent emerald button featuring a sparkle icon to draw the operator's attention to the primary workflow advancement action. |
