"""Unit tests for focal entity resolution."""
import pytest

from src.services.investigation.focal import resolve_focal_principals, FocalResult


def _principal(pid: str, display_name: str = "", refs: list | None = None):
    return {
        "id": pid,
        "display_name": display_name or pid.removeprefix("principal_"),
        "entity_type": "principal",
        "kind": "user",
        "refs": refs or [],
    }


def _event(action: str, actor_id: str, target_ids: list[str] | None = None):
    targets = [{"target_entity_id": tid} for tid in (target_ids or [])]
    return {
        "id": f"evt_{action}",
        "action": action,
        "actor": {"actor_entity_id": actor_id},
        "targets": targets,
        "ts": "2026-01-15T10:00:00Z",
        "outcome": "succeeded",
    }


def _relationship(rel_type: str, from_id: str, to_id: str):
    return {
        "id": f"rel_{from_id}_{to_id}",
        "relationship_type": rel_type,
        "from_entity_id": from_id,
        "to_entity_id": to_id,
    }


class TestResolveFocalPrincipals:
    def test_single_principal_with_evidence(self):
        """Single principal who is the actor returns as primary with high confidence."""
        principals = [_principal("principal_alice", "alice@example.com")]
        events = [_event("credential.reset", "principal_alice", ["credential_alice_pw"])]
        rels = [_relationship("has_credential", "principal_alice", "credential_alice_pw")]

        result = resolve_focal_principals("Did alice change creds?", None, principals, events, rels)

        assert result.primary_id == "principal_alice"
        assert result.focal_ids == ["principal_alice"]
        assert result.confidence >= 0.7

    def test_multiple_principals_clear_winner(self):
        """One principal is much more active than others -- selected as primary."""
        principals = [
            _principal("principal_alice"),
            _principal("principal_bob"),
        ]
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"]),
            _event("credential.enroll", "principal_alice", ["credential_alice_mfa"]),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
            _relationship("has_credential", "principal_alice", "credential_alice_mfa"),
        ]

        result = resolve_focal_principals("investigation", None, principals, events, rels)

        assert result.primary_id == "principal_alice"
        assert "principal_alice" in result.focal_ids
        assert result.confidence >= 0.7

    def test_multiple_principals_tied_activity(self):
        """Two principals with equal activity -- primary is None, lower confidence."""
        principals = [
            _principal("principal_alice"),
            _principal("principal_bob"),
        ]
        events = [
            _event("credential.reset", "principal_alice", ["credential_bob_pw"]),
            _event("credential.reset", "principal_bob", ["credential_alice_pw"]),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
            _relationship("has_credential", "principal_bob", "credential_bob_pw"),
        ]

        result = resolve_focal_principals("investigation", None, principals, events, rels)

        assert result.primary_id is None
        assert len(result.focal_ids) == 2
        assert result.confidence < 0.7

    def test_hint_overrides_activity(self):
        """principal_hint matching overrides activity-based selection."""
        principals = [
            _principal("principal_alice"),
            _principal("principal_bob"),
        ]
        events = [
            _event("credential.reset", "principal_bob", ["credential_alice_pw"]),
            _event("credential.enroll", "principal_bob", ["credential_bob_mfa"]),
        ]
        rels = []

        result = resolve_focal_principals(
            "investigation", "principal_alice", principals, events, rels,
        )

        assert result.primary_id == "principal_alice"
        assert result.confidence >= 0.8

    def test_question_contains_principal_name(self):
        """Question mentioning a principal name selects it."""
        principals = [
            _principal("principal_alice", "alice@example.com"),
            _principal("principal_bob", "bob@example.com"),
        ]
        events = [_event("credential.reset", "principal_alice", [])]
        rels = []

        result = resolve_focal_principals(
            "Did alice@example.com change credentials?", None, principals, events, rels,
        )

        assert result.primary_id == "principal_alice"

    def test_no_evidence_events(self):
        """No evidence events -- all principals focal with low confidence."""
        principals = [
            _principal("principal_alice"),
            _principal("principal_bob"),
        ]

        result = resolve_focal_principals("investigation", None, principals, [], [])

        assert len(result.focal_ids) == 2
        assert result.primary_id is None
        assert result.confidence <= 0.3

    def test_target_to_principal_resolution(self):
        """Evidence targeting a credential resolves to the owning principal."""
        principals = [
            _principal("principal_alice"),
            _principal("principal_bob"),
        ]
        # Bob resets Alice's credential
        events = [
            _event("credential.reset", "principal_bob", ["credential_alice_pw"]),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
        ]

        result = resolve_focal_principals("investigation", None, principals, events, rels)

        # Both should be focal: bob as actor, alice as resolved target
        assert "principal_alice" in result.focal_ids
        assert "principal_bob" in result.focal_ids

    def test_empty_principals(self):
        """No principals returns empty result."""
        result = resolve_focal_principals("question", None, [], [], [])

        assert result.focal_ids == []
        assert result.primary_id is None
        assert result.confidence == 0.0

    def test_hint_partial_match(self):
        """Hint with partial ID match still works."""
        principals = [_principal("principal_alice", "alice@example.com")]
        events = [_event("credential.reset", "principal_alice", [])]

        result = resolve_focal_principals("question", "alice", principals, events, [])

        assert result.primary_id == "principal_alice"

    def test_question_matches_multiple_principals(self):
        """Question referencing multiple principals doesn't force a single primary."""
        principals = [
            _principal("principal_mgarcia", "mgarcia@meridian-systems.example"),
            _principal("principal_cgarcia", "cgarcia@meridian-systems.example"),
        ]
        events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"]),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]

        result = resolve_focal_principals(
            "Was mgarcia taken over via cgarcia?", None, principals, events, rels,
        )

        assert "principal_mgarcia" in result.focal_ids
        assert "principal_cgarcia" in result.focal_ids
