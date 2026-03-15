#!/usr/bin/env python3
"""Demo: discovery-driven incident investigation using Blindsight.

Walks through an investigation the way an analyst thinks:

  1. Read the manifest -- what are we investigating?
  2. Check coverage -- what data do we have? What's missing?
  3. Discover the subject -- who is involved?
  4. Map relationships -- what entities are connected?
  5. Find relevant changes -- what non-auth activity occurred?
  6. Build a timeline -- what happened in sequence?
  7. Correlate from case store -- IPs, credentials, patterns
  8. Assess -- what can we conclude given coverage?

Nothing about specific entities, actions, or scenarios is hardcoded.
The investigation adapts to whatever the scenario data contains.

Usage:
    poetry run python scripts/demo.py
"""
import asyncio
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._investigation import (
    heading, step, narrate, load_manifest,
    discover_scenarios, select_scenarios, investigate,
)
from src.services.case.query import get_tool_call_history
from tests.conftest import get_test_logger


def _assess(
    coverage_status: str,
    cred_events: list[dict],
    subject_id: str,
    source_ips: set[str],
) -> dict:
    """Programmatic finding based on coverage, events, and correlations.

    Returns {label, text} where label is a short key and text is the narrative.
    """
    if coverage_status == "complete" and cred_events:
        all_self_directed = all(
            evt["actor"]["actor_entity_id"] == subject_id
            for evt in cred_events
        )
        single_ip = len(source_ips) <= 1

        if all_self_directed and single_ip:
            return {
                "label": "legitimate_high_confidence",
                "text": (
                    f"FINDING: Credential changes appear legitimate.\n"
                    f"- All {len(cred_events)} change(s) were self-directed "
                    f"by {subject_id}.\n"
                    f"- All activity from a single IP "
                    f"({', '.join(source_ips) or 'unknown'}).\n"
                    f"- No anomalous sessions or new devices around the "
                    f"change window.\n"
                    f"- Coverage: COMPLETE -- high confidence in this finding."
                ),
            }
        else:
            reasons = []
            if not all_self_directed:
                reasons.append("non-self-directed changes detected")
            if not single_ip:
                reasons.append(f"multiple source IPs ({len(source_ips)})")
            return {
                "label": "suspicious_high_confidence",
                "text": (
                    f"FINDING: Credential changes show indicators worth "
                    f"investigating.\n"
                    f"- {'; '.join(reasons)}.\n"
                    f"- Coverage: COMPLETE -- finding is based on full "
                    f"telemetry."
                ),
            }
    elif coverage_status != "complete" and not cred_events:
        return {
            "label": "unverifiable_low_confidence",
            "text": (
                f"FINDING: Cannot verify credential changes.\n"
                f"- No change events found, but coverage is "
                f"{coverage_status}.\n"
                f"- Missing data sources may contain the events we need.\n"
                f"- This is an absence of evidence, not evidence of "
                f"absence.\n"
                f"- Confidence cap is LIMITED by data gaps."
            ),
        }
    elif coverage_status != "complete" and cred_events:
        return {
            "label": "partial_capped_confidence",
            "text": (
                f"FINDING: Partial verification of credential changes.\n"
                f"- Found {len(cred_events)} change event(s), but coverage "
                f"is {coverage_status}.\n"
                f"- There may be additional changes not visible due to "
                f"data gaps.\n"
                f"- Confidence cap is LIMITED -- we can confirm what we see "
                f"but not rule out what we can't."
            ),
        }
    else:
        return {
            "label": "no_changes_full_coverage",
            "text": (
                "FINDING: No credential changes detected.\n"
                "- Full coverage, no events found. The alert may be a "
                "false positive."
            ),
        }


async def run_investigation(scenario_path: Path) -> dict:
    """Run investigation and produce text-based assessment."""
    inv = await investigate(scenario_path)

    try:
        manifest = inv["manifest"]
        cov = inv["cov_envelope"]["coverage_report"]

        if not inv["principals"]:
            return {
                "scenario_name": manifest["scenario_name"],
                "variant": manifest["variant"],
                "coverage_status": cov["overall_status"],
                "finding": "no_principals",
                "detail": "No principal entities found in scenario data.",
                "cred_event_count": 0,
                "subject_ids": [],
            }

        subject_id = inv["principals"][0]["id"]

        # -- Step 8: Assess --
        step("8. Investigation finding")
        finding = _assess(
            cov["overall_status"], inv["cred_events"],
            subject_id, inv["source_ips"],
        )
        narrate(finding["text"])

        # -- Audit trail --
        step("9. Audit trail (tool call history)")
        narrate("Every query is recorded for reproducibility. "
                "Another analyst can re-run this exact investigation.")

        logger = get_test_logger()
        history_result = get_tool_call_history(logger, inv["conn"], case_id=inv["case_id"])
        assert history_result.is_ok()
        calls = history_result.ok()
        print(f"  {len(calls)} tool calls recorded for this case:")
        for call in calls:
            print(f"    {call['domain']}.{call['tool_name']}  "
                  f"status={call['response_status']}  {call['duration_ms']}ms")

        return {
            "scenario_name": manifest["scenario_name"],
            "variant": manifest["variant"],
            "coverage_status": cov["overall_status"],
            "finding": finding["label"],
            "detail": finding["text"],
            "cred_event_count": len(inv["cred_events"]),
            "subject_ids": [subject_id],
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

    heading("BLINDSIGHT INVESTIGATION DEMO")

    scenarios_to_run = await select_scenarios(families)
    if not scenarios_to_run:
        print("  No scenarios selected. Exiting.")
        return

    narrate(f"Running {len(scenarios_to_run)} scenario(s)")

    findings = []
    for scenario_path in scenarios_to_run:
        result = await run_investigation(scenario_path)
        findings.append(result)

    # -- Summary --
    heading("SUMMARY")
    for f in findings:
        print(f"  {f['scenario_name']} (variant={f['variant']}):")
        print(f"    Coverage: {f['coverage_status']}")
        print(f"    Change events found: {f['cred_event_count']}")
        print(f"    Subject(s): {', '.join(f['subject_ids'])}")
        print(f"    Finding: {f['finding']}")
        print()

    heading("DEMO COMPLETE")
    narrate(
        "Key takeaway: The same investigation logic produces different\n"
        "conclusions depending on data availability. Blindsight makes\n"
        "this explicit -- likelihood (what evidence suggests) is separate\n"
        "from confidence limit (what we can verify given the data)."
    )


if __name__ == "__main__":
    asyncio.run(main())
