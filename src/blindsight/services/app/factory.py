"""Factory for creating application domain integrations."""
import logging
from pathlib import Path
from typing import Any

from blindsight.services.identity.factory import IntegrationMode
from blindsight.types.integration import DomainIntegration


def create_app_integration(
    mode: IntegrationMode,
    config: dict[str, Any],
    logger: logging.Logger,
) -> DomainIntegration:
    """Create an application domain integration instance.

    Args:
        mode: REPLAY or LIVE
        config: Mode-specific configuration
            REPLAY: {"scenario_path": "path/to/scenario"}
            LIVE: TBD
        logger: Logger instance
    """
    if mode == IntegrationMode.REPLAY:
        from blindsight.services.app.replay_integration import ReplayAppIntegration
        return ReplayAppIntegration(
            scenario_path=Path(config["scenario_path"]),
            logger=logger,
        )
    raise ValueError(f"Unsupported integration mode: {mode}")
