"""Scoring functions for investigation hypothesis building.

Pure functions -- no I/O, no side effects. General claim builders that
work across all scenario families (credential_change, password_takeover,
superadmin_escalation, account_substitution).
"""
from src.services.investigation.focal import FocalResult
from src.services.investigation.resolution import build_target_to_principal_map
from src.types.core import (
    Claim, EvidenceItem, Hypothesis, Ref, TimeRange,
)
from src.utils.time import within_minutes
from src.utils.ulid import generate_ulid


# ---------------------------------------------------------------------------
# Claim categories -- the single source of truth for claim typing.
# Builders set these; classification, polarity, and narrative read them.
# ---------------------------------------------------------------------------

SELF_DIRECTED = "self_directed"
CROSS_ACTOR = "cross_actor"
CROSS_ACCOUNT_CREDENTIAL = "cross_account_credential"
SELF_CREDENTIAL = "self_credential"
SINGLE_IP = "single_ip"
SHARED_IP = "shared_ip"
IP_SHIFT = "ip_shift"
NO_IP = "no_ip"
LIFECYCLE_CREATE = "lifecycle_create"
LIFECYCLE_DELETE = "lifecycle_delete"
LIFECYCLE_DISABLE = "lifecycle_disable"
PRIVILEGE_SELF_GRANT = "privilege_self_grant"
PRIVILEGE_GRANT = "privilege_grant"
PRIVILEGE_FAILED = "privilege_failed"
TEMPORAL_CLUSTER = "temporal_cluster"
FAILED_OUTCOME = "failed_outcome"
COVERAGE_GAP = "coverage_gap"

# Aggregation-derived categories
LIFECYCLE_CHAIN = "lifecycle_chain"
SHARED_INDICATOR = "shared_indicator"
CREDENTIAL_SEQUENCE = "credential_sequence"
ACTION_BURST = "action_burst"


# ---------------------------------------------------------------------------
# Evidence items (unchanged)
# ---------------------------------------------------------------------------

def build_evidence_items(
    cred_events: list[dict],
    cov_envelope: dict,
    time_range: TimeRange,
) -> list[EvidenceItem]:
    """Wrap discovered events and coverage into EvidenceItem objects."""
    items = []

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
        collected_at=time_range.end,
        related_entity_ids=[],
        related_event_ids=[],
    ))

    return items


# ---------------------------------------------------------------------------
# Claim builders
# ---------------------------------------------------------------------------

def build_claims(
    evidence_events: list[dict],
    all_events: list[dict],
    focal: FocalResult,
    evidence_items: list[EvidenceItem],
    cov_envelope: dict,
    time_range: TimeRange,
    relationships: list[dict],
    aggregated_facts: list | None = None,
) -> list[Claim]:
    """Create Claim objects from evidence patterns.

    Each builder returns typed claims with neutral polarity and a category
    tag. The hypothesis scorer assigns polarity based on the overall
    pattern classification.
    """
    evidence_ids = [ei.id for ei in evidence_items]
    cov_status = cov_envelope["coverage_report"]["overall_status"]
    focal_ids = set(focal.focal_ids)

    # Build target-to-principal map for resolving credential/session targets
    target_to_principal = build_target_to_principal_map(relationships, focal_ids)

    claims: list[Claim] = []

    claims.extend(_claims_actor_pattern(
        evidence_events, focal, target_to_principal, evidence_ids, cov_status, time_range,
    ))
    claims.extend(_claims_ip_pattern(
        all_events, focal, evidence_ids, cov_status, time_range,
    ))
    claims.extend(_claims_credential_targeting(
        evidence_events, focal, target_to_principal, evidence_ids, time_range,
    ))
    claims.extend(_claims_lifecycle(
        evidence_events, evidence_ids, time_range,
    ))
    claims.extend(_claims_privilege(
        evidence_events, focal, target_to_principal, evidence_ids, time_range,
    ))
    claims.extend(_claims_temporal_clustering(
        evidence_events, evidence_ids, time_range,
    ))
    claims.extend(_claims_failed_outcomes(
        evidence_events, evidence_ids, time_range,
    ))
    claims.extend(_claims_coverage(
        cov_envelope, evidence_ids, time_range,
    ))

    if aggregated_facts:
        claims.extend(_claims_from_aggregated_facts(
            aggregated_facts, evidence_items, time_range,
        ))

    return claims



def _resolve_target_principals(
    evt: dict,
    target_to_principal: dict[str, str],
    focal_ids: set[str],
) -> set[str]:
    """Resolve event targets to principal IDs."""
    resolved: set[str] = set()
    for tgt in evt.get("targets", []):
        tid = tgt.get("target_entity_id", "")
        if tid in focal_ids:
            resolved.add(tid)
        elif tid in target_to_principal:
            resolved.add(target_to_principal[tid])
    return resolved


def _claims_actor_pattern(
    evidence_events: list[dict],
    focal: FocalResult,
    target_to_principal: dict[str, str],
    evidence_ids: list[str],
    cov_status: str,
    time_range: TimeRange,
) -> list[Claim]:
    """Self-directed vs cross-actor claim."""
    if not evidence_events:
        return []

    focal_ids = set(focal.focal_ids)
    claims = []

    # Classify each event as self-directed or cross-actor.
    # Privilege events are excluded from self-directed counting because
    # self-granting a privilege is a distinct (and concerning) pattern,
    # not benign self-service activity like a password reset.
    self_directed_count = 0
    cross_actor_events: list[dict] = []

    for evt in evidence_events:
        action = evt.get("action", "")
        if action.startswith("privilege."):
            continue  # handled by _claims_privilege
        actor_id = evt.get("actor", {}).get("actor_entity_id", "")
        target_principals = _resolve_target_principals(evt, target_to_principal, focal_ids)

        # Self-directed: actor is targeting only themselves/their own resources
        if target_principals <= {actor_id} or not target_principals:
            self_directed_count += 1
        else:
            cross_actor_events.append(evt)

    if self_directed_count > 0 and not cross_actor_events:
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"All {self_directed_count} evidence event(s) are "
                      f"self-directed activity",
            polarity="neutral",
            confidence=0.95 if cov_status == "complete" else 0.6,
            category=SELF_DIRECTED,
            backed_by_evidence_ids=evidence_ids,
            subject_entity_ids=sorted(focal_ids),
            time_range=time_range,
        ))
    elif cross_actor_events:
        actors = set()
        targets = set()
        for evt in cross_actor_events:
            actors.add(evt["actor"]["actor_entity_id"])
            targets.update(
                _resolve_target_principals(evt, target_to_principal, focal_ids)
            )
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"Cross-actor activity: {len(cross_actor_events)} event(s) "
                      f"with actors {sorted(actors)} targeting "
                      f"principals {sorted(targets - actors)}",
            polarity="neutral",
            confidence=0.9,
            category=CROSS_ACTOR,
            backed_by_evidence_ids=evidence_ids,
            subject_entity_ids=sorted(actors | targets),
            time_range=time_range,
        ))
        if self_directed_count > 0:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"{self_directed_count} self-directed event(s) alongside "
                          f"cross-actor activity",
                polarity="neutral",
                confidence=0.7,
                category=SELF_DIRECTED,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=sorted(focal_ids),
                time_range=time_range,
            ))

    return claims


def _claims_credential_targeting(
    evidence_events: list[dict],
    focal: FocalResult,
    target_to_principal: dict[str, str],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Credential-targeted event claims (reset, enroll, revoke).

    Detects cross-account credential operations where the actor is not the
    owning principal of the targeted credential. This is the distinguishing
    signal for password takeover scenarios.
    """
    credential_actions = {"credential.reset", "credential.enroll", "credential.revoke"}
    focal_ids = set(focal.focal_ids)
    claims = []

    for evt in evidence_events:
        action = evt.get("action", "")
        if action not in credential_actions:
            continue

        actor_id = evt.get("actor", {}).get("actor_entity_id", "")
        target_ids = [t.get("target_entity_id", "") for t in evt.get("targets", [])]

        # Resolve credential targets to owning principals
        target_owners: set[str] = set()
        for tid in target_ids:
            if tid in target_to_principal:
                target_owners.add(target_to_principal[tid])
            elif tid in focal_ids:
                target_owners.add(tid)

        # Cross-account credential targeting: actor is not the credential owner
        is_cross_account = target_owners and actor_id not in target_owners
        # Also check the event's own context for cross_account flag
        ctx = evt.get("context") or {}
        if ctx.get("cross_account"):
            is_cross_account = True

        verb = action.split(".")[-1]
        owner_str = ", ".join(sorted(target_owners)) if target_owners else "unknown"

        if is_cross_account:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Cross-account credential {verb}: {actor_id} "
                          f"{verb} credential owned by {owner_str} at {evt['ts']}",
                polarity="neutral",
                confidence=0.95,
                category=CROSS_ACCOUNT_CREDENTIAL,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[actor_id] + sorted(target_owners),
                time_range=time_range,
            ))
        else:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Credential {verb}: {actor_id} {verb} own credential "
                          f"at {evt['ts']}",
                polarity="neutral",
                confidence=0.8,
                category=SELF_CREDENTIAL,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[actor_id],
                time_range=time_range,
            ))

    return claims


def _claims_ip_pattern(
    all_events: list[dict],
    focal: FocalResult,
    evidence_ids: list[str],
    cov_status: str,
    time_range: TimeRange,
) -> list[Claim]:
    """IP analysis claims derived from all_events."""
    # Build actor -> IPs mapping
    actor_ips: dict[str, set[str]] = {}
    for evt in all_events:
        actor_id = evt.get("actor", {}).get("actor_entity_id", "")
        ctx = evt.get("context") or {}
        ip = ctx.get("source_ip")
        if ip:
            actor_ips.setdefault(actor_id, set()).add(ip)

    if not actor_ips:
        return [Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement="No source IP context available in events",
            polarity="neutral",
            confidence=0.5,
            category=NO_IP,
            backed_by_evidence_ids=evidence_ids,
            time_range=time_range,
        )]

    claims = []
    all_ips = set()
    for ips in actor_ips.values():
        all_ips.update(ips)

    # Single IP across all actors
    if len(all_ips) == 1:
        ip = next(iter(all_ips))
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"All activity from single source IP ({ip})",
            polarity="neutral",
            confidence=0.9 if cov_status == "complete" else 0.5,
            category=SINGLE_IP,
            backed_by_evidence_ids=evidence_ids,
            subject_entity_ids=sorted(focal.focal_ids),
            time_range=time_range,
        ))
    else:
        # Multiple actors sharing the same IP
        ip_to_actors: dict[str, set[str]] = {}
        for actor, ips in actor_ips.items():
            for ip in ips:
                ip_to_actors.setdefault(ip, set()).add(actor)

        shared_ips = {ip: actors for ip, actors in ip_to_actors.items() if len(actors) > 1}
        if shared_ips:
            for ip, actors in shared_ips.items():
                claims.append(Claim(
                    id=generate_ulid(),
                    tlp="AMBER",
                    statement=f"Shared source IP {ip} across actors: "
                              f"{sorted(actors)}",
                    polarity="neutral",
                    confidence=0.85,
                    category=SHARED_IP,
                    backed_by_evidence_ids=evidence_ids,
                    subject_entity_ids=sorted(actors),
                    time_range=time_range,
                ))

        # Multiple IPs for a single actor
        for actor, ips in actor_ips.items():
            if len(ips) > 1:
                claims.append(Claim(
                    id=generate_ulid(),
                    tlp="AMBER",
                    statement=f"Actor {actor} observed from {len(ips)} IPs: "
                              f"{sorted(ips)}",
                    polarity="neutral",
                    confidence=0.8,
                    category=IP_SHIFT,
                    backed_by_evidence_ids=evidence_ids,
                    subject_entity_ids=[actor],
                    time_range=time_range,
                ))

    return claims


_LIFECYCLE_CATEGORY = {
    "create": LIFECYCLE_CREATE,
    "delete": LIFECYCLE_DELETE,
    "disable": LIFECYCLE_DISABLE,
}


def _claims_lifecycle(
    evidence_events: list[dict],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Account lifecycle claims (create, delete, disable)."""
    lifecycle_actions = {"auth.account.create", "auth.account.delete", "auth.account.disable"}
    claims = []

    for evt in evidence_events:
        action = evt.get("action", "")
        if action not in lifecycle_actions:
            continue

        actor_id = evt["actor"]["actor_entity_id"]
        target_ids = [t["target_entity_id"] for t in evt.get("targets", [])]
        verb = action.split(".")[-1]

        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"Account {verb}: {actor_id} {verb}d {', '.join(target_ids)} "
                      f"at {evt['ts']}",
            polarity="neutral",
            confidence=0.9,
            category=_LIFECYCLE_CATEGORY.get(verb, LIFECYCLE_CREATE),
            backed_by_evidence_ids=evidence_ids,
            subject_entity_ids=[actor_id] + target_ids,
            time_range=time_range,
        ))

    return claims


def _claims_privilege(
    evidence_events: list[dict],
    focal: FocalResult,
    target_to_principal: dict[str, str],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Privilege change claims."""
    focal_ids = set(focal.focal_ids)
    claims = []

    for evt in evidence_events:
        if not evt.get("action", "").startswith("privilege."):
            continue

        actor_id = evt["actor"]["actor_entity_id"]
        target_principals = _resolve_target_principals(evt, target_to_principal, focal_ids)
        outcome = evt.get("outcome", "unknown")
        ctx = evt.get("context") or {}

        target_ids = [t["target_entity_id"] for t in evt.get("targets", [])]
        role = ctx.get("role_name", ctx.get("privilege", "unknown"))

        if outcome == "failed":
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Failed privilege grant: {actor_id} attempted "
                          f"to grant {role} to {', '.join(target_ids)} at {evt['ts']}",
                polarity="neutral",
                confidence=0.85,
                category=PRIVILEGE_FAILED,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[actor_id] + target_ids,
                time_range=time_range,
            ))
        elif actor_id in target_principals or actor_id in target_ids:
            # Self-grant
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Self-grant: {actor_id} granted {role} to "
                          f"self at {evt['ts']}",
                polarity="neutral",
                confidence=0.95,
                category=PRIVILEGE_SELF_GRANT,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[actor_id],
                time_range=time_range,
            ))
        else:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Privilege grant: {actor_id} granted {role} to "
                          f"{', '.join(target_ids)} at {evt['ts']}",
                polarity="neutral",
                confidence=0.8,
                category=PRIVILEGE_GRANT,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[actor_id] + target_ids,
                time_range=time_range,
            ))

    return claims


def _claims_temporal_clustering(
    evidence_events: list[dict],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Detect sequences of 3+ evidence events within 10 minutes."""
    if len(evidence_events) < 3:
        return []

    sorted_events = sorted(evidence_events, key=lambda e: e.get("ts", ""))
    claims = []
    cluster: list[dict] = [sorted_events[0]]

    for evt in sorted_events[1:]:
        prev_ts = cluster[-1].get("ts", "")
        curr_ts = evt.get("ts", "")
        if within_minutes(prev_ts, curr_ts, 10):
            cluster.append(evt)
        else:
            if len(cluster) >= 3:
                claims.append(_make_cluster_claim(cluster, evidence_ids, time_range))
            cluster = [evt]

    if len(cluster) >= 3:
        claims.append(_make_cluster_claim(cluster, evidence_ids, time_range))

    return claims



def _make_cluster_claim(
    cluster: list[dict],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> Claim:
    actions = [e.get("action", "?") for e in cluster]
    first_ts = cluster[0].get("ts", "?")
    last_ts = cluster[-1].get("ts", "?")
    return Claim(
        id=generate_ulid(),
        tlp="AMBER",
        statement=f"Temporal cluster: {len(cluster)} events in rapid succession "
                  f"({first_ts} to {last_ts}): {', '.join(actions)}",
        polarity="neutral",
        confidence=0.7,
        category=TEMPORAL_CLUSTER,
        backed_by_evidence_ids=evidence_ids,
        time_range=time_range,
    )


def _claims_failed_outcomes(
    evidence_events: list[dict],
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Claims for events with outcome == failed."""
    failed = [e for e in evidence_events if e.get("outcome") == "failed"]
    if not failed:
        return []

    claims = []
    for evt in failed:
        actor_id = evt["actor"]["actor_entity_id"]
        target_ids = [t["target_entity_id"] for t in evt.get("targets", [])]
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"Failed action: {evt['action']} by {actor_id} "
                      f"targeting {', '.join(target_ids)} at {evt['ts']}",
            polarity="neutral",
            confidence=0.8,
            category=FAILED_OUTCOME,
            backed_by_evidence_ids=evidence_ids,
            subject_entity_ids=[actor_id] + target_ids,
            time_range=time_range,
        ))

    return claims


def _claims_coverage(
    cov_envelope: dict,
    evidence_ids: list[str],
    time_range: TimeRange,
) -> list[Claim]:
    """Coverage claim if not complete."""
    cov_status = cov_envelope["coverage_report"]["overall_status"]
    if cov_status == "complete":
        return []

    return [Claim(
        id=generate_ulid(),
        tlp="AMBER",
        statement=f"Coverage is {cov_status} -- findings are constrained "
                  f"by data gaps",
        polarity="neutral",
        confidence=1.0,
        category=COVERAGE_GAP,
        backed_by_evidence_ids=[evidence_ids[-1]] if evidence_ids else [],
        time_range=time_range,
    )]


def _claims_from_aggregated_facts(
    aggregated_facts: list,
    evidence_items: list[EvidenceItem],
    time_range: TimeRange,
) -> list[Claim]:
    """Convert EvidenceFacts into Claims with precise evidence backing."""
    # Build event_id -> set[evidence_item_id] mapping
    event_to_evidence: dict[str, set[str]] = {}
    for ei in evidence_items:
        for evt_id in ei.related_event_ids:
            event_to_evidence.setdefault(evt_id, set()).add(ei.id)

    claims = []
    for fact in aggregated_facts:
        # Collect only the evidence items whose events overlap with this fact
        backed_by: set[str] = set()
        for evt_id in fact.event_ids:
            backed_by.update(event_to_evidence.get(evt_id, set()))

        # Fall back to all evidence if no overlap found
        if not backed_by:
            backed_by = {ei.id for ei in evidence_items}

        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=fact.summary,
            polarity="neutral",
            confidence=fact.confidence,
            category=fact.fact_type,
            backed_by_evidence_ids=sorted(backed_by),
            subject_entity_ids=fact.entity_ids,
            time_range=time_range,
        ))

    return claims


# ---------------------------------------------------------------------------
# Hypothesis building -- pattern classification and polarity assignment
# ---------------------------------------------------------------------------

# Categories that gate each candidate pattern
_LIFECYCLE_CATEGORIES = {LIFECYCLE_CREATE, LIFECYCLE_DELETE, LIFECYCLE_DISABLE}


def _classify_pattern(claims: list[Claim]) -> str:
    """Classify the evidence pattern from claim categories.

    When multiple pattern signals are present, pick the dominant one
    by counting how many claims match each candidate pattern's polarity
    rules.
    """
    categories = {c.category for c in claims}

    has_lifecycle = bool(categories & _LIFECYCLE_CATEGORIES)
    has_cross_actor = CROSS_ACTOR in categories
    has_self_directed = SELF_DIRECTED in categories
    has_shared_ip = SHARED_IP in categories
    has_self_grant = PRIVILEGE_SELF_GRANT in categories
    has_credential_takeover = CROSS_ACCOUNT_CREDENTIAL in categories

    candidates: list[tuple[str, int]] = []

    if has_credential_takeover and has_cross_actor:
        candidates.append(("credential_takeover", _count_category_matches(
            claims, _POLARITY_RULES["credential_takeover"],
        )))

    if has_self_grant:
        candidates.append(("privilege_escalation", _count_category_matches(
            claims, _POLARITY_RULES["privilege_escalation"],
        )))

    if has_lifecycle:
        candidates.append(("account_manipulation", _count_category_matches(
            claims, _POLARITY_RULES["account_manipulation"],
        )))

    if has_cross_actor and has_shared_ip:
        candidates.append(("coordinated_cross_account", _count_category_matches(
            claims, _POLARITY_RULES["coordinated_cross_account"],
        )))
    elif has_cross_actor:
        candidates.append(("cross_account", _count_category_matches(
            claims, _POLARITY_RULES["cross_account"],
        )))

    if has_self_directed and not has_cross_actor:
        candidates.append(("legitimate_self_service", _count_category_matches(
            claims, _POLARITY_RULES["legitimate_self_service"],
        )))

    if not candidates:
        return "unclear"

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _count_category_matches(claims: list[Claim], rules: dict[str, str]) -> int:
    """Count how many claims have a category that appears in the rules."""
    return sum(1 for c in claims if c.category in rules)


_PATTERN_STATEMENTS = {
    "legitimate_self_service": "Activity is consistent with legitimate self-service",
    "credential_takeover": "Evidence indicates cross-account credential takeover",
    "account_manipulation": "Evidence indicates account manipulation",
    "privilege_escalation": "Evidence indicates privilege escalation",
    "coordinated_cross_account": "Evidence indicates coordinated cross-account operations",
    "cross_account": "Evidence indicates cross-account activity",
    "unclear": None,  # falls back to question-based
}

# Polarity rules: map from claim category to supports/contradicts per pattern
_POLARITY_RULES: dict[str, dict[str, str]] = {
    "legitimate_self_service": {
        SELF_DIRECTED: "supports",
        SELF_CREDENTIAL: "supports",
        SINGLE_IP: "supports",
        CROSS_ACTOR: "contradicts",
        SHARED_IP: "contradicts",
        CROSS_ACCOUNT_CREDENTIAL: "contradicts",
    },
    "credential_takeover": {
        CROSS_ACCOUNT_CREDENTIAL: "supports",
        CROSS_ACTOR: "supports",
        SHARED_IP: "supports",
        LIFECYCLE_DELETE: "supports",
        FAILED_OUTCOME: "supports",
        TEMPORAL_CLUSTER: "supports",
        LIFECYCLE_CHAIN: "supports",
        SHARED_INDICATOR: "supports",
        CREDENTIAL_SEQUENCE: "supports",
        ACTION_BURST: "supports",
        SELF_DIRECTED: "contradicts",
        SELF_CREDENTIAL: "contradicts",
    },
    "account_manipulation": {
        LIFECYCLE_CREATE: "supports",
        LIFECYCLE_DELETE: "supports",
        LIFECYCLE_DISABLE: "supports",
        CROSS_ACTOR: "supports",
        TEMPORAL_CLUSTER: "supports",
        LIFECYCLE_CHAIN: "supports",
        ACTION_BURST: "supports",
        SELF_DIRECTED: "contradicts",
    },
    "privilege_escalation": {
        PRIVILEGE_SELF_GRANT: "supports",
        PRIVILEGE_GRANT: "supports",
        PRIVILEGE_FAILED: "supports",
        CROSS_ACTOR: "supports",
        TEMPORAL_CLUSTER: "supports",
        ACTION_BURST: "supports",
    },
    "coordinated_cross_account": {
        CROSS_ACTOR: "supports",
        SHARED_IP: "supports",
        TEMPORAL_CLUSTER: "supports",
        SHARED_INDICATOR: "supports",
        ACTION_BURST: "supports",
        SELF_DIRECTED: "contradicts",
    },
    "cross_account": {
        CROSS_ACTOR: "supports",
        TEMPORAL_CLUSTER: "supports",
        SELF_DIRECTED: "contradicts",
    },
    "unclear": {},
}


def _assign_polarity(claims: list[Claim], pattern: str) -> list[Claim]:
    """Assign polarity to claims based on the classified pattern.

    Returns a new list of claims with polarity updated. Claims whose
    category does not appear in the pattern's rules keep their original
    polarity (typically neutral).
    """
    rules = _POLARITY_RULES.get(pattern, {})
    result = []

    for claim in claims:
        polarity = rules.get(claim.category)
        if polarity:
            result.append(claim.model_copy(update={"polarity": polarity}))
        else:
            result.append(claim)

    return result


def build_hypothesis(
    claims: list[Claim],
    cov_envelope: dict,
    investigation_question: str,
    evidence_events: list[dict],
    evidence_prefixes: list[str],
) -> tuple[Hypothesis, list[Claim]]:
    """Create a Hypothesis with pattern-driven scoring.

    Classifies the evidence pattern from claims, assigns polarity,
    and scores mechanically.

    Returns (hypothesis, polarity_assigned_claims). The second value is
    the claims list with polarity updated -- callers should use this for
    narrative generation and LLM prompts instead of the original neutral
    claims.
    """
    cov = cov_envelope["coverage_report"]
    cov_status = cov["overall_status"]

    # Classify pattern and assign polarity
    pattern = _classify_pattern(claims)
    scored_claims = _assign_polarity(claims, pattern)

    supporting = [c for c in scored_claims if c.polarity == "supports"]
    contradicting = [c for c in scored_claims if c.polarity == "contradicts"]

    # Score mechanically
    if supporting and contradicting:
        sup_weight = sum(c.confidence for c in supporting)
        con_weight = sum(c.confidence for c in contradicting)
        likelihood = sup_weight / (sup_weight + con_weight)
    elif supporting:
        likelihood = sum(c.confidence for c in supporting) / len(supporting)
    elif contradicting:
        likelihood = sum(c.confidence for c in contradicting) / len(contradicting)
    elif evidence_events:
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

    gaps = [cov["id"]] if cov_status != "complete" else []

    next_evidence_requests = []
    if cov_status != "complete":
        next_evidence_requests.append({
            "domain": "identity",
            "tool": "search_events",
            "params": {
                "actions": [f"{p}*" for p in evidence_prefixes],
            },
            "priority": "high",
        })

    # Pattern-driven statement
    statement = _PATTERN_STATEMENTS.get(pattern)
    if not statement:
        statement = f"Assessment of: {investigation_question}"

    hyp = Hypothesis(
        id=generate_ulid(),
        tlp="AMBER",
        iq_id=investigation_question,
        statement=statement,
        likelihood_score=round(likelihood, 3),
        confidence_limit=round(confidence_limit, 3),
        supporting_claim_ids=[c.id for c in supporting],
        contradicting_claim_ids=[c.id for c in contradicting] or None,
        gaps=gaps,
        next_evidence_requests=next_evidence_requests,
        status="open",
    )

    return hyp, scored_claims


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------

_NEXT_STEPS_BY_CATEGORY: list[tuple[str, str]] = [
    (LIFECYCLE_CREATE, "Audit account lifecycle and creation patterns"),
    (LIFECYCLE_DELETE, "Audit account lifecycle and deletion patterns"),
    (LIFECYCLE_DISABLE, "Review account disable actions for remediation context"),
    (PRIVILEGE_GRANT, "Review privilege grants and authorization chains"),
    (PRIVILEGE_SELF_GRANT, "Investigate self-grant escalation path"),
    (CROSS_ACTOR, "Correlate cross-actor activity across domains"),
    (SHARED_IP, "Correlate source IPs across actors"),
    (IP_SHIFT, "Investigate IP address changes for session anomalies"),
    (TEMPORAL_CLUSTER, "Review rapid action sequences for automation indicators"),
    (FAILED_OUTCOME, "Investigate failed actions for brute-force or policy blocks"),
    (CROSS_ACCOUNT_CREDENTIAL, "Investigate cross-account credential changes for takeover indicators"),
    (LIFECYCLE_CHAIN, "Review account lifecycle chain for coordinated manipulation"),
    (SHARED_INDICATOR, "Investigate shared network indicators across actors"),
    (CREDENTIAL_SEQUENCE, "Trace credential abuse sequence end-to-end"),
    (ACTION_BURST, "Review burst of repeated actions for automation or attack tooling"),
]


def build_narrative(
    hypothesis: Hypothesis,
    claims: list[Claim],
    cov_envelope: dict,
) -> dict:
    """Build formulaic narrative text for mechanical mode.

    Returns dict with: hypothesis_text, likelihood_assessment,
    confidence_assessment, gaps, next_steps.
    """
    cov = cov_envelope["coverage_report"]
    cov_status = cov["overall_status"]

    supporting = [c for c in claims if c.polarity == "supports"]
    contradicting = [c for c in claims if c.polarity == "contradicts"]

    # Hypothesis text
    hypothesis_text = hypothesis.statement

    # Likelihood assessment
    if supporting and not contradicting:
        likelihood_assessment = (
            f"Evidence supports the hypothesis. "
            f"{len(supporting)} supporting claim(s) with average confidence "
            f"{sum(c.confidence for c in supporting) / len(supporting):.2f}."
        )
    elif supporting and contradicting:
        likelihood_assessment = (
            f"Mixed evidence. {len(supporting)} supporting and "
            f"{len(contradicting)} contradicting claim(s). "
            f"Likelihood reduced due to contradicting evidence."
        )
    else:
        likelihood_assessment = (
            "Insufficient evidence to strongly support or contradict the hypothesis."
        )

    # Confidence assessment
    if cov_status == "complete":
        confidence_assessment = (
            "Full telemetry coverage available. "
            "Confidence limit is high (0.95)."
        )
    elif cov_status == "partial":
        confidence_assessment = (
            f"Partial telemetry coverage. "
            f"Confidence limit capped at 0.6 due to data gaps. "
            f"Findings may be incomplete."
        )
    else:
        confidence_assessment = (
            f"Coverage is {cov_status}. "
            f"Confidence limit is low (0.3). "
            f"Cannot draw reliable conclusions from available data."
        )

    # Gaps
    gaps = []
    if cov_status != "complete":
        for src in cov.get("sources", []):
            if src["status"] != "complete":
                gap_msg = f"{src['source_name']}: {src['status']}"
                if src.get("notes"):
                    gap_msg += f" -- {src['notes']}"
                gaps.append(gap_msg)

    # Next steps -- derived from claim categories present
    next_steps = []
    if cov_status != "complete":
        next_steps.append("Obtain complete telemetry to raise confidence limit")

    present_categories = {c.category for c in claims}
    seen_steps: set[str] = set()
    for cat, step_text in _NEXT_STEPS_BY_CATEGORY:
        if cat in present_categories and step_text not in seen_steps:
            next_steps.append(step_text)
            seen_steps.add(step_text)

    if not next_steps:
        next_steps.append("Investigation complete with high confidence")

    return {
        "hypothesis_text": hypothesis_text,
        "likelihood_assessment": likelihood_assessment,
        "confidence_assessment": confidence_assessment,
        "gaps": gaps,
        "next_steps": next_steps,
    }
