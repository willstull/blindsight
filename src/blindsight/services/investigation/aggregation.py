"""Evidence aggregation: compress raw events into higher-signal facts.

Pure functions -- no I/O. Runs between evidence discovery and claim
building to surface lifecycle chains, shared indicators, credential
sequences, and action bursts.
"""
from pydantic import BaseModel, Field

from src.services.investigation.resolution import build_target_to_principal_map
from src.utils.time import within_minutes


class EvidenceFact(BaseModel):
    """Internal scoring construct -- not an ontology type."""
    fact_type: str  # lifecycle_chain | shared_indicator | credential_sequence | action_burst
    summary: str
    event_ids: list[str]
    entity_ids: list[str]  # principals only, no raw credential/session IDs
    time_range_start: str
    time_range_end: str
    confidence: float


def aggregate_evidence(
    evidence_events: list[dict],
    all_events: list[dict],
    relationships: list[dict],
    focal_ids: list[str],
) -> list[EvidenceFact]:
    """Run all sub-aggregators and merge results."""
    facts: list[EvidenceFact] = []
    facts.extend(_aggregate_lifecycle_chains(evidence_events, relationships, focal_ids))
    facts.extend(_aggregate_shared_indicators(all_events, focal_ids))
    facts.extend(_aggregate_credential_sequences(evidence_events, all_events, relationships, focal_ids))
    facts.extend(_aggregate_action_bursts(evidence_events))
    return facts


def _aggregate_lifecycle_chains(
    evidence_events: list[dict],
    relationships: list[dict],
    focal_ids: list[str],
) -> list[EvidenceFact]:
    """Find chains of account create/delete/disable events.

    Groups events from the same actor or targeting related principals
    within 30 minutes into lifecycle chains.
    """
    lifecycle_actions = {"auth.account.create", "auth.account.delete", "auth.account.disable"}
    lifecycle_events = [
        e for e in evidence_events if e.get("action", "") in lifecycle_actions
    ]
    if not lifecycle_events:
        return []

    principal_ids = set(focal_ids)
    target_to_principal = build_target_to_principal_map(relationships, principal_ids)

    # Sort by timestamp
    sorted_events = sorted(lifecycle_events, key=lambda e: e.get("ts", ""))

    # Group into chains: consecutive lifecycle events within 30 minutes
    chains: list[list[dict]] = []
    current_chain: list[dict] = [sorted_events[0]]

    for evt in sorted_events[1:]:
        prev_ts = current_chain[-1].get("ts", "")
        curr_ts = evt.get("ts", "")
        if within_minutes(prev_ts, curr_ts, 30):
            current_chain.append(evt)
        else:
            chains.append(current_chain)
            current_chain = [evt]
    chains.append(current_chain)

    facts = []
    for chain in chains:
        if len(chain) < 2:
            continue

        event_ids = [e.get("id", "") for e in chain]
        actors = set()
        target_principals = set()
        for evt in chain:
            actors.add(evt.get("actor", {}).get("actor_entity_id", ""))
            for tgt in evt.get("targets", []):
                tid = tgt.get("target_entity_id", "")
                if tid in principal_ids:
                    target_principals.add(tid)
                elif tid in target_to_principal:
                    target_principals.add(target_to_principal[tid])

        # Build summary
        actions = [e.get("action", "").split(".")[-1] for e in chain]
        action_summary = " + ".join(dict.fromkeys(actions))  # preserve order, dedup
        first_actor = sorted(actors)[0] if actors else "unknown"
        minutes = _minutes_between(chain[0].get("ts", ""), chain[-1].get("ts", ""))

        entity_ids = sorted(actors | target_principals)

        facts.append(EvidenceFact(
            fact_type="lifecycle_chain",
            summary=f"{first_actor} performed {action_summary} within {minutes} minutes",
            event_ids=event_ids,
            entity_ids=entity_ids,
            time_range_start=chain[0].get("ts", ""),
            time_range_end=chain[-1].get("ts", ""),
            confidence=0.85,
        ))

    return facts


def _aggregate_shared_indicators(
    all_events: list[dict],
    focal_ids: list[str],
) -> list[EvidenceFact]:
    """Find IPs shared by 2+ focal actors."""
    focal_set = set(focal_ids)

    ip_to_actors: dict[str, set[str]] = {}
    ip_to_events: dict[str, list[dict]] = {}

    for evt in all_events:
        actor_id = evt.get("actor", {}).get("actor_entity_id", "")
        if actor_id not in focal_set:
            continue
        ctx = evt.get("context") or {}
        ip = ctx.get("source_ip")
        if ip:
            ip_to_actors.setdefault(ip, set()).add(actor_id)
            ip_to_events.setdefault(ip, []).append(evt)

    facts = []
    for ip, actors in ip_to_actors.items():
        if len(actors) < 2:
            continue
        events = ip_to_events[ip]
        sorted_events = sorted(events, key=lambda e: e.get("ts", ""))
        facts.append(EvidenceFact(
            fact_type="shared_indicator",
            summary=f"Actors {sorted(actors)} share source IP {ip}",
            event_ids=[e.get("id", "") for e in sorted_events],
            entity_ids=sorted(actors),
            time_range_start=sorted_events[0].get("ts", ""),
            time_range_end=sorted_events[-1].get("ts", ""),
            confidence=0.8,
        ))

    return facts


def _aggregate_credential_sequences(
    evidence_events: list[dict],
    all_events: list[dict],
    relationships: list[dict],
    focal_ids: list[str],
) -> list[EvidenceFact]:
    """Find cross-account credential ops followed by target activity."""
    credential_actions = {"credential.reset", "credential.enroll", "credential.revoke"}
    principal_ids = set(focal_ids)
    target_to_principal = build_target_to_principal_map(relationships, principal_ids)

    facts = []
    for evt in evidence_events:
        action = evt.get("action", "")
        if action not in credential_actions:
            continue

        actor_id = evt.get("actor", {}).get("actor_entity_id", "")

        # Resolve credential targets to owning principals
        target_owners: set[str] = set()
        for tgt in evt.get("targets", []):
            tid = tgt.get("target_entity_id", "")
            if tid in target_to_principal:
                target_owners.add(target_to_principal[tid])
            elif tid in principal_ids:
                target_owners.add(tid)

        # Only cross-account: actor is not the credential owner
        if not target_owners or actor_id in target_owners:
            continue

        evt_ts = evt.get("ts", "")

        # Check for follow-on activity from target principals in all_events
        followon_events = []
        for e in all_events:
            e_actor = e.get("actor", {}).get("actor_entity_id", "")
            if e_actor in target_owners and within_minutes(evt_ts, e.get("ts", ""), 30):
                if e.get("id") != evt.get("id"):
                    followon_events.append(e)

        if not followon_events:
            continue

        all_seq_events = [evt] + sorted(followon_events, key=lambda e: e.get("ts", ""))
        owner_str = ", ".join(sorted(target_owners))

        facts.append(EvidenceFact(
            fact_type="credential_sequence",
            summary=f"{actor_id} reset credential for {owner_str}, "
                    f"followed by {len(followon_events)} activity events",
            event_ids=[e.get("id", "") for e in all_seq_events],
            entity_ids=sorted({actor_id} | target_owners),
            time_range_start=all_seq_events[0].get("ts", ""),
            time_range_end=all_seq_events[-1].get("ts", ""),
            confidence=0.9,
        ))

    return facts


def _aggregate_action_bursts(
    evidence_events: list[dict],
) -> list[EvidenceFact]:
    """Find actions with 3+ events within 15 minutes."""
    # Group events by action
    action_groups: dict[str, list[dict]] = {}
    for evt in evidence_events:
        action = evt.get("action", "")
        action_groups.setdefault(action, []).append(evt)

    facts = []
    for action, events in action_groups.items():
        if len(events) < 3:
            continue

        sorted_events = sorted(events, key=lambda e: e.get("ts", ""))

        # Sliding window: find bursts within 15 minutes
        cluster: list[dict] = [sorted_events[0]]
        for evt in sorted_events[1:]:
            if within_minutes(cluster[-1].get("ts", ""), evt.get("ts", ""), 15):
                cluster.append(evt)
            else:
                if len(cluster) >= 3:
                    _emit_burst(facts, action, cluster)
                cluster = [evt]
        if len(cluster) >= 3:
            _emit_burst(facts, action, cluster)

    return facts


def _emit_burst(facts: list[EvidenceFact], action: str, cluster: list[dict]) -> None:
    actors = set()
    for e in cluster:
        actors.add(e.get("actor", {}).get("actor_entity_id", ""))

    facts.append(EvidenceFact(
        fact_type="action_burst",
        summary=f"{len(cluster)} {action} events in rapid succession "
                f"({cluster[0].get('ts', '?')} to {cluster[-1].get('ts', '?')})",
        event_ids=[e.get("id", "") for e in cluster],
        entity_ids=sorted(actors),
        time_range_start=cluster[0].get("ts", ""),
        time_range_end=cluster[-1].get("ts", ""),
        confidence=0.7,
    ))


def _minutes_between(ts1: str, ts2: str) -> int:
    """Compute minutes between two timestamps, or 0 on failure."""
    try:
        from src.utils.time import parse_rfc3339
        t1 = parse_rfc3339(ts1)
        t2 = parse_rfc3339(ts2)
        return int(abs((t2 - t1).total_seconds()) / 60)
    except (ValueError, TypeError):
        return 0
