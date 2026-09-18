# 66 — Post-MVP Product Roadmap

## Purpose
Define a disciplined path beyond the local MVP so future capabilities improve contributor productivity without weakening human oversight, provenance, policy compliance, or the reliability of the core image pipeline.

## Scope
The roadmap covers candidate post-MVP capabilities, sequencing criteria, architectural guardrails, discovery questions, and measurable outcomes. It does not commit implementation dates, promise Adobe API access, or replace the MVP acceptance plan.

## Decisions / requirements
Post-MVP work is prioritized by user value, safety, evidence quality, and operational cost rather than by feature novelty. The first expansion tier should strengthen the existing workflow: richer batch triage, saved filters, configurable review presets, better calibration tools, improved recovery, package manifests, and clearer policy-update workflows. These additions must preserve source immutability, durable state transitions, audit history, and explicit approval.

A second tier may add multiple local workspaces, role-aware review, shared project exports, more provider adapters, configurable metadata languages, and stronger comparison tools. Multi-user or networked operation requires a new threat model, authentication, authorization, concurrency strategy, and privacy review; it must not be smuggled in through a convenience setting. Provider abstraction should support evaluation and failover without allowing model-specific assumptions to leak into policy decisions.

A third tier may explore analytics on acceptance outcomes, calibrated active learning for thresholds, duplicate and similarity assistance, controlled cloud backup, or optional marketplace integrations. Direct submission, if ever pursued, remains a separate product decision with explicit account security, Adobe terms, queue limits, disclosure handling, and a kill switch. Automation may recommend actions, but human review and provenance remain required until policy and evidence justify a change.

Each candidate receives a discovery brief with user problem, affected invariants, data classification, performance and cost impact, legal and policy review, migration needs, test strategy, rollback plan, and success metrics. Experiments should be reversible and isolated from production records. Deprecated behavior receives a migration and communication plan.

## Affected blueprint areas
This roadmap extends product scope, architecture, domain and API contracts, provider integration, review policy, observability, deployment, and testing documents 01, 07, 14, 33–39, 45–65.

## Dependencies
Priorities depend on MVP telemetry, operator interviews, Adobe policy changes, support incidents, provider economics, security review, and the stability of the core state machine and storage model.

## Acceptance criteria
- Every proposed feature has a problem statement, risk review, and measurable outcome.
- No roadmap item removes human approval or provenance without explicit governance.
- Network, multi-user, cloud, and marketplace features receive separate security and legal gates.
- Migration and rollback implications are identified before commitment.
- Post-MVP experiments do not corrupt or silently reinterpret MVP records.
- Priorities are revisited using evidence from real operation.

## Risks / open questions
Roadmap pressure may encourage unsafe automation or direct submission before controls mature. The owner must choose the first post-MVP outcome, define whether shared workspaces are strategically important, determine what telemetry can inform prioritization, and establish governance for policy-sensitive feature changes.