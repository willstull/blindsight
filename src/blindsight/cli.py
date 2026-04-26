"""Blindsight CLI entry point.

Subcommands:
  install            Wire up the investigation MCP server in Claude Code.
  describe-scenario  List bundled scenarios or describe one.
  run-investigation  Run an investigation against a scenario.
  generate-report    Render a Markdown report for a saved case.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from blindsight.config import load_config
from blindsight.services.investigation import scenario_catalog
from blindsight.services.investigation.pipeline import run_investigation
from blindsight.services.investigation.reporting import generate_report_for_case


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blindsight")
    sub = parser.add_subparsers(dest="cmd", required=True)

    install = sub.add_parser("install", help="Wire up Claude Code MCP config")
    install.add_argument("--project", action="store_true",
                         help="Write to ./.mcp.json instead of ~/.claude/settings.json")
    install.add_argument("--dry-run", action="store_true",
                         help="Print planned writes without touching the filesystem")

    desc = sub.add_parser("describe-scenario", help="List or describe scenarios")
    desc.add_argument("name", nargs="?", default=None,
                      help="Scenario name (omit to list all)")

    run = sub.add_parser("run-investigation", help="Run an investigation")
    run.add_argument("scenario", help="Scenario name or path")
    run.add_argument("--question", default=None,
                     help="Override scenario's investigation_question")
    run.add_argument("--use-llm", action="store_true")
    run.add_argument("--llm-model", default=None)

    rep = sub.add_parser("generate-report", help="Render a report for a saved case")
    rep.add_argument("case_id")
    rep.add_argument("--use-llm", action="store_true")
    rep.add_argument("--llm-model", default=None)

    return parser


def _cmd_install(args: argparse.Namespace) -> int:
    from blindsight.installer import plan_install, apply_install, format_plan

    try:
        plan = plan_install(project_scope=args.project)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(format_plan(plan))
    if args.dry_run:
        print("\n(dry-run — no changes made)")
        return 0

    apply_install(plan)
    print("\ninstalled. Restart Claude Code to pick up the change.")
    return 0


def _cmd_describe_scenario(args: argparse.Namespace) -> int:
    result = scenario_catalog.describe_scenario(args.name)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") != "error" else 1


def _cli_logger() -> logging.Logger:
    log = logging.getLogger("blindsight.cli")
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


def _cmd_run_investigation(args: argparse.Namespace) -> int:
    scenario_path = scenario_catalog.resolve_scenario(args.scenario)
    if scenario_path is None:
        print(f"error: scenario {args.scenario!r} not found", file=sys.stderr)
        return 1

    config = load_config()
    config.cases_dir.mkdir(parents=True, exist_ok=True)
    log = _cli_logger()
    question = args.question
    if question is None:
        manifest = scenario_catalog.load_manifest(scenario_path)
        question = manifest["question"]

    report = asyncio.run(run_investigation(
        scenario_path=scenario_path,
        logger=log,
        investigation_question=question,
        use_llm=args.use_llm,
        llm_model=args.llm_model,
        cases_dir=str(config.cases_dir),
    ))
    print(json.dumps(report.model_dump(exclude_none=True), indent=2, default=str))
    return 0


def _cmd_generate_report(args: argparse.Namespace) -> int:
    config = load_config()
    log = _cli_logger()
    try:
        markdown = asyncio.run(generate_report_for_case(
            cases_dir=config.cases_dir,
            case_id=args.case_id,
            logger=log,
            use_llm=args.use_llm,
            llm_model=args.llm_model,
        ))
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(markdown)
    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    dispatch = {
        "install": _cmd_install,
        "describe-scenario": _cmd_describe_scenario,
        "run-investigation": _cmd_run_investigation,
        "generate-report": _cmd_generate_report,
    }
    rc = dispatch[args.cmd](args)
    sys.exit(rc)
