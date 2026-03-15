#!/usr/bin/env python3
"""Generate superadmin escalation replay scenario fixtures.

Produces baseline + 3 degraded variants modeling a privilege escalation
attack where a compromised admin creates an account and escalates it
to superadmin via a race condition.

Usage:
    python tests/fixtures/replay/generate_superadmin_escalation.py
"""
import json
from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# ---------- shared entity / relationship definitions ----------

ENTITIES_IDENTITY = [
    {
        "id": "credential_kwilson_pw",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "password",
        "display_name": "kwilson password",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_kwilson"}],
    },
    {
        "id": "credential_rchen_ops_pw",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "password",
        "display_name": "rchen.ops password",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_rchen_ops"}],
        "first_seen": "2026-03-12T11:55:00Z",
    },
    {
        "id": "device_d01",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "browser",
        "display_name": "Safari on macOS",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_safari_mac"}],
        "attributes": {"note": "legitimate device"},
    },
    {
        "id": "device_d02",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "browser",
        "display_name": "Chrome on Windows",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_chrome_win"}],
        "attributes": {"note": "adversary device"},
    },
    {
        "id": "principal_kwilson",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "kwilson@cascade-industries.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_kwilson"}],
        "attributes": {"email": "kwilson@cascade-industries.example", "role": "compromised admin"},
        "first_seen": "2026-03-01T09:00:00Z",
        "last_seen": "2026-03-13T04:22:00Z",
    },
    {
        "id": "principal_rchen_ops",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "rchen.ops@cascade-industries.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_rchen_ops"}],
        "attributes": {"email": "rchen.ops@cascade-industries.example", "role": "escalated account"},
        "first_seen": "2026-03-12T11:55:00Z",
        "last_seen": "2026-03-13T04:22:00Z",
    },
    {
        "id": "session_d01",
        "tlp": "GREEN",
        "entity_type": "session",
        "kind": "web_session",
        "display_name": "kwilson session",
        "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_d01"}],
    },
    {
        "id": "session_d02",
        "tlp": "GREEN",
        "entity_type": "session",
        "kind": "web_session",
        "display_name": "rchen.ops session",
        "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_d02"}],
    },
]

RELATIONSHIPS_IDENTITY = [
    {
        "id": "rel_d01",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "authenticated_as",
        "from_entity_id": "session_d01",
        "to_entity_id": "principal_kwilson",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_d02",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "authenticated_as",
        "from_entity_id": "session_d02",
        "to_entity_id": "principal_rchen_ops",
        "first_seen": "2026-03-12T11:58:00Z",
    },
    {
        "id": "rel_d03",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_kwilson",
        "to_entity_id": "credential_kwilson_pw",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_d04",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_rchen_ops",
        "to_entity_id": "credential_rchen_ops_pw",
        "first_seen": "2026-03-12T11:55:00Z",
    },
    {
        "id": "rel_d05",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_d01",
        "to_entity_id": "device_d01",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_d06",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_d02",
        "to_entity_id": "device_d02",
        "first_seen": "2026-03-12T11:58:00Z",
    },
    {
        "id": "rel_d07",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "created_by",
        "from_entity_id": "principal_rchen_ops",
        "to_entity_id": "principal_kwilson",
        "first_seen": "2026-03-12T11:55:00Z",
    },
]

# ---------- app domain entities / events ----------

ENTITIES_APP = [
    {
        "id": "resource_financial_system",
        "tlp": "GREEN",
        "entity_type": "resource",
        "kind": "application",
        "display_name": "Financial System",
        "refs": [{"ref_type": "resource_id", "system": "app_audit", "value": "res_financial_system"}],
    },
]

RELATIONSHIPS_APP: list[dict] = []


def _generate_app_events() -> list[dict]:
    """Generate 20 app.resource.access events for rchen.ops hitting the financial system."""
    events = []
    for i in range(1, 21):
        # Spread across Mar 12 12:00:00 - 12:04:45 (every 15 seconds)
        minutes = (i - 1) * 15 // 60
        seconds = (i - 1) * 15 % 60
        events.append({
            "id": f"evt_app_d{i:03d}",
            "tlp": "GREEN",
            "domain": "app",
            "ts": f"2026-03-12T12:{minutes:02d}:{seconds:02d}Z",
            "action": "app.resource.access",
            "actor": {"actor_entity_id": "principal_rchen_ops"},
            "targets": [{"target_entity_id": "resource_financial_system"}],
            "outcome": "succeeded",
            "context": {
                "resource": "financial_system",
                "count": 1,
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "app_audit", "value": f"app_evt_{i:03d}"}
            ],
        })
    return events


APP_EVENTS = _generate_app_events()

APP_COVERAGE = {
    "domain": "app",
    "overall_status": "unknown",
    "sources": [
        {
            "source_name": "app_audit",
            "status": "unknown",
        },
    ],
    "notes": "No app domain server available for verification",
}

# ---------- identity events ----------

# Normal kwilson logins: Mar 1-11, 09:00 and 17:00, skip weekends (Mar 2 Sun, 8 Sat, 9 Sun)
_NORMAL_LOGIN_DAYS = [1, 3, 4, 5, 6, 7, 10, 11]  # skip 2 (Sun), 8 (Sat), 9 (Sun)


def _generate_identity_events() -> list[dict]:
    """Generate all 17 identity events for the baseline scenario."""
    events = []
    idx = 1

    # Normal kwilson logins (8 events, 2 per day on 4 days to get 8)
    for day in _NORMAL_LOGIN_DAYS:
        if idx > 8:
            break
        hour = 9 if idx % 2 == 1 else 17
        events.append({
            "id": f"evt_d{idx:03d}",
            "tlp": "GREEN",
            "domain": "identity",
            "ts": f"2026-03-{day:02d}T{hour:02d}:00:00Z",
            "action": "auth.login",
            "actor": {"actor_entity_id": "principal_kwilson"},
            "targets": [{"target_entity_id": "session_d01"}],
            "outcome": "succeeded",
            "context": {
                "source_ip": "198.51.100.10",
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari",
                "session_id": "sess_d01",
                "device_id": "device_d01",
                "auth_method": "password",
                "login_type": "interactive",
            },
            "raw_refs": [
                {"ref_type": "event_id", "system": "okta", "value": f"okta_evt_d{idx:03d}"}
            ],
        })
        idx += 1

    # Adversary login as kwilson (evt_d009)
    events.append({
        "id": "evt_d009",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:50:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_kwilson"},
        "targets": [{"target_entity_id": "session_d01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome",
            "session_id": "sess_d01",
            "device_id": "device_d02",
            "auth_method": "password",
            "login_type": "interactive",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d009"}
        ],
    })

    # Account creation (evt_d010)
    events.append({
        "id": "evt_d010",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:55:00Z",
        "action": "auth.account.create",
        "actor": {"actor_entity_id": "principal_kwilson"},
        "targets": [{"target_entity_id": "principal_rchen_ops"}],
        "outcome": "succeeded",
        "context": {
            "target_role": "standard_user",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d010"}
        ],
    })

    # Privilege grants (evt_d011, evt_d012, evt_d013)
    events.append({
        "id": "evt_d011",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:56:00Z",
        "action": "privilege.grant",
        "actor": {"actor_entity_id": "principal_kwilson"},
        "targets": [{"target_entity_id": "principal_rchen_ops"}],
        "outcome": "succeeded",
        "context": {
            "privilege_type": "role",
            "role": "company_admin",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d011"}
        ],
    })

    events.append({
        "id": "evt_d012",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:56:30Z",
        "action": "privilege.grant",
        "actor": {"actor_entity_id": "principal_kwilson"},
        "targets": [{"target_entity_id": "principal_rchen_ops"}],
        "outcome": "succeeded",
        "context": {
            "privilege_type": "role",
            "role": "accountant",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d012"}
        ],
    })

    events.append({
        "id": "evt_d013",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:57:00Z",
        "action": "privilege.grant",
        "actor": {"actor_entity_id": "principal_rchen_ops"},
        "targets": [{"target_entity_id": "principal_rchen_ops"}],
        "outcome": "succeeded",
        "context": {
            "privilege_type": "role",
            "role": "superadmin",
            "escalation_method": "race_condition",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d013"}
        ],
    })

    # rchen_ops login (evt_d014)
    events.append({
        "id": "evt_d014",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T11:58:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_rchen_ops"},
        "targets": [{"target_entity_id": "session_d02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome",
            "session_id": "sess_d02",
            "device_id": "device_d02",
            "auth_method": "password",
            "login_type": "interactive",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d014"}
        ],
    })

    # Continued rchen_ops logins (evt_d015, evt_d016)
    events.append({
        "id": "evt_d015",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T13:33:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_rchen_ops"},
        "targets": [{"target_entity_id": "session_d02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome",
            "session_id": "sess_d02",
            "device_id": "device_d02",
            "auth_method": "password",
            "login_type": "interactive",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d015"}
        ],
    })

    events.append({
        "id": "evt_d016",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-12T13:40:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_rchen_ops"},
        "targets": [{"target_entity_id": "session_d02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome",
            "session_id": "sess_d02",
            "device_id": "device_d02",
            "auth_method": "password",
            "login_type": "interactive",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d016"}
        ],
    })

    # Account disabled / failed login (evt_d017)
    events.append({
        "id": "evt_d017",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-13T04:22:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_rchen_ops"},
        "targets": [{"target_entity_id": "session_d02"}],
        "outcome": "failed",
        "context": {
            "source_ip": "203.0.113.42",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome",
            "session_id": "sess_d02",
            "device_id": "device_d02",
            "auth_method": "password",
            "login_type": "interactive",
            "failure_reason": "account_disabled",
        },
        "raw_refs": [
            {"ref_type": "event_id", "system": "okta", "value": "okta_evt_d017"}
        ],
    })

    # Sort by timestamp
    events.sort(key=lambda e: e["ts"])
    return events


IDENTITY_EVENTS = _generate_identity_events()

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
    scenario_dir = SCENARIOS_DIR / "superadmin_escalation_baseline"
    identity_dir = scenario_dir / "domains" / "identity"
    app_dir = scenario_dir / "domains" / "app"

    events = list(IDENTITY_EVENTS)

    manifest = {
        "scenario_name": "superadmin_escalation_baseline",
        "version": "1.0",
        "description": "Baseline scenario: superadmin privilege escalation with complete telemetry",
        "investigation_question": "Did the compromised kwilson account escalate rchen.ops to superadmin at Cascade Industries?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "baseline",
        "tags": ["superadmin_escalation", "identity_domain", "app_domain", "complete_coverage"],
    }

    identity_coverage = {
        "domain": "identity",
        "overall_status": "complete",
        "sources": [
            {
                "source_name": "okta",
                "status": "complete",
            },
        ],
        "notes": "Baseline scenario with complete telemetry from Okta",
    }

    # Expected tool output
    privilege_events = [e for e in events if e["action"].startswith("privilege.")]
    account_events = [e for e in events if e["action"].startswith("auth.account.")]
    privilege_event_ids = sorted([e["id"] for e in privilege_events])
    account_event_ids = sorted([e["id"] for e in account_events])

    # get_neighbors for principal_rchen_ops:
    # from_entity_id == principal_rchen_ops: rel_d04 (has_credential -> credential_rchen_ops_pw),
    #                                        rel_d07 (created_by -> principal_kwilson)
    # to_entity_id == principal_rchen_ops: rel_d02 (authenticated_as <- session_d02)
    # That's 3 relationships, 3 neighbor entities
    expected_tool_output = {
        "scenario_name": "superadmin_escalation_baseline",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["privilege.grant"],
                },
                "expected": {
                    "status": "success",
                    "event_count": 3,
                    "event_ids": privilege_event_ids,
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["auth.account.create"],
                },
                "expected": {
                    "status": "success",
                    "event_count": 1,
                    "event_ids": account_event_ids,
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_entity",
                "args": {"entity_id": "principal_kwilson"},
                "expected": {
                    "status": "success",
                    "entity_count": 1,
                    "entity_ids": ["principal_kwilson"],
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_neighbors",
                "args": {"entity_id": "principal_rchen_ops"},
                "expected": {
                    "status": "success",
                    "entity_count": 3,
                    "relationship_count": 3,
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
                    "source_count": 1,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(identity_dir / "entities.ndjson", sorted(ENTITIES_IDENTITY, key=lambda e: e["id"]))
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", sorted(RELATIONSHIPS_IDENTITY, key=lambda r: r["id"]))
    _write_yaml(identity_dir / "coverage.yaml", identity_coverage)
    _write_ndjson(app_dir / "entities.ndjson", ENTITIES_APP)
    _write_ndjson(app_dir / "events.ndjson", APP_EVENTS)
    _write_ndjson(app_dir / "relationships.ndjson", RELATIONSHIPS_APP)
    _write_yaml(app_dir / "coverage.yaml", APP_COVERAGE)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Baseline: {len(ENTITIES_IDENTITY)} identity entities, {len(events)} identity events, "
          f"{len(RELATIONSHIPS_IDENTITY)} identity relationships, "
          f"{len(ENTITIES_APP)} app entities, {len(APP_EVENTS)} app events")
    return events


# ---------- degraded: no role logs ----------


def generate_degraded_no_role_logs(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "superadmin_escalation_degraded_no_role_logs"
    identity_dir = scenario_dir / "domains" / "identity"
    app_dir = scenario_dir / "domains" / "app"

    # Remove all privilege.grant events (evt_d011, evt_d012, evt_d013)
    events = [e for e in baseline_events if e["action"] != "privilege.grant"]

    manifest = {
        "scenario_name": "superadmin_escalation_degraded_no_role_logs",
        "version": "1.0",
        "description": "Degraded: privilege audit logs unavailable",
        "investigation_question": "Did the compromised kwilson account escalate rchen.ops to superadmin at Cascade Industries?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "degraded_no_role_logs",
        "tags": ["superadmin_escalation", "identity_domain", "app_domain", "privilege_audit_unavailable"],
    }

    identity_coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["privilege_audit_unavailable"],
                "notes": "Privilege change audit logs unavailable",
            },
        ],
        "notes": "Privilege audit logs unavailable; escalation events not visible",
    }

    expected_tool_output = {
        "scenario_name": "superadmin_escalation_degraded_no_role_logs",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["privilege.grant"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 0,
                    "event_ids": [],
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
                    "source_count": 1,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(identity_dir / "entities.ndjson", sorted(ENTITIES_IDENTITY, key=lambda e: e["id"]))
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", sorted(RELATIONSHIPS_IDENTITY, key=lambda r: r["id"]))
    _write_yaml(identity_dir / "coverage.yaml", identity_coverage)
    _write_ndjson(app_dir / "entities.ndjson", ENTITIES_APP)
    _write_ndjson(app_dir / "events.ndjson", APP_EVENTS)
    _write_ndjson(app_dir / "relationships.ndjson", RELATIONSHIPS_APP)
    _write_yaml(app_dir / "coverage.yaml", APP_COVERAGE)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded no role logs: {len(ENTITIES_IDENTITY)} identity entities, {len(events)} identity events")


# ---------- degraded: no access logs ----------


def generate_degraded_no_access_logs(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "superadmin_escalation_degraded_no_access_logs"
    identity_dir = scenario_dir / "domains" / "identity"

    # Identity fixtures unchanged from baseline
    events = list(baseline_events)

    manifest = {
        "scenario_name": "superadmin_escalation_degraded_no_access_logs",
        "version": "1.0",
        "description": "Degraded: app domain access logs unavailable",
        "investigation_question": "Did the compromised kwilson account escalate rchen.ops to superadmin at Cascade Industries?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity"],
        "variant": "degraded_no_access_logs",
        "tags": ["superadmin_escalation", "identity_domain", "app_domain_missing"],
    }

    identity_coverage = {
        "domain": "identity",
        "overall_status": "complete",
        "sources": [
            {
                "source_name": "okta",
                "status": "complete",
            },
        ],
        "notes": "Baseline scenario with complete telemetry from Okta",
    }

    privilege_event_ids = sorted([e["id"] for e in events if e["action"].startswith("privilege.")])

    expected_tool_output = {
        "scenario_name": "superadmin_escalation_degraded_no_access_logs",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["privilege.grant"],
                },
                "expected": {
                    "status": "success",
                    "event_count": 3,
                    "event_ids": privilege_event_ids,
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
                    "source_count": 1,
                },
            },
        ],
    }

    # No app domain directory at all
    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(identity_dir / "entities.ndjson", sorted(ENTITIES_IDENTITY, key=lambda e: e["id"]))
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", sorted(RELATIONSHIPS_IDENTITY, key=lambda r: r["id"]))
    _write_yaml(identity_dir / "coverage.yaml", identity_coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded no access logs: {len(ENTITIES_IDENTITY)} identity entities, {len(events)} identity events, no app domain")


# ---------- degraded: no creation context ----------


def generate_degraded_no_creation_context(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "superadmin_escalation_degraded_no_creation_context"
    identity_dir = scenario_dir / "domains" / "identity"
    app_dir = scenario_dir / "domains" / "app"

    # Remove evt_d010 (auth.account.create)
    events = [e for e in baseline_events if e["id"] != "evt_d010"]

    # Remove rel_d07 (created_by)
    relationships = [r for r in RELATIONSHIPS_IDENTITY if r["id"] != "rel_d07"]

    # Keep principal_rchen_ops entity (entities unchanged)

    manifest = {
        "scenario_name": "superadmin_escalation_degraded_no_creation_context",
        "version": "1.0",
        "description": "Degraded: account provisioning context unavailable",
        "investigation_question": "Did the compromised kwilson account escalate rchen.ops to superadmin at Cascade Industries?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "degraded_no_creation_context",
        "tags": ["superadmin_escalation", "identity_domain", "app_domain", "provisioning_context_unavailable"],
    }

    identity_coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["provisioning_context_unavailable"],
                "notes": "Account provisioning context unavailable",
            },
        ],
        "notes": "Account creation context unavailable; cannot attribute rchen.ops to kwilson",
    }

    privilege_event_ids = sorted([e["id"] for e in events if e["action"].startswith("privilege.")])

    # get_neighbors for principal_rchen_ops without rel_d07:
    # from_entity_id == principal_rchen_ops: rel_d04 (has_credential -> credential_rchen_ops_pw)
    # to_entity_id == principal_rchen_ops: rel_d02 (authenticated_as <- session_d02)
    # That's 2 relationships, 2 neighbor entities
    expected_tool_output = {
        "scenario_name": "superadmin_escalation_degraded_no_creation_context",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": ["privilege.grant", "auth.account.create"],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 3,
                    "event_ids": privilege_event_ids,
                    "coverage_overall_status": "partial",
                },
            },
            {
                "tool": "get_neighbors",
                "args": {"entity_id": "principal_rchen_ops"},
                "expected": {
                    "status": "partial",
                    "entity_count": 2,
                    "relationship_count": 2,
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
                    "source_count": 1,
                },
            },
        ],
    }

    _write_yaml(scenario_dir / "manifest.yaml", manifest)
    _write_ndjson(identity_dir / "entities.ndjson", sorted(ENTITIES_IDENTITY, key=lambda e: e["id"]))
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", sorted(relationships, key=lambda r: r["id"]))
    _write_yaml(identity_dir / "coverage.yaml", identity_coverage)
    _write_ndjson(app_dir / "entities.ndjson", ENTITIES_APP)
    _write_ndjson(app_dir / "events.ndjson", APP_EVENTS)
    _write_ndjson(app_dir / "relationships.ndjson", RELATIONSHIPS_APP)
    _write_yaml(app_dir / "coverage.yaml", APP_COVERAGE)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)

    print(f"Degraded no creation context: {len(ENTITIES_IDENTITY)} identity entities, "
          f"{len(events)} identity events, {len(relationships)} identity relationships")


# ---------- main ----------


if __name__ == "__main__":
    baseline_events = generate_baseline()
    generate_degraded_no_role_logs(baseline_events)
    generate_degraded_no_access_logs(baseline_events)
    generate_degraded_no_creation_context(baseline_events)
    print("Done.")
