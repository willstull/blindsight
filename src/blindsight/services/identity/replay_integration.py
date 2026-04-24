"""Replay-backed identity domain integration.

Thin subclass of ReplayDomainIntegration for the identity domain.
All 7 core contract methods are inherited from the base class.
"""
import logging
from pathlib import Path

from blindsight.services.replay.domain_integration import ReplayDomainIntegration


class ReplayIdentityIntegration(ReplayDomainIntegration):
    """Identity domain replay integration."""

    def __init__(self, scenario_path: Path, logger: logging.Logger) -> None:
        super().__init__(scenario_path, "identity", "identity", logger)
