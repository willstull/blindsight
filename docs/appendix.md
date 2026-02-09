# Appendix: Terms and Definitions

## Core project nouns

**Domain**
A category of telemetry defined by where activity occurs and which audit/admin logs record it (identity, cloud, network, endpoint, application, SaaS, data, email/collab, CI/CD, third-party). Domains are an operational grouping, not a framework.

**MCP server**
A running service that exposes tools to an MCP client (an LLM host). In this project, MCP servers provide investigation queries over one or more domains and always return normalized records and coverage.

**Tool**
A callable capability exposed by an MCP server (example: `search_events`, `get_entity`, `describe_coverage`). Tools have stable request/response shapes.

**Tool contract**
The specification for tool names, request/response schemas, response envelope rules, and invariants (what must always be returned, required fields, pagination rules, error semantics). This is the “API contract” for MCP tools.

**Integration**
A concrete implementation inside an MCP server that connects to a data source or platform (Okta, Entra ID, CloudTrail, Splunk, Datadog, GitHub audit logs, local files) and translates raw outputs into normalized records. An integration can be live (queries APIs) or replay-backed (reads fixture files). All integrations implement the DomainIntegration interface.

**Case store**
The persistent store holding investigation state and outputs: normalized records, evidence references, claims, hypotheses, coverage, and tool-call history. Implemented with DuckDB in this project.

**Case MCP server**
The MCP server that reads/writes the case store and provides cross-domain correlation and case queries. It is not a domain.

## Ontology terms

**Ontology**
The shared structure for the project’s records and investigation objects (entities, events, relationships, evidence, claims, hypotheses, cases, coverage).

**Normalized record**
A record translated into the project’s standard structure so different integrations can be compared and correlated. Includes Entities, ActionEvents, and Relationships.

**Entity**
A “thing” referenced in investigations. Examples: principal (user/service account), session, credential, device, IP address, resource, application, tenant. Entities have stable IDs and references to source identifiers.

**ActionEvent (event)**
A normalized action in time: who did what, to what, when, with what outcome. Events carry source references back to raw records.

**Relationship (edge)**
A typed link between entities (example: principal “owns” credential, principal “initiated” session, session “used” source IP).

**EvidenceItem (evidence)**
A pointer (and optional snapshot) to raw source material used to support analysis: log record IDs, query references, file hashes, exported artifacts. Evidence includes sensitivity marking.

**Source reference**
A structured pointer to where evidence came from (source system, query or file, record identifier, timestamp, hash).

**Coverage report**
A machine-readable statement of what data was available for a query and what was missing or unreliable (missing sources, missing fields, retention gaps, latency). Returned with every tool response.

**Claim**
A single atomic statement derived from evidence (example: “Principal X had password reset at time T”). Claims link to evidence items.

**Assumption**
An explicitly stated condition taken as true for the investigation (example: “Okta logs are complete for the window”). Assumptions have a strength label (solid/caveated/unsupported).

**Hypothesis**
A testable statement about what happened (example: “Account takeover occurred via credential reset”). Hypotheses reference supporting/contradicting claims and list remaining evidence needed.

**Likelihood score**
How strongly the current evidence supports a hypothesis, ignoring data gaps. Range and meaning are defined in the tool contract/spec.

**Confidence limit**
The maximum confidence allowed given coverage problems (missing sources, retention gaps, missing fields). This caps how certain you can be even if evidence looks strong.

**Investigation question (IQ)**
A concrete question responders want answered (scope, timeline, containment checks). IQs can be tied to required domains and expected outputs.

**Finding**
A human-readable summary of one or more claims/hypotheses, with explicit evidence links and coverage limitations.

## Replay and evaluation terms

**Replay dataset**
A packaged scenario bundle used for deterministic testing and evaluation. It can contain evidence from multiple domains. It includes data plus metadata (manifest, coverage, expected outputs).

**Replay scenario**
A single test case: question + time window + replay dataset inputs + expected outputs and success criteria.

**Scenario family**
A baseline scenario plus its degraded variants (for coverage/retention/field loss).

**Baseline variant**
The “complete coverage” version of a scenario.

**Degraded variant**
A version of the same scenario with controlled data loss (missing source, retention gap, missing fields, latency).

**Golden output**
The expected response output saved for regression tests. A run is considered correct if it matches the golden output under defined comparison rules.

**Deterministic output**
Given the same replay dataset and request, the output is identical (or identical under a defined canonical ordering rule).

## Operational terms

**Read-only**
Integrations are queried without making state changes in the source systems (no remediation, no configuration changes, no ticket updates unless explicitly out of scope).

**Query-in-place**
The MCP server retrieves data from where it already lives (APIs, existing log platforms, exported files) rather than building a new ingestion/indexing pipeline as the default path.

**Correlation**
Linking records across domains and integrations using pivot fields (principal IDs, emails, client IDs, IPs, session IDs, resource IDs, timestamps). Implemented in the case store.

**Pivot field**
A field used to join data across sources (examples: `principal_id`, `email`, `source_ip`, `session_id`, `client_id`, `resource_id`).

**Retention gap**
A period where relevant logs are not available due to retention limits or missing collection.

**Data latency**
Delay between an event occurring and it appearing in the source system/search results.

**Scope**
The set of affected identities/resources/sessions/actions supported by available evidence. Scope is bounded by coverage.

**Containment verification**
Evidence-based checks showing no continuing malicious activity after remediation, with explicit limitations when negative proof is not possible.

## Sensitivity and handling terms

**TLP (Traffic Light Protocol)**
A marking on cases, evidence, and outputs indicating sharing restrictions: RED, AMBER, AMBER_STRICT, GREEN, CLEAR.

**Data minimization**
Only store the minimal evidence needed to support claims and reproducibility (prefer references/hashes over full raw copies unless required for replay).

## Domain list (canonical names)

**Endpoint domain**
OS and EDR telemetry: process execution, persistence, file/registry, memory indicators.

**Network domain**
Traffic telemetry: DNS, HTTP(S), TLS, NetFlow, VPN, east-west traffic.

**Identity domain**
Authentication and authorization telemetry: users, sessions, tokens, MFA, federation, privilege use.

**Cloud infrastructure domain**
Cloud audit/admin telemetry: IAM, control plane events, resource changes, credential issuance.

**SaaS domain**
Third-party platform audit telemetry: admin actions, OAuth apps, file/mail access, tenant configuration.

**Application domain**
First-party app audit logs and business-logic security events: user actions, permission checks, abuse patterns.

**Data domain**
Database/object store access telemetry: queries, bulk reads/writes, exports, backups access.

**Email and collaboration domain**
Mail and docs telemetry: phishing artifacts, mailbox rules, sharing links, OAuth consent abuse.

**CI/CD and developer tooling domain**
Repo and pipeline telemetry: commits, workflow runs, secrets access, runner activity, artifact access.

**Third party and supply chain domain**
Vendor/integration trust telemetry: partner access, API integrations, update mechanisms, MSP activity.

## Naming conventions

**Server naming**
`identity-mcp`, `cloud-mcp`, `case-mcp` (or equivalent). Domain name + `-mcp`.

**Scenario naming**
`<scenario_family>_<baseline|degraded_<type>>`
Example: `credential_change_baseline`, `credential_change_degraded_missing_fields`.
