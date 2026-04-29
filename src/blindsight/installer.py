"""Claude Code MCP-config installer.

Registers the `blindsight-investigation` MCP server with Claude Code by
shelling out to the `claude mcp` CLI. This delegates the
config-file format and location to Claude Code itself, which is the
correct authority. Direct writes to `~/.claude/settings.json` do not work:
that file is for Claude Code settings, not MCP server registration.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


_SERVER_NAME = "blindsight-investigation"
_BIN_NAME = "blindsight-investigation-mcp"
_CLAUDE_BIN = "claude"


@dataclass
class InstallPlan:
    scope: str  # "user" or "project"
    command: str
    seed_dirs: list[str]


def _resolve_command() -> str:
    found = shutil.which(_BIN_NAME)
    if found is None:
        raise RuntimeError(
            f"{_BIN_NAME!r} not found on PATH. "
            f"Install the package first (e.g. `pipx install blindsight`)."
        )
    return found


def _resolve_claude_cli() -> str:
    found = shutil.which(_CLAUDE_BIN)
    if found is None:
        raise RuntimeError(
            "`claude` CLI not found on PATH. Install Claude Code first: "
            "https://claude.com/claude-code"
        )
    return found


def plan_install(project_scope: bool = False) -> InstallPlan:
    """Compute what `install` would do without touching the filesystem."""
    _resolve_claude_cli()  # fail fast if claude CLI missing
    command = _resolve_command()
    from pathlib import Path
    seed_dirs = [
        str(Path.home() / ".blindsight" / "cases"),
        str(Path.home() / ".blindsight" / "scenarios"),
    ]
    return InstallPlan(
        scope="project" if project_scope else "user",
        command=command,
        seed_dirs=seed_dirs,
    )


def apply_install(plan: InstallPlan) -> None:
    """Register the server with Claude Code and seed directories.

    Idempotent: removes any prior registration of the same name first,
    then adds the current one. Errors from `claude mcp` surface to the
    caller for CLI display.
    """
    claude = _resolve_claude_cli()

    # Remove prior registration (ignore failure — server may not exist).
    subprocess.run(
        [claude, "mcp", "remove", "-s", plan.scope, _SERVER_NAME],
        capture_output=True,
        check=False,
    )

    # Add fresh registration. -- separator stops claude from parsing
    # subsequent args as its own options.
    result = subprocess.run(
        [claude, "mcp", "add", "-s", plan.scope, _SERVER_NAME, "--", plan.command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`claude mcp add` failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    from pathlib import Path
    for d in plan.seed_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


def format_plan(plan: InstallPlan) -> str:
    lines = [
        f"Scope:    {plan.scope}",
        f"Command:  {plan.command}",
        f"Action:   claude mcp add -s {plan.scope} {_SERVER_NAME} -- {plan.command}",
        f"Seed dirs:",
    ]
    for d in plan.seed_dirs:
        lines.append(f"  {d}")
    return "\n".join(lines)


@dataclass
class UninstallPlan:
    scope: str
    purge_data: bool
    data_dirs: list[str]


def plan_uninstall(project_scope: bool = False, purge_data: bool = False) -> UninstallPlan:
    """Compute what `uninstall` would do without touching the filesystem."""
    _resolve_claude_cli()
    from pathlib import Path
    data_dirs = [
        str(Path.home() / ".blindsight" / "cases"),
        str(Path.home() / ".blindsight" / "scenarios"),
    ]
    return UninstallPlan(
        scope="project" if project_scope else "user",
        purge_data=purge_data,
        data_dirs=data_dirs,
    )


def apply_uninstall(plan: UninstallPlan) -> None:
    """Remove the Claude Code MCP registration. Optionally purge data dirs.

    Idempotent: `claude mcp remove` returning non-zero (server not registered)
    is treated as success. Data-dir purge is opt-in via `purge_data`; case
    DuckDB files are user data and must not be deleted by accident.
    """
    claude = _resolve_claude_cli()
    result = subprocess.run(
        [claude, "mcp", "remove", "-s", plan.scope, _SERVER_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    # rc != 0 typically means "no such server" — fine, idempotent.
    # Surface stderr only if it looks like an unexpected failure.
    if result.returncode != 0 and "not found" not in (result.stderr or "").lower():
        # Best-effort: don't raise on remove. Print to stderr at the CLI layer
        # if the caller wants visibility. Most users see no output here.
        pass

    if plan.purge_data:
        import shutil as _shutil
        from pathlib import Path
        for d in plan.data_dirs:
            p = Path(d)
            if p.is_dir():
                _shutil.rmtree(p)


def format_uninstall_plan(plan: UninstallPlan) -> str:
    lines = [
        f"Scope:    {plan.scope}",
        f"Action:   claude mcp remove -s {plan.scope} {_SERVER_NAME}",
    ]
    if plan.purge_data:
        lines.append(f"Purge:")
        for d in plan.data_dirs:
            lines.append(f"  rm -rf {d}")
    else:
        lines.append(f"Data dirs preserved: {', '.join(plan.data_dirs)}")
        lines.append(f"  (pass --purge-data to delete)")
    return "\n".join(lines)
