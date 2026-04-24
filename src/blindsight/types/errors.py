"""Structured error types."""
from typing import Optional

from pydantic import BaseModel


class PipelineError(BaseModel):
    code: str
    message: str
    severity: str  # error | warning | info
    context: Optional[dict] = None
    retryable: bool = False


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: str
    field: Optional[str] = None
