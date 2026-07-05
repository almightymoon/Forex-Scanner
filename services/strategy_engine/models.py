"""Strategy rule models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid


class RuleOperator(str, Enum):
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"
    PRESENT = "present"


class Combinator(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass
class StrategyRule:
    """Single condition — e.g. EMA20 > EMA50, RSI > 60, bullish BOS present."""

    field: str
    operator: RuleOperator
    value: Optional[float | str] = None
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "label": self.label or self.field,
        }


@dataclass
class Strategy:
    id: str
    name: str
    rules: list[StrategyRule]
    combinator: Combinator = Combinator.AND
    action: str = "buy"
    active: bool = True
    symbols: list[str] = field(default_factory=list)
    min_score: int = 0
    user_id: str = "system"

    @staticmethod
    def create(name: str, rules: list[StrategyRule], action: str = "buy", user_id: str = "") -> "Strategy":
        return Strategy(
            id=str(uuid.uuid4())[:8],
            name=name,
            rules=rules,
            action=action,
            user_id=user_id,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rules": [r.to_dict() for r in self.rules],
            "combinator": self.combinator.value,
            "action": self.action,
            "active": self.active,
            "symbols": self.symbols,
            "min_score": self.min_score,
            "user_id": self.user_id,
        }
