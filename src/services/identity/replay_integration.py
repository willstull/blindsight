"""Replay-backed identity domain integration.

Reads NDJSON fixture files and serves them through the DomainIntegration
interface. Builds in-memory indexes for efficient lookups.
"""
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.services.identity.coverage import (
    build_coverage_report,
    build_limitations,
)
from src.types.core import (
    ActionEvent,
    Actor,
    CoverageReport,
    Entity,
    Ref,
    Relationship,
    SourceStatus,
    Target,
    TimeRange,
)
from src.types.envelope import IntegrationResult
from src.types.integration import DomainIntegration
from src.utils.serialization import load_ndjson, load_yaml
from src.utils.time import is_within_range


class ReplayIdentityIntegration(DomainIntegration):
    """Reads from NDJSON fixtures and serves normalized records."""

    def __init__(self, scenario_path: Path, logger: logging.Logger) -> None:
        self._logger = logger
        self._scenario_path = scenario_path
        self._domain_dir = scenario_path / "domains" / "identity"

        # Load data eagerly
        raw_entities = load_ndjson(self._domain_dir / "entities.ndjson")
        raw_events = load_ndjson(self._domain_dir / "events.ndjson")
        raw_rels = load_ndjson(self._domain_dir / "relationships.ndjson")
        self._coverage_data = load_yaml(self._domain_dir / "coverage.yaml")

        # Parse into typed objects
        self._entities = [_parse_entity(r) for r in raw_entities]
        self._events = [_parse_event(r) for r in raw_events]
        self._relationships = [_parse_relationship(r) for r in raw_rels]

        # Build indexes
        self._entity_by_id: dict[str, Entity] = {e.id: e for e in self._entities}
        self._rels_by_from: dict[str, list[Relationship]] = defaultdict(list)
        self._rels_by_to: dict[str, list[Relationship]] = defaultdict(list)
        for rel in self._relationships:
            self._rels_by_from[rel.from_entity_id].append(rel)
            self._rels_by_to[rel.to_entity_id].append(rel)

        self._logger.info(
            "ReplayIdentityIntegration loaded",
            extra={
                "entity_count": len(self._entities),
                "event_count": len(self._events),
                "relationship_count": len(self._relationships),
            },
        )

    def _make_coverage(self, time_range: Optional[TimeRange] = None) -> CoverageReport:
        if time_range is None:
            time_range = TimeRange(
                start="2026-01-01T00:00:00Z",
                end="2026-01-31T23:59:59Z",
            )
        return build_coverage_report(
            self._logger, "identity", time_range, self._coverage_data
        )

    def _make_limitations(self) -> list[str]:
        return build_limitations(self._coverage_data)

    # -- Metadata methods --

    async def describe_domain(self) -> dict:
        entity_types = sorted({e.entity_type for e in self._entities})
        action_prefixes = sorted({a.split(".")[0] + "." for a in {e.action for e in self._events}})
        return {
            "domain": "identity",
            "version": "0.1.0",
            "capabilities": {
                "supported_entity_types": entity_types,
                "supported_actions_prefixes": action_prefixes,
                "supports_neighbors": True,
                "supports_coverage": True,
            },
        }

    async def describe_types(self) -> dict:
        entity_types = sorted({e.entity_type for e in self._entities})
        rel_types = sorted({r.relationship_type for r in self._relationships})
        context_fields: set[str] = set()
        for evt in self._events:
            if evt.context:
                context_fields.update(evt.context.keys())
        return {
            "domain": "identity",
            "types": {
                "entity_type_enum": entity_types,
                "relationship_types": rel_types,
                "context_fields": sorted(context_fields),
            },
        }

    # -- Evidence methods --

    async def get_entity(self, entity_id: str) -> IntegrationResult:
        entity = self._entity_by_id.get(entity_id)
        if entity is None:
            return IntegrationResult(
                coverage=self._make_coverage(),
                limitations=self._make_limitations(),
            )
        return IntegrationResult(
            entities=[entity],
            coverage=self._make_coverage(),
            limitations=self._make_limitations(),
        )

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[list[str]] = None,
        kinds: Optional[list[str]] = None,
        limit: int = 100,
        page_token: Optional[str] = None,
    ) -> IntegrationResult:
        results = self._entities
        q_lower = query.lower()
        results = [
            e for e in results
            if q_lower in e.display_name.lower() or q_lower in e.id.lower()
        ]
        if entity_types:
            results = [e for e in results if e.entity_type in entity_types]
        if kinds:
            results = [e for e in results if e.kind in kinds]
        results = results[:limit]
        return IntegrationResult(
            entities=results,
            coverage=self._make_coverage(),
            limitations=self._make_limitations(),
        )

    async def search_events(
        self,
        time_range: TimeRange,
        actions: Optional[list[str]] = None,
        actor_entity_ids: Optional[list[str]] = None,
        target_entity_ids: Optional[list[str]] = None,
        filters: Optional[dict] = None,
        limit: int = 2000,
        page_token: Optional[str] = None,
    ) -> IntegrationResult:
        filtered = [
            e for e in self._events
            if is_within_range(e.ts, time_range.start, time_range.end)
        ]

        if actions:
            filtered = _filter_by_actions(filtered, actions)

        if actor_entity_ids:
            filtered = [
                e for e in filtered
                if e.actor.actor_entity_id in actor_entity_ids
            ]

        if target_entity_ids:
            target_set = set(target_entity_ids)
            filtered = [
                e for e in filtered
                if any(t.target_entity_id in target_set for t in e.targets)
            ]

        filtered = filtered[:limit]

        # Collect referenced entities
        ref_ids: set[str] = set()
        for evt in filtered:
            ref_ids.add(evt.actor.actor_entity_id)
            for t in evt.targets:
                ref_ids.add(t.target_entity_id)
        entities = [self._entity_by_id[eid] for eid in ref_ids if eid in self._entity_by_id]

        return IntegrationResult(
            entities=entities,
            events=filtered,
            coverage=self._make_coverage(time_range),
            limitations=self._make_limitations(),
        )

    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[list[str]] = None,
        time_range: Optional[TimeRange] = None,
        depth: int = 1,
        limit: int = 2000,
        page_token: Optional[str] = None,
    ) -> IntegrationResult:
        # Bidirectional traversal
        rels: list[Relationship] = []
        rels.extend(self._rels_by_from.get(entity_id, []))
        rels.extend(self._rels_by_to.get(entity_id, []))

        if relationship_types:
            rels = [r for r in rels if r.relationship_type in relationship_types]

        # Collect neighbor entity IDs
        neighbor_ids: set[str] = set()
        for r in rels:
            if r.from_entity_id != entity_id:
                neighbor_ids.add(r.from_entity_id)
            if r.to_entity_id != entity_id:
                neighbor_ids.add(r.to_entity_id)

        neighbors = [self._entity_by_id[eid] for eid in neighbor_ids if eid in self._entity_by_id]

        return IntegrationResult(
            entities=neighbors[:limit],
            relationships=rels[:limit],
            coverage=self._make_coverage(time_range),
            limitations=self._make_limitations(),
        )

    async def describe_coverage(
        self,
        time_range: TimeRange,
        sources: Optional[list[str]] = None,
        scopes: Optional[dict] = None,
    ) -> IntegrationResult:
        return IntegrationResult(
            coverage=self._make_coverage(time_range),
            limitations=self._make_limitations(),
        )


# -- Parsing helpers --


def _parse_ref(d: dict) -> Ref:
    return Ref(
        ref_type=d["ref_type"],
        system=d["system"],
        value=d["value"],
        url=d.get("url"),
        observed_at=d.get("observed_at"),
    )


def _parse_entity(d: dict) -> Entity:
    return Entity(
        id=d["id"],
        tlp=d["tlp"],
        entity_type=d["entity_type"],
        kind=d["kind"],
        display_name=d["display_name"],
        refs=[_parse_ref(r) for r in d.get("refs", [])],
        attributes=d.get("attributes"),
        first_seen=d.get("first_seen"),
        last_seen=d.get("last_seen"),
        confidence=d.get("confidence"),
    )


def _parse_event(d: dict) -> ActionEvent:
    return ActionEvent(
        id=d["id"],
        tlp=d["tlp"],
        domain=d["domain"],
        ts=d["ts"],
        action=d["action"],
        actor=Actor(actor_entity_id=d["actor"]["actor_entity_id"]),
        targets=[
            Target(
                target_entity_id=t["target_entity_id"],
                role=t.get("role"),
            )
            for t in d.get("targets", [])
        ],
        outcome=d.get("outcome", "unknown"),
        raw_refs=[_parse_ref(r) for r in d.get("raw_refs", [])],
        context=d.get("context"),
        related_entity_ids=d.get("related_entity_ids"),
        ingested_at=d.get("ingested_at"),
    )


def _parse_relationship(d: dict) -> Relationship:
    return Relationship(
        id=d["id"],
        tlp=d["tlp"],
        domain=d["domain"],
        relationship_type=d["relationship_type"],
        from_entity_id=d["from_entity_id"],
        to_entity_id=d["to_entity_id"],
        first_seen=d.get("first_seen"),
        last_seen=d.get("last_seen"),
        evidence_refs=[_parse_ref(r) for r in d.get("evidence_refs", [])] if d.get("evidence_refs") else None,
    )


def _filter_by_actions(events: list[ActionEvent], actions: list[str]) -> list[ActionEvent]:
    """Filter events by action list, supporting prefix matching with '*'."""
    exact = set()
    prefixes = []
    for a in actions:
        if a.endswith("*"):
            prefixes.append(a[:-1])
        else:
            exact.add(a)

    result = []
    for e in events:
        if e.action in exact:
            result.append(e)
        elif any(e.action.startswith(p) for p in prefixes):
            result.append(e)
    return result
