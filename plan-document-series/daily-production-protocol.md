# Daily Production Protocol

## Status

| Attribute | Value |
|---|---|
| Document Name | Daily Production Protocol |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Operations - Standard Operating Procedure |

## Overview

This document defines the step-by-step daily workflow for operators managing the Adobe Stock AI Image Studio. It covers the entire lifecycle of a batch, from initial AI generation through automated quality control, manual triage, metadata tagging, and final submission to the stock platform.

## Phase 1: Generation

The production cycle begins with sourcing high-quality raw material.

| Task | Details |
|---|---|
| Volume Target | Produce approximately 50 images per daily batch. |
| Resolution | Images must be high-resolution, targeting the 2K to 4K range. |
| Tooling | Utilize external AI generation platforms such as Gemini Pro, Midjourney, or Stable Diffusion. |
| Upscaling | Optionally apply 2x to 4x upscaling algorithms to images that require additional resolution before ingestion. |

## Phase 2: Ingest

Once the batch is generated, it must be loaded into the studio pipeline.

| Task | Details |
|---|---|
| Access Dashboard | Open a web browser and navigate to the local dashboard at localhost on port 3000. |
| Upload | Drag the entire generated batch of JPEG files into the Dropzone component. |
| Confirmation | Verify that the files are accepted and the loading state completes successfully. |

## Phase 3: Automated Quality Control

After ingestion, the backend processes the images autonomously.

| Task | Details |
|---|---|
| Monitor Progress | Observe the StatsBar at the top of the dashboard. |
| Status Shifts | Watch the counter badges as records transition sequentially from Pending, to Auditing, and finally resolving into either Passed or Flagged statuses. |
| Wait | Do not interfere with the batch until the Auditing count reaches zero, indicating the automated pipeline has finished evaluating the current ingest. |

## Phase 4: Triage

Human intervention is required to handle exceptions and finalize approvals.

| Task | Details |
|---|---|
| Review Flagged | Select the Flagged filter tab to isolate images that failed automated checks. |
| Discard Defects | Permanently discard images that exhibit genuine, unfixable defects (e.g., severe anatomical distortions, corrupted generations). |
| Inspect False Positives | For images flagged due to subjective traits like intentional soft focus or artistic blur, open the InspectionModal. Pan and zoom to evaluate the image at 100%. If the image is artistically sound, use the manual override button to approve it. |
| Batch Approve | Once triage is complete, return to the main view and click the "Batch Approve Passed" button in the StatsBar to finalize all clean images simultaneously. |

## Phase 5: Auto-Tagging

Approved images must be enriched with metadata to comply with stock agency requirements.

| Task | Details |
|---|---|
| Automation | The system automatically intercepts approved records. |
| Generation | Titles and relevant keywords are generated for each image using the Gemini API. |
| Embedding | The generated metadata is written directly into the image file headers using ExifTool. No manual tagging is required during this phase. |

## Phase 6: Stock Upload

The final phase involves transferring the processed assets to the distribution platform.

| Task | Details |
|---|---|
| Locate Files | Navigate to the local `ready_to_upload` directory where the system has staged the finalized, tagged images. |
| Access Portal | Open the Adobe Stock Contributor portal in a web browser. |
| Transfer | Drag the files from the local directory into the portal's upload interface. |
| Compliance | Ensure the Generative AI disclosure checkbox is selected for the entire batch, as mandated by Adobe Stock policies for AI-generated content. |
| Queue Limits | Submit the batch while respecting the platform's queue limit of approximately 50 files per submission to prevent upload failures or timeouts. |
