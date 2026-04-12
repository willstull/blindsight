"""Unit tests for pipeline helper functions.

Tests for _coverage_observations_from_response(),
_build_gap_assessment_prompt(), and _merge_coverage_envelopes().
"""
from src.services.investigation.pipeline import (
    _coverage_observations_from_response,
    _build_gap_assessment_prompt,
    _merge_coverage_envelopes,
)
from src.types.core import CoverageObservation, GapAssessment


class TestCoverageObservationsFromResponse:
    """Test _coverage_observations_from_response() classification."""

    def test_complete_response_no_observations(self):
        """Complete coverage, results present -> no observations."""
        response = {
            "coverage_report": {
                "overall_status": "complete",
                "sources": [{"source_name": "idp", "status": "complete"}],
            },
            "entities": [{"id": "e1"}],
        }
        obs = _coverage_observations_from_response("Test", "search_entities", response)
        assert obs == []

    def test_partial_source_coverage_gap(self):
        """Partial source status -> coverage_gap observation."""
        response = {
            "coverage_report": {
                "sources": [{"source_name": "idp", "status": "partial",
                             "notes": "Retention gap before March"}],
            },
        }
        obs = _coverage_observations_from_response("Check", "describe_coverage", response)
        coverage_gaps = [o for o in obs if o.observation_type == "coverage_gap"]
        assert len(coverage_gaps) == 1
        assert "Retention gap" in coverage_gaps[0].description

    def test_missing_source_coverage_gap(self):
        """Missing source -> coverage_gap observation."""
        response = {
            "coverage_report": {
                "sources": [{"source_name": "mfa_stream", "status": "missing",
                             "notes": "MFA source unavailable"}],
            },
        }
        obs = _coverage_observations_from_response("Check", "describe_coverage", response)
        coverage_gaps = [o for o in obs if o.observation_type == "coverage_gap"]
        assert len(coverage_gaps) == 1

    def test_missing_fields_observation(self):
        """Source with missing_fields -> missing_fields observation."""
        response = {
            "coverage_report": {
                "sources": [{"source_name": "idp", "status": "partial",
                             "missing_fields": ["display_name", "source_ip"]}],
            },
        }
        obs = _coverage_observations_from_response("Check", "describe_coverage", response)
        mf = [o for o in obs if o.observation_type == "missing_fields"]
        assert len(mf) == 1
        assert "display_name" in mf[0].description

    def test_limitations_observation(self):
        """Response with limitations array -> limitation observations."""
        response = {
            "coverage_report": {"sources": []},
            "limitations": ["Rate limited: only 100 of 500 events returned"],
        }
        obs = _coverage_observations_from_response("Search", "search_events", response)
        lims = [o for o in obs if o.observation_type == "limitation"]
        assert len(lims) == 1
        assert "Rate limited" in lims[0].description

    def test_empty_results_are_empty_result_not_coverage_gap(self):
        """Empty events/entities/relationships -> empty_result, NOT coverage_gap."""
        response = {
            "coverage_report": {"sources": []},
            "entities": [],
            "events": [],
            "relationships": [],
        }
        obs = _coverage_observations_from_response("Correlate", "get_neighbors", response)
        for o in obs:
            assert o.observation_type == "empty_result", (
                f"Empty result should be 'empty_result', got '{o.observation_type}'"
            )
        assert len(obs) == 3  # one per key


class TestGapAssessmentPrompt:
    """Test _build_gap_assessment_prompt() contract."""

    def _make_claim(self, polarity="supports", statement="Test claim", confidence=0.8):
        from src.types.core import Claim
        return Claim(
            id="c1", tlp="AMBER", statement=statement,
            polarity=polarity, confidence=confidence, category="test",
        )

    def test_prompt_includes_contract_elements(self):
        """Prompt must include all contract elements."""
        gaps = [{"gap_id": "g1", "source_name": "idp", "status": "partial",
                 "description": "MFA source unavailable"}]
        claims = [
            self._make_claim("supports", "Actor performed credential reset", 0.85),
            self._make_claim("contradicts", "Self-directed activity", 0.6),
        ]
        obs = [CoverageObservation(
            tool_name="search_events", stage="Search",
            observation_type="empty_result",
            description="search_events returned 0 events", result_count=0,
        )]
        prompt = _build_gap_assessment_prompt(
            "Evidence indicates credential takeover",
            claims, gaps, obs,
        )

        # Hypothesis
        assert "credential takeover" in prompt

        # Claims
        assert "credential reset" in prompt
        assert "Self-directed" in prompt

        # Gap to classify
        assert "g1" in prompt
        assert "MFA source unavailable" in prompt

        # Observation context
        assert "empty_result" in prompt

        # Allowed relevance values
        assert "critical" in prompt
        assert "relevant" in prompt
        assert "minor" in prompt
        assert "irrelevant" in prompt

        # could_change_conclusion definition
        assert "could_change_conclusion" in prompt
        assert "support a different hypothesis" in prompt
        assert "materially weaken" in prompt

        # Instructions
        assert "Classify ONLY the gaps listed above" in prompt
        assert "Do NOT invent" in prompt


class TestMergeCoverageEnvelopes:
    """Test _merge_coverage_envelopes() combining multi-domain coverage."""

    def _envelope(self, domain, status, source_name, source_status, notes=None):
        return {
            "coverage_report": {
                "domain": domain,
                "overall_status": status,
                "sources": [{"source_name": source_name, "status": source_status}],
                "notes": notes,
            }
        }

    def test_empty_inputs(self):
        result = _merge_coverage_envelopes()
        assert result == {}

    def test_single_envelope_prefixes_sources(self):
        env = self._envelope("identity", "complete", "okta", "complete")
        result = _merge_coverage_envelopes(env)
        report = result["coverage_report"]
        assert report["overall_status"] == "complete"
        assert len(report["sources"]) == 1
        assert report["sources"][0]["source_name"] == "identity:okta"

    def test_both_complete(self):
        env1 = self._envelope("identity", "complete", "okta", "complete")
        env2 = self._envelope("app", "complete", "app_audit", "complete")
        result = _merge_coverage_envelopes(env1, env2)
        report = result["coverage_report"]
        assert report["overall_status"] == "complete"
        assert len(report["sources"]) == 2
        source_names = {s["source_name"] for s in report["sources"]}
        assert "identity:okta" in source_names
        assert "app:app_audit" in source_names

    def test_identity_complete_app_partial(self):
        env1 = self._envelope("identity", "complete", "okta", "complete")
        env2 = self._envelope("app", "partial", "app_audit", "partial")
        result = _merge_coverage_envelopes(env1, env2)
        assert result["coverage_report"]["overall_status"] == "partial"

    def test_identity_partial_app_missing(self):
        env1 = self._envelope("identity", "partial", "okta", "partial")
        env2 = self._envelope("app", "missing", "app_audit", "missing")
        result = _merge_coverage_envelopes(env1, env2)
        assert result["coverage_report"]["overall_status"] == "missing"
