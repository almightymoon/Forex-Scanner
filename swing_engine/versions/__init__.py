"""Swing engine version registry."""

from __future__ import annotations

from typing import Callable

SUPPORTED_VERSIONS: dict[str, str] = {
    "1.0.0": "v1",
}

DEFAULT_VERSION = "1.0.0"


def resolve_version(version: str | None) -> str:
    v = version or DEFAULT_VERSION
    if v not in SUPPORTED_VERSIONS:
        raise ValueError(f"Unsupported swing engine version: {v}. Available: {list(SUPPORTED_VERSIONS)}")
    return v


def get_pipeline(version: str | None = None) -> Callable:
    v = resolve_version(version)
    if v == "1.0.0":
        from swing_engine.versions.v1 import detect_v1
        return detect_v1
    raise ValueError(f"No pipeline for version {v}")
