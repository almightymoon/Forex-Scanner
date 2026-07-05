"""In-memory strategy persistence."""

import json
from pathlib import Path

from .models import Combinator, RuleOperator, Strategy, StrategyRule

DEFAULT_STRATEGIES = [
    Strategy(
        id="trend-momentum",
        name="Trend + Momentum",
        rules=[
            StrategyRule("ema20.ema50", RuleOperator.CROSS_ABOVE, label="EMA20 > EMA50"),
            StrategyRule("rsi", RuleOperator.GT, 60, label="RSI > 60"),
            StrategyRule("smc.bos", RuleOperator.PRESENT, "buy", label="Bullish BOS"),
        ],
        combinator=Combinator.AND,
        action="buy",
    ),
]


class StrategyStorage:
    def __init__(self, path: str = "data/strategies.json"):
        self.path = Path(path)
        self._strategies: dict[str, Strategy] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            for item in raw:
                s = _from_dict(item)
                self._strategies[s.id] = s
        else:
            for s in DEFAULT_STRATEGIES:
                self._strategies[s.id] = s
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.to_dict() for s in self._strategies.values()]
        self.path.write_text(json.dumps(data, indent=2))

    def list_all(self) -> list[Strategy]:
        return list(self._strategies.values())

    def list_for_user(self, user_id: str) -> list[Strategy]:
        return [s for s in self._strategies.values() if s.user_id in (user_id, "system")]

    def get(self, strategy_id: str) -> Strategy | None:
        return self._strategies.get(strategy_id)

    def save(self, strategy: Strategy) -> Strategy:
        self._strategies[strategy.id] = strategy
        self._save()
        return strategy

    def delete(self, strategy_id: str, user_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        if strategy.user_id == "system":
            return False
        if strategy.user_id != user_id:
            return False
        del self._strategies[strategy_id]
        self._save()
        return True


def _from_dict(data: dict) -> Strategy:
    return Strategy(
        id=data["id"],
        name=data["name"],
        rules=[
            StrategyRule(
                field=r["field"],
                operator=RuleOperator(r["operator"]),
                value=r.get("value"),
                label=r.get("label", ""),
            )
            for r in data["rules"]
        ],
        combinator=Combinator(data.get("combinator", "AND")),
        action=data.get("action", "buy"),
        active=data.get("active", True),
        symbols=data.get("symbols", []),
        min_score=data.get("min_score", 0),
        user_id=data.get("user_id", "system"),
    )
