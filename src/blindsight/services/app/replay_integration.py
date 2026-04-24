"""Replay-backed application domain integration.

Thin subclass of ReplayDomainIntegration for the app domain.
All 7 core contract methods are inherited from the base class.
"""
import logging
from pathlib import Path

from src.services.replay.domain_integration import ReplayDomainIntegration


class ReplayAppIntegration(ReplayDomainIntegration):
    """Application domain replay integration."""

    def __init__(self, scenario_path: Path, logger: logging.Logger) -> None:
        super().__init__(scenario_path, "app", "app", logger)
