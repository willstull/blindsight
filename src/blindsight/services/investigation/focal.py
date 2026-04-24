"""Focal entity resolution for investigation pipeline.

Pure functions -- no I/O, no side effects. Determines which principals
are central to an investigation based on evidence activity, relationships,
and optional hints.
"""
import re
from pydantic import BaseModel, Field

from blindsight.services.investigation.resolution import build_target_to_principal_map


class FocalResult(BaseModel):
    focal_ids: list[str] = Field(default_factory=list)
    primary_id: str | None = None
    confidence: float = 0.5
    rationale: list[str] = Field(default_factory=list)


def resolve_focal_principals(
    investigation_question: str,
    principal_hint: str | None,
    principals: list[dict],
    evidence_events: list[dict],
    relationships: list[dict],
) -> FocalResult:
    """Determine which principals are focal to the investigation.

    Resolution strategy (deterministic, no LLM):
    1. Hint match -- if principal_hint matches a principal ID or display_name.
    2. Question match -- extract names/identifiers from the question and match.
    3. Evidence role expansion -- resolve event targets to principals via relationships.
    4. Focal set -- all principals that appear as actors or resolved targets.
    5. Primary selection -- strongest evidence involvement, or None if ambiguous.
    """
    if not principals:
        return FocalResult(
            confidence=0.0,
            rationale=["No principals provided"],
        )

    principal_by_id = {p["id"]: p for p in principals}
    rationale: list[str] = []

    # Build target-to-principal mapping from relationships
    target_to_principal = build_target_to_principal_map(relationships, set(principal_by_id.keys()))

    # Step 1: Hint match
    if principal_hint:
        hint_match = _match_hint(principal_hint, principals)
        if hint_match:
            rationale.append(f"Hint matched principal: {hint_match}")

    # Step 2: Question match
    question_matches = _match_question(investigation_question, principals)
    if question_matches:
        rationale.append(
            f"Question references principal(s): {', '.join(question_matches)}"
        )

    # Step 3-4: Build focal set from evidence activity
    actor_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}

    for evt in evidence_events:
        actor_id = evt.get("actor", {}).get("actor_entity_id", "")
        if actor_id in principal_by_id:
            actor_counts[actor_id] = actor_counts.get(actor_id, 0) + 1

        for tgt in evt.get("targets", []):
            target_id = tgt.get("target_entity_id", "")
            # Direct principal target
            if target_id in principal_by_id:
                target_counts[target_id] = target_counts.get(target_id, 0) + 1
            # Resolve via relationships (e.g., credential -> principal)
            elif target_id in target_to_principal:
                resolved_id = target_to_principal[target_id]
                target_counts[resolved_id] = target_counts.get(resolved_id, 0) + 1

    # Focal set: principals with any evidence involvement
    focal_ids_set: set[str] = set()
    focal_ids_set.update(actor_counts.keys())
    focal_ids_set.update(target_counts.keys())

    # Step 5: Primary selection
    # Priority: hint > question match (if unique) > evidence activity
    primary_id: str | None = None
    confidence = 0.5

    if principal_hint:
        hint_match = _match_hint(principal_hint, principals)
        if hint_match:
            primary_id = hint_match
            focal_ids_set.add(hint_match)
            confidence = 0.9
            rationale.append(f"Primary set from hint: {hint_match}")

    if primary_id is None and len(question_matches) == 1:
        qm = question_matches[0]
        if qm in focal_ids_set or not focal_ids_set:
            primary_id = qm
            focal_ids_set.add(qm)
            confidence = 0.8
            rationale.append(f"Primary set from question match: {qm}")

    if primary_id is None and focal_ids_set:
        # Score by combined activity
        scores: dict[str, int] = {}
        for pid in focal_ids_set:
            scores[pid] = actor_counts.get(pid, 0) + target_counts.get(pid, 0)

        sorted_by_score = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_by_score) == 1:
            primary_id = sorted_by_score[0][0]
            confidence = 0.85
            rationale.append(f"Single focal principal: {primary_id}")
        elif len(sorted_by_score) >= 2:
            top_score = sorted_by_score[0][1]
            second_score = sorted_by_score[1][1]
            if top_score > second_score:
                primary_id = sorted_by_score[0][0]
                confidence = 0.7
                rationale.append(
                    f"Primary by activity ({top_score} vs {second_score}): "
                    f"{primary_id}"
                )
            else:
                # Tied -- no primary
                confidence = 0.4
                rationale.append(
                    f"Ambiguous: {len(sorted_by_score)} principals with "
                    f"similar activity levels"
                )

    # Step 6: Empty case -- no evidence activity
    if not focal_ids_set:
        focal_ids_set = set(principal_by_id.keys())
        confidence = 0.2
        rationale.append(
            "No evidence activity found; all principals included as focal"
        )

    focal_ids = sorted(focal_ids_set)

    return FocalResult(
        focal_ids=focal_ids,
        primary_id=primary_id,
        confidence=confidence,
        rationale=rationale,
    )



def _match_hint(hint: str, principals: list[dict]) -> str | None:
    """Match a principal_hint against IDs and display_names."""
    hint_lower = hint.lower()
    for p in principals:
        if p["id"].lower() == hint_lower:
            return p["id"]
        if p.get("display_name", "").lower() == hint_lower:
            return p["id"]
    # Partial match
    for p in principals:
        if hint_lower in p["id"].lower():
            return p["id"]
        if hint_lower in p.get("display_name", "").lower():
            return p["id"]
    return None


def _match_question(question: str, principals: list[dict]) -> list[str]:
    """Extract principal references from the investigation question."""
    matches: list[str] = []
    question_lower = question.lower()

    for p in principals:
        if p["id"] in matches:
            continue

        display = p.get("display_name", "")

        # Check display_name (e.g., "alice@example.com")
        if display and display.lower() in question_lower:
            matches.append(p["id"])
            continue

        # Check local part of email display names (before @)
        if display and "@" in display:
            local_part = display.split("@")[0].lower()
            if len(local_part) >= 4 and local_part in question_lower:
                matches.append(p["id"])
                continue

        # Check email-like patterns in refs
        ref_matched = False
        for ref in p.get("refs", []):
            val = ref.get("value", "")
            if val and val.lower() in question_lower:
                matches.append(p["id"])
                ref_matched = True
                break
        if ref_matched:
            continue

        # Check if the principal ID (without prefix) appears in question.
        # Try both exact and with underscores/dots normalized, since
        # questions may use "garcia.carlos" while IDs use "garcia_carlos".
        short_name = p["id"].removeprefix("principal_")
        if len(short_name) >= 4:
            short_lower = short_name.lower()
            dotted = short_lower.replace("_", ".")
            if short_lower in question_lower or dotted in question_lower:
                matches.append(p["id"])

    return matches
