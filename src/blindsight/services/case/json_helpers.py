"""JSON serialization helpers for DuckDB case store columns.

DuckDB JSON columns are physically VARCHAR. These helpers provide canonical
serialization/deserialization to avoid NULL-vs-empty-array ambiguity.
"""
import json
from typing import Any, Optional

from pydantic import BaseModel


def to_json(value: Any) -> Optional[str]:
    """Serialize a value for INSERT into a JSON column.

    Returns None (SQL NULL) for None values, JSON string otherwise.
    Pydantic models are dumped with exclude_none=True.
    """
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(exclude_none=True))
    if isinstance(value, str):
        return value
    return json.dumps(value)


def from_json(value: Any) -> Any:
    """Deserialize a JSON column value from SELECT.

    SQL NULL -> None, JSON string -> parsed, already parsed -> pass through.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value
