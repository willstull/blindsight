"""Unit tests for evidence aggregation functions."""
import pytest

from src.services.investigation.aggregation import (
    aggregate_evidence,
    _aggregate_lifecycle_chains,
    _aggregate_shared_indicators,
    _aggregate_credential_sequences,
    _aggregate_action_bursts,
    EvidenceFact,
)


def _event(
    action: str,
    actor_id: str,
    target_ids: list[str] | None = None,
    ts: str = "2026-01-15T10:00:00Z",
    outcome: str = "succeeded",
    source_ip: str | None = None,
    event_id: str | None = None,
):
    targets = [{"target_entity_id": tid} for tid in (target_ids or [])]
    context = {}
    if source_ip:
        context["source_ip"] = source_ip
    return {
        "id": event_id or f"evt_{action}_{ts}",
        "action": action,
        "actor": {"actor_entity_id": actor_id},
        "targets": targets,
        "ts": ts,
        "outcome": outcome,
        "raw_refs": [],
        "context": context,
    }


def _relationship(rel_type: str, from_id: str, to_id: str):
    return {
        "id": f"rel_{from_id}_{to_id}",
        "relationship_type": rel_type,
        "from_entity_id": from_id,
        "to_entity_id": to_id,
    }


class TestAggregateLifecycleChains:
    def test_delete_and_create_chain(self):
        events = [
            _event("auth.account.delete", "principal_garcia", ["principal_jeff"],
                   ts="2026-03-25T09:05:00Z", event_id="e1"),
            _event("auth.account.create", "principal_garcia", ["principal_jef"],
                   ts="2026-03-25T09:10:00Z", event_id="e2"),
        ]
        focal_ids = ["principal_garcia", "principal_jeff", "principal_jef"]
        facts = _aggregate_lifecycle_chains(events, [], focal_ids)
        assert len(facts) == 1
        assert facts[0].fact_type == "lifecycle_chain"
        assert "principal_garcia" in facts[0].entity_ids
        assert len(facts[0].event_ids) == 2

    def test_no_chain_when_too_far_apart(self):
        events = [
            _event("auth.account.delete", "principal_garcia", ["principal_jeff"],
                   ts="2026-01-01T09:00:00Z", event_id="e1"),
            _event("auth.account.create", "principal_garcia", ["principal_jef"],
                   ts="2026-06-01T09:00:00Z", event_id="e2"),
        ]
        facts = _aggregate_lifecycle_chains(events, [], ["principal_garcia"])
        assert len(facts) == 0

    def test_multiple_chains(self):
        events = [
            _event("auth.account.create", "principal_a", ["principal_b"],
                   ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.account.disable", "principal_a", ["principal_c"],
                   ts="2026-01-10T10:05:00Z", event_id="e2"),
            # Gap > 30 min
            _event("auth.account.delete", "principal_d", ["principal_e"],
                   ts="2026-01-10T12:00:00Z", event_id="e3"),
            _event("auth.account.create", "principal_d", ["principal_f"],
                   ts="2026-01-10T12:05:00Z", event_id="e4"),
        ]
        focal_ids = ["principal_a", "principal_b", "principal_c", "principal_d", "principal_e", "principal_f"]
        facts = _aggregate_lifecycle_chains(events, [], focal_ids)
        assert len(facts) == 2


class TestAggregateSharedIndicators:
    def test_shared_ip_across_actors(self):
        events = [
            _event("auth.login", "principal_alice", [], source_ip="10.0.0.1",
                   ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.login", "principal_bob", [], source_ip="10.0.0.1",
                   ts="2026-01-10T10:05:00Z", event_id="e2"),
        ]
        facts = _aggregate_shared_indicators(events, ["principal_alice", "principal_bob"])
        assert len(facts) == 1
        assert facts[0].fact_type == "shared_indicator"
        assert "10.0.0.1" in facts[0].summary

    def test_no_shared_when_single_actor(self):
        events = [
            _event("auth.login", "principal_alice", [], source_ip="10.0.0.1",
                   ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.login", "principal_alice", [], source_ip="10.0.0.1",
                   ts="2026-01-10T10:05:00Z", event_id="e2"),
        ]
        facts = _aggregate_shared_indicators(events, ["principal_alice"])
        assert len(facts) == 0


class TestAggregateCredentialSequences:
    def test_cross_account_reset_with_followon(self):
        evidence_events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   ts="2026-03-15T02:32:00Z", event_id="e1"),
        ]
        all_events = evidence_events + [
            _event("auth.login", "principal_mgarcia", [],
                   ts="2026-03-15T02:35:00Z", event_id="e2"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        facts = _aggregate_credential_sequences(
            evidence_events, all_events, rels,
            ["principal_cgarcia", "principal_mgarcia"],
        )
        assert len(facts) == 1
        assert facts[0].fact_type == "credential_sequence"
        assert "principal_cgarcia" in facts[0].entity_ids
        assert "principal_mgarcia" in facts[0].entity_ids

    def test_no_sequence_without_followon(self):
        evidence_events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   ts="2026-03-15T02:32:00Z", event_id="e1"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        facts = _aggregate_credential_sequences(
            evidence_events, evidence_events, rels,
            ["principal_cgarcia", "principal_mgarcia"],
        )
        assert len(facts) == 0

    def test_self_reset_excluded(self):
        evidence_events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   ts="2026-01-15T10:00:00Z", event_id="e1"),
        ]
        all_events = evidence_events + [
            _event("auth.login", "principal_alice", [],
                   ts="2026-01-15T10:05:00Z", event_id="e2"),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
        ]
        facts = _aggregate_credential_sequences(
            evidence_events, all_events, rels, ["principal_alice"],
        )
        assert len(facts) == 0


class TestAggregateActionBursts:
    def test_burst_detected(self):
        events = [
            _event("auth.account.create", "principal_a", ["principal_b"],
                   ts=f"2026-01-10T10:{i:02d}:00Z", event_id=f"e{i}")
            for i in range(5)
        ]
        facts = _aggregate_action_bursts(events)
        assert len(facts) == 1
        assert facts[0].fact_type == "action_burst"
        assert facts[0].event_ids == [f"e{i}" for i in range(5)]

    def test_no_burst_below_threshold(self):
        events = [
            _event("auth.account.create", "principal_a", ["principal_b"],
                   ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.account.create", "principal_a", ["principal_c"],
                   ts="2026-01-10T10:01:00Z", event_id="e2"),
        ]
        facts = _aggregate_action_bursts(events)
        assert len(facts) == 0

    def test_different_actions_not_grouped(self):
        events = [
            _event("auth.account.create", "principal_a", [], ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.account.delete", "principal_a", [], ts="2026-01-10T10:01:00Z", event_id="e2"),
            _event("credential.reset", "principal_a", [], ts="2026-01-10T10:02:00Z", event_id="e3"),
        ]
        facts = _aggregate_action_bursts(events)
        assert len(facts) == 0


class TestAggregateEvidence:
    def test_empty_events(self):
        facts = aggregate_evidence([], [], [], [])
        assert facts == []

    def test_combined_output(self):
        evidence_events = [
            _event("auth.account.delete", "principal_garcia", ["principal_jeff"],
                   ts="2026-03-25T09:05:00Z", source_ip="10.0.0.1", event_id="e1"),
            _event("auth.account.create", "principal_garcia", ["principal_jef"],
                   ts="2026-03-25T09:10:00Z", source_ip="10.0.0.1", event_id="e2"),
            _event("auth.account.create", "principal_garcia", ["principal_extra"],
                   ts="2026-03-25T09:11:00Z", source_ip="10.0.0.1", event_id="e3"),
        ]
        all_events = evidence_events + [
            _event("auth.login", "principal_mreyes", [],
                   ts="2026-03-25T09:02:00Z", source_ip="10.0.0.1", event_id="e0"),
        ]
        focal_ids = ["principal_garcia", "principal_mreyes"]
        facts = aggregate_evidence(evidence_events, all_events, [], focal_ids)
        fact_types = {f.fact_type for f in facts}
        assert "lifecycle_chain" in fact_types
        assert "shared_indicator" in fact_types

    def test_fact_type_values(self):
        """All facts have one of the expected fact_type values."""
        evidence_events = [
            _event("auth.account.delete", "principal_a", ["principal_b"],
                   ts="2026-01-10T10:00:00Z", event_id="e1"),
            _event("auth.account.create", "principal_a", ["principal_c"],
                   ts="2026-01-10T10:05:00Z", event_id="e2"),
        ]
        facts = aggregate_evidence(evidence_events, evidence_events, [], ["principal_a"])
        valid_types = {"lifecycle_chain", "shared_indicator", "credential_sequence", "action_burst"}
        for f in facts:
            assert f.fact_type in valid_types
