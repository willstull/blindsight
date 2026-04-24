"""Shared resolution helpers for investigation services."""


def build_target_to_principal_map(
    relationships: list[dict],
    principal_ids: set[str],
) -> dict[str, str]:
    """Map non-principal entity IDs to owning principals via relationships.

    Handles has_credential, authenticated_as, uses_device, created_by,
    and deleted_by relationship types. This is the union of the resolution
    logic needed by both scoring (ownership types) and focal resolution
    (ownership + lifecycle types).
    """
    target_to_principal: dict[str, str] = {}
    ownership_types = {
        "has_credential", "authenticated_as", "uses_device",
        "created_by", "deleted_by",
    }

    for rel in relationships:
        rel_type = rel.get("relationship_type", "")
        from_id = rel.get("from_entity_id", "")
        to_id = rel.get("to_entity_id", "")

        if rel_type in ownership_types:
            if from_id in principal_ids and to_id not in principal_ids:
                target_to_principal[to_id] = from_id
            elif to_id in principal_ids and from_id not in principal_ids:
                target_to_principal[from_id] = to_id

    return target_to_principal
