"""Shared replay-backed domain integration.

Reads NDJSON fixture files and serves them through the DomainIntegration
interface. Builds in-memory indexes for efficient lookups. Domain-specific
subclasses (identity, app) inherit this and add convenience methods.
"""
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from blindsight.utils.coverage import (
    build_coverage_report,
    build_limitations,
)
from blindsight.types.core import (
    ActionEvent,
    CoverageReport,
    Entity,
    Relationship,
    TimeRange,
)
from blindsight.types.envelope import IntegrationResult
from blindsight.types.integration import DomainIntegration
from blindsight.utils.serialization import load_ndjson, load_yaml
from blindsight.utils.time import is_within_range


class ReplayDomainIntegration(DomainIntegration):
    """Generic replay integration that serves normalized records from NDJSON fixtures.

    Subclasses pass domain_name and domain_dir_name to the constructor.
    All 7 core contract methods are implemented here.
    """

    def __init__(
        self,
        scenario_path: Path,
        domain_name: str,
        domain_dir_name: str,
        logger: logging.Logger,
    ) -> None:
        self._logger = logger
        self._scenario_path = scenario_path
        self._domain_name = domain_name
        self._domain_dir = scenario_path / "domains" / domain_dir_name

        # Load data eagerly
        raw_entities = load_ndjson(self._domain_dir / "entities.ndjson")
        raw_events = load_ndjson(self._domain_dir / "events.ndjson")
        raw_rels = load_ndjson(self._domain_dir / "relationships.ndjson")
        self._coverage_data = load_yaml(self._domain_dir / "coverage.yaml")

        # Parse into typed objects
        self._entities = [Entity.model_validate(r) for r in raw_entities]
        self._events = [ActionEvent.model_validate(r) for r in raw_events]
        self._relationships = [Relationship.model_validate(r) for r in raw_rels]

        # Build indexes
        self._entity_by_id: dict[str, Entity] = {e.id: e for e in self._entities}
        self._rels_by_from: dict[str, list[Relationship]] = defaultdict(list)
        self._rels_by_to: dict[str, list[Relationship]] = defaultdict(list)
        for rel in self._relationships:
            self._rels_by_from[rel.from_entity_id].append(rel)
            self._rels_by_to[rel.to_entity_id].append(rel)

        self._logger.info(
            f"Replay{domain_name.title()}Integration loaded",
            extra={
                "domain": domain_name,
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
            self._logger, self._domain_name, time_range, self._coverage_data
        )

    def _make_limitations(self) -> list[str]:
        return build_limitations(self._coverage_data)

    # -- Metadata methods --

    async def describe_domain(self) -> dict:
        entity_types = sorted({e.entity_type for e in self._entities})
        action_prefixes = sorted({a.split(".")[0] + "." for a in {e.action for e in self._events}})
        return {
            "domain": self._domain_name,
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
            "domain": self._domain_name,
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
        # Bidirectional traversal at depth 1
        rels: list[Relationship] = []
        rels.extend(self._rels_by_from.get(entity_id, []))
        rels.extend(self._rels_by_to.get(entity_id, []))

        if relationship_types:
            rels = [r for r in rels if r.relationship_type in relationship_types]

        if time_range:
            rels = [r for r in rels if self._rel_overlaps_range(r, time_range)]

        # Collect neighbor entity IDs from depth-1
        neighbor_ids: set[str] = set()
        for r in rels:
            if r.from_entity_id != entity_id:
                neighbor_ids.add(r.from_entity_id)
            if r.to_entity_id != entity_id:
                neighbor_ids.add(r.to_entity_id)

        # Depth-2: traverse one more hop from each depth-1 neighbor
        if depth >= 2:
            depth1_ids = set(neighbor_ids)
            for nid in depth1_ids:
                hop2_rels: list[Relationship] = []
                hop2_rels.extend(self._rels_by_from.get(nid, []))
                hop2_rels.extend(self._rels_by_to.get(nid, []))
                if relationship_types:
                    hop2_rels = [r for r in hop2_rels if r.relationship_type in relationship_types]
                if time_range:
                    hop2_rels = [r for r in hop2_rels if self._rel_overlaps_range(r, time_range)]
                for r in hop2_rels:
                    if r not in rels:
                        rels.append(r)
                    if r.from_entity_id != nid:
                        neighbor_ids.add(r.from_entity_id)
                    if r.to_entity_id != nid:
                        neighbor_ids.add(r.to_entity_id)
            neighbor_ids.discard(entity_id)

        neighbors = [self._entity_by_id[eid] for eid in neighbor_ids if eid in self._entity_by_id]

        return IntegrationResult(
            entities=neighbors[:limit],
            relationships=rels[:limit],
            coverage=self._make_coverage(time_range),
            limitations=self._make_limitations(),
        )

    @staticmethod
    def _rel_overlaps_range(rel: Relationship, time_range: TimeRange) -> bool:
        """Check if a relationship's time bounds overlap the given range."""
        if not rel.first_seen and not rel.last_seen:
            return True
        if rel.first_seen and rel.last_seen:
            return not (rel.last_seen < time_range.start or rel.first_seen > time_range.end)
        ts = rel.first_seen or rel.last_seen
        return time_range.start <= ts <= time_range.end

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
