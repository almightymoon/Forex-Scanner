"""Evaluate user-defined strategy rules against scan context."""

from shared.types.models import IndicatorValues, SMCPattern, SignalDirection

from .models import Combinator, RuleOperator, Strategy, StrategyRule


class StrategyEvaluator:
    def evaluate(
        self,
        strategy: Strategy,
        indicators: IndicatorValues,
        smc_patterns: list[SMCPattern],
        score: int = 0,
    ) -> tuple[bool, list[str]]:
        if not strategy.active:
            return False, []
        if strategy.min_score and score < strategy.min_score:
            return False, [f"Score {score} below minimum {strategy.min_score}"]

        results: list[tuple[bool, str]] = []
        for rule in strategy.rules:
            ok, reason = self._check_rule(rule, indicators, smc_patterns)
            results.append((ok, reason))

        if strategy.combinator == Combinator.AND:
            matched = all(r[0] for r in results)
        else:
            matched = any(r[0] for r in results)

        reasons = [r[1] for r in results if r[0]]
        return matched, reasons

    def _check_rule(
        self,
        rule: StrategyRule,
        indicators: IndicatorValues,
        smc_patterns: list[SMCPattern],
    ) -> tuple[bool, str]:
        if rule.field.startswith("smc."):
            return self._check_smc(rule, smc_patterns)
        return self._check_indicator(rule, indicators)

    def _check_indicator(self, rule: StrategyRule, indicators: IndicatorValues) -> tuple[bool, str]:
        if "." in rule.field:
            left_field, right_field = rule.field.split(".", 1)
            left = _indicator_value(indicators, left_field)
            right = _indicator_value(indicators, right_field)
        else:
            left = _indicator_value(indicators, rule.field)
            right = rule.value

        if left is None:
            return False, f"{rule.field}: no data"

        ok = _compare(left, rule.operator, right)
        label = rule.label or rule.field
        return ok, f"{label} satisfied" if ok else f"{label} not met"

    def _check_smc(self, rule: StrategyRule, patterns: list[SMCPattern]) -> tuple[bool, str]:
        pattern_type = rule.field.replace("smc.", "")
        if rule.operator == RuleOperator.PRESENT:
            found = [p for p in patterns if p.pattern_type == pattern_type]
            if not found:
                return False, f"No {pattern_type} detected"
            if rule.value:
                direction = str(rule.value).lower()
                found = [p for p in found if p.direction.value == direction]
            ok = len(found) > 0
            label = pattern_type.replace("_", " ").title()
            return ok, f"{label} present" if ok else f"{label} not found"
        return False, f"Unsupported SMC operator: {rule.operator}"


def _indicator_value(indicators: IndicatorValues, field: str) -> float | None:
    mapping = {
        "ema20": indicators.ema_20,
        "ema50": indicators.ema_50,
        "ema200": indicators.ema_200,
        "rsi": indicators.rsi_14,
        "macd": indicators.macd_histogram,
        "atr": indicators.atr_14,
        "adx": indicators.adx_14,
    }
    return mapping.get(field.lower())


def _compare(left: float, op: RuleOperator, right: float | str | None) -> bool:
    if right is None:
        return False
    right_val = float(right) if not isinstance(right, float) else right
    if op == RuleOperator.GT:
        return left > right_val
    if op == RuleOperator.LT:
        return left < right_val
    if op == RuleOperator.GTE:
        return left >= right_val
    if op == RuleOperator.LTE:
        return left <= right_val
    if op == RuleOperator.EQ:
        return abs(left - right_val) < 1e-9
    if op == RuleOperator.CROSS_ABOVE:
        return left > right_val
    if op == RuleOperator.CROSS_BELOW:
        return left < right_val
    return False
