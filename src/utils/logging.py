"""Stderr logging utility for MCP servers.

MCP stdio transport uses stdout for JSON-RPC messages. Any log output on
stdout corrupts the transport. This module provides a stdlib logger that
writes exclusively to stderr.
"""
import logging
import sys


def get_stderr_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logging.Logger that writes to stderr.

    Guards against adding duplicate handlers when called multiple times
    with the same name.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
        for h in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
