# ADR-0004: Domain-Based Investigation Architecture

## Status

Accepted

## Context

Security incidents span multiple domains: identity (authentication, authorization), network (traffic, connections), and resources (file access, API calls, cloud operations). Each domain has distinct data sources, query patterns, and expertise requirements.

Monolithic investigation tools struggle with the breadth of domain knowledge required. Responders often need specialized context from each domain.

## Decision

Structure the system around investigation domains:
- Identity domain: principals, credentials, sessions, authentication events
- Network domain: endpoints, connections, traffic flows
- Cloud infrastructure domain: cloud resources, control plane events
- SaaS domain, application domain, data domain, etc.

Each domain:
- Defines entity types and action event taxonomies for its scope
- Implements MCP tools following shared tool contracts (search, get, neighbors)
- Returns domain-specific entities with normalized record structure
- Includes coverage reports indicating visibility gaps

Domains share a common ontology for core types (Entity, ActionEvent, Relationship, CoverageReport) but extend with domain-specific kinds and attributes.

## Rationale

- Separates concerns by investigation domain
- Allows independent development and testing of each domain
- Enables domain experts to focus on their area
- Supports incremental implementation (identity first, others later)
- Scales to additional domains (e.g., email, endpoint) without core changes
- Clear boundaries reduce coupling between integrations

## Consequences

Positive:
- Modular development and testing
- Domain expertise can be applied per domain
- Clear scope for initial implementation (identity domain only)
- Extensible to new domains without redesign

Negative:
- Cross-domain correlation requires coordination
- Duplicate effort if domains need similar query patterns
- Risk of inconsistent conventions across domains
- Complexity in managing domain interactions
