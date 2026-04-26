"""Runtime configuration for Blindsight.

Resolves cases_dir, scenarios_dir, and ANTHROPIC_API_KEY from
environment variables, an optional `~/.blindsight/config.toml`, and
sensible defaults.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import blindsight


_DEFAULT_CONFIG_FILE = Path.home() / ".blindsight" / "config.toml"
_DEFAULT_CASES_DIR = Path.home() / ".blindsight" / "cases"


@dataclass(frozen=True)
class Config:
    cases_dir: Path
    scenarios_dir: Path
    anthropic_api_key: str | None


def _bundled_scenarios_dir() -> Path:
    return Path(blindsight.__file__).parent / "scenarios"


def _read_config_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(config_file: Path = _DEFAULT_CONFIG_FILE) -> Config:
    file_data = _read_config_file(config_file)

    cases_dir_str = (
        os.environ.get("BLINDSIGHT_CASES_DIR")
        or file_data.get("cases_dir")
        or str(_DEFAULT_CASES_DIR)
    )
    scenarios_dir_str = (
        os.environ.get("BLINDSIGHT_SCENARIOS_DIR")
        or file_data.get("scenarios_dir")
        or str(_bundled_scenarios_dir())
    )

    return Config(
        cases_dir=Path(cases_dir_str),
        scenarios_dir=Path(scenarios_dir_str),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
