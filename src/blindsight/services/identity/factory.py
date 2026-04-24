"""Factory for creating identity domain integrations."""
import logging
from enum import Enum
from pathlib import Path
from typing import Any

from blindsight.types.integration import DomainIntegration


class IntegrationMode(Enum):
    REPLAY = "replay"
    LIVE = "live"


def create_identity_integration(
    mode: IntegrationMode,
    config: dict[str, Any],
    logger: logging.Logger,
) -> DomainIntegration:
    """Create an identity domain integration instance.

    Args:
        mode: REPLAY or LIVE
        config: Mode-specific configuration
            REPLAY: {"scenario_path": "path/to/scenario"}
            LIVE: TBD
        logger: Logger instance
    """
    if mode == IntegrationMode.REPLAY:
        from blindsight.services.identity.replay_integration import ReplayIdentityIntegration
        return ReplayIdentityIntegration(
            scenario_path=Path(config["scenario_path"]),
            logger=logger,
        )
    raise ValueError(f"Unsupported integration mode: {mode}")
