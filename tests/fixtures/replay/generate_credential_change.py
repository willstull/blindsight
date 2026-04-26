#!/usr/bin/env python3
"""Generate credential change replay scenario fixtures.

Produces baseline + 3 degraded variants. Commit the generated output as static
fixtures. This script is a dev tool, not production code.

Usage:
    python tests/fixtures/replay/generate_credential_change.py
"""
import json
import os
from pathlib import Path

import yaml
import blindsight

SCENARIOS_DIR = Path(blindsight.__file__).parent / "scenarios"

# ---------- shared entity / relationship definitions ----------

ENTITIES_BASELINE = [
    {
        "id": "principal_alice",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "alice@example.com",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_alice"}],
        "attributes": {"email": "alice@example.com"},
        "first_seen": "2026-01-01T08:00:00Z",
        "last_seen": "2026-01-31T17:00:00Z",
    },
    {
        "id": "credential_alice_pw",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "password",
        "display_name": "alice password",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_alice"}],
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-15T10:30:00Z",
    },
    {
        "id": "credential_alice_mfa",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "mfa_totp",
        "display_name": "alice TOTP factor",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_mfa_alice"}],
        "first_seen": "2026-01-16T14:00:00Z",
        "last_seen": "2026-01-16T14:00:00Z",
    },
    # sessions
    *[
        {
            "id": f"session_{i:02d}",
            "tlp": "GREEN",
            "entity_type": "session",
            "kind": "web_session",
            "display_name": f"alice session {i:02d}",
            "refs": [{"ref_type": "session_id", "system": "okta", "value": f"sess_{i:02d}"}],
        }
        for i in range(1, 6)
    ],
    # devices
    {
        "id": "device_01",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "browser",
        "display_name": "Chrome on macOS",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_chrome_mac"}],
    },
    {
        "id": "device_02",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "mobile",
        "display_name": "iPhone 15",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_iphone15"}],
    },
]

RELATIONSHIPS_BASELINE = [
    # 5x authenticated_as  (session -> principal)
    *[
        {
            "id": f"rel_{i:02d}",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "authenticated_as",
            "from_entity_id": f"session_{i:02d}",
            "to_entity_id": "principal_alice",
            "first_seen": f"2026-01-{(i*6):02d}T09:00:00Z",
        }
        for i in range(1, 6)
    ],
    # 2x has_credential  (principal -> credential)
    {
        "id": "rel_06",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_alice",
        "to_entity_id": "credential_alice_pw",
        "first_seen": "2026-01-01T00:00:00Z",
    },
    {
        "id": "rel_07",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_alice",
        "to_entity_id": "credential_alice_mfa",
        "first_seen": "2026-01-16T14:00:00Z",
    },
    # 1x uses_device (session -> device)
    {
        "id": "rel_08",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_01",
        "to_entity_id": "device_01",
        "first_seen": "2026-01-06T09:00:00Z",
    },
]


def _make_login_event(idx: int, day: int, hour: int, session_idx: int) -> dict:
    """Generate a single auth.login event."""
    return {
        "id": f"evt_{idx:03d}",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": f"2026-01-{day:02d}T{hour:02d}:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_alice"},
        "targets": [{"target_entity_id": f"session_{(session_idx % 5) + 1:02d}"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "session_id": f"sess_{(session_idx % 5) + 1:02d}",
            "auth_method": "password",
            "login_type": "interactive",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_{idx:03d}"}
        ],
    }


def _generate_login_events() -> list[dict]:
    """Generate 50 auth.login events spread across January 2026."""
    events = []
    idx = 1
    # 2 logins per day for days 1-31, skip some weekends
    skip_days = {5, 12, 19, 26}  # four Sundays
    for day in range(1, 32):
        if day in skip_days:
            continue
        events.append(_make_login_event(idx, day, 9, idx))
        idx += 1
        events.append(_make_login_event(idx, day, 14, idx))
        idx += 1
        if len(events) >= 50:
            break
    return events[:50]


def _generate_baseline_events() -> list[dict]:
    """Generate all 52 baseline events."""
    logins = _generate_login_events()
    next_idx = len(logins) + 1

    credential_reset = {
        "id": f"evt_{next_idx:03d}",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-01-15T10:30:00Z",
        "action": "credential.reset",
        "actor": {"actor_entity_id": "principal_alice"},
        "targets": [{"target_entity_id": "credential_alice_pw", "role": "primary"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "session_id": "sess_03",
            "credential_type": "password",
            "change": "reset",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_{next_idx:03d}"}
        ],
    }

    credential_enroll = {
        "id": f"evt_{next_idx + 1:03d}",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-01-16T14:00:00Z",
        "action": "credential.enroll",
        "actor": {"actor_entity_id": "principal_alice"},
        "targets": [{"target_entity_id": "credential_alice_mfa", "role": "primary"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "session_id": "sess_03",
            "credential_type": "mfa_totp",
            "change": "enroll",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_{next_idx + 1:03d}"}
        ],
    }

    all_events = logins + [credential_reset, credential_enroll]
    # Sort by timestamp
    all_events.sort(key=lambda e: e["ts"])
    return all_events


def _write_ndjson(filepath: Path, records: list[dict]) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w") as f:
        for record in records:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")


def _write_yaml(filepath: Path, data: dict) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _write_json(filepath: Path, data: dict) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# ---------- baseline ----------


def generate_baseline():
    scenario_dir = SCENARIOS_DIR / "credential_change_baseline"
    domain_dir = scenario_dir / "domains" / "identity"

    events = _generate_baseline_events()

    # find the credential event IDs
    cred_events = [e for e in events if e["action"].startswith("credential.")]
    cred_event_ids = [e["id"] for e in cred_events]

    # entities referenced by credential events (actor + targets)
    cred_entity_ids = set()
    for e in cred_events:
        cred_entity_ids.add(e["actor"]["actor_entity_id"])
        for t in e["targets"]:
            cred_entity_ids.add(t["target_entity_id"])

    manifest = {
        "scenario_name": "credential_change_baseline",
        "version": "1.0",
        "description": "Baseline scenario: credential change with complete telemetry",
        "investigation_question": "Did principal alice@example.com change credentials in January 2026?",
        "time_range": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "baseline",
        "tags": ["credential_change", "identity_domain", "complete_coverage"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "complete",
        "sources": [
            {
                "source_name": "okta",
                "status": "complete",
            }
        ],
        "notes": "Baseline scenario with complete telemetry from all sources",
    }

    # get_neighbors: principal_alice has rels to 5 sessions + 2 credentials + uses_device goes from session_01
    # Bidirectional: from principal_alice (2 has_credential) + to principal_alice (5 authenticated_as)
    # That's 7 relationships, 7 neighbor entities (5 sessions + 2 credentials)
    neighbor_entity_ids = [f"session_{i:02d}" for i in range(1, 6)] + [
        "credential_alice_pw",
        "credential_alice_mfa",
    ]

    expected_tool_output = {
        "scenario_name": "credential_change_baseline",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                    "actions": ["credential.reset", "credential.enroll"],
                },
                "expected": {
                    "status": "success",
                    "event_count": 2,
                    "event_ids": sorted(cred_event_ids),
                    "entity_count": len(cred_entity_ids),
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_entity",
                "args": {"entity_id": "principal_alice"},
                "expected": {
                    "status": "success",
                    "entity_count": 1,
                    "entity_ids": ["principal_alice"],
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_neighbors",
                "args": {"entity_id": "principal_alice"},
                "expected": {
                    "status": "success",
                    "entity_count": 7,
                    "relationship_count": 7,
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                },
                "expected": {
                    "status": "success",
                    "coverage_overall_status": "complete",
                    "source_count": 1,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(domain_dir / "entities.ndjson", ENTITIES_BASELINE)
    _write_ndjson(domain_dir / "events.ndjson", events)
    _write_ndjson(domain_dir / "relationships.ndjson", RELATIONSHIPS_BASELINE)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Baseline: {len(ENTITIES_BASELINE)} entities, {len(events)} events, {len(RELATIONSHIPS_BASELINE)} relationships")
    return events  # needed for degraded variants


# ---------- degraded 1a: retention gap ----------


def generate_degraded_retention_gap(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "credential_change_degraded_retention_gap"
    domain_dir = scenario_dir / "domains" / "identity"

    # Remove auth.login events from Jan 10-20
    events = []
    for e in baseline_events:
        if e["action"] == "auth.login":
            day = int(e["ts"][8:10])
            if 10 <= day <= 20:
                continue
        events.append(e)

    # Credential events should still be present
    cred_events = [e for e in events if e["action"].startswith("credential.")]
    assert len(cred_events) == 2, f"Expected 2 credential events, got {len(cred_events)}"

    manifest = {
        "scenario_name": "credential_change_degraded_retention_gap",
        "version": "1.0",
        "description": "Degraded: auth event retention gap Jan 10-20, credential audit complete",
        "investigation_question": "Did principal alice@example.com change credentials in January 2026?",
        "time_range": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_retention_gap",
        "tags": ["credential_change", "identity_domain", "retention_gap"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "auth_stream",
                "status": "partial",
                "quality_flags": ["retention_gap"],
                "notes": "Auth event logs unavailable 2026-01-10 to 2026-01-20",
            },
            {
                "source_name": "credential_audit_stream",
                "status": "complete",
                "notes": "Credential change events from dedicated audit log",
            },
        ],
        "notes": "Auth event stream has 10-day retention gap; credential audit stream is complete",
    }

    cred_event_ids = sorted([e["id"] for e in cred_events])
    cred_entity_ids = set()
    for e in cred_events:
        cred_entity_ids.add(e["actor"]["actor_entity_id"])
        for t in e["targets"]:
            cred_entity_ids.add(t["target_entity_id"])

    expected_tool_output = {
        "scenario_name": "credential_change_degraded_retention_gap",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                    "actions": ["credential.reset", "credential.enroll"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 2,
                    "event_ids": cred_event_ids,
                    "entity_count": len(cred_entity_ids),
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                },
                "expected": {
                    "status": "partial",
                    "coverage_overall_status": "partial",
                    "source_count": 2,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(domain_dir / "entities.ndjson", ENTITIES_BASELINE)
    _write_ndjson(domain_dir / "events.ndjson", events)
    _write_ndjson(domain_dir / "relationships.ndjson", RELATIONSHIPS_BASELINE)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded retention gap: {len(ENTITIES_BASELINE)} entities, {len(events)} events")


# ---------- degraded 1b: missing fields ----------


def generate_degraded_missing_fields(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "credential_change_degraded_missing_fields"
    domain_dir = scenario_dir / "domains" / "identity"

    # Remove source_ip and user_agent from all event context objects
    events = []
    for e in baseline_events:
        e_copy = json.loads(json.dumps(e))
        if e_copy.get("context"):
            e_copy["context"].pop("source_ip", None)
            e_copy["context"].pop("user_agent", None)
        events.append(e_copy)

    cred_events = [e for e in events if e["action"].startswith("credential.")]
    cred_event_ids = sorted([e["id"] for e in cred_events])

    manifest = {
        "scenario_name": "credential_change_degraded_missing_fields",
        "version": "1.0",
        "description": "Degraded: source_ip and user_agent fields missing from all events",
        "investigation_question": "Did principal alice@example.com change credentials in January 2026?",
        "time_range": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_missing_fields",
        "tags": ["credential_change", "identity_domain", "missing_fields"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "missing_fields": ["source_ip", "user_agent"],
            }
        ],
        "missing_fields": ["source_ip", "user_agent"],
        "notes": "Okta logs available but missing network context fields",
    }

    expected_tool_output = {
        "scenario_name": "credential_change_degraded_missing_fields",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                    "actions": ["credential.reset", "credential.enroll"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 2,
                    "event_ids": cred_event_ids,
                    "coverage_overall_status": "partial",
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(domain_dir / "entities.ndjson", ENTITIES_BASELINE)
    _write_ndjson(domain_dir / "events.ndjson", events)
    _write_ndjson(domain_dir / "relationships.ndjson", RELATIONSHIPS_BASELINE)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded missing fields: {len(ENTITIES_BASELINE)} entities, {len(events)} events")


# ---------- degraded 1c: missing MFA ----------


def generate_degraded_missing_mfa(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "credential_change_degraded_missing_mfa"
    domain_dir = scenario_dir / "domains" / "identity"

    # Remove credential.enroll event
    events = [e for e in baseline_events if e["action"] != "credential.enroll"]

    # Remove credential_alice_mfa entity
    entities = [e for e in ENTITIES_BASELINE if e["id"] != "credential_alice_mfa"]

    # Remove has_credential for MFA
    relationships = [r for r in RELATIONSHIPS_BASELINE if r["to_entity_id"] != "credential_alice_mfa"]

    cred_events = [e for e in events if e["action"].startswith("credential.")]
    cred_event_ids = sorted([e["id"] for e in cred_events])

    manifest = {
        "scenario_name": "credential_change_degraded_missing_mfa",
        "version": "1.0",
        "description": "Degraded: MFA provider logs unavailable, only password credential events visible",
        "investigation_question": "Did principal alice@example.com change credentials in January 2026?",
        "time_range": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_missing_mfa",
        "tags": ["credential_change", "identity_domain", "missing_source"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "complete",
            },
            {
                "source_name": "mfa_provider",
                "status": "missing",
                "notes": "MFA provider logs unavailable",
            },
        ],
        "notes": "MFA provider logs unavailable; only password credential events visible",
    }

    expected_tool_output = {
        "scenario_name": "credential_change_degraded_missing_mfa",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                    "actions": ["credential.reset", "credential.enroll"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 1,
                    "event_ids": cred_event_ids,
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-01-01T00:00:00Z",
                    "time_range_end": "2026-01-31T23:59:59Z",
                },
                "expected": {
                    "status": "partial",
                    "coverage_overall_status": "partial",
                    "source_count": 2,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(domain_dir / "entities.ndjson", entities)
    _write_ndjson(domain_dir / "events.ndjson", events)
    _write_ndjson(domain_dir / "relationships.ndjson", relationships)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded missing MFA: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")


# ---------- main ----------


if __name__ == "__main__":
    baseline_events = generate_baseline()
    generate_degraded_retention_gap(baseline_events)
    generate_degraded_missing_fields(baseline_events)
    generate_degraded_missing_mfa(baseline_events)
    print("Done.")
