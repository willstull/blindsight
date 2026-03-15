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
from src.services.investigation.scoring import (
    build_evidence_items as _build_evidence_items_raw,
    build_claims as _build_claims,
    build_hypothesis as _build_hypothesis_raw,
)
from src.types.core import TimeRange


def _build_evidence_items(cred_events, cov_envelope, manifest):
    return _build_evidence_items_raw(cred_events, cov_envelope, manifest["time_range"])


def _build_hypothesis(claims, cov_envelope, manifest, cred_events, evidence_prefixes):
    return _build_hypothesis_raw(
        claims, cov_envelope, manifest.get("question", "IQ-unknown"),
        cred_events, evidence_prefixes,
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
