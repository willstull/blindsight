"""Structured error types."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PipelineError:
    code: str
    message: str
    severity: str  # error | warning | info
    context: Optional[dict] = None
    retryable: bool = False


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str
    field: Optional[str] = None
