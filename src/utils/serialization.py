"""Serialization helpers for NDJSON and YAML loading."""
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml


def dataclass_to_dict(obj: Any) -> dict:
    """Convert a dataclass to dict, recursively stripping None values."""
    raw = asdict(obj)
    return _strip_nones(raw)


def _strip_nones(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nones(item) for item in obj]
    return obj


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
