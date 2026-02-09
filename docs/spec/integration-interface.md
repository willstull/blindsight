# Integration Interface

> Generic boundary for domain integrations (live or replay)

## Purpose

Define a stable integration interface that:
- Works with both **replay datasets** and **live telemetry sources**
- Keeps live integration choice **TBD** without blocking progress
- Enforces consistent tool contracts across all domains
- Enables deterministic testing with mocked/replay integrations

---

## Three-Layer Model

An integration is the domain's source-specific translator that fetches records and emits normalized entities/events/relationships with source references. The MCP server exposes the stable tool interface that calls the integration.

### Layer 1: Source System

The telemetry source that holds raw data:
- **Identity providers**: Okta, Entra ID (Azure AD), Auth0
- **Cloud audit logs**: AWS CloudTrail, Azure Activity Log, GCP Cloud Audit Logs
- **Application logs**: Splunk, Elasticsearch, custom SIEM
- **File exports**: NDJSON fixtures, CSV files, PCAP captures

### Layer 2: Integration

Source-specific translator that does two jobs:

1. **Query**: Fetch records from the source system
   - Live: Call REST API, run Splunk SPL, query database
   - Replay: Read fixture files from disk

2. **Normalize**: Map source data to normalized records
   - Translate vendor schema to Entity/ActionEvent/Relationship
   - Generate normalized IDs
   - Attach raw_refs for source references
   - Build coverage reports

Examples:
- `ReplayIdentityIntegration`: Reads NDJSON fixtures, outputs normalized records
- `OktaIntegration`: Calls Okta System Log API, normalizes to normalized records
- `EntraIntegration`: Calls Microsoft Graph API, normalizes to normalized records
- `SplunkIntegration`: Runs SPL query, parses results, normalizes to normalized records

### Layer 3: Domain MCP Server

The MCP server wraps the integration and exposes tools to the LLM client:
- Defines tool signatures (search_events, get_entity, get_neighbors, etc.)
- Routes tool calls to integration methods
- Returns response envelope (status, items, coverage_report)
- Manages configuration, logging, error handling

**Key Insight**: Replay integration is just another integration implementation. Same tools, different integration. This enables evaluation without live integrations—swap the integration, not the tool contract.

### Why This Matters

- **Add new vendors**: Write new integration without changing tool contract
- **Test everything with replay**: Use replay integration for deterministic evaluation
- **Avoid vendor lock-in**: Core types and case store never see vendor schemas
- **Defer live integration**: Prove architecture with replay, add live sources later

---

## Integration Interface

All domain integrations (identity, network, resource, etc.) implement this interface:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TimeRange:
    start: str  # RFC3339 timestamp
    end: str

@dataclass
class IntegrationResponse:
    """Standard response from all integration methods"""
    status: str                     # "success" | "partial" | "error"
    items: List[Dict[str, Any]]     # Entities, events, or relationships
    coverage_report: Dict[str, Any] # Coverage metadata (REQUIRED)
    error: Optional[Dict[str, Any]] = None
    limitations: List[str] = None
    next_page_token: Optional[str] = None

class DomainIntegration(ABC):
    """
    Abstract base class for all domain integrations.

    Implementations:
    - ReplayIntegration: Reads from replay datasets
    - LiveIntegration: Queries real telemetry sources
    """

    @abstractmethod
    async def describe_domain(self) -> Dict[str, Any]:
        """
        Return domain capabilities and current coverage status.

        Returns:
            {
                "domain": str,
                "version": str,
                "capabilities": {...},
                "coverage_report": {...}
            }
        """
        pass

    @abstractmethod
    async def describe_types(self) -> Dict[str, Any]:
        """
        Return type schema for filtering/searching.

        Returns:
            {
                "domain": str,
                "coverage_report": {...},
                "types": {
                    "entity_type_enum": [str],
                    "relationship_types": [str],
                    "context_fields": [str]
                }
            }
        """
        pass

    @abstractmethod
    async def get_entity(
        self,
        entity_id: str
    ) -> IntegrationResponse:
        """
        Fetch a single entity by normalized ID.

        Args:
            entity_id: Normalized entity ID within case

        Returns:
            IntegrationResponse with items=[Entity] or error
        """
        pass

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        kinds: Optional[List[str]] = None,
        limit: int = 100,
        page_token: Optional[str] = None
    ) -> IntegrationResponse:
        """
        Search entities by free-text query and filters.

        Args:
            query: Free-text search string
            entity_types: Filter by entity_type (e.g., ["principal", "credential"])
            kinds: Filter by kind (domain-specific subtypes)
            limit: Max results per page (1-500)
            page_token: Continuation token from previous page

        Returns:
            IntegrationResponse with items=[Entity, ...]
        """
        pass

    @abstractmethod
    async def search_events(
        self,
        time_range: TimeRange,
        actions: Optional[List[str]] = None,
        actor_entity_ids: Optional[List[str]] = None,
        target_entity_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 2000,
        page_token: Optional[str] = None
    ) -> IntegrationResponse:
        """
        Search normalized events with time bounds and filters.

        Args:
            time_range: Required time bounds
            actions: Filter by action taxonomy (e.g., ["auth.login.*"])
            actor_entity_ids: Filter by actor
            target_entity_ids: Filter by target
            filters: Additional filters (context fields, outcome, etc.)
            limit: Max results per page (1-2000)
            page_token: Continuation token

        Returns:
            IntegrationResponse with items=[ActionEvent, ...] + entities
        """
        pass

    @abstractmethod
    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: Optional[List[str]] = None,
        time_range: Optional[TimeRange] = None,
        depth: int = 1,
        limit: int = 2000,
        page_token: Optional[str] = None
    ) -> IntegrationResponse:
        """
        Traverse relationships from an entity.

        Args:
            entity_id: Starting entity
            relationship_types: Filter edges (e.g., ["has_credential"])
            time_range: Time bounds for relationships
            depth: Traversal depth (1-2)
            limit: Max results per page
            page_token: Continuation token

        Returns:
            IntegrationResponse with entities=[...], relationships=[...]
        """
        pass

    @abstractmethod
    async def describe_coverage(
        self,
        time_range: TimeRange,
        sources: Optional[List[str]] = None,
        scopes: Optional[Dict[str, Any]] = None
    ) -> IntegrationResponse:
        """
        Return coverage status and gaps for time range.

        Args:
            time_range: Time window to check
            sources: Filter by source names
            scopes: Optional scope filters (e.g., principal_entity_id)

        Returns:
            IntegrationResponse with coverage_report as main payload
        """
        pass
```

---

## Implementation: Replay Integration

```python
import json
from pathlib import Path

class ReplayIdentityIntegration(DomainIntegration):
    """Replay integration: reads from NDJSON fixture files"""

    def __init__(self, data_dir: str):
        """
        Initialize with replay dataset directory.

        Args:
            data_dir: Path to scenario data (e.g., "scenarios/cred_change/domains/identity")
        """
        self.data_dir = Path(data_dir)
        self.entities = self._load_ndjson("entities.ndjson")
        self.events = self._load_ndjson("events.ndjson")
        self.relationships = self._load_ndjson("relationships.ndjson")
        self.coverage = self._load_yaml("coverage.yaml")

    def _load_ndjson(self, filename: str) -> List[Dict]:
        """Load newline-delimited JSON file"""
        path = self.data_dir / filename
        if not path.exists():
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def _load_yaml(self, filename: str) -> Dict:
        """Load YAML file"""
        import yaml
        with open(self.data_dir / filename) as f:
            return yaml.safe_load(f)

    async def describe_domain(self) -> Dict[str, Any]:
        """Return identity domain capabilities from replay metadata"""
        return {
            "domain": "identity",
            "version": "0.1.0",
            "capabilities": {
                "supported_entity_types": ["principal", "credential", "session"],
                "supported_actions_prefixes": ["auth.", "credential."],
                "supports_neighbors": True,
                "supports_coverage": True
            },
            "coverage_report": self._build_coverage_report(None)
        }

    async def search_events(
        self,
        time_range: TimeRange,
        actions: Optional[List[str]] = None,
        **kwargs
    ) -> IntegrationResponse:
        """Search events in replay dataset"""
        from datetime import datetime

        start = datetime.fromisoformat(time_range.start.replace('Z', '+00:00'))
        end = datetime.fromisoformat(time_range.end.replace('Z', '+00:00'))

        # Filter by time range
        filtered = [
            e for e in self.events
            if start <= datetime.fromisoformat(e["ts"].replace('Z', '+00:00')) <= end
        ]

        # Filter by actions
        if actions:
            filtered = [e for e in filtered if e["action"] in actions]

        # Apply limit
        limit = kwargs.get("limit", 2000)
        filtered = filtered[:limit]

        # Build response
        status = "success" if self.coverage["overall_status"] == "complete" else "partial"
        coverage_report = self._build_coverage_report(time_range)

        return IntegrationResponse(
            status=status,
            items=filtered,
            coverage_report=coverage_report,
            limitations=self._build_limitations()
        )

    def _build_coverage_report(self, time_range: Optional[TimeRange]) -> Dict:
        """Build coverage report from replay metadata"""
        from ulid import ULID

        return {
            "id": str(ULID()),
            "tlp": "GREEN",
            "domain": "identity",
            "time_range": {
                "start": time_range.start if time_range else "2026-01-01T00:00:00Z",
                "end": time_range.end if time_range else "2026-01-31T23:59:59Z"
            },
            "overall_status": self.coverage["overall_status"],
            "sources": self.coverage["sources"],
            "notes": self.coverage.get("notes", "")
        }

    def _build_limitations(self) -> List[str]:
        """Build human-readable limitations from coverage"""
        limitations = []
        for source in self.coverage["sources"]:
            if source["status"] == "missing":
                limitations.append(f"{source['source_name']} unavailable")
            elif source["status"] == "partial":
                limitations.append(f"{source['source_name']} incomplete")
        return limitations

    # Implement other methods similarly...
```

---

## Implementation: Live Integration (Stub)

```python
class LiveIdentityIntegration(DomainIntegration):
    """
    Live integration: queries real telemetry sources.

    STUB: Interface defined, implementation TBD.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with live source configuration.

        Args:
            config: Source config (API endpoint, credentials, etc.)
        """
        self.config = config
        # TBD: Initialize API clients, connections, etc.

    async def search_events(
        self,
        time_range: TimeRange,
        **kwargs
    ) -> IntegrationResponse:
        """
        Query live telemetry source.

        Implementation TBD: Choose source (Okta, AWS CloudTrail, etc.)
        """
        # Pseudocode:
        # 1. Translate request to source API call
        # 2. Execute query (read-only)
        # 3. Normalize results to normalized ActionEvent schema
        # 4. Generate coverage report based on API response metadata
        # 5. Return IntegrationResponse

        raise NotImplementedError("Live integration: source integration TBD")
```

---

## Integration Factory Pattern

```python
from enum import Enum

class IntegrationMode(Enum):
    REPLAY = "replay"
    LIVE = "live"

def create_identity_integration(
    mode: IntegrationMode,
    config: Dict[str, Any]
) -> DomainIntegration:
    """
    Factory: Create identity domain integration (replay or live).

    Args:
        mode: REPLAY or LIVE
        config: Mode-specific configuration
            - REPLAY: {"data_dir": "path/to/scenario/domains/identity"}
            - LIVE: {"source": "okta", "api_key": "...", ...}

    Returns:
        DomainIntegration instance
    """
    if mode == IntegrationMode.REPLAY:
        return ReplayIdentityIntegration(data_dir=config["data_dir"])
    elif mode == IntegrationMode.LIVE:
        return LiveIdentityIntegration(config=config)
    else:
        raise ValueError(f"Unknown integration mode: {mode}")
```

**Usage**:
```python
# Testing: Use replay integration
integration = create_identity_integration(
    mode=IntegrationMode.REPLAY,
    config={"data_dir": "tests/fixtures/replay/scenarios/cred_change/domains/identity"}
)

# Production: Use live integration (TBD)
integration = create_identity_integration(
    mode=IntegrationMode.LIVE,
    config={"source": "okta", "api_key": os.getenv("OKTA_API_KEY"), ...}
)
```

---

## Integration Contract Validation

```python
import pytest

async def validate_integration_contract(integration: DomainIntegration):
    """
    Test suite: Verify integration implements interface correctly.

    Use this to validate both replay and live integrations.
    """

    # 1. describe_domain returns required fields
    domain_info = await integration.describe_domain()
    assert "domain" in domain_info
    assert "version" in domain_info
    assert "capabilities" in domain_info
    assert "coverage_report" in domain_info

    # 2. search_events requires time_range
    with pytest.raises(TypeError):
        await integration.search_events()  # Missing required arg

    # 3. search_events returns IntegrationResponse
    response = await integration.search_events(
        time_range=TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")
    )
    assert isinstance(response, IntegrationResponse)
    assert response.coverage_report is not None

    # 4. Coverage report has required fields
    cov = response.coverage_report
    assert "overall_status" in cov
    assert "sources" in cov
    assert cov["overall_status"] in ["complete", "partial", "missing", "unknown"]

    # ... more validation ...
```

---

## Benefits of This Interface

### 1. Progress Without Live Integration
- Implement replay integration → measurable progress
- Write tests against replay integration → evaluation harness complete
- Live integration becomes "swap integration" later

### 2. Deterministic Testing
- Replay integration produces same outputs every time
- Golden output comparison works reliably
- No flaky tests from live source changes

### 3. Easy Mocking
```python
class MockIdentityIntegration(DomainIntegration):
    """Minimal mock for unit tests"""

    async def search_events(self, time_range, **kwargs):
        return IntegrationResponse(
            status="success",
            items=[],  # Empty result
            coverage_report={"overall_status": "complete", "sources": []}
        )

    # Implement other methods as no-ops...
```

### 4. Swappable Implementations
```python
# Test mode
integration = ReplayIdentityIntegration(data_dir="tests/fixtures/...")

# Production mode (future)
integration = LiveOktaIntegration(config=okta_config)

# Interface is identical
events = await integration.search_events(time_range=...)
```

---

## Integration Configuration

```yaml
# config/domains.yaml
domains:
  identity:
    mode: replay  # or "live"
    replay:
      data_dir: "tests/fixtures/replay/scenarios/baseline/domains/identity"
    live:
      source: okta
      api_endpoint: "https://dev-12345.okta.com"
      api_key: "env://OKTA_API_KEY"
      timeout_ms: 30000
      max_rows: 2000
```

```python
# Load integration from config
def load_domain_integration(domain_name: str, config: Dict) -> DomainIntegration:
    """Load domain integration from configuration"""
    domain_config = config["domains"][domain_name]
    mode = IntegrationMode(domain_config["mode"])

    if mode == IntegrationMode.REPLAY:
        return create_identity_integration(
            mode=mode,
            config=domain_config["replay"]
        )
    elif mode == IntegrationMode.LIVE:
        return create_identity_integration(
            mode=mode,
            config=domain_config["live"]
        )
```

---

## Summary: Integration Interface

**Key Principles**:
1. ✅ Generic boundary: Works with replay or live sources
2. ✅ Consistent contract: All domains implement same interface
3. ✅ TBD-friendly: Live integration choice deferred
4. ✅ Testable: Replay integration enables deterministic tests
5. ✅ Swappable: Change mode without changing tool code

**Interface Methods**:
- `describe_domain()` - Capabilities discovery
- `describe_types()` - Type schema
- `get_entity(id)` - Single entity lookup
- `search_entities(query, filters)` - Entity search
- `search_events(time_range, filters)` - Event search
- `get_neighbors(id, depth)` - Relationship traversal
- `describe_coverage(time_range)` - Gap analysis

**Standard Response**:
- `IntegrationResponse` with `status`, `items`, `coverage_report`, `error`, `limitations`

This interface makes **"no live source required"** evaluation feasible while keeping live integration as a clean future addition.
