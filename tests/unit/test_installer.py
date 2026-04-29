"""Tests for the Claude Code MCP-config installer."""
from pathlib import Path

import pytest

from blindsight import installer


@pytest.fixture
def fake_command(monkeypatch):
    monkeypatch.setattr(
        installer, "_resolve_command",
        lambda: "/usr/local/bin/blindsight-investigation-mcp",
    )


@pytest.fixture
def fake_claude_cli(monkeypatch):
    monkeypatch.setattr(
        installer, "_resolve_claude_cli",
        lambda: "/usr/local/bin/claude",
    )


def _make_plan(tmp_path, scope="user", command="/usr/local/bin/blindsight-investigation-mcp"):
    return installer.InstallPlan(
        scope=scope,
        command=command,
        seed_dirs=[str(tmp_path / "cases"), str(tmp_path / "scenarios")],
    )


class TestApplyInstall:
    def test_invokes_claude_mcp_remove_then_add(self, tmp_path, fake_claude_cli, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        monkeypatch.setattr(installer.subprocess, "run", fake_run)

        plan = _make_plan(tmp_path)
        installer.apply_install(plan)

        assert len(calls) == 2
        assert calls[0][1:5] == ["mcp", "remove", "-s", "user"]
        assert calls[1][1:5] == ["mcp", "add", "-s", "user"]
        assert "blindsight-investigation" in calls[1]
        assert plan.command in calls[1]

    def test_uses_project_scope_when_requested(self, tmp_path, fake_claude_cli, monkeypatch):
        calls = []
        monkeypatch.setattr(
            installer.subprocess, "run",
            lambda cmd, **kw: (calls.append(cmd), type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())[1],
        )

        plan = _make_plan(tmp_path, scope="project")
        installer.apply_install(plan)

        assert calls[1][3:5] == ["-s", "project"]

    def test_remove_failure_is_ignored(self, tmp_path, fake_claude_cli, monkeypatch):
        """Remove may fail because no prior registration exists; that's fine."""
        results = [
            type("R", (), {"returncode": 1, "stdout": "", "stderr": "not found"})(),
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        ]
        monkeypatch.setattr(
            installer.subprocess, "run",
            lambda cmd, **kw: results.pop(0),
        )

        plan = _make_plan(tmp_path)
        installer.apply_install(plan)  # no exception

    def test_add_failure_raises(self, tmp_path, fake_claude_cli, monkeypatch):
        results = [
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
            type("R", (), {"returncode": 2, "stdout": "", "stderr": "bad scope"})(),
        ]
        monkeypatch.setattr(
            installer.subprocess, "run",
            lambda cmd, **kw: results.pop(0),
        )

        plan = _make_plan(tmp_path)
        with pytest.raises(RuntimeError, match="claude mcp add. failed"):
            installer.apply_install(plan)

    def test_idempotent_on_repeat_runs(self, tmp_path, fake_claude_cli, monkeypatch):
        """Repeat runs invoke the same remove+add sequence; no state accumulates."""
        calls = []
        monkeypatch.setattr(
            installer.subprocess, "run",
            lambda cmd, **kw: (calls.append(tuple(cmd)), type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())[1],
        )

        plan = _make_plan(tmp_path)
        installer.apply_install(plan)
        installer.apply_install(plan)

        assert calls[0:2] == calls[2:4]

    def test_seeds_directories(self, tmp_path, fake_claude_cli, monkeypatch):
        monkeypatch.setattr(
            installer.subprocess, "run",
            lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        )

        plan = _make_plan(tmp_path)
        installer.apply_install(plan)

        for d in plan.seed_dirs:
            assert Path(d).is_dir()


class TestPlanInstall:
    def test_user_scope(self, fake_command, fake_claude_cli):
        plan = installer.plan_install(project_scope=False)
        assert plan.scope == "user"
        assert plan.command == "/usr/local/bin/blindsight-investigation-mcp"

    def test_project_scope(self, fake_command, fake_claude_cli):
        plan = installer.plan_install(project_scope=True)
        assert plan.scope == "project"

    def test_raises_when_binary_not_on_path(self, monkeypatch):
        # claude CLI present, blindsight binary missing
        monkeypatch.setattr(installer, "_resolve_claude_cli", lambda: "/usr/local/bin/claude")
        monkeypatch.setattr(installer.shutil, "which", lambda _: None)
        with pytest.raises(RuntimeError, match="not found on PATH"):
            installer.plan_install()

    def test_raises_when_claude_cli_missing(self, fake_command, monkeypatch):
        monkeypatch.setattr(installer.shutil, "which",
                            lambda name: None if name == "claude" else "/bin/blindsight-investigation-mcp")
        with pytest.raises(RuntimeError, match="`claude` CLI not found"):
            installer.plan_install()


class TestUninstall:
    def _no_op_run(self, returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            class R:
                pass
            R.returncode = returncode
            R.stdout = ""
            R.stderr = stderr
            return R()
        return fake_run

    def test_invokes_claude_mcp_remove(self, fake_claude_cli, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        monkeypatch.setattr(installer.subprocess, "run", fake_run)
        plan = installer.UninstallPlan(scope="user", purge_data=False, data_dirs=[])
        installer.apply_uninstall(plan)

        assert len(calls) == 1
        assert calls[0][1:5] == ["mcp", "remove", "-s", "user"]
        assert "blindsight-investigation" in calls[0]

    def test_remove_failure_silent_when_not_registered(self, fake_claude_cli, monkeypatch):
        """Removing an already-removed server is idempotent."""
        monkeypatch.setattr(installer.subprocess, "run",
                            self._no_op_run(returncode=1, stderr="server not found"))
        plan = installer.UninstallPlan(scope="user", purge_data=False, data_dirs=[])
        installer.apply_uninstall(plan)  # no exception

    def test_purge_data_deletes_dirs(self, tmp_path, fake_claude_cli, monkeypatch):
        cases = tmp_path / "cases"
        scenarios = tmp_path / "scenarios"
        cases.mkdir()
        scenarios.mkdir()
        (cases / "marker.txt").write_text("x")

        monkeypatch.setattr(installer.subprocess, "run", self._no_op_run())
        plan = installer.UninstallPlan(
            scope="user", purge_data=True,
            data_dirs=[str(cases), str(scenarios)],
        )
        installer.apply_uninstall(plan)

        assert not cases.exists()
        assert not scenarios.exists()

    def test_no_purge_preserves_dirs(self, tmp_path, fake_claude_cli, monkeypatch):
        cases = tmp_path / "cases"
        cases.mkdir()
        marker = cases / "data.duckdb"
        marker.write_text("user data")

        monkeypatch.setattr(installer.subprocess, "run", self._no_op_run())
        plan = installer.UninstallPlan(
            scope="user", purge_data=False,
            data_dirs=[str(cases)],
        )
        installer.apply_uninstall(plan)

        assert cases.is_dir()
        assert marker.read_text() == "user data"

    def test_plan_uninstall_user_scope(self, fake_claude_cli):
        plan = installer.plan_uninstall()
        assert plan.scope == "user"
        assert plan.purge_data is False

    def test_plan_uninstall_project_scope_with_purge(self, fake_claude_cli):
        plan = installer.plan_uninstall(project_scope=True, purge_data=True)
        assert plan.scope == "project"
        assert plan.purge_data is True
