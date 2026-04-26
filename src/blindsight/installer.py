"""Claude Code MCP-config installer.

Writes a `blindsight-investigation` entry into the user's Claude Code
settings (or the project-scope `.mcp.json`), preserving any existing
entries and writing a `.bak` before overwriting.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


_USER_CONFIG = Path.home() / ".claude" / "settings.json"
_PROJECT_CONFIG = Path.cwd() / ".mcp.json"
_SERVER_NAME = "blindsight-investigation"
_BIN_NAME = "blindsight-investigation-mcp"


@dataclass
class InstallPlan:
    config_path: Path
    command: str
    backup_path: Path | None  # None if config_path didn't exist yet
    seed_dirs: list[Path]


def _resolve_command() -> str:
    found = shutil.which(_BIN_NAME)
    if found is None:
        raise RuntimeError(
            f"{_BIN_NAME!r} not found on PATH. "
            f"Install the package first (e.g. `pipx install blindsight`)."
        )
    return found


def _config_path(project_scope: bool) -> Path:
    return _PROJECT_CONFIG if project_scope else _USER_CONFIG


def _read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as fh:
        return json.load(fh)


def _merge(existing: dict, command: str) -> dict:
    """Add or update the blindsight-investigation entry, preserve everything else."""
    merged = dict(existing)
    servers = dict(merged.get("mcpServers", {}))
    servers[_SERVER_NAME] = {"command": command, "args": []}
    merged["mcpServers"] = servers
    return merged


def plan_install(project_scope: bool = False) -> InstallPlan:
    """Compute what `install` would do without touching the filesystem."""
    config_path = _config_path(project_scope)
    command = _resolve_command()
    backup = config_path.with_suffix(config_path.suffix + ".bak") if config_path.exists() else None
    seed_dirs = [
        Path.home() / ".blindsight" / "cases",
        Path.home() / ".blindsight" / "scenarios",
    ]
    return InstallPlan(
        config_path=config_path,
        command=command,
        backup_path=backup,
        seed_dirs=seed_dirs,
    )


def apply_install(plan: InstallPlan) -> None:
    """Execute the install plan: backup, merge, seed directories."""
    if plan.config_path.exists() and plan.backup_path is not None:
        shutil.copy2(plan.config_path, plan.backup_path)

    plan.config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing(plan.config_path)
    merged = _merge(existing, plan.command)
    with plan.config_path.open("w") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")

    for d in plan.seed_dirs:
        d.mkdir(parents=True, exist_ok=True)


def format_plan(plan: InstallPlan) -> str:
    lines = [
        f"Config:   {plan.config_path}",
        f"Command:  {plan.command}",
        f"Backup:   {plan.backup_path or '(none — config does not exist yet)'}",
        f"Seed dirs:",
    ]
    for d in plan.seed_dirs:
        lines.append(f"  {d}")
    return "\n".join(lines)
