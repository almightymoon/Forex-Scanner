"""Swing structure validation — deterministic integrity checks."""

from __future__ import annotations

from services.quant_engine.swing.models import Swing, SwingSide


def validate_swings(
    swings: list[Swing],
    *,
    confirmed_only: bool = False,
    require_alternating: bool = True,
) -> tuple[bool, list[str]]:
    """
    Validate swing list integrity.

    Returns (passed, issues).
    """
    issues: list[str] = []

    if not swings:
        return True, issues

    indices = [s.index for s in swings]
    if indices != sorted(indices):
        issues.append("Swings are not in chronological order")

    ids = [s.id for s in swings]
    if len(ids) != len(set(ids)):
        issues.append("Duplicate swing IDs detected")

    price_keys = [(s.index, s.side, round(s.price, 8)) for s in swings]
    if len(price_keys) != len(set(price_keys)):
        issues.append("Duplicate swings at same index/side/price")

    if confirmed_only:
        unconfirmed = [s for s in swings if not s.confirmed]
        if unconfirmed:
            issues.append(f"{len(unconfirmed)} unconfirmed swings in confirmed-only set")

    if require_alternating and len(swings) >= 2:
        for i in range(1, len(swings)):
            if swings[i].side == swings[i - 1].side:
                issues.append(
                    f"Non-alternating swings at indices {swings[i-1].index} and {swings[i].index}"
                )
                break

    for i in range(1, len(swings)):
        if swings[i].index == swings[i - 1].index:
            issues.append(f"Impossible structure: two swings at index {swings[i].index}")

    return len(issues) == 0, issues


def filter_confirmed(swings: list[Swing]) -> list[Swing]:
    return [s for s in swings if s.confirmed]


def ensure_alternating(swings: list[Swing]) -> list[Swing]:
    """Keep strongest swing when consecutive same-side pivots remain."""
    if len(swings) < 2:
        return swings

    out: list[Swing] = [swings[0]]
    for swing in swings[1:]:
        last = out[-1]
        if swing.side != last.side:
            out.append(swing)
            continue
        if swing.side == SwingSide.HIGH and swing.price >= last.price:
            out[-1] = swing
        elif swing.side == SwingSide.LOW and swing.price <= last.price:
            out[-1] = swing
    return out
