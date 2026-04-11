# ADR-0009: Categorical Scoring with LLM Gap Relevance

## Status

Accepted (supersedes ADR-0005)

## Context

ADR-0005 introduced dual numeric scores: likelihood_score (0-1) for evidence strength and confidence_limit (0-1) for coverage-based ceiling. In practice, the numeric precision implied calibration the system did not have. A likelihood of 0.884 vs 0.850 carried no meaningful distinction, yet the numbers suggested otherwise.

More importantly, the confidence limit was set mechanically from coverage status (complete->0.95, partial->0.6, missing->0.3) without reasoning about whether specific gaps mattered for the hypothesis. A missing MFA source and a missing display_name field both produced the same 0.6 cap.

## Decision

Replace numeric scores with categorical low/medium/high bands. Introduce a structured LLM call to classify coverage gap relevance.

**Likelihood** stays deterministic and evidence-driven. The existing aggregation, claim building, pattern classification, and polarity assignment pipeline is unchanged. A new `score_likelihood()` function maps the internal numeric calculation to a band:
- high: strong supporting evidence, no strong contradictions
- medium: mixed evidence or weaker support
- low: little support or strong contradiction

**Confidence** is determined in two steps:
1. Coverage gaps are extracted from the coverage report and pipeline tool call observations.
2. Gap relevance is classified by either an LLM provider (when `use_llm=True`) or a conservative fallback provider. Each gap receives a structured assessment: relevance (critical/relevant/minor/irrelevant) and could_change_conclusion (boolean).
3. Deterministic band logic maps the assessments to confidence: low if any critical gap could change the conclusion, medium if any critical or relevant gap exists, high otherwise.

The LLM's only role is gap classification. It does not determine likelihood, produce scores, or generate unstructured scoring prose.

**`could_change_conclusion` contract:**
- true: if this missing evidence were available, it could reasonably support a different hypothesis or materially weaken the current one
- false: it would improve detail or confidence, but is unlikely to alter the main conclusion

## Rationale

- Eliminates false precision (0.884 vs 0.850 meant nothing)
- Makes confidence context-dependent: the same "partial" coverage can be critical for one hypothesis and irrelevant for another
- One scoring path with two gap-assessment providers, not dual scoring modes
- The LLM call is narrow, structured, and falls back conservatively
- Deterministic tests stay deterministic (mock the gap assessment provider)
- The prompt contract is explicit and snapshot-tested

## Consequences

Positive:
- Scoring output is honest about its precision level
- Coverage gap relevance is assessed per-hypothesis instead of mechanically
- The system can distinguish between gaps that matter and gaps that don't
- Investigation reports include structured gap assessments for transparency

Negative:
- One additional LLM call per investigation when use_llm=True (1-5s latency)
- Band boundaries require calibration against test scenarios
- Breaking change to Hypothesis and InvestigationReport field names
- DuckDB schema migration (destructive for hypotheses table)

## Supersedes

ADR-0005 (Coverage-Aware Hypothesis Scoring). The separation of likelihood from confidence remains. The change is in representation (bands instead of floats) and confidence determination (gap relevance classification instead of mechanical coverage status mapping).
