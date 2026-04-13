"""Unit tests for scoring claim builders and hypothesis construction."""
import pytest

from src.services.investigation.focal import FocalResult
from src.services.investigation.aggregation import EvidenceFact
from src.services.investigation.scoring import (
    build_claims,
    build_hypothesis,
    build_evidence_items,
    extract_coverage_gaps,
    fallback_gap_assessments,
    score_and_classify,
    score_confidence_from_gaps,
    score_likelihood,
    SELF_DIRECTED,
    CROSS_ACTOR,
    CROSS_ACCOUNT_CREDENTIAL,
    SELF_CREDENTIAL,
    SINGLE_IP,
    SHARED_IP,
    IP_SHIFT,
    LIFECYCLE_CREATE,
    LIFECYCLE_DELETE,
    LIFECYCLE_CHAIN,
    CREDENTIAL_SEQUENCE,
    ACTION_BURST,
    PRIVILEGE_SELF_GRANT,
    PRIVILEGE_GRANT,
    PRIVILEGE_FAILED,
    TEMPORAL_CLUSTER,
    FAILED_OUTCOME,
    COVERAGE_GAP,
)
from src.types.core import CoverageObservation, GapAssessment, TimeRange


_TIME_RANGE = TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")


def _cov_envelope(status: str = "complete"):
    return {
        "coverage_report": {
            "id": "cov-001",
            "overall_status": status,
            "sources": [{"source_name": "idp", "status": status}],
        }
    }


def _focal(focal_ids: list[str], primary_id: str | None = None):
    return FocalResult(
        focal_ids=focal_ids,
        primary_id=primary_id,
        confidence=0.9,
        rationale=[],
    )


def _event(
    action: str,
    actor_id: str,
    target_ids: list[str] | None = None,
    ts: str = "2026-01-15T10:00:00Z",
    outcome: str = "succeeded",
    source_ip: str | None = None,
    domain: str = "identity",
):
    targets = [{"target_entity_id": tid} for tid in (target_ids or [])]
    context = {}
    if source_ip:
        context["source_ip"] = source_ip
    return {
        "id": f"evt_{action}_{ts}",
        "domain": domain,
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


def _build(evidence_events, all_events=None, focal=None, rels=None, cov_status="complete"):
    """Helper to build claims in one shot."""
    if all_events is None:
        all_events = evidence_events
    if focal is None:
        actors = set()
        for e in evidence_events:
            actors.add(e["actor"]["actor_entity_id"])
        focal = _focal(sorted(actors), sorted(actors)[0] if len(actors) == 1 else None)
    if rels is None:
        rels = []

    cov = _cov_envelope(cov_status)
    evidence_items = build_evidence_items(evidence_events, cov, _TIME_RANGE)
    claims = build_claims(evidence_events, all_events, focal, evidence_items, cov, _TIME_RANGE, rels)
    return claims


def _categories(claims):
    """Extract set of categories from claims."""
    return {c.category for c in claims}


def _score_and_build(claims, question, events, gap_assessments=None):
    """Helper: score_and_classify + build_hypothesis in one call."""
    sr = score_and_classify(claims, events, question)
    confidence = score_confidence_from_gaps(gap_assessments or [])
    hyp = build_hypothesis(
        scoring_result=sr,
        confidence=confidence,
        gap_assessments=gap_assessments or [],
        investigation_question=question,
    )
    return hyp, sr.scored_claims


class TestSelfDirectedCredentialChange:
    def test_self_directed_produces_claim(self):
        """Alice resets her own credential -- self-directed claim."""
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="198.51.100.10"),
            _event("credential.enroll", "principal_alice", ["credential_alice_mfa"],
                   ts="2026-01-16T14:00:00Z", source_ip="198.51.100.10"),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
            _relationship("has_credential", "principal_alice", "credential_alice_mfa"),
        ]
        focal = _focal(["principal_alice"], "principal_alice")

        claims = _build(events, focal=focal, rels=rels)

        assert SELF_DIRECTED in _categories(claims)

    def test_self_directed_high_likelihood(self):
        """Self-directed + single IP => high likelihood hypothesis."""
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="198.51.100.10"),
        ]
        rels = [_relationship("has_credential", "principal_alice", "credential_alice_pw")]
        focal = _focal(["principal_alice"], "principal_alice")
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, rels)
        hyp, _scored = _score_and_build(claims, "Did alice change creds?", events)

        assert hyp.likelihood == "high"
        assert hyp.confidence == "high"


class TestCrossActorActivity:
    def test_cross_actor_claim(self):
        """mreyes creates garcia_carlos -- cross-actor claim."""
        events = [
            _event("auth.account.create", "principal_mreyes", ["principal_garcia_carlos"],
                   source_ip="198.51.100.10"),
        ]
        focal = _focal(["principal_mreyes", "principal_garcia_carlos"])

        claims = _build(events, focal=focal)

        assert CROSS_ACTOR in _categories(claims)


class TestAccountLifecycle:
    def test_lifecycle_claims(self):
        """Create + delete + create events produce lifecycle claims."""
        events = [
            _event("auth.account.create", "principal_mreyes", ["principal_garcia_carlos"],
                   ts="2026-03-10T09:00:00Z", source_ip="198.51.100.10"),
            _event("auth.account.delete", "principal_garcia_carlos", ["principal_jeff_greenfield"],
                   ts="2026-03-10T09:05:00Z", source_ip="203.0.113.42"),
            _event("auth.account.create", "principal_garcia_carlos", ["principal_jef_greenfield"],
                   ts="2026-03-10T09:10:00Z", source_ip="203.0.113.42"),
        ]
        focal = _focal(["principal_mreyes", "principal_garcia_carlos"])

        claims = _build(events, focal=focal)

        cats = _categories(claims)
        assert LIFECYCLE_CREATE in cats
        assert LIFECYCLE_DELETE in cats
        lifecycle = [c for c in claims if c.category in {LIFECYCLE_CREATE, LIFECYCLE_DELETE}]
        assert len(lifecycle) >= 3


class TestPrivilegeSelfGrant:
    def test_self_grant_claim(self):
        """rchen_ops grants self superadmin."""
        events = [
            _event("privilege.grant", "principal_rchen_ops", ["principal_rchen_ops"],
                   source_ip="203.0.113.42"),
        ]
        focal = _focal(["principal_rchen_ops"], "principal_rchen_ops")

        claims = _build(events, focal=focal)

        assert PRIVILEGE_SELF_GRANT in _categories(claims)


class TestIPOverlap:
    def test_shared_ip_claim(self):
        """Two actors sharing 203.0.113.42 alongside distinct IPs."""
        all_events = [
            _event("auth.login", "principal_alice", [], source_ip="203.0.113.42",
                   ts="2026-01-15T10:00:00Z"),
            _event("auth.login", "principal_bob", [], source_ip="203.0.113.42",
                   ts="2026-01-15T10:01:00Z"),
            _event("auth.login", "principal_alice", [], source_ip="198.51.100.10",
                   ts="2026-01-15T10:02:00Z"),
        ]
        evidence_events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="203.0.113.42"),
        ]
        focal = _focal(["principal_alice", "principal_bob"])
        rels = [_relationship("has_credential", "principal_alice", "credential_alice_pw")]
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(evidence_events, cov, _TIME_RANGE)
        claims = build_claims(
            evidence_events, all_events, focal, evidence_items, cov, _TIME_RANGE, rels,
        )

        assert SHARED_IP in _categories(claims)


class TestTemporalClustering:
    def test_cluster_claim(self):
        """5 events in 4 minutes produce a clustering claim."""
        events = [
            _event("auth.account.create", "principal_a", ["principal_b"],
                   ts="2026-01-15T10:00:00Z"),
            _event("privilege.grant", "principal_a", ["principal_b"],
                   ts="2026-01-15T10:01:00Z"),
            _event("auth.account.delete", "principal_b", ["principal_c"],
                   ts="2026-01-15T10:02:00Z"),
            _event("auth.account.create", "principal_b", ["principal_d"],
                   ts="2026-01-15T10:03:00Z"),
            _event("privilege.grant", "principal_b", ["principal_d"],
                   ts="2026-01-15T10:04:00Z"),
        ]
        focal = _focal(["principal_a", "principal_b"])

        claims = _build(events, focal=focal)

        assert TEMPORAL_CLUSTER in _categories(claims)


class TestFailedOutcomes:
    def test_failed_outcome_claim(self):
        """privilege.grant with outcome=failed produces failed-outcome claim."""
        events = [
            _event("privilege.grant", "principal_mgarcia", ["principal_admin"],
                   outcome="failed"),
        ]
        focal = _focal(["principal_mgarcia"], "principal_mgarcia")

        claims = _build(events, focal=focal)

        assert FAILED_OUTCOME in _categories(claims)


class TestDegradedCoverage:
    def test_coverage_claim_and_confidence(self):
        """Partial coverage produces neutral coverage claim and lower confidence."""
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="198.51.100.10"),
        ]
        rels = [_relationship("has_credential", "principal_alice", "credential_alice_pw")]
        focal = _focal(["principal_alice"], "principal_alice")
        cov = _cov_envelope("partial")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, rels)

        cov_claims = [c for c in claims if c.category == COVERAGE_GAP]
        assert len(cov_claims) >= 1
        assert cov_claims[0].polarity == "neutral"

        # With partial coverage and no LLM, fallback_gap_assessments produces
        # relevant gaps -> confidence "medium"
        gaps = extract_coverage_gaps(cov, [])
        gap_assessments = fallback_gap_assessments(gaps)
        hyp, _scored = _score_and_build(claims, "question", events, gap_assessments)
        assert hyp.confidence == "medium"


class TestNoEvidenceEvents:
    def test_no_evidence_neutral(self):
        """Empty event list produces neutral assessment with low likelihood."""
        focal = _focal(["principal_alice"], "principal_alice")
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items([], cov, _TIME_RANGE)
        claims = build_claims([], [], focal, evidence_items, cov, _TIME_RANGE, [])
        hyp, _scored = _score_and_build(claims, "question", [])

        assert hyp.likelihood == "low"


class TestHypothesisPatternClassification:
    def test_lifecycle_cross_actor_pattern(self):
        """Lifecycle + cross-actor claims => account manipulation hypothesis."""
        events = [
            _event("auth.account.create", "principal_mreyes", ["principal_garcia_carlos"],
                   ts="2026-03-10T09:00:00Z", source_ip="198.51.100.10"),
            _event("auth.account.delete", "principal_garcia_carlos", ["principal_jeff_greenfield"],
                   ts="2026-03-10T09:05:00Z", source_ip="203.0.113.42"),
        ]
        focal = _focal(["principal_mreyes", "principal_garcia_carlos"])
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, [])
        hyp, _scored = _score_and_build(claims, "investigation", events)

        assert "self-service" not in hyp.statement.lower()
        assert any(word in hyp.statement.lower() for word in [
            "manipulation", "account", "cross-account",
        ])
        assert hyp.likelihood == "high"

    def test_privilege_escalation_pattern(self):
        """Self-grant claim => privilege escalation hypothesis."""
        events = [
            _event("privilege.grant", "principal_rchen_ops", ["principal_rchen_ops"],
                   source_ip="203.0.113.42"),
        ]
        focal = _focal(["principal_rchen_ops"], "principal_rchen_ops")
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, [])
        hyp, _scored = _score_and_build(claims, "investigation", events)

        assert "escalation" in hyp.statement.lower()
        assert hyp.likelihood == "high"

    def test_score_and_classify_returns_polarity_assigned_claims(self):
        """score_and_classify returns claims with polarity set, not all neutral."""
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="198.51.100.10"),
        ]
        rels = [_relationship("has_credential", "principal_alice", "credential_alice_pw")]
        focal = _focal(["principal_alice"], "principal_alice")
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, rels)

        assert all(c.polarity == "neutral" for c in claims)

        sr = score_and_classify(claims, events, "question")

        polarities = {c.polarity for c in sr.scored_claims}
        assert "supports" in polarities, (
            f"Expected some supporting claims in scored output, got: "
            f"{[(c.category, c.polarity) for c in sr.scored_claims]}"
        )

    def test_multi_signal_not_neutral_fallback(self):
        """Scenario with lifecycle + privilege + cross-actor should score high."""
        events = [
            _event("auth.account.create", "principal_kwilson", ["principal_rchen_ops"],
                   ts="2026-03-10T09:00:00Z", source_ip="198.51.100.10"),
            _event("privilege.grant", "principal_rchen_ops", ["principal_rchen_ops"],
                   ts="2026-03-10T09:05:00Z", source_ip="203.0.113.42"),
            _event("privilege.grant", "principal_kwilson", ["principal_rchen_ops"],
                   ts="2026-03-10T09:06:00Z", source_ip="198.51.100.10"),
        ]
        focal = _focal(["principal_kwilson", "principal_rchen_ops"])
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, [])
        hyp, scored = _score_and_build(claims, "investigation", events)

        assert hyp.likelihood == "high", (
            f"Multi-signal scenario should be high. "
            f"Hypothesis: {hyp.statement}. "
            f"Categories: {[(c.category, c.polarity) for c in scored]}"
        )

    def test_credential_takeover_pattern(self):
        """Cross-account credential reset + cross-actor => credential takeover."""
        events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   ts="2026-03-15T02:32:00Z", source_ip="203.0.113.42"),
            _event("auth.account.delete", "principal_mgarcia", ["principal_dlopez"],
                   ts="2026-03-15T02:40:00Z", source_ip="203.0.113.42"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        focal = _focal(["principal_cgarcia", "principal_mgarcia"])
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        claims = build_claims(events, events, focal, evidence_items, cov, _TIME_RANGE, rels)
        hyp, scored = _score_and_build(claims, "investigation", events)

        assert "credential takeover" in hyp.statement.lower(), (
            f"Expected credential takeover hypothesis, got: {hyp.statement}"
        )
        assert hyp.likelihood == "high"


class TestCredentialTargeting:
    def test_cross_account_credential_claim(self):
        """cgarcia resets mgarcia's credential -- cross-account credential claim."""
        events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   source_ip="203.0.113.42"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        focal = _focal(["principal_cgarcia", "principal_mgarcia"])

        claims = _build(events, focal=focal, rels=rels)

        assert CROSS_ACCOUNT_CREDENTIAL in _categories(claims)

    def test_self_credential_claim(self):
        """alice resets own credential -- self credential claim, not cross-account."""
        events = [
            _event("credential.reset", "principal_alice", ["credential_alice_pw"],
                   source_ip="198.51.100.10"),
        ]
        rels = [
            _relationship("has_credential", "principal_alice", "credential_alice_pw"),
        ]
        focal = _focal(["principal_alice"], "principal_alice")

        claims = _build(events, focal=focal, rels=rels)

        assert CROSS_ACCOUNT_CREDENTIAL not in _categories(claims)
        assert SELF_CREDENTIAL in _categories(claims)


class TestCategoryFieldPresent:
    """Every claim produced by build_claims has a non-default category."""

    def test_all_claims_categorized(self):
        """No claim should have the default 'uncategorized' category."""
        events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   ts="2026-03-15T02:32:00Z", source_ip="203.0.113.42"),
            _event("auth.account.delete", "principal_mgarcia", ["principal_dlopez"],
                   ts="2026-03-15T02:40:00Z", source_ip="203.0.113.42"),
            _event("privilege.grant", "principal_mgarcia", ["principal_mgarcia"],
                   ts="2026-03-15T02:45:00Z", outcome="failed", source_ip="203.0.113.42"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        focal = _focal(["principal_cgarcia", "principal_mgarcia"])

        claims = _build(events, focal=focal, rels=rels)

        uncategorized = [c for c in claims if c.category == "uncategorized"]
        assert uncategorized == [], (
            f"Found uncategorized claims: "
            f"{[(c.statement, c.category) for c in uncategorized]}"
        )


class TestAggregatedFactsClaims:
    """Verify aggregated facts produce supporting claims via build_claims."""

    def _make_fact(self, fact_type, summary="test", event_ids=None, entity_ids=None):
        return EvidenceFact(
            fact_type=fact_type,
            summary=summary,
            event_ids=event_ids or ["evt-1"],
            entity_ids=entity_ids or ["principal_a"],
            time_range_start="2026-01-10T10:00:00Z",
            time_range_end="2026-01-10T10:05:00Z",
            confidence=0.85,
        )

    def test_lifecycle_chain_supports_account_manipulation(self):
        """lifecycle_chain fact produces supporting claim in account_manipulation."""
        events = [
            _event("auth.account.create", "principal_a", ["principal_b"],
                   ts="2026-01-10T10:00:00Z"),
            _event("auth.account.delete", "principal_a", ["principal_c"],
                   ts="2026-01-10T10:05:00Z"),
        ]
        focal = _focal(["principal_a", "principal_b"])
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        fact = self._make_fact(
            "lifecycle_chain",
            "principal_a performed delete + create within 5 minutes",
            event_ids=[e["id"] for e in events],
            entity_ids=["principal_a", "principal_b", "principal_c"],
        )
        claims = build_claims(
            events, events, focal, evidence_items, cov, _TIME_RANGE, [],
            aggregated_facts=[fact],
        )
        hyp, scored = _score_and_build(claims, "investigation", events)

        chain_claims = [c for c in scored if c.category == LIFECYCLE_CHAIN]
        assert len(chain_claims) == 1
        assert chain_claims[0].polarity == "supports"

    def test_credential_sequence_supports_credential_takeover(self):
        """credential_sequence fact produces supporting claim in credential_takeover."""
        events = [
            _event("credential.reset", "principal_cgarcia", ["credential_mgarcia_pw"],
                   ts="2026-03-15T02:32:00Z", source_ip="203.0.113.42"),
        ]
        rels = [
            _relationship("has_credential", "principal_mgarcia", "credential_mgarcia_pw"),
        ]
        focal = _focal(["principal_cgarcia", "principal_mgarcia"])
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        fact = self._make_fact(
            "credential_sequence",
            "principal_cgarcia reset credential for principal_mgarcia",
            event_ids=[e["id"] for e in events],
            entity_ids=["principal_cgarcia", "principal_mgarcia"],
        )
        claims = build_claims(
            events, events, focal, evidence_items, cov, _TIME_RANGE, rels,
            aggregated_facts=[fact],
        )
        hyp, scored = _score_and_build(claims, "investigation", events)

        seq_claims = [c for c in scored if c.category == CREDENTIAL_SEQUENCE]
        assert len(seq_claims) == 1
        assert seq_claims[0].polarity == "supports"

    def test_unknown_fact_type_stays_neutral(self):
        """An unrecognized fact_type produces a claim with no polarity rule match."""
        events = [
            _event("auth.login", "principal_alice", [],
                   ts="2026-01-15T10:00:00Z", source_ip="198.51.100.10"),
        ]
        focal = _focal(["principal_alice"], "principal_alice")
        cov = _cov_envelope("complete")
        evidence_items = build_evidence_items(events, cov, _TIME_RANGE)
        fact = self._make_fact(
            "unknown_aggregation_type",
            "Some unknown aggregation",
        )
        claims = build_claims(
            events, events, focal, evidence_items, cov, _TIME_RANGE, [],
            aggregated_facts=[fact],
        )
        hyp, scored = _score_and_build(claims, "question", events)

        unknown_claims = [c for c in scored if c.category == "unknown_aggregation_type"]
        assert len(unknown_claims) == 1
        assert unknown_claims[0].polarity == "neutral"


# ---------------------------------------------------------------------------
# New tests for band scoring and gap assessment
# ---------------------------------------------------------------------------


class TestLikelihoodBandMapping:
    """Test score_likelihood() directly with various claim sets."""

    def _claim(self, polarity="supports", confidence=0.85, category="test"):
        from src.types.core import Claim
        return Claim(
            id="test",
            tlp="AMBER",
            statement="test",
            polarity=polarity,
            confidence=confidence,
            category=category,
        )

    def test_all_supporting_high_confidence(self):
        claims = [self._claim("supports", 0.9), self._claim("supports", 0.85)]
        assert score_likelihood(claims, [{"id": "e1"}]) == "high"

    def test_mixed_support_contradiction(self):
        claims = [self._claim("supports", 0.5), self._claim("contradicts", 0.5)]
        assert score_likelihood(claims, [{"id": "e1"}]) == "medium"

    def test_only_contradicting(self):
        claims = [self._claim("contradicts", 0.3)]
        assert score_likelihood(claims, [{"id": "e1"}]) == "low"

    def test_no_claims_no_events(self):
        assert score_likelihood([], []) == "low"

    def test_no_claims_some_events(self):
        assert score_likelihood([], [{"id": "e1"}]) == "medium"

    def test_weak_supporting(self):
        claims = [self._claim("supports", 0.55)]
        assert score_likelihood(claims, [{"id": "e1"}]) == "medium"


class TestConfidenceBandFromGaps:
    """Test score_confidence_from_gaps() with various gap assessments."""

    def _gap(self, relevance="relevant", could_change=False):
        return GapAssessment(
            gap_id="test", relevance=relevance,
            could_change_conclusion=could_change, reason="test",
        )

    def test_empty_gaps(self):
        assert score_confidence_from_gaps([]) == "high"

    def test_minor_only(self):
        assert score_confidence_from_gaps([self._gap("minor")]) == "high"

    def test_irrelevant_only(self):
        assert score_confidence_from_gaps([self._gap("irrelevant")]) == "high"

    def test_relevant_gap(self):
        assert score_confidence_from_gaps([self._gap("relevant")]) == "medium"

    def test_critical_could_not_change(self):
        assert score_confidence_from_gaps([self._gap("critical", False)]) == "medium"

    def test_critical_could_change(self):
        assert score_confidence_from_gaps([self._gap("critical", True)]) == "low"


class TestFallbackGapAssessments:
    """Test fallback_gap_assessments() with generic and real fixture notes."""

    def test_missing_source(self):
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "missing", "description": "idp is missing"}]
        assessments = fallback_gap_assessments(gaps)
        assert len(assessments) == 1
        assert assessments[0].relevance == "critical"
        assert assessments[0].could_change_conclusion is True

    def test_partial_with_retention_gap(self):
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "partial",
                 "description": "Retention gap: events before 2026-03-01 unavailable"}]
        assessments = fallback_gap_assessments(gaps)
        assert assessments[0].relevance == "critical"
        assert assessments[0].could_change_conclusion is True

    def test_partial_with_session_tracking(self):
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "partial",
                 "description": "No session tracking available for this tenant"}]
        assessments = fallback_gap_assessments(gaps)
        assert assessments[0].relevance == "critical"
        assert assessments[0].could_change_conclusion is True

    def test_partial_with_underscored_keyword(self):
        """Normalization handles underscores in keywords."""
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "partial",
                 "description": "no_session_tracking in environment"}]
        assessments = fallback_gap_assessments(gaps)
        assert assessments[0].relevance == "critical"

    def test_partial_generic(self):
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "partial",
                 "description": "Partial data for display_name field"}]
        assessments = fallback_gap_assessments(gaps)
        assert assessments[0].relevance == "relevant"
        assert assessments[0].could_change_conclusion is False

    def test_empty_gaps(self):
        assert fallback_gap_assessments([]) == []


class TestExtractCoverageGaps:
    """Test extract_coverage_gaps() with coverage envelopes and observations."""

    def test_complete_coverage_no_gaps(self):
        cov = {"coverage_report": {
            "overall_status": "complete",
            "sources": [{"source_name": "idp", "status": "complete"}],
        }}
        gaps = extract_coverage_gaps(cov, [])
        assert gaps == []

    def test_partial_source(self):
        cov = {"coverage_report": {
            "overall_status": "partial",
            "sources": [{"source_name": "idp", "status": "partial", "notes": "Missing MFA data"}],
        }}
        gaps = extract_coverage_gaps(cov, [])
        assert len(gaps) == 1
        assert gaps[0]["gap_id"] == "source_idp"

    def test_observations_coverage_gap_included(self):
        cov = {"coverage_report": {"overall_status": "complete", "sources": []}}
        obs = [CoverageObservation(
            tool_name="search_events", stage="Search",
            observation_type="coverage_gap", description="retention gap detected",
        )]
        gaps = extract_coverage_gaps(cov, obs)
        assert len(gaps) == 1

    def test_observations_empty_result_excluded(self):
        cov = {"coverage_report": {"overall_status": "complete", "sources": []}}
        obs = [CoverageObservation(
            tool_name="get_neighbors", stage="Correlate",
            observation_type="empty_result", description="0 neighbors",
            result_count=0,
        )]
        gaps = extract_coverage_gaps(cov, obs)
        assert gaps == []


class TestBuildHypothesis:
    """Test build_hypothesis() assembly from _ScoringResult + gap assessments."""

    def test_basic_construction(self):
        sr = score_and_classify([], [], "test question")
        hyp = build_hypothesis(
            scoring_result=sr,
            confidence="high",
            gap_assessments=[],
            investigation_question="test question",
        )
        assert hyp.likelihood == sr.likelihood
        assert hyp.confidence == "high"
        assert hyp.gap_assessments == []

    def test_gap_assessments_populated(self):
        sr = score_and_classify([], [], "test question")
        ga = GapAssessment(
            gap_id="g1", relevance="critical",
            could_change_conclusion=True, reason="missing MFA",
        )
        hyp = build_hypothesis(
            scoring_result=sr, confidence="low",
            gap_assessments=[ga], investigation_question="test",
        )
        assert len(hyp.gap_assessments) == 1
        assert hyp.gap_assessments[0].gap_id == "g1"

    def test_gaps_derived_from_critical_and_relevant(self):
        sr = score_and_classify([], [], "test question")
        gas = [
            GapAssessment(gap_id="g1", relevance="critical", could_change_conclusion=True, reason="r"),
            GapAssessment(gap_id="g2", relevance="relevant", could_change_conclusion=False, reason="r"),
            GapAssessment(gap_id="g3", relevance="minor", could_change_conclusion=False, reason="r"),
        ]
        hyp = build_hypothesis(
            scoring_result=sr, confidence="low",
            gap_assessments=gas, investigation_question="test",
        )
        assert "g1" in hyp.gaps
        assert "g2" in hyp.gaps
        assert "g3" not in hyp.gaps
