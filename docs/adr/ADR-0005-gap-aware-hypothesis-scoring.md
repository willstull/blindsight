# ADR-0005: Gap-Aware Hypothesis Scoring

## Status

Accepted

## Context

Incident investigations frequently encounter missing data: retention gaps, disabled logging, unavailable sources, incomplete field coverage. Traditional confidence scoring treats confidence as a single metric that doesn't distinguish between "evidence supports this" and "we can verify this."

Reporting high confidence conclusions when critical data is missing creates false certainty. Responders need to know both what the evidence suggests and what cannot be verified.

## Decision

Separate likelihood scoring from confidence bounds using two independent metrics:

**Likelihood Score** (0.0 to 1.0): Given available evidence, how probable is this hypothesis?
- Based on supporting and contradicting claims
- Reflects strength of available evidence
- Calculated from observable data

**Confidence Limit** (0.0 to 1.0): Given coverage gaps, what is the maximum justified confidence?
- Based on coverage reports from queries
- Reflects data availability and completeness
- Limits how certain we can be regardless of evidence strength

Final confidence = min(likelihood_score, confidence_limit)

Hypotheses include explicit gap references (coverage report IDs) that constrain the confidence limit.

## Rationale

- Distinguishes "strong evidence" from "complete visibility"
- Makes missing data visible in conclusions
- Prevents false certainty when coverage is poor
- Supports investigator decision-making about evidence gaps
- Aligns with intelligence analysis best practices (confidence vs. likelihood)
- Enables systematic testing of gap-handling behavior

## Consequences

Positive:
- Explicit handling of incomplete data
- Responders can see what's missing, not just what's present
- Testable behavior with degraded datasets
- Aligns with honest uncertainty communication

Negative:
- More complex scoring model than single confidence value
- Requires coverage report generation for all queries
- May produce conservative confidence limits
- Users must understand two-metric system
