# 04 — Compliance and Legal Risk Register

## Purpose
Identify legal and contributor risks that technical QC and multimodal review cannot eliminate. The register provides controls, owners, evidence expectations, and escalation paths for images that may be commercially unsafe even when they meet file specifications.

## Scope
The register covers trademarks and logos, protected product designs, recognizable people and celebrity likenesses, copyright-like visual imitation, privacy, misleading metadata, generative-AI disclosure, provider data handling, and contributor-account consequences. It excludes legal opinions and formal rights clearance services.

## Decisions and requirements
The studio must treat semantic AI findings as risk signals requiring human judgment. A logo-like mark, famous vehicle signature, celebrity likeness, or recognizable protected character must be flagged for review and must not be silently removed from a title or keyword list to make an item appear safe. The reviewer needs evidence, a reason code, and a way to reject or quarantine the asset.

Metadata must describe the actual image without inserting trademarked terms for search advantage. The system should maintain forbidden-term validation and record both generated and final metadata. Personal data in filenames, OCR output, provider prompts, logs, or diagnostic bundles should be minimized. Uploaded images sent to an external model require a visible configuration and privacy decision, including retention assumptions and a user-controlled disable or degraded mode where feasible.

Generative-AI disclosure is a contributor responsibility and must be surfaced as a required checklist item before ready staging. The software may prepare evidence but must not claim that embedded IPTC or XMP fields satisfy a portal checkbox unless current policy explicitly says so.

## Affected blueprint areas
This register affects the Gemini semantic audit, metadata generation, dashboard review modal, approval endpoint, metadata embedding, diagnostic logging, configuration, storage retention, and release checklist. It is a required input for documents 03, 05, 06, 33–39, 48, 63, and 65–66.

## Dependencies
Controls depend on current Adobe contributor policy, legal counsel or organizational risk tolerance, provider terms, privacy requirements, and a durable audit-event model. The UI and API must support explicit risk classifications and reviewer reasons rather than a single pass/fail value.

## Acceptance criteria
- Risk categories, severity, control, owner, and residual risk are documented.
- High-risk findings block ready staging until a human resolves them.
- Generated and final metadata are retained with provenance.
- External image processing and data-retention behavior are disclosed in configuration or documentation.
- Logs and exports avoid unnecessary personal data and secrets.
- Release evidence includes a policy and legal-risk review.

## Risks and open questions
AI detection can miss subtle infringement or produce false positives. The project has no rights-management integration and cannot prove originality. The acceptable treatment of recognizable people, generic brand-like shapes, and user-supplied images needs an explicit policy. The owner must decide whether any risk categories are permanently disqualifying and how long rejected or quarantined assets should be retained.