"""Swing engine version registry."""

from __future__ import annotations

from typing import Callable

SUPPORTED_VERSIONS: dict[str, str] = {
    "1.0.0": "v1",
    "1.1.0": "v1_1",
    "1.2.0": "v1_2",
    "1.3.0": "v1_3",
    "1.4.0": "v1_4",
    "2.0.0": "v2_0",
}

DEFAULT_VERSION = "2.0.0"


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
    if v == "1.1.0":
        from swing_engine.versions.v1_1 import detect_v1_1
        return detect_v1_1
    if v == "1.2.0":
        from swing_engine.versions.v1_2 import detect_v1_2
        return detect_v1_2
    if v == "1.3.0":
        from swing_engine.versions.v1_3 import detect_v1_3
        return detect_v1_3
    if v == "1.4.0":
        from swing_engine.versions.v1_4 import detect_v1_4
        return detect_v1_4
    if v == "2.0.0":
        from swing_engine.versions.v2_0 import detect_v2_0
        return detect_v2_0
    raise ValueError(f"No pipeline for version {v}")
