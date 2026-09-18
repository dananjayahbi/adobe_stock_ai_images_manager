# 34 — Semantic Audit Prompt and Response Contract

## Purpose
Define a stable semantic quality contract for identifying visual defects, possible intellectual-property concerns, and uncertainty without allowing a model confidence value to become an unattended approval decision.

## Scope
The contract covers prompt responsibilities, finding categories, severity, confidence interpretation, structured response fields, evidence references, and versioning. It does not define provider transport, generic JSON sanitation, metadata generation, or legal conclusions.

## Decisions / requirements
The semantic audit evaluates anatomy defects, malformed geometry, incoherent objects, rendering artifacts, suspicious logos or marks, recognizable protected products, celebrity likeness concerns, and other configured commercial-risk categories. The prompt must instruct the model to describe visible evidence conservatively, distinguish observation from inference, and return uncertainty when the image is ambiguous. It must not ask the model to certify copyright clearance, policy compliance, or marketplace acceptance.

The response contract contains an overall recommendation, bounded confidence from 0.0 through 1.0, an ordered collection of findings, and an uncertainty or limitation field. Each finding has a stable category, severity, concise explanation, optional region reference, and confidence. Categories include technical-looking artifact, anatomy, text or logo concern, likeness concern, composition concern, and unknown. Severity is informational, warning, high risk, or blocking-candidate; the final hard-block decision belongs to policy and human review.

The model must return structured JSON through the provider’s response mode. Unknown fields are ignored only after validation records their presence; missing required fields produce an invalid-result outcome. Empty findings are valid only when the response explicitly indicates no observed issue. A high confidence score with a high-risk finding remains high risk. A low confidence score without findings remains uncertain, not passed.

Prompt text, response schema version, model identifier, normalized image hash, and relevant policy version are stored as provenance. Re-audits create new evidence rather than replacing an earlier audit. The UI must present findings as advisory evidence and show limitations, especially for trademarks, likenesses, and subtle artifacts. Human reviewers can confirm, dismiss, or escalate a finding with a reason.

## Affected blueprint areas
This formalizes the semantic audit JSON described in the blueprint’s Gemini service and its relationship to `semantic_confidence`, `failure_reasons`, review badges, and approval eligibility. It feeds documents 36–39, 44, and 53–54.

## Dependencies
It depends on documents 03–06, 12, 27, 33, 36, 38, and 39. Current Adobe and legal guidance must define which risk categories block ready staging and which only require acknowledgment.

## Acceptance criteria
- Findings have stable categories, severity, explanation, and bounded confidence.
- Model confidence cannot independently authorize approval or READY.
- Invalid, incomplete, contradictory, and uncertain responses are review-required.
- The response and prompt versions are retained with artifact provenance.
- Reviewers can distinguish observed evidence from legal or policy conclusions.
- Re-audit history remains append-only and attributable.

## Risks / open questions
Vision models may miss subtle defects or hallucinate marks and likenesses. Region references may be imprecise and should not be treated as proof. The project must choose the supported finding taxonomy, define whether unknown findings block packaging, and establish a labeled evaluation set before changing prompt wording or thresholds.