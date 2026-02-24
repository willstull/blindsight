"""ULID generation utility."""
from ulid import ULID


def generate_ulid() -> str:
    return str(ULID())
