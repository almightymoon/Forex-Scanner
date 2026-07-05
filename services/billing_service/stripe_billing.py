"""Stripe subscription billing (scaffold)."""

from dataclasses import dataclass
from typing import Optional

from shared.configs.settings import get_settings

settings = get_settings()


@dataclass
class Plan:
    id: str
    name: str
    price_monthly: float
    features: list[str]
    max_pairs: int
    min_alert_score: int
    api_access: bool


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        price_monthly=0,
        features=["5 pairs", "Scores 70+", "Basic dashboard", "Economic calendar"],
        max_pairs=5,
        min_alert_score=70,
        api_access=False,
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        price_monthly=29.99,
        features=[
            "28+ pairs", "Scores 60+", "SMC analysis", "Telegram alerts",
            "Multi-timeframe", "Trade levels",
        ],
        max_pairs=28,
        min_alert_score=60,
        api_access=False,
    ),
    "elite": Plan(
        id="elite",
        name="Elite",
        price_monthly=79.99,
        features=[
            "All pairs + metals", "Scores 50+", "AI explanations",
            "Discord + Email alerts", "API access", "Priority scanning",
            "Backtesting (coming soon)",
        ],
        max_pairs=999,
        min_alert_score=50,
        api_access=True,
    ),
}


class BillingService:
    def __init__(self):
        self._stripe_key = settings.STRIPE_SECRET_KEY
        self._stripe = None
        if self._stripe_key:
            try:
                import stripe
                stripe.api_key = self._stripe_key
                self._stripe = stripe
            except ImportError:
                pass

    def get_plans(self) -> list[dict]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "price_monthly": p.price_monthly,
                "features": p.features,
                "max_pairs": p.max_pairs,
            }
            for p in PLANS.values()
        ]

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return PLANS.get(plan_id)

    def create_checkout_session(self, plan_id: str, user_email: str, success_url: str, cancel_url: str) -> dict:
        plan = PLANS.get(plan_id)
        if not plan or plan.price_monthly == 0:
            return {"error": "Invalid plan"}

        if not self._stripe:
            return {
                "mode": "mock",
                "plan": plan_id,
                "message": f"Mock checkout for {plan.name} (${plan.price_monthly}/mo)",
                "checkout_url": success_url,
            }

        session = self._stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"FX Navigators {plan.name}"},
                    "unit_amount": int(plan.price_monthly * 100),
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user_email,
        )
        return {"checkout_url": session.url, "session_id": session.id}

    def check_access(self, plan_id: str, feature: str) -> bool:
        plan = PLANS.get(plan_id, PLANS["free"])
        if feature == "api":
            return plan.api_access
        if feature == "all_pairs":
            return plan.max_pairs > 5
        return True
