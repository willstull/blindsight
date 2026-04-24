"""TLP (Traffic Light Protocol) policy helpers."""
from blindsight.types.core import TLPLevel, TLP_ORDER


def normalize_tlp(value: str | None, default: TLPLevel = "AMBER") -> TLPLevel:
    """Normalize a TLP string to a valid TLPLevel."""
    if not value:
        return default
    normalized = value.upper()
    if normalized in TLP_ORDER:
        return normalized  # type: ignore[return-value]
    return default


def max_tlp(values: list[str | None], default: TLPLevel = "AMBER") -> TLPLevel:
    """Return the highest TLP marking from a list of values."""
    levels = [normalize_tlp(v, default=default) for v in values]
    if not levels:
        return default
    return max(levels, key=lambda level: TLP_ORDER[level])
