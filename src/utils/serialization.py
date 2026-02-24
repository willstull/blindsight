"""Serialization helpers for NDJSON and YAML loading."""
import json
from pathlib import Path
from typing import Any

import yaml


def dataclass_to_dict(obj: Any) -> dict:
    """Convert a Pydantic model to dict, excluding None values."""
    return obj.model_dump(exclude_none=True)


def load_ndjson(filepath: Path) -> list[dict]:
    """Load newline-delimited JSON file. Returns empty list if file missing."""
    if not filepath.exists():
        return []
    with filepath.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_yaml(filepath: Path) -> dict:
    """Load a YAML file."""
    with filepath.open() as f:
        return yaml.safe_load(f)
