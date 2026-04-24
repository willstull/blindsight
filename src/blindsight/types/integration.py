"""Domain integration abstract base class.

All domain integrations implement this interface.
Metadata methods return dict. Evidence methods return IntegrationResult.
"""
from abc import ABC, abstractmethod
from typing import Optional

from blindsight.types.core import TimeRange
from blindsight.types.envelope import IntegrationResult


class DomainIntegration(ABC):
    """Abstract base class for all domain integrations."""

    # -- Metadata methods (return dict) --

    @abstractmethod
    async def describe_domain(self) -> dict:
        """Return domain capabilities and current coverage status."""

    @abstractmethod
    async def describe_types(self) -> dict:
        """Return type schema for filtering/searching."""

    # -- Evidence methods (return IntegrationResult) --

    @abstractmethod
    async def get_entity(self, entity_id: str) -> IntegrationResult:
        """Fetch a single entity by normalized ID."""

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_types: Optional[list[str]] = None,
        kinds: Optional[list[str]] = None,
        limit: int = 100,
        page_token: Optional[str] = None,
    ) -> IntegrationResult:
        """Search entities by free-text query and filters."""

    @abstractmethod
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
        """Search normalized events with time bounds and filters."""

    @abstractmethod
    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[list[str]] = None,
        time_range: Optional[TimeRange] = None,
        depth: int = 1,
        limit: int = 2000,
        page_token: Optional[str] = None,
    ) -> IntegrationResult:
        """Traverse relationships from an entity."""

    @abstractmethod
    async def describe_coverage(
        self,
        time_range: TimeRange,
        sources: Optional[list[str]] = None,
        scopes: Optional[dict] = None,
    ) -> IntegrationResult:
        """Return coverage status and gaps for time range."""
