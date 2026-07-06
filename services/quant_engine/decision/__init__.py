"""Decision orchestration and supporting engines."""

from services.quant_engine.decision.models import MomentumAnalysis, SRAnalysis, VolumeAnalysis
from services.quant_engine.trend.models import TrendAnalysis

__all__ = [
    "DecisionEngine",
    "TrendAnalysis",
    "MomentumAnalysis",
    "SRAnalysis",
    "VolumeAnalysis",
]


def __getattr__(name: str):
    if name == "DecisionEngine":
        from services.quant_engine.decision.engine import DecisionEngine

        return DecisionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
