"""Tests for the Claude Code MCP-config installer."""
import json

import pytest

from blindsight import installer


@pytest.fixture
def fake_command(monkeypatch):
    monkeypatch.setattr(installer, "_resolve_command", lambda: "/usr/local/bin/blindsight-investigation-mcp")


def _make_plan(tmp_path, project_scope=False, command="/usr/local/bin/blindsight-investigation-mcp"):
    config_path = tmp_path / ("project_mcp.json" if project_scope else "user_settings.json")
    return installer.InstallPlan(
        config_path=config_path,
        command=command,
        backup_path=config_path.with_suffix(config_path.suffix + ".bak") if config_path.exists() else None,
        seed_dirs=[tmp_path / "cases", tmp_path / "scenarios"],
    )


class TestApplyInstall:
    def test_writes_config_when_none_exists(self, tmp_path):
        plan = _make_plan(tmp_path)
        installer.apply_install(plan)

        assert plan.config_path.exists()
        data = json.loads(plan.config_path.read_text())
        assert data == {
            "mcpServers": {
                "blindsight-investigation": {
                    "command": "/usr/local/bin/blindsight-investigation-mcp",
                    "args": [],
                }
            }
        }

    def test_preserves_unrelated_top_level_keys(self, tmp_path):
        existing = {
            "theme": "dark",
            "mcpServers": {"other-server": {"command": "other"}},
        }
        config_path = tmp_path / "settings.json"
        config_path.write_text(json.dumps(existing))

        plan = installer.InstallPlan(
            config_path=config_path,
            command="/bin/blindsight-investigation-mcp",
            backup_path=config_path.with_suffix(".json.bak"),
            seed_dirs=[],
        )
        installer.apply_install(plan)

        data = json.loads(config_path.read_text())
        assert data["theme"] == "dark"
        assert data["mcpServers"]["other-server"] == {"command": "other"}
        assert data["mcpServers"]["blindsight-investigation"]["command"] == "/bin/blindsight-investigation-mcp"

    def test_writes_backup_before_overwriting(self, tmp_path):
        config_path = tmp_path / "settings.json"
        config_path.write_text('{"existing": "content"}')

        plan = installer.InstallPlan(
            config_path=config_path,
            command="/bin/blindsight-investigation-mcp",
            backup_path=config_path.with_suffix(".json.bak"),
            seed_dirs=[],
        )
        installer.apply_install(plan)

        assert plan.backup_path.exists()
        assert json.loads(plan.backup_path.read_text()) == {"existing": "content"}

    def test_idempotent_on_repeat_runs(self, tmp_path):
        plan = _make_plan(tmp_path)
        installer.apply_install(plan)
        first = plan.config_path.read_text()

        # Second run with the same plan should produce the same output
        plan2 = installer.InstallPlan(
            config_path=plan.config_path,
            command=plan.command,
            backup_path=plan.config_path.with_suffix(".json.bak"),
            seed_dirs=plan.seed_dirs,
        )
        installer.apply_install(plan2)
        second = plan.config_path.read_text()

        assert first == second

    def test_seeds_directories(self, tmp_path):
        plan = _make_plan(tmp_path)
        installer.apply_install(plan)

        for d in plan.seed_dirs:
            assert d.is_dir()


class TestPlanInstall:
    def test_user_scope_uses_claude_settings(self, fake_command, monkeypatch, tmp_path):
        monkeypatch.setattr(installer, "_USER_CONFIG", tmp_path / ".claude" / "settings.json")
        plan = installer.plan_install(project_scope=False)
        assert plan.config_path == tmp_path / ".claude" / "settings.json"
        assert plan.command == "/usr/local/bin/blindsight-investigation-mcp"

    def test_project_scope_uses_local_mcp_json(self, fake_command, monkeypatch, tmp_path):
        monkeypatch.setattr(installer, "_PROJECT_CONFIG", tmp_path / ".mcp.json")
        plan = installer.plan_install(project_scope=True)
        assert plan.config_path == tmp_path / ".mcp.json"

    def test_raises_when_binary_not_on_path(self, monkeypatch):
        monkeypatch.setattr(installer.shutil, "which", lambda _: None)
        with pytest.raises(RuntimeError, match="not found on PATH"):
            installer.plan_install()
