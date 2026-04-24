"""Shared investigation logic for demo scripts.

Extracted to allow multiple demo frontends (demo_local.py, demo_agent.py)
to share scenario discovery and manifest loading.
"""
import logging
import tempfile
from pathlib import Path

from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import radiolist_dialog

from blindsight.services.identity.replay_integration import ReplayIdentityIntegration
from blindsight.utils.mcp_envelope import build_envelope
from blindsight.services.case.store import open_case_db, create_case
from blindsight.services.case.ingest import ingest_domain_response, record_tool_call
from blindsight.services.case.query import (
    query_events, query_neighbors, get_timeline, get_tool_call_history,
)
from blindsight.types.core import TimeRange
from blindsight.utils.ulid import generate_ulid
from blindsight.utils.serialization import load_yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "replay" / "scenarios"

DIVIDER = "-" * 72
SECTION = "=" * 72


def heading(text):
    print(f"\n{SECTION}")
    print(f"  {text}")
    print(SECTION)


def step(text):
    print(f"\n{DIVIDER}")
    print(f"  {text}")
    print(DIVIDER)


def narrate(text):
    """Print investigation narrative in a distinct style."""
    for line in text.strip().splitlines():
        print(f"  >> {line.strip()}")


def load_manifest(scenario_path: Path) -> dict:
    """Read manifest.yaml and return structured metadata."""
    manifest = load_yaml(scenario_path / "manifest.yaml")
    time_range = manifest.get("time_range", {})
    return {
        "scenario_name": manifest.get("scenario_name", scenario_path.name),
        "description": manifest.get("description", ""),
        "question": manifest.get("investigation_question", ""),
        "time_range": TimeRange(
            start=time_range.get("start", "2026-01-01T00:00:00Z"),
            end=time_range.get("end", "2026-01-31T23:59:59Z"),
        ),
        "variant": manifest.get("variant", "unknown"),
        "tags": manifest.get("tags", []),
        "domains": manifest.get("domains", []),
    }


def discover_scenarios() -> dict[str, dict]:
    """Find all scenario directories, grouped by family.

    Returns {family_name: {"baseline": Path, "degraded": [Path, ...]}}.
    Family name derived by stripping _baseline or _degraded_* suffix.
    """
    all_paths = sorted(
        p for p in SCENARIOS_DIR.iterdir()
        if p.is_dir() and (p / "manifest.yaml").exists()
    )
    families: dict[str, dict] = {}
    for path in all_paths:
        manifest = load_yaml(path / "manifest.yaml")
        name = path.name
        # Derive family from directory name (check degraded first since
        # degraded variant names may contain "baseline" as a word)
        if "_degraded_" in name:
            family = name.split("_degraded_")[0]
        elif name.endswith("_baseline"):
            family = name.removesuffix("_baseline")
        else:
            family = name
        if family not in families:
            families[family] = {"baseline": None, "degraded": []}
        if manifest.get("variant") == "baseline":
            families[family]["baseline"] = path
        else:
            families[family]["degraded"].append(path)
    return families


async def _radio_select(title: str, values: list[tuple[str, str]]) -> str | None:
    """Present a radiolist dialog. Returns the selected value or None."""
    try:
        result = await radiolist_dialog(
            title=HTML(f"<b>{title}</b>"),
            text="Use arrow keys to navigate, Enter to select, Esc to cancel.",
            values=values,
        ).run_async()
        return result
    except (EOFError, KeyboardInterrupt):
        return None


async def select_scenarios(families: dict[str, dict]) -> list[Path]:
    """Two-level interactive menu for scenario selection.

    Level 1: pick all families or a specific family.
    Level 2 (if family chosen): pick all scenarios or a specific one.
    """
    sorted_families = sorted(families.keys())

    # -- Level 1: family selection --
    values: list[tuple[str, str]] = [
        ("__all__", "All families (baseline + first degraded each)"),
    ]
    for family_name in sorted_families:
        fam = families[family_name]
        count = (1 if fam["baseline"] else 0) + len(fam["degraded"])
        values.append((family_name, f"{family_name} ({count} scenarios)"))

    choice = await _radio_select("Select a scenario family", values)
    if choice is None:
        return []

    if choice == "__all__":
        paths = []
        for family_name in sorted_families:
            fam = families[family_name]
            if fam["baseline"]:
                paths.append(fam["baseline"])
            if fam["degraded"]:
                paths.append(fam["degraded"][0])
        return paths

    # -- Level 2: scenario selection within family --
    family_name = choice
    fam = families[family_name]
    family_paths: list[Path] = []
    if fam["baseline"]:
        family_paths.append(fam["baseline"])
    family_paths.extend(fam["degraded"])

    values2: list[tuple[str, str]] = [
        ("__all__", f"All {family_name} ({len(family_paths)} scenarios)"),
    ]
    for path in family_paths:
        m = load_manifest(path)
        values2.append((str(path), f"{m['scenario_name']} ({m['variant']})"))

    choice2 = await _radio_select(f"Select scenario in {family_name}", values2)
    if choice2 is None:
        return []

    if choice2 == "__all__":
        return family_paths
    return [Path(choice2)]


async def investigate(scenario_path: Path) -> dict:
    """Run a full discovery-driven investigation against a scenario.

    Returns a dict with raw envelopes and extracted data that callers
    can use for assessment (text-based or structured).

    Keys: manifest, conn, case_id, db_path, tmp_dir,
          cov_envelope, principals, neighbor_envelope,
          cred_events, evidence_prefixes, source_ips, creds,
          timeline, all_case_events
    """
    logger = logging.getLogger("demo")
    manifest = load_manifest(scenario_path)
    time_range = manifest["time_range"]

    integration = ReplayIdentityIntegration(scenario_path=scenario_path, logger=logger)

    tmp_dir = Path(tempfile.mkdtemp(prefix="blindsight_demo_"))
    db_path = tmp_dir / "case.duckdb"

    heading(f"INVESTIGATION: {manifest['description']}")
    narrate(f"Question: {manifest['question']}")
    narrate(f"Scenario: {manifest['scenario_name']} (variant={manifest['variant']})")
    narrate(f"Time range: {time_range.start} to {time_range.end}")

    # -- Open case --
    step("Open case")
    db_result = open_case_db(logger, db_path)
    assert db_result.is_ok()
    conn = db_result.ok()
    case_id = generate_ulid()
    result = create_case(
        logger, conn, case_id,
        title=manifest["description"],
        tlp="AMBER",
        severity="sev3",
        tags=manifest["tags"],
    )
    assert result.is_ok()
    print(f"  Case opened: {manifest['description']}")

    # -- Step 1: Check coverage --
    step("1. What data do we have? (describe_coverage)")
    narrate("Before looking at events, check what sources are available "
            "and whether there are gaps.")
    cov_result = await integration.describe_coverage(time_range=time_range)
    cov_envelope = build_envelope(generate_ulid(), "identity", cov_result)
    cov = cov_envelope["coverage_report"]
    print(f"  Overall coverage: {cov['overall_status']}")
    for src in cov["sources"]:
        line = f"    {src['source_name']}: {src['status']}"
        if src.get("notes"):
            line += f"  -- {src['notes']}"
        if src.get("missing_fields"):
            line += f"  (missing: {', '.join(src['missing_fields'])})"
        print(line)
    if cov.get("notes"):
        print(f"  Notes: {cov['notes']}")

    if cov["overall_status"] == "complete":
        narrate("Full telemetry available. Findings will be high-confidence.")
    else:
        limitations = cov_envelope.get("limitations", [])
        narrate(f"Coverage is {cov['overall_status']}. "
                f"Gaps: {', '.join(limitations) if limitations else 'see source details'}. "
                "Findings will have a lower confidence cap.")

    ingest_domain_response(logger, conn, cov_envelope)

    # -- Step 2: Discover subject principal(s) --
    step("2. Discover the subject (search_entities)")
    narrate("Find all principals in the scenario. No hardcoded entity IDs.")
    principal_result = await integration.search_entities(
        "", entity_types=["principal"],
    )
    principal_envelope = build_envelope(generate_ulid(), "identity", principal_result)
    principals = principal_envelope.get("entities", [])

    if not principals:
        print("  No principals found -- cannot proceed.")
        conn.close()
        return {
            "manifest": manifest,
            "conn": None,
            "case_id": case_id,
            "db_path": db_path,
            "tmp_dir": tmp_dir,
            "cov_envelope": cov_envelope,
            "principals": [],
            "neighbor_envelope": {},
            "cred_events": [],
            "evidence_prefixes": [],
            "source_ips": set(),
            "creds": [],
            "timeline": [],
            "all_case_events": [],
        }

    subject = principals[0]
    subject_id = subject["id"]
    print(f"  Found {len(principals)} principal(s). Investigating: "
          f"{subject['display_name']} ({subject['entity_type']}/{subject['kind']})")
    refs = subject.get("refs", [])
    for ref in refs:
        print(f"    ref: {ref['ref_type']}={ref['value']} (system={ref['system']})")

    ingest_domain_response(logger, conn, principal_envelope)
    record_tool_call(
        logger, conn, case_id=case_id, request_id=generate_ulid(),
        domain="identity", tool_name="search_entities",
        request_params={"query": "", "entity_types": ["principal"]},
        response_status=principal_envelope["status"],
        response_body={"entity_count": len(principals)},
        duration_ms=10,
    )

    # -- Step 3: Map relationships --
    step("3. What is the subject connected to? (get_neighbors)")
    narrate("Map credentials, sessions, and devices linked to this principal.")
    neighbor_result = await integration.get_neighbors(subject_id)
    neighbor_envelope = build_envelope(generate_ulid(), "identity", neighbor_result)

    by_type: dict[str, list[dict]] = {}
    for rel in neighbor_envelope.get("relationships", []):
        by_type.setdefault(rel["relationship_type"], []).append(rel)
    entities_by_id = {e["id"]: e for e in neighbor_envelope["entities"]}

    for rel_type, rels in sorted(by_type.items()):
        print(f"  {rel_type}:")
        for rel in rels:
            other_id = (rel["to_entity_id"]
                        if rel["from_entity_id"] == subject_id
                        else rel["from_entity_id"])
            other = entities_by_id.get(other_id, {})
            name = other.get("display_name", other_id)
            kind = other.get("kind", "?")
            print(f"    {other_id} ({kind}) \"{name}\"")

    ingest_domain_response(logger, conn, neighbor_envelope)
    record_tool_call(
        logger, conn, case_id=case_id, request_id=generate_ulid(),
        domain="identity", tool_name="get_neighbors",
        request_params={"entity_id": subject_id},
        response_status=neighbor_envelope["status"],
        response_body={
            "entity_count": len(neighbor_envelope["entities"]),
            "relationship_count": len(neighbor_envelope.get("relationships", [])),
        },
        duration_ms=12,
    )

    # -- Step 4: Discover domain capabilities --
    step("4. What action types exist? (describe_domain)")
    domain_info = await integration.describe_domain()
    capabilities = domain_info.get("capabilities", {})
    all_prefixes = capabilities.get("supported_actions_prefixes", [])
    # Evidence = everything except auth.login (auth.account.* is evidence)
    evidence_prefixes = [p for p in all_prefixes if p != "auth."]
    # auth.account.* actions are also evidence if auth. prefix is present
    has_auth_prefix = "auth." in all_prefixes
    print(f"  Supported action prefixes: {all_prefixes}")
    print(f"  Evidence prefixes (non-auth-login): {evidence_prefixes}")
    if has_auth_prefix:
        print(f"  Note: auth.account.* treated as evidence, auth.login as background")

    # -- Step 5: Find relevant events --
    step("5. What changes occurred? (search_events)")
    narrate("Search for non-login events. These are the primary evidence "
            "(credential changes, account lifecycle, privilege changes, etc.).")

    cred_events = []
    for prefix in evidence_prefixes:
        prefix_result = await integration.search_events(
            time_range=time_range,
            actions=[f"{prefix}*"],
        )
        prefix_envelope = build_envelope(generate_ulid(), "identity", prefix_result)
        events = prefix_envelope.get("events", [])
        cred_events.extend(events)
        ingest_domain_response(logger, conn, prefix_envelope)
        record_tool_call(
            logger, conn, case_id=case_id, request_id=generate_ulid(),
            domain="identity", tool_name="search_events",
            request_params={
                "actions": [f"{prefix}*"],
                "time_range_start": time_range.start,
                "time_range_end": time_range.end,
            },
            response_status=prefix_envelope["status"],
            response_body={"event_count": len(events)},
            duration_ms=35,
        )
    # Also search for auth.account.* if auth. prefix is present
    if has_auth_prefix:
        acct_result = await integration.search_events(
            time_range=time_range,
            actions=["auth.account.*"],
        )
        acct_envelope = build_envelope(generate_ulid(), "identity", acct_result)
        acct_events = acct_envelope.get("events", [])
        cred_events.extend(acct_events)
        ingest_domain_response(logger, conn, acct_envelope)
        record_tool_call(
            logger, conn, case_id=case_id, request_id=generate_ulid(),
            domain="identity", tool_name="search_events",
            request_params={
                "actions": ["auth.account.*"],
                "time_range_start": time_range.start,
                "time_range_end": time_range.end,
            },
            response_status=acct_envelope["status"],
            response_body={"event_count": len(acct_events)},
            duration_ms=35,
        )

    if not cred_events:
        print("  No non-auth events found.")
        narrate("Without change events, we cannot verify the alert. "
                "This is a coverage gap, not a negative finding.")
    else:
        print(f"  Found {len(cred_events)} change event(s):")
        for evt in cred_events:
            ctx = evt.get("context", {})
            targets = evt.get("targets", [])
            target_ids = [t["target_entity_id"] for t in targets]
            print(f"    {evt['ts']}  {evt['action']}  outcome={evt['outcome']}")
            print(f"      actor:   {evt['actor']['actor_entity_id']}")
            print(f"      target:  {', '.join(target_ids)}")
            if ctx.get("source_ip"):
                print(f"      src_ip:  {ctx['source_ip']}")
            if ctx.get("session_id"):
                print(f"      session: {ctx['session_id']}")
            if ctx.get("credential_type"):
                print(f"      type:    {ctx['credential_type']}")

    # -- Step 6: Timeline around changes --
    step("6. What happened around the changes? (timeline)")
    narrate("Check surrounding activity. An attacker who takes over an account "
            "typically changes credentials then uses the account differently.")

    if cred_events:
        sorted_events = sorted(cred_events, key=lambda e: e["ts"])
        first_ts = sorted_events[0]["ts"]
        last_ts = sorted_events[-1]["ts"]
        narrow_start = first_ts[:10] + "T00:00:00Z"
        last_day = int(last_ts[8:10])
        narrow_end = last_ts[:8] + f"{min(last_day + 2, 28):02d}T23:59:59Z"
    else:
        narrow_start = time_range.start
        narrow_end = time_range.end

    all_result = await integration.search_events(
        time_range=TimeRange(start=narrow_start, end=narrow_end),
    )
    all_envelope = build_envelope(generate_ulid(), "identity", all_result)
    ingest_domain_response(logger, conn, all_envelope)
    record_tool_call(
        logger, conn, case_id=case_id, request_id=generate_ulid(),
        domain="identity", tool_name="search_events",
        request_params={"time_range_start": narrow_start,
                        "time_range_end": narrow_end},
        response_status=all_envelope["status"],
        response_body={"event_count": len(all_envelope.get("events", []))},
        duration_ms=28,
    )

    evidence_actions = {evt["action"] for evt in cred_events}

    timeline_result = get_timeline(
        logger, conn,
        time_range_start=narrow_start,
        time_range_end=narrow_end,
    )
    assert timeline_result.is_ok()
    timeline = timeline_result.ok()

    print(f"  Activity from {narrow_start[:10]} to {narrow_end[:10]}:")
    current_date = None
    for evt in timeline:
        ts = str(evt["ts"])
        date = ts[:10]
        if date != current_date:
            current_date = date
            print(f"\n    {date}:")
        actor = evt["actor"]["actor_entity_id"]
        marker = " <<<" if evt["action"] in evidence_actions else ""
        ctx = evt.get("context") or {}
        ip_str = f"  ip={ctx['source_ip']}" if ctx.get("source_ip") else ""
        print(f"      {ts[11:19]}  {evt['action']:<22} "
              f"actor={actor}{ip_str}{marker}")

    # -- Step 7: Correlate from case store --
    step("7. Correlation assessment (case store queries)")

    all_events_result = query_events(logger, conn, actor_entity_id=subject_id)
    assert all_events_result.is_ok()
    all_case_events = all_events_result.ok()
    source_ips = set()
    for evt in all_case_events:
        ctx = evt.get("context") or {}
        if ctx.get("source_ip"):
            source_ips.add(ctx["source_ip"])

    print(f"  Distinct source IPs for {subject_id}: "
          f"{source_ips or '{none recorded}'}")

    cred_neighbors = query_neighbors(
        logger, conn,
        entity_id=subject_id,
        relationship_types=["has_credential"],
    )
    assert cred_neighbors.is_ok()
    creds = cred_neighbors.ok()
    print(f"  Credentials linked to subject: {len(creds)}")
    for c in creds:
        print(f"    {c['id']} ({c['kind']}) \"{c['display_name']}\"")

    for c in creds:
        ev_result = query_events(logger, conn, target_entity_id=c["id"])
        assert ev_result.is_ok()
        evts = ev_result.ok()
        if evts:
            print(f"    events targeting {c['id']}:")
            for evt in evts:
                print(f"      {evt['ts']}  {evt['action']}  "
                      f"outcome={evt['outcome']}")

    return {
        "manifest": manifest,
        "conn": conn,
        "case_id": case_id,
        "db_path": db_path,
        "tmp_dir": tmp_dir,
        "cov_envelope": cov_envelope,
        "principals": principals,
        "neighbor_envelope": neighbor_envelope,
        "cred_events": cred_events,
        "evidence_prefixes": evidence_prefixes,
        "source_ips": source_ips,
        "creds": creds,
        "timeline": timeline,
        "all_case_events": all_case_events,
    }
