# ADR-0004: Plane-Based Investigation Architecture

## Status

Accepted

## Context

Security incidents span multiple domains: identity (authentication, authorization), network (traffic, connections), and resources (file access, API calls, cloud operations). Each domain has distinct data sources, query patterns, and expertise requirements.

Monolithic investigation tools struggle with the breadth of domain knowledge required. Responders often need specialized context from each domain.

## Decision

Structure the system around investigation "planes":
- Identity plane: principals, credentials, sessions, authentication events
- Network plane: endpoints, connections, traffic flows
- Resource plane: files, APIs, cloud resources, access events

Each plane:
- Defines entity types and action event taxonomies for its domain
- Implements MCP tools following shared contracts (search, get, neighbors)
- Returns domain-specific entities with canonical object structure
- Includes coverage reports indicating visibility gaps

Planes share a common ontology for core types (Entity, ActionEvent, Relationship, CoverageReport) but extend with domain-specific kinds and attributes.

## Rationale

- Separates concerns by investigation domain
- Allows independent development and testing of each plane
- Enables domain experts to focus on their area
- Supports incremental implementation (identity first, others later)
- Scales to additional planes (e.g., email, endpoint) without core changes
- Clear boundaries reduce coupling between adapters

## Consequences

Positive:
- Modular development and testing
- Domain expertise can be applied per plane
- Clear scope for initial implementation (identity plane only)
- Extensible to new domains without redesign

Negative:
- Cross-plane correlation requires coordination
- Duplicate effort if planes need similar query patterns
- Risk of inconsistent conventions across planes
- Complexity in managing plane interactions
