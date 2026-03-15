#!/usr/bin/env python3
"""Generate password takeover replay scenario fixtures.

Produces baseline + 3 degraded variants modeling a cross-account password
takeover where a compromised account resets a dormant account's credentials
and uses it for lateral movement.

Usage:
    python tests/fixtures/replay/generate_password_takeover.py
"""
import json
from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# ---------- shared entity / relationship definitions ----------

ENTITIES_BASELINE = sorted(
    [
        {
            "id": "credential_cgarcia_pw",
            "tlp": "GREEN",
            "entity_type": "credential",
            "kind": "password",
            "display_name": "cgarcia password",
            "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_cgarcia"}],
        },
        {
            "id": "credential_mgarcia_pw_new",
            "tlp": "GREEN",
            "entity_type": "credential",
            "kind": "password",
            "display_name": "mgarcia password (post-reset)",
            "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_mgarcia_new"}],
            "first_seen": "2026-03-15T02:32:00Z",
        },
        {
            "id": "credential_mgarcia_pw_old",
            "tlp": "GREEN",
            "entity_type": "credential",
            "kind": "password",
            "display_name": "mgarcia password (pre-reset)",
            "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_mgarcia_old"}],
            "last_seen": "2026-03-15T02:32:00Z",
        },
        {
            "id": "device_c01",
            "tlp": "GREEN",
            "entity_type": "device",
            "kind": "browser",
            "display_name": "Chrome on Windows",
            "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_chrome_win"}],
            "attributes": {"description": "legitimate device"},
        },
        {
            "id": "device_c02",
            "tlp": "GREEN",
            "entity_type": "device",
            "kind": "browser",
            "display_name": "Tor Browser on Linux",
            "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_tor_linux"}],
            "attributes": {"description": "adversary device"},
        },
        {
            "id": "network_endpoint_adversary",
            "tlp": "GREEN",
            "entity_type": "network_endpoint",
            "kind": "ip_address",
            "display_name": "Adversary IP 203.0.113.42",
            "refs": [{"ref_type": "ip_address", "system": "network_flow", "value": "203.0.113.42"}],
            "attributes": {"ip": "203.0.113.42", "geo": "RO"},
        },
        {
            "id": "network_endpoint_corporate",
            "tlp": "GREEN",
            "entity_type": "network_endpoint",
            "kind": "ip_address",
            "display_name": "Corporate IP 198.51.100.10",
            "refs": [{"ref_type": "ip_address", "system": "network_flow", "value": "198.51.100.10"}],
            "attributes": {"ip": "198.51.100.10", "geo": "US-CA"},
        },
        {
            "id": "principal_cgarcia",
            "tlp": "GREEN",
            "entity_type": "principal",
            "kind": "user",
            "display_name": "cgarcia@meridian-systems.example",
            "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_cgarcia"}],
            "attributes": {"email": "cgarcia@meridian-systems.example", "status": "compromised active user"},
            "first_seen": "2026-03-01T09:00:00Z",
            "last_seen": "2026-03-16T09:00:00Z",
        },
        {
            "id": "principal_dlopez",
            "tlp": "GREEN",
            "entity_type": "principal",
            "kind": "user",
            "display_name": "dlopez@meridian-systems.example",
            "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_dlopez"}],
            "attributes": {"email": "dlopez@meridian-systems.example", "status": "deleted user"},
            "first_seen": "2026-03-01T08:00:00Z",
            "last_seen": "2026-03-15T02:40:00Z",
        },
        {
            "id": "principal_mgarcia",
            "tlp": "GREEN",
            "entity_type": "principal",
            "kind": "user",
            "display_name": "mgarcia@meridian-systems.example",
            "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_mgarcia"}],
            "attributes": {"email": "mgarcia@meridian-systems.example", "status": "dormant account taken over"},
            "first_seen": "2026-03-15T02:35:00Z",
            "last_seen": "2026-03-16T09:00:00Z",
        },
        {
            "id": "session_c01",
            "tlp": "GREEN",
            "entity_type": "session",
            "kind": "web_session",
            "display_name": "cgarcia session",
            "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_c01"}],
        },
        {
            "id": "session_c02",
            "tlp": "GREEN",
            "entity_type": "session",
            "kind": "web_session",
            "display_name": "mgarcia session",
            "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_c02"}],
        },
    ],
    key=lambda e: e["id"],
)

RELATIONSHIPS_BASELINE = sorted(
    [
        {
            "id": "rel_c01",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "authenticated_as",
            "from_entity_id": "session_c01",
            "to_entity_id": "principal_cgarcia",
            "first_seen": "2026-03-01T09:00:00Z",
        },
        {
            "id": "rel_c02",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "authenticated_as",
            "from_entity_id": "session_c02",
            "to_entity_id": "principal_mgarcia",
            "first_seen": "2026-03-15T02:35:00Z",
        },
        {
            "id": "rel_c03",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "has_credential",
            "from_entity_id": "principal_cgarcia",
            "to_entity_id": "credential_cgarcia_pw",
            "first_seen": "2026-03-01T09:00:00Z",
        },
        {
            "id": "rel_c04",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "has_credential",
            "from_entity_id": "principal_mgarcia",
            "to_entity_id": "credential_mgarcia_pw_old",
            "first_seen": "2026-03-15T02:32:00Z",
        },
        {
            "id": "rel_c05",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "has_credential",
            "from_entity_id": "principal_mgarcia",
            "to_entity_id": "credential_mgarcia_pw_new",
            "first_seen": "2026-03-15T02:32:00Z",
        },
        {
            "id": "rel_c06",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "uses_device",
            "from_entity_id": "session_c01",
            "to_entity_id": "device_c01",
            "first_seen": "2026-03-01T09:00:00Z",
        },
        {
            "id": "rel_c07",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "uses_device",
            "from_entity_id": "session_c02",
            "to_entity_id": "device_c02",
            "first_seen": "2026-03-15T02:35:00Z",
        },
        {
            "id": "rel_c08",
            "tlp": "GREEN",
            "domain": "identity",
            "relationship_type": "deleted_by",
            "from_entity_id": "principal_dlopez",
            "to_entity_id": "principal_mgarcia",
            "first_seen": "2026-03-15T02:40:00Z",
        },
    ],
    key=lambda r: r["id"],
)

# ---------- event generation ----------

# Normal cgarcia logins: Mar 1-10, 09:00 and 17:00, skip weekends (Mar 2 Sun, 8 Sat, 9 Sun)
_NORMAL_LOGIN_DAYS = [1, 3, 4, 5, 6, 7, 10]  # skip 2 (Sun), 8 (Sat), 9 (Sun)


def _generate_normal_logins() -> list[dict]:
    """Generate 8 normal auth.login events for cgarcia (Mar 1-10, two per day where possible)."""
    events = []
    idx = 1
    for day in _NORMAL_LOGIN_DAYS:
        events.append({
            "id": f"evt_c{idx:03d}",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": f"2026-03-{day:02d}T09:00:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_cgarcia"},
            "targets": [{"target_entity_id": "session_c01"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "198.51.100.10",
                "session_id": "sess_c01",
                "device_id": "dev_chrome_win",
                "auth_method": "password",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_c{idx:03d}"}
            ],
        })
        idx += 1
        if idx <= 8:
            events.append({
                "id": f"evt_c{idx:03d}",
                "tlp": "GREEN",
                "domain": "identity",
                "ts": f"2026-03-{day:02d}T17:00:00Z",
                "action": "auth.login",
                "actor": {"actor_entity_id": "principal_cgarcia"},
                "targets": [{"target_entity_id": "session_c01"}],
                "outcome": "succeeded",
                "context": {
                    "source_ip": "198.51.100.10",
                    "session_id": "sess_c01",
                    "device_id": "dev_chrome_win",
                    "auth_method": "password",
                },
                "raw_refs": [
                    {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_c{idx:03d}"}
                ],
            })
            idx += 1
        if idx > 8:
            break
    return events[:8]


def _generate_baseline_events() -> list[dict]:
    """Generate all baseline events (normal logins + attack sequence)."""
    logins = _generate_normal_logins()

    attack_events = [
        # evt_c009: unusual-hour login from adversary IP
        {
            "id": "evt_c009",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T02:30:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_cgarcia"},
            "targets": [{"target_entity_id": "session_c01"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "session_id": "sess_c01",
                "device_id": "dev_tor_linux",
                "auth_method": "password",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c009"}
            ],
        },
        # evt_c010: cross-account password reset
        {
            "id": "evt_c010",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T02:32:00Z",
            "action": "credential.reset",
            "actor": {"actor_entity_id": "principal_cgarcia"},
            "targets": [{"target_entity_id": "credential_mgarcia_pw_old", "role": "primary"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "credential_type": "password",
                "change": "reset",
                "cross_account": True,
                "target_principal": "principal_mgarcia",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c010"}
            ],
        },
        # evt_c011: dormant account login from adversary IP
        {
            "id": "evt_c011",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T02:35:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "session_c02"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "session_id": "sess_c02",
                "device_id": "dev_tor_linux",
                "auth_method": "password",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c011"}
            ],
        },
        # evt_c012: account deletion
        {
            "id": "evt_c012",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T02:40:00Z",
            "action": "auth.account.delete",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "principal_dlopez"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "reason": "cleanup",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c012"}
            ],
        },
        # evt_c013: failed privilege escalation
        {
            "id": "evt_c013",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T02:45:00Z",
            "action": "privilege.grant",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "principal_mgarcia"}],
            "outcome": "failed",
            "context": {
                "source_ip": "203.0.113.42",
                "privilege_type": "role",
                "role": "superadmin",
                "failure_reason": "verification_required",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c013"}
            ],
        },
        # evt_c014: continued adversary login
        {
            "id": "evt_c014",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-15T14:00:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "session_c02"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "session_id": "sess_c02",
                "device_id": "dev_tor_linux",
                "auth_method": "password",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c014"}
            ],
        },
        # evt_c015: continued adversary login
        {
            "id": "evt_c015",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-16T01:00:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "session_c02"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "203.0.113.42",
                "session_id": "sess_c02",
                "device_id": "dev_tor_linux",
                "auth_method": "password",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c015"}
            ],
        },
        # evt_c016: account locked
        {
            "id": "evt_c016",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": "2026-03-16T09:00:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_mgarcia"},
            "targets": [{"target_entity_id": "session_c02"}],
            "outcome": "failed",
            "context": {
                "source_ip": "203.0.113.42",
                "session_id": "sess_c02",
                "device_id": "dev_tor_linux",
                "auth_method": "password",
                "failure_reason": "account_locked",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": "okta_evt_c016"}
            ],
        },
    ]

    all_events = logins + attack_events
    all_events.sort(key=lambda e: e["ts"])
    return all_events


# ---------- helpers ----------


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
    scenario_dir = SCENARIOS_DIR / "password_takeover_baseline"
    domain_dir = scenario_dir / "domains" / "identity"

    events = _generate_baseline_events()

    manifest = {
        "scenario_name": "password_takeover_baseline",
        "version": "1.0",
        "description": "Baseline scenario: cross-account password takeover with complete telemetry",
        "investigation_question": (
            "Was the dormant account mgarcia at Meridian Systems taken over "
            "via cross-account password change from the compromised cgarcia account?"
        ),
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "baseline",
        "tags": ["password_takeover", "identity_domain", "complete_coverage"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "complete",
        "sources": [
            {"source_name": "okta", "status": "complete"},
            {"source_name": "network_flow", "status": "complete"},
        ],
        "notes": "Baseline with complete telemetry from Okta and network flow data",
    }

    # search_events for credential.*, privilege.*, auth.account.*
    search_actions = ["credential.reset", "privilege.grant", "auth.account.delete"]
    matching_events = [e for e in events if any(e["action"].startswith(a.split(".*")[0]) for a in search_actions)]
    matching_event_ids = sorted([e["id"] for e in matching_events])
    matching_entity_ids = set()
    for e in matching_events:
        matching_entity_ids.add(e["actor"]["actor_entity_id"])
        for t in e["targets"]:
            matching_entity_ids.add(t["target_entity_id"])

    # get_neighbors for principal_mgarcia: rels where mgarcia is from or to
    mgarcia_rels = [
        r for r in RELATIONSHIPS_BASELINE
        if r["from_entity_id"] == "principal_mgarcia" or r["to_entity_id"] == "principal_mgarcia"
    ]
    mgarcia_neighbor_ids = set()
    for r in mgarcia_rels:
        if r["from_entity_id"] == "principal_mgarcia":
            mgarcia_neighbor_ids.add(r["to_entity_id"])
        else:
            mgarcia_neighbor_ids.add(r["from_entity_id"])

    expected_tool_output = {
        "scenario_name": "password_takeover_baseline",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["credential.*", "privilege.*", "auth.account.*"],
                },
                "expected": {
                    "status": "success",
                    "event_count": len(matching_events),
                    "event_ids": matching_event_ids,
                    "entity_count": len(matching_entity_ids),
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_entity",
                "args": {"entity_id": "principal_cgarcia"},
                "expected": {
                    "status": "success",
                    "entity_count": 1,
                    "entity_ids": ["principal_cgarcia"],
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_neighbors",
                "args": {"entity_id": "principal_mgarcia"},
                "expected": {
                    "status": "success",
                    "entity_count": len(mgarcia_neighbor_ids),
                    "relationship_count": len(mgarcia_rels),
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                },
                "expected": {
                    "status": "success",
                    "coverage_overall_status": "complete",
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

    print(f"Baseline: {len(ENTITIES_BASELINE)} entities, {len(events)} events, {len(RELATIONSHIPS_BASELINE)} relationships")
    return events


# ---------- degraded: no network context ----------


def generate_degraded_no_network_context(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "password_takeover_degraded_no_network_context"
    domain_dir = scenario_dir / "domains" / "identity"

    # Strip source_ip from context of ALL events
    events = []
    for e in baseline_events:
        e_copy = json.loads(json.dumps(e))
        if e_copy.get("context"):
            e_copy["context"].pop("source_ip", None)
        events.append(e_copy)

    # Remove network_endpoint entities
    entities = sorted(
        [e for e in ENTITIES_BASELINE if not e["id"].startswith("network_endpoint_")],
        key=lambda e: e["id"],
    )

    manifest = {
        "scenario_name": "password_takeover_degraded_no_network_context",
        "version": "1.0",
        "description": "Degraded: network flow data unavailable, IP and geolocation context missing",
        "investigation_question": (
            "Was the dormant account mgarcia at Meridian Systems taken over "
            "via cross-account password change from the compromised cgarcia account?"
        ),
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_no_network_context",
        "tags": ["password_takeover", "identity_domain", "missing_network"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {"source_name": "okta", "status": "complete"},
            {
                "source_name": "network_flow",
                "status": "missing",
                "notes": "Network flow data unavailable",
            },
        ],
        "notes": "Network flow data missing; IP and geolocation context unavailable",
    }

    expected_tool_output = {
        "scenario_name": "password_takeover_degraded_no_network_context",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["credential.*", "privilege.*", "auth.account.*"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 3,
                    "event_ids": sorted(["evt_c010", "evt_c012", "evt_c013"]),
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
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
    _write_ndjson(domain_dir / "relationships.ndjson", RELATIONSHIPS_BASELINE)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded no network context: {len(entities)} entities, {len(events)} events")


# ---------- degraded: no historical baseline ----------


def generate_degraded_no_historical_baseline(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "password_takeover_degraded_no_historical_baseline"
    domain_dir = scenario_dir / "domains" / "identity"

    # Remove all events before Mar 14 (evt_c001 through evt_c008)
    events = [e for e in baseline_events if e["ts"] >= "2026-03-14T00:00:00Z"]

    # Set principal_cgarcia first_seen to null
    entities = []
    for ent in ENTITIES_BASELINE:
        e_copy = json.loads(json.dumps(ent))
        if e_copy["id"] == "principal_cgarcia":
            e_copy["first_seen"] = None
        entities.append(e_copy)
    entities.sort(key=lambda e: e["id"])

    manifest = {
        "scenario_name": "password_takeover_degraded_no_historical_baseline",
        "version": "1.0",
        "description": "Degraded: historical authentication logs prior to 2026-03-14 unavailable",
        "investigation_question": (
            "Was the dormant account mgarcia at Meridian Systems taken over "
            "via cross-account password change from the compromised cgarcia account?"
        ),
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_no_historical_baseline",
        "tags": ["password_takeover", "identity_domain", "retention_gap"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["retention_gap"],
                "notes": "Authentication logs prior to 2026-03-14 unavailable",
            },
            {"source_name": "network_flow", "status": "complete"},
        ],
        "notes": "Historical baseline unavailable due to log retention gap",
    }

    expected_tool_output = {
        "scenario_name": "password_takeover_degraded_no_historical_baseline",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["credential.*", "privilege.*", "auth.account.*"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 3,
                    "event_ids": sorted(["evt_c010", "evt_c012", "evt_c013"]),
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
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
    _write_ndjson(domain_dir / "relationships.ndjson", RELATIONSHIPS_BASELINE)
    _write_yaml(domain_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded no historical baseline: {len(entities)} entities, {len(events)} events")


# ---------- degraded: no cross-account link ----------


def generate_degraded_no_cross_account_link(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "password_takeover_degraded_no_cross_account_link"
    domain_dir = scenario_dir / "domains" / "identity"

    # Remove evt_c010 (credential.reset event)
    events = [e for e in baseline_events if e["id"] != "evt_c010"]

    # Merge mgarcia credential entities: keep only credential_mgarcia_pw_new renamed to credential_mgarcia_pw
    entities = []
    for ent in ENTITIES_BASELINE:
        if ent["id"] == "credential_mgarcia_pw_old":
            continue  # remove old credential
        if ent["id"] == "credential_mgarcia_pw_new":
            e_copy = json.loads(json.dumps(ent))
            e_copy["id"] = "credential_mgarcia_pw"
            e_copy["display_name"] = "mgarcia password"
            e_copy["refs"] = [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_mgarcia"}]
            entities.append(e_copy)
        else:
            entities.append(ent)
    entities.sort(key=lambda e: e["id"])

    # Update relationships: rel_c04 points to credential_mgarcia_pw, remove rel_c05
    relationships = []
    for r in RELATIONSHIPS_BASELINE:
        if r["id"] == "rel_c04":
            r_copy = json.loads(json.dumps(r))
            r_copy["to_entity_id"] = "credential_mgarcia_pw"
            relationships.append(r_copy)
        elif r["id"] == "rel_c05":
            continue  # remove
        else:
            relationships.append(r)
    relationships.sort(key=lambda r: r["id"])

    manifest = {
        "scenario_name": "password_takeover_degraded_no_cross_account_link",
        "version": "1.0",
        "description": "Degraded: credential audit logs missing, cross-account password change invisible",
        "investigation_question": (
            "Was the dormant account mgarcia at Meridian Systems taken over "
            "via cross-account password change from the compromised cgarcia account?"
        ),
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_no_cross_account_link",
        "tags": ["password_takeover", "identity_domain", "credential_audit_missing"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["credential_audit_missing"],
                "notes": "Credential change audit logs unavailable",
            },
            {"source_name": "network_flow", "status": "complete"},
        ],
        "notes": "Credential audit logs missing; cross-account password change invisible",
    }

    # Without evt_c010, only evt_c012 (auth.account.delete) and evt_c013 (privilege.grant) match
    expected_tool_output = {
        "scenario_name": "password_takeover_degraded_no_cross_account_link",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["credential.*", "privilege.*", "auth.account.*"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 2,
                    "event_ids": sorted(["evt_c012", "evt_c013"]),
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "describe_coverage",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
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

    print(f"Degraded no cross-account link: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")


# ---------- main ----------


if __name__ == "__main__":
    baseline_events = generate_baseline()
    generate_degraded_no_network_context(baseline_events)
    generate_degraded_no_historical_baseline(baseline_events)
    generate_degraded_no_cross_account_link(baseline_events)
    print("Done.")
