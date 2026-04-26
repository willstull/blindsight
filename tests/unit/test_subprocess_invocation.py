"""Regression tests: subprocess MCP server invocations must use sys.executable.

Bare `python` resolves through PATH, which under `pipx install` points at
the user's system python rather than the pipx venv where blindsight is
installed — yielding ModuleNotFoundError when the top-level investigation
server tries to spawn child case/identity/app servers. Using sys.executable
pins each child to the same interpreter that's already running blindsight.
"""
import sys
from pathlib import Path


_INVOCATION_SITES = [
    Path(__file__).parent.parent.parent / "src" / "blindsight" / "servers" / "investigation_mcp.py",
    Path(__file__).parent.parent.parent / "src" / "blindsight" / "services" / "investigation" / "pipeline.py",
]


def test_no_bare_python_subprocess_invocations():
    """Production code must use sys.executable, not the string 'python'."""
    offenders = []
    for path in _INVOCATION_SITES:
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '"python"' in line or "'python'" in line:
                offenders.append(f"{path.name}:{lineno}: {stripped}")
    assert not offenders, (
        "subprocess invocations must use sys.executable; bare 'python' "
        "breaks under pipx-style isolated installs:\n  "
        + "\n  ".join(offenders)
    )
