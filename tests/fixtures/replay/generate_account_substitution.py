#!/usr/bin/env python3
"""Generate account substitution replay scenario fixtures.

Produces baseline + 3 degraded variants modeling an account substitution
attack pattern where a sleeper account deletes a legitimate admin and
creates a lookalike replacement.

Usage:
    python tests/fixtures/replay/generate_account_substitution.py
"""
import json
from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# ---------- shared entity / relationship definitions ----------

ENTITIES_IDENTITY_BASELINE = [
    {
        "id": "credential_garcia_carlos_pw",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "password",
        "display_name": "garcia.carlos password",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_garcia_carlos"}],
    },
    {
        "id": "credential_jef_greenfield_mfa",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "mfa_totp",
        "display_name": "jef.greenfield TOTP factor",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_mfa_jef_greenfield"}],
        "first_seen": "2026-03-25T10:05:00Z",
    },
    {
        "id": "credential_mreyes_pw",
        "tlp": "GREEN",
        "entity_type": "credential",
        "kind": "password",
        "display_name": "mreyes password",
        "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred_pw_mreyes"}],
    },
    {
        "id": "device_b01",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "browser",
        "display_name": "Chrome on Windows",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_chrome_win"}],
    },
    {
        "id": "device_b02",
        "tlp": "GREEN",
        "entity_type": "device",
        "kind": "browser",
        "display_name": "Firefox on Linux",
        "refs": [{"ref_type": "device_id", "system": "okta", "value": "dev_firefox_linux"}],
    },
    {
        "id": "principal_garcia_carlos",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "garcia.carlos@greenfield-corp.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_garcia_carlos"}],
        "attributes": {"email": "garcia.carlos@greenfield-corp.example", "role": "sleeper account"},
        "first_seen": "2026-03-03T14:30:00Z",
        "last_seen": "2026-03-27T09:00:00Z",
    },
    {
        "id": "principal_jef_greenfield",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "jef.greenfield@greenfield-corp.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_jef_greenfield"}],
        "attributes": {"email": "jef.greenfield@greenfield-corp.example", "role": "lookalike replacement"},
        "first_seen": "2026-03-25T03:18:00Z",
        "last_seen": "2026-03-26T17:00:00Z",
    },
    {
        "id": "principal_jeff_greenfield",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "jeff.greenfield@greenfield-corp.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_jeff_greenfield"}],
        "attributes": {"email": "jeff.greenfield@greenfield-corp.example", "role": "deleted legitimate admin"},
        "first_seen": "2026-03-01T08:00:00Z",
        "last_seen": "2026-03-25T03:14:00Z",
    },
    {
        "id": "principal_mreyes",
        "tlp": "GREEN",
        "entity_type": "principal",
        "kind": "user",
        "display_name": "mreyes@greenfield-corp.example",
        "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u_mreyes"}],
        "attributes": {"email": "mreyes@greenfield-corp.example", "role": "compromised admin"},
        "first_seen": "2026-03-01T09:00:00Z",
        "last_seen": "2026-03-27T17:00:00Z",
    },
    {
        "id": "session_b01",
        "tlp": "GREEN",
        "entity_type": "session",
        "kind": "web_session",
        "display_name": "mreyes session",
        "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_b01"}],
    },
    {
        "id": "session_b02",
        "tlp": "GREEN",
        "entity_type": "session",
        "kind": "web_session",
        "display_name": "garcia_carlos session",
        "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_b02"}],
    },
    {
        "id": "session_b03",
        "tlp": "GREEN",
        "entity_type": "session",
        "kind": "web_session",
        "display_name": "jef_greenfield session",
        "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess_b03"}],
    },
]

RELATIONSHIPS_IDENTITY_BASELINE = [
    {
        "id": "rel_b01",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "authenticated_as",
        "from_entity_id": "session_b01",
        "to_entity_id": "principal_mreyes",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_b02",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "authenticated_as",
        "from_entity_id": "session_b02",
        "to_entity_id": "principal_garcia_carlos",
        "first_seen": "2026-03-03T14:30:00Z",
    },
    {
        "id": "rel_b03",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "authenticated_as",
        "from_entity_id": "session_b03",
        "to_entity_id": "principal_jef_greenfield",
        "first_seen": "2026-03-25T03:18:00Z",
    },
    {
        "id": "rel_b04",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_mreyes",
        "to_entity_id": "credential_mreyes_pw",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_b05",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_garcia_carlos",
        "to_entity_id": "credential_garcia_carlos_pw",
        "first_seen": "2026-03-03T14:30:00Z",
    },
    {
        "id": "rel_b06",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "has_credential",
        "from_entity_id": "principal_jef_greenfield",
        "to_entity_id": "credential_jef_greenfield_mfa",
        "first_seen": "2026-03-25T10:05:00Z",
    },
    {
        "id": "rel_b07",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_b01",
        "to_entity_id": "device_b01",
        "first_seen": "2026-03-01T09:00:00Z",
    },
    {
        "id": "rel_b08",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_b02",
        "to_entity_id": "device_b02",
        "first_seen": "2026-03-25T03:12:00Z",
    },
    {
        "id": "rel_b09",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "uses_device",
        "from_entity_id": "session_b03",
        "to_entity_id": "device_b02",
        "first_seen": "2026-03-25T11:00:00Z",
    },
    {
        "id": "rel_b10",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "created_by",
        "from_entity_id": "principal_garcia_carlos",
        "to_entity_id": "principal_mreyes",
        "first_seen": "2026-03-03T14:30:00Z",
    },
    {
        "id": "rel_b11",
        "tlp": "GREEN",
        "domain": "identity",
        "relationship_type": "deleted_by",
        "from_entity_id": "principal_jeff_greenfield",
        "to_entity_id": "principal_garcia_carlos",
        "first_seen": "2026-03-25T03:14:00Z",
    },
]

# ---------- identity events ----------

EVENTS_IDENTITY_BASELINE = [
    # Background auth.login for mreyes (Mar 1-3, 2 per day at 09:00 and 14:00)
    {
        "id": "evt_b001",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-01T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b001"}],
    },
    {
        "id": "evt_b002",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-01T14:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b002"}],
    },
    {
        "id": "evt_b003",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-02T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b003"}],
    },
    {
        "id": "evt_b004",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-02T14:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b004"}],
    },
    {
        "id": "evt_b005",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-03T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b005"}],
    },
    {
        "id": "evt_b006",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-03T14:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "session_b01"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b01",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b006"}],
    },
    # Sleeper creation and privilege grant (Mar 3)
    {
        "id": "evt_b007",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-03T14:30:00Z",
        "action": "auth.account.create",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "principal_garcia_carlos"}],
        "outcome": "succeeded",
        "context": {"target_role": "company_admin"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b007"}],
    },
    {
        "id": "evt_b008",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-03T14:35:00Z",
        "action": "privilege.grant",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "principal_garcia_carlos"}],
        "outcome": "succeeded",
        "context": {"privilege_type": "role", "role": "company_admin"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b008"}],
    },
    # Sleeper logins (Mar 3-5)
    {
        "id": "evt_b009",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-03T15:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "session_b02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b02",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b009"}],
    },
    {
        "id": "evt_b010",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-04T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "session_b02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b02",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b010"}],
    },
    {
        "id": "evt_b011",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-05T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "session_b02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "198.51.100.10",
            "device_id": "device_b01",
            "session_id": "sess_b02",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b011"}],
    },
    # Dormancy gap (Mar 6-24: no garcia_carlos events)
    # Sleeper reactivation at unusual hour from adversary device (Mar 25)
    {
        "id": "evt_b012",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T03:12:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "session_b02"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "device_id": "device_b02",
            "session_id": "sess_b02",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b012"}],
    },
    # Account deletion (Mar 25)
    {
        "id": "evt_b013",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T03:14:00Z",
        "action": "auth.account.delete",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "principal_jeff_greenfield"}],
        "outcome": "succeeded",
        "context": {"reason": "substitution"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b013"}],
    },
    # Lookalike creation (Mar 25)
    {
        "id": "evt_b014",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T03:18:00Z",
        "action": "auth.account.create",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "principal_jef_greenfield"}],
        "outcome": "succeeded",
        "context": {"target_role": "financial_admin"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b014"}],
    },
    # Privilege grant to lookalike (Mar 25)
    {
        "id": "evt_b015",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T10:00:00Z",
        "action": "privilege.grant",
        "actor": {"actor_entity_id": "principal_garcia_carlos"},
        "targets": [{"target_entity_id": "principal_jef_greenfield"}],
        "outcome": "succeeded",
        "context": {"privilege_type": "role", "role": "financial_admin"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b015"}],
    },
    # MFA enrollment for lookalike (Mar 25)
    {
        "id": "evt_b016",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T10:05:00Z",
        "action": "credential.enroll",
        "actor": {"actor_entity_id": "principal_jef_greenfield"},
        "targets": [{"target_entity_id": "credential_jef_greenfield_mfa"}],
        "outcome": "succeeded",
        "context": {"credential_type": "mfa_totp", "change": "enroll"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b016"}],
    },
    # Continued logins from stale session (Mar 25-26)
    {
        "id": "evt_b017",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T11:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_jef_greenfield"},
        "targets": [{"target_entity_id": "session_b03"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "device_id": "device_b02",
            "session_id": "sess_b03",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b017"}],
    },
    {
        "id": "evt_b018",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-25T16:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_jef_greenfield"},
        "targets": [{"target_entity_id": "session_b03"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "device_id": "device_b02",
            "session_id": "sess_b03",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b018"}],
    },
    {
        "id": "evt_b019",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-26T09:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_jef_greenfield"},
        "targets": [{"target_entity_id": "session_b03"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "device_id": "device_b02",
            "session_id": "sess_b03",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b019"}],
    },
    {
        "id": "evt_b020",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-26T14:00:00Z",
        "action": "auth.login",
        "actor": {"actor_entity_id": "principal_jef_greenfield"},
        "targets": [{"target_entity_id": "session_b03"}],
        "outcome": "succeeded",
        "context": {
            "source_ip": "203.0.113.42",
            "device_id": "device_b02",
            "session_id": "sess_b03",
            "auth_method": "password",
        },
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b020"}],
    },
    # IR remediation (Mar 27)
    {
        "id": "evt_b021",
        "tlp": "GREEN",
        "domain": "identity",
        "ts": "2026-03-27T09:00:00Z",
        "action": "auth.account.disable",
        "actor": {"actor_entity_id": "principal_mreyes"},
        "targets": [{"target_entity_id": "principal_garcia_carlos"}],
        "outcome": "succeeded",
        "context": {"reason": "ir_remediation"},
        "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "okta_evt_b021"}],
    },
]

# ---------- app domain placeholder fixtures ----------

ENTITIES_APP = [
    {
        "id": "resource_payment_system",
        "tlp": "GREEN",
        "entity_type": "resource",
        "kind": "application",
        "display_name": "Payment System",
        "refs": [{"ref_type": "resource_id", "system": "app_audit", "value": "app_payment_system"}],
    },
    {
        "id": "resource_financial_system",
        "tlp": "GREEN",
        "entity_type": "resource",
        "kind": "application",
        "display_name": "Financial System",
        "refs": [{"ref_type": "resource_id", "system": "app_audit", "value": "app_financial_system"}],
    },
]

RELATIONSHIPS_APP: list[dict] = []


def _generate_app_events() -> list[dict]:
    """Generate app domain events for the lookalike account.

    Includes profile manipulation (user updates to make the lookalike pass
    as the deleted admin) followed by financial activity.
    """
    events = []
    idx = 1

    # Profile manipulation: sleeper edits lookalike to resemble deleted admin.
    # These happen right after account creation (Mar 25 03:18) and before
    # the lookalike starts operating. The sleeper modifies display name,
    # email, and contact fields to match jeff.greenfield's profile.
    profile_updates = [
        {
            "ts": "2026-03-25T03:20:00Z",
            "field": "display_name",
            "old_value": "jef.greenfield",
            "new_value": "Jeff Greenfield",
        },
        {
            "ts": "2026-03-25T03:21:00Z",
            "field": "email_alias",
            "old_value": None,
            "new_value": "jeff.greenfield@greenfield-corp.example",
        },
        {
            "ts": "2026-03-25T03:22:00Z",
            "field": "phone",
            "old_value": None,
            "new_value": "+1-555-0142",
        },
        {
            "ts": "2026-03-25T03:23:00Z",
            "field": "department",
            "old_value": None,
            "new_value": "Finance",
        },
    ]
    for update in profile_updates:
        events.append({
            "id": f"evt_app_b{idx:03d}",
            "tlp": "GREEN",
            "domain": "app",
            "ts": update["ts"],
            "action": "app.user.update",
            "actor": {"actor_entity_id": "principal_garcia_carlos"},
            "targets": [{"target_entity_id": "principal_jef_greenfield"}],
            "outcome": "succeeded",
            "context": {
                "field": update["field"],
                "old_value": update["old_value"],
                "new_value": update["new_value"],
            },
            "raw_refs": [{"ref_type": "event_id", "system": "app_audit", "value": f"app_evt_b{idx:03d}"}],
        })
        idx += 1

    # 10 transaction events spread across Mar 25 11:30-16:00
    base_minutes = [30, 60, 90, 120, 150, 180, 210, 240, 260, 270]
    for offset in base_minutes:
        hour = 11 + offset // 60
        minute = offset % 60
        events.append({
            "id": f"evt_app_b{idx:03d}",
            "tlp": "GREEN",
            "domain": "app",
            "ts": f"2026-03-25T{hour:02d}:{minute:02d}:00Z",
            "action": "app.invoice.create",
            "actor": {"actor_entity_id": "principal_jef_greenfield"},
            "targets": [{"target_entity_id": "resource_financial_system"}],
            "outcome": "succeeded",
            "context": {"amount": "500.00", "recipient": "ext_account"},
            "raw_refs": [{"ref_type": "event_id", "system": "app_audit", "value": f"app_evt_b{idx:03d}"}],
        })
        idx += 1

    # 3 disbursement events at 17:00, 17:30, 18:00
    for hour, minute in [(17, 0), (17, 30), (18, 0)]:
        events.append({
            "id": f"evt_app_b{idx:03d}",
            "tlp": "GREEN",
            "domain": "app",
            "ts": f"2026-03-25T{hour:02d}:{minute:02d}:00Z",
            "action": "app.payment.create",
            "actor": {"actor_entity_id": "principal_jef_greenfield"},
            "targets": [{"target_entity_id": "resource_payment_system"}],
            "outcome": "succeeded",
            "context": {"amount": "5125.00", "method": "debit_card"},
            "raw_refs": [{"ref_type": "event_id", "system": "app_audit", "value": f"app_evt_b{idx:03d}"}],
        })
        idx += 1

    events.sort(key=lambda e: e["ts"])
    return events


EVENTS_APP = _generate_app_events()

COVERAGE_APP = {
    "domain": "app",
    "overall_status": "unknown",
    "sources": [
        {
            "source_name": "app_audit",
            "status": "unknown",
        }
    ],
    "notes": "No app domain server available for verification",
}

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


def _write_app_domain(scenario_dir: Path) -> None:
    """Write the app domain placeholder fixtures into a scenario directory."""
    app_dir = scenario_dir / "domains" / "app"
    _write_ndjson(app_dir / "entities.ndjson", ENTITIES_APP)
    _write_ndjson(app_dir / "events.ndjson", EVENTS_APP)
    _write_ndjson(app_dir / "relationships.ndjson", RELATIONSHIPS_APP)
    _write_yaml(app_dir / "coverage.yaml", COVERAGE_APP)


# ---------- baseline ----------


def generate_baseline():
    scenario_dir = SCENARIOS_DIR / "account_substitution_baseline"
    identity_dir = scenario_dir / "domains" / "identity"

    entities = sorted(ENTITIES_IDENTITY_BASELINE, key=lambda e: e["id"])
    relationships = sorted(RELATIONSHIPS_IDENTITY_BASELINE, key=lambda r: r["id"])
    events = sorted(EVENTS_IDENTITY_BASELINE, key=lambda e: e["ts"])

    # Non-auth events (account lifecycle, privilege, credential actions)
    non_auth_events = [e for e in events if not e["action"].startswith("auth.login")]
    non_auth_event_ids = sorted([e["id"] for e in non_auth_events])

    # Entities referenced by non-auth events
    non_auth_entity_ids = set()
    for e in non_auth_events:
        non_auth_entity_ids.add(e["actor"]["actor_entity_id"])
        for t in e["targets"]:
            non_auth_entity_ids.add(t["target_entity_id"])

    # get_neighbors for principal_garcia_carlos:
    # from garcia_carlos: has_credential (rel_b05), created_by (rel_b10)
    # to garcia_carlos: authenticated_as (rel_b02), deleted_by (rel_b11)
    # neighbor entities: credential_garcia_carlos_pw, principal_mreyes, session_b02, principal_jeff_greenfield
    garcia_neighbor_count = 4
    garcia_rel_count = 4

    manifest = {
        "scenario_name": "account_substitution_baseline",
        "version": "1.0",
        "description": "Baseline scenario: account substitution with complete telemetry",
        "investigation_question": "Did garcia.carlos, created by compromised admin mreyes, delete jeff.greenfield and substitute a lookalike account at Greenfield Corp?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "baseline",
        "tags": ["account_substitution", "identity_domain", "app_domain", "complete_coverage"],
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
        "notes": "Baseline scenario with complete telemetry from Okta",
    }

    expected_tool_output = {
        "scenario_name": "account_substitution_baseline",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": [
                        "auth.account.create",
                        "auth.account.delete",
                        "auth.account.disable",
                        "credential.enroll",
                        "privilege.grant",
                    ],
                },
                "expected": {
                    "status": "success",
                    "event_count": len(non_auth_events),
                    "event_ids": non_auth_event_ids,
                    "entity_count": len(non_auth_entity_ids),
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_entity",
                "args": {"entity_id": "principal_mreyes"},
                "expected": {
                    "status": "success",
                    "entity_count": 1,
                    "entity_ids": ["principal_mreyes"],
                    "coverage_overall_status": "complete",
                },
            },
            {
                "tool": "get_neighbors",
                "args": {"entity_id": "principal_garcia_carlos"},
                "expected": {
                    "status": "success",
                    "entity_count": garcia_neighbor_count,
                    "relationship_count": garcia_rel_count,
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
    _write_ndjson(identity_dir / "entities.ndjson", entities)
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", relationships)
    _write_yaml(identity_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)
    _write_app_domain(scenario_dir)

    print(f"Baseline: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")
    return events


# ---------- degraded 1: no sleeper creation ----------


def generate_degraded_no_sleeper_creation(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "account_substitution_degraded_no_sleeper_creation"
    identity_dir = scenario_dir / "domains" / "identity"

    # Remove evt_b007 (auth.account.create for garcia_carlos)
    events = [e for e in baseline_events if e["id"] != "evt_b007"]

    # Remove rel_b10 (created_by)
    relationships = sorted(
        [r for r in RELATIONSHIPS_IDENTITY_BASELINE if r["id"] != "rel_b10"],
        key=lambda r: r["id"],
    )

    entities = sorted(ENTITIES_IDENTITY_BASELINE, key=lambda e: e["id"])

    manifest = {
        "scenario_name": "account_substitution_degraded_no_sleeper_creation",
        "version": "1.0",
        "description": "Degraded: sleeper account creation event missing due to provisioning log rotation",
        "investigation_question": "Did garcia.carlos, created by compromised admin mreyes, delete jeff.greenfield and substitute a lookalike account at Greenfield Corp?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "degraded_no_sleeper_creation",
        "tags": ["account_substitution", "identity_domain", "app_domain", "provisioning_gap"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["provisioning_gap"],
                "notes": "Account provisioning logs rotated before retention window",
            }
        ],
        "notes": "Account provisioning records unavailable; cannot attribute sleeper creation",
    }

    expected_tool_output = {
        "scenario_name": "account_substitution_degraded_no_sleeper_creation",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": [
                        "auth.account.create",
                        "auth.account.delete",
                        "auth.account.disable",
                        "credential.enroll",
                        "privilege.grant",
                    ],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 6,
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
    _write_ndjson(identity_dir / "entities.ndjson", entities)
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", relationships)
    _write_yaml(identity_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)
    _write_app_domain(scenario_dir)

    print(f"Degraded no sleeper creation: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")


# ---------- degraded 2: no session tracking ----------


def generate_degraded_no_session_tracking(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "account_substitution_degraded_no_session_tracking"
    identity_dir = scenario_dir / "domains" / "identity"

    # Remove session entities
    session_ids = {"session_b01", "session_b02", "session_b03"}
    entities = sorted(
        [e for e in ENTITIES_IDENTITY_BASELINE if e["id"] not in session_ids],
        key=lambda e: e["id"],
    )

    # Remove authenticated_as (rel_b01-03) and uses_device (rel_b07-09) relationships
    removed_rels = {"rel_b01", "rel_b02", "rel_b03", "rel_b07", "rel_b08", "rel_b09"}
    relationships = sorted(
        [r for r in RELATIONSHIPS_IDENTITY_BASELINE if r["id"] not in removed_rels],
        key=lambda r: r["id"],
    )

    events = sorted(baseline_events, key=lambda e: e["ts"])

    manifest = {
        "scenario_name": "account_substitution_degraded_no_session_tracking",
        "version": "1.0",
        "description": "Degraded: session tracking unavailable; stale-session and device signals absent",
        "investigation_question": "Did garcia.carlos, created by compromised admin mreyes, delete jeff.greenfield and substitute a lookalike account at Greenfield Corp?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "degraded_no_session_tracking",
        "tags": ["account_substitution", "identity_domain", "app_domain", "session_tracking_unavailable"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["session_tracking_unavailable"],
                "notes": "Session correlation unavailable",
            }
        ],
        "notes": "Session tracking unavailable; stale-session and device signals absent",
    }

    expected_tool_output = {
        "scenario_name": "account_substitution_degraded_no_session_tracking",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": [
                        "auth.account.create",
                        "auth.account.delete",
                        "auth.account.disable",
                        "credential.enroll",
                        "privilege.grant",
                    ],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 7,
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
    _write_ndjson(identity_dir / "entities.ndjson", entities)
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", relationships)
    _write_yaml(identity_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)
    _write_app_domain(scenario_dir)

    print(f"Degraded no session tracking: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")


# ---------- degraded 3: no delete event ----------


def generate_degraded_no_delete_event(baseline_events: list[dict]):
    scenario_dir = SCENARIOS_DIR / "account_substitution_degraded_no_delete_event"
    identity_dir = scenario_dir / "domains" / "identity"

    # Remove evt_b013 (auth.account.delete)
    events = [e for e in baseline_events if e["id"] != "evt_b013"]

    # Remove rel_b11 (deleted_by) and principal_jeff_greenfield entity
    relationships = sorted(
        [r for r in RELATIONSHIPS_IDENTITY_BASELINE if r["id"] != "rel_b11"],
        key=lambda r: r["id"],
    )
    entities = sorted(
        [e for e in ENTITIES_IDENTITY_BASELINE if e["id"] != "principal_jeff_greenfield"],
        key=lambda e: e["id"],
    )

    manifest = {
        "scenario_name": "account_substitution_degraded_no_delete_event",
        "version": "1.0",
        "description": "Degraded: account deletion event and deleted account not visible",
        "investigation_question": "Did garcia.carlos, created by compromised admin mreyes, delete jeff.greenfield and substitute a lookalike account at Greenfield Corp?",
        "time_range": {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-31T23:59:59Z",
        },
        "domains": ["identity", "app"],
        "variant": "degraded_no_delete_event",
        "tags": ["account_substitution", "identity_domain", "app_domain", "lifecycle_incomplete"],
    }

    coverage = {
        "domain": "identity",
        "overall_status": "partial",
        "sources": [
            {
                "source_name": "okta",
                "status": "partial",
                "quality_flags": ["lifecycle_incomplete"],
                "notes": "Account deletion events not captured",
            }
        ],
        "notes": "Account lifecycle incomplete; deletion event and deleted account not visible",
    }

    expected_tool_output = {
        "scenario_name": "account_substitution_degraded_no_delete_event",
        "tool_calls": [
            {
                "tool": "search_events",
                "args": {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "actions": [
                        "auth.account.create",
                        "auth.account.delete",
                        "auth.account.disable",
                        "credential.enroll",
                        "privilege.grant",
                    ],
                },
                "expected": {
                    "status": "partial",
                    "event_count": 6,
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
    _write_ndjson(identity_dir / "entities.ndjson", entities)
    _write_ndjson(identity_dir / "events.ndjson", events)
    _write_ndjson(identity_dir / "relationships.ndjson", relationships)
    _write_yaml(identity_dir / "coverage.yaml", coverage)
    _write_json(scenario_dir / "expected_tool_output.json", expected_tool_output)
    _write_app_domain(scenario_dir)

    print(f"Degraded no delete event: {len(entities)} entities, {len(events)} events, {len(relationships)} relationships")


# ---------- main ----------


if __name__ == "__main__":
    baseline_events = generate_baseline()
    generate_degraded_no_sleeper_creation(baseline_events)
    generate_degraded_no_session_tracking(baseline_events)
    generate_degraded_no_delete_event(baseline_events)
    print("Done.")
