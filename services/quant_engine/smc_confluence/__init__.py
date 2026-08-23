"""SMC Confluence Engine v1 — context assembly for DecisionEngine."""

from services.quant_engine.smc_confluence.engine import SMCConfluenceEngine, build_smc_context
from services.quant_engine.smc_confluence.models import (
    SMC_CONFLUENCE_ENGINE_VERSION,
    AlgorithmVersions,
    ConfluenceBias,
    ConfluenceStrength,
    ConflictItem,
    EvidenceItem,
    SMCContextSnapshot,
)

__all__ = [
    "SMC_CONFLUENCE_ENGINE_VERSION",
    "AlgorithmVersions",
    "ConfluenceBias",
    "ConfluenceStrength",
    "ConflictItem",
    "EvidenceItem",
    "SMCConfluenceEngine",
    "SMCContextSnapshot",
    "build_smc_context",
]
