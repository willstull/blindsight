#!/usr/bin/env python3
"""Demo: deterministic local investigation with structured analytic types.

Runs the investigation pipeline locally (no LLM, no API calls) and produces
structured EvidenceItem, Claim, and Hypothesis objects with mechanical scoring.
Persists to the case store and verifies the round-trip.

For the LLM-driven version that goes through the MCP interface, see demo_agent.py.

Usage:
    poetry run python scripts/demo_local.py
"""
import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._investigation import (
    heading, step, narrate, load_manifest,
    discover_scenarios, select_scenarios, investigate,
)
from src.services.case.ingest import (
    ingest_evidence_items, ingest_claims, ingest_hypotheses,
)
from src.services.case.json_helpers import from_json
from src.types.core import EvidenceItem, Claim, Hypothesis, Ref, TimeRange
from src.utils.ulid import generate_ulid


def _build_evidence_items(
    cred_events: list[dict],
    cov_envelope: dict,
    manifest: dict,
) -> list[EvidenceItem]:
    """Wrap discovered events and coverage into EvidenceItem objects."""
    items = []

    # One evidence item per credential change event
    for evt in cred_events:
        raw_refs = []
        for rr in evt.get("raw_refs", []):
            raw_refs.append(Ref(**rr))

        targets = evt.get("targets", [])
        related_entity_ids = [t["target_entity_id"] for t in targets]
        related_entity_ids.append(evt["actor"]["actor_entity_id"])

        items.append(EvidenceItem(
            id=generate_ulid(),
            tlp="AMBER",
            domain="identity",
            summary=f"{evt['action']} by {evt['actor']['actor_entity_id']} "
                    f"at {evt['ts']} (outcome={evt['outcome']})",
            raw_refs=raw_refs,
            collected_at=evt["ts"],
            related_entity_ids=related_entity_ids,
            related_event_ids=[evt["id"]],
        ))

    # Coverage as evidence
    cov = cov_envelope["coverage_report"]
    items.append(EvidenceItem(
        id=generate_ulid(),
        tlp="AMBER",
        domain="identity",
        summary=f"Coverage report: {cov['overall_status']} "
                f"({len(cov.get('sources', []))} source(s))",
        raw_refs=[],
        collected_at=manifest["time_range"].end,
        related_entity_ids=[],
        related_event_ids=[],
    ))

    return items


def _build_claims(
    cred_events: list[dict],
    source_ips: set[str],
    subject_id: str,
    evidence_items: list[EvidenceItem],
    cov_envelope: dict,
    time_range: TimeRange,
) -> list[Claim]:
    """Create Claim objects from correlation findings."""
    claims = []
    evidence_ids = [ei.id for ei in evidence_items]
    cov_status = cov_envelope["coverage_report"]["overall_status"]

    if cred_events:
        all_self_directed = all(
            evt["actor"]["actor_entity_id"] == subject_id
            for evt in cred_events
        )

        if all_self_directed:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"All {len(cred_events)} credential change(s) were "
                          f"self-directed by {subject_id}",
                polarity="supports",
                confidence=0.95 if cov_status == "complete" else 0.6,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))

        single_ip = len(source_ips) <= 1
        if single_ip and source_ips:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"All activity from single source IP "
                          f"({', '.join(source_ips)})",
                polarity="supports",
                confidence=0.9 if cov_status == "complete" else 0.5,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))
        elif len(source_ips) > 1:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Multiple source IPs observed ({len(source_ips)}): "
                          f"{', '.join(sorted(source_ips))}",
                polarity="contradicts",
                confidence=0.8,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))

    # Coverage claim
    if cov_status != "complete":
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"Coverage is {cov_status} -- findings are constrained "
                      f"by data gaps",
            polarity="neutral",
            confidence=1.0,
            backed_by_evidence_ids=[evidence_ids[-1]] if evidence_ids else [],
            time_range=time_range,
        ))

    return claims


def _build_hypothesis(
    claims: list[Claim],
    cov_envelope: dict,
    manifest: dict,
    cred_events: list[dict],
    evidence_prefixes: list[str],
) -> Hypothesis:
    """Create a Hypothesis with scores derived from coverage and claims."""
    cov = cov_envelope["coverage_report"]
    cov_status = cov["overall_status"]

    supporting = [c for c in claims if c.polarity == "supports"]
    contradicting = [c for c in claims if c.polarity == "contradicts"]

    # Likelihood from claim confidences
    if supporting:
        likelihood = sum(c.confidence for c in supporting) / len(supporting)
    elif cred_events:
        likelihood = 0.5
    else:
        likelihood = 0.3

    # Confidence limit from coverage
    if cov_status == "complete":
        confidence_limit = 0.95
    elif cov_status == "partial":
        confidence_limit = 0.6
    else:
        confidence_limit = 0.3

    # Contradicting claims reduce likelihood
    if contradicting:
        likelihood *= 0.7

    gaps = [cov["id"]] if cov_status != "complete" else []

    next_evidence_requests = []
    if cov_status != "complete":
        next_evidence_requests.append({
            "domain": "identity",
            "tool": "search_events",
            "params": {
                "actions": [f"{p}*" for p in evidence_prefixes],
                "time_range_start": manifest["time_range"].start,
                "time_range_end": manifest["time_range"].end,
            },
            "priority": "high",
        })

    return Hypothesis(
        id=generate_ulid(),
        tlp="AMBER",
        iq_id=manifest.get("question", "IQ-unknown"),
        statement="Credential changes are legitimate self-service activity",
        likelihood_score=round(likelihood, 3),
        confidence_limit=round(confidence_limit, 3),
        supporting_claim_ids=[c.id for c in supporting],
        contradicting_claim_ids=[c.id for c in contradicting] or None,
        gaps=gaps,
        next_evidence_requests=next_evidence_requests,
        status="open",
    )


async def run_analysis(scenario_path: Path) -> dict:
    """Run investigation + structured analysis for a scenario."""
    inv = await investigate(scenario_path)

    try:
        manifest = inv["manifest"]
        cov_envelope = inv["cov_envelope"]
        cov = cov_envelope["coverage_report"]
        conn = inv["conn"]
        logger = logging.getLogger("demo_analysis")

        if not inv["principals"]:
            return {
                "scenario_name": manifest["scenario_name"],
                "variant": manifest["variant"],
                "hypothesis": None,
            }

        subject_id = inv["principals"][0]["id"]

        # -- Step 8: Build evidence items --
        step("8. Build evidence items")
        evidence_items = _build_evidence_items(
            inv["cred_events"], cov_envelope, manifest,
        )
        result = ingest_evidence_items(logger, conn, evidence_items)
        assert result.is_ok()
        print(f"  Ingested {result.ok()} evidence item(s)")
        for ei in evidence_items:
            print(f"    {ei.id}: {ei.summary[:70]}...")

        # -- Step 9: Build claims --
        step("9. Build claims from correlations")
        claims = _build_claims(
            inv["cred_events"], inv["source_ips"], subject_id,
            evidence_items, cov_envelope, manifest["time_range"],
        )
        result = ingest_claims(logger, conn, claims)
        assert result.is_ok()
        print(f"  Ingested {result.ok()} claim(s)")
        for c in claims:
            print(f"    [{c.polarity}] {c.statement}")
            print(f"      confidence={c.confidence}")

        # -- Step 10: Build hypothesis --
        step("10. Build hypothesis")
        hypothesis = _build_hypothesis(
            claims, cov_envelope, manifest,
            inv["cred_events"], inv["evidence_prefixes"],
        )
        print(f"  Statement: {hypothesis.statement}")
        print(f"  Likelihood score: {hypothesis.likelihood_score}")
        print(f"  Confidence limit: {hypothesis.confidence_limit}")
        print(f"  Supporting claims: {len(hypothesis.supporting_claim_ids)}")
        if hypothesis.contradicting_claim_ids:
            print(f"  Contradicting claims: {len(hypothesis.contradicting_claim_ids)}")
        print(f"  Gaps: {hypothesis.gaps or '(none)'}")
        if hypothesis.next_evidence_requests:
            print(f"  Next evidence requests: {len(hypothesis.next_evidence_requests)}")
            for req in hypothesis.next_evidence_requests:
                print(f"    {req['domain']}.{req['tool']} "
                      f"(priority={req['priority']})")

        # -- Step 11: Ingest hypothesis and verify round-trip --
        step("11. Persist and verify (case store round-trip)")
        result = ingest_hypotheses(logger, conn, [hypothesis])
        assert result.is_ok()
        print(f"  Hypothesis ingested: {hypothesis.id}")

        # Query back from DB
        row = conn.execute(
            "SELECT * FROM hypotheses WHERE id = ?", [hypothesis.id]
        ).fetchone()
        cols = [d[0] for d in conn.description]
        stored = dict(zip(cols, row))
        print(f"\n  Round-trip verification:")
        print(f"    likelihood_score: {stored['likelihood_score']}")
        print(f"    confidence_cap:   {stored['confidence_cap']}")
        print(f"    status:           {stored['status']}")
        stored_claims = from_json(stored["supporting_claim_ids"])
        print(f"    supporting_claims: {len(stored_claims)}")
        stored_gaps = from_json(stored["gaps"])
        print(f"    gaps:             {stored_gaps}")
        stored_reqs = from_json(stored["next_evidence_requests"])
        print(f"    next_requests:    {len(stored_reqs)}")

        # Verify claim count in DB
        claim_count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0]
        print(f"\n  Case store totals:")
        print(f"    Evidence items: {evidence_count}")
        print(f"    Claims: {claim_count}")
        print(f"    Hypotheses: 1")

        return {
            "scenario_name": manifest["scenario_name"],
            "variant": manifest["variant"],
            "coverage_status": cov["overall_status"],
            "hypothesis": {
                "id": hypothesis.id,
                "statement": hypothesis.statement,
                "likelihood_score": hypothesis.likelihood_score,
                "confidence_limit": hypothesis.confidence_limit,
                "supporting_claims": len(hypothesis.supporting_claim_ids),
                "gaps": len(hypothesis.gaps),
                "next_requests": len(hypothesis.next_evidence_requests),
                "status": hypothesis.status,
            },
            "claim_count": len(claims),
            "evidence_count": len(evidence_items),
        }
    finally:
        if inv["conn"] is not None:
            inv["conn"].close()
        shutil.rmtree(inv["tmp_dir"], ignore_errors=True)


async def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    families = discover_scenarios()

    heading("BLINDSIGHT LOCAL INVESTIGATION DEMO")

    scenarios_to_run = await select_scenarios(families)
    if not scenarios_to_run:
        print("  No scenarios selected. Exiting.")
        return

    narrate(f"Running {len(scenarios_to_run)} scenario(s)")

    results = []
    for scenario_path in scenarios_to_run:
        result = await run_analysis(scenario_path)
        results.append(result)

    # -- Summary --
    heading("HYPOTHESIS SUMMARY")
    for r in results:
        hyp = r.get("hypothesis")
        print(f"  {r['scenario_name']} (variant={r['variant']}):")
        if hyp is None:
            print(f"    No hypothesis (no principals found)")
        else:
            print(f"    Coverage:         {r['coverage_status']}")
            print(f"    Evidence items:   {r['evidence_count']}")
            print(f"    Claims:           {r['claim_count']}")
            print(f"    Likelihood:       {hyp['likelihood_score']}")
            print(f"    Confidence limit: {hyp['confidence_limit']}")
            print(f"    Gaps:             {hyp['gaps']}")
            print(f"    Next requests:    {hyp['next_requests']}")
        print()

    heading("LOCAL DEMO COMPLETE")
    narrate(
        "Key takeaway: Structured Claim and Hypothesis objects make the\n"
        "reasoning chain explicit and auditable. The confidence_limit\n"
        "drops when coverage is incomplete, even if likelihood stays\n"
        "similar -- this is what coverage-aware scoring means."
    )


if __name__ == "__main__":
    asyncio.run(main())
