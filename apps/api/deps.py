"""API dependency injection with FastAPI Depends support."""

from typing import Annotated

from fastapi import Depends

from services.billing_service.stripe_billing import BillingService
from services.dashboard_service import DashboardService
from services.market_data_service.factory import create_market_data_provider
from services.market_data_service.service import MarketDataService
from services.replay_engine.replay import ReplayEngine
from services.scanner_service.data_loader import DataLoader
from services.scanner_service.pipeline import ScannerPipeline
from services.scanner_service.scanner_service import ScannerService
from services.strategy_engine import StrategyEngine

_pipeline: ScannerPipeline | None = None
_scanner: ScannerService | None = None
_dashboard: DashboardService | None = None
_billing: BillingService | None = None
_replay: ReplayEngine | None = None
_market_data: MarketDataService | None = None
_strategy: StrategyEngine | None = None


def get_market_data() -> MarketDataService:
    global _market_data
    if _market_data is None:
        provider = create_market_data_provider()
        _market_data = provider if isinstance(provider, MarketDataService) else MarketDataService(provider)
    return _market_data


def get_pipeline() -> ScannerPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ScannerPipeline(data_loader=DataLoader(market_data=get_market_data()))
    return _pipeline


def get_scanner_service(
    pipeline: Annotated[ScannerPipeline, Depends(get_pipeline)],
) -> ScannerService:
    return ScannerService(pipeline)


def get_dashboard_service(
    scanner: Annotated[ScannerService, Depends(get_scanner_service)],
) -> DashboardService:
    return DashboardService(scanner)


def get_billing_service() -> BillingService:
    global _billing
    if _billing is None:
        _billing = BillingService()
    return _billing


def get_replay_engine(
    market_data: Annotated[MarketDataService, Depends(get_market_data)],
) -> ReplayEngine:
    return ReplayEngine(market_data=market_data)


def get_strategy_engine() -> StrategyEngine:
    global _strategy
    if _strategy is None:
        _strategy = StrategyEngine()
    return _strategy


# Typed aliases for route injection
PipelineDep = Annotated[ScannerPipeline, Depends(get_pipeline)]
ScannerDep = Annotated[ScannerService, Depends(get_scanner_service)]
DashboardDep = Annotated[DashboardService, Depends(get_dashboard_service)]
BillingDep = Annotated[BillingService, Depends(get_billing_service)]
ReplayDep = Annotated[ReplayEngine, Depends(get_replay_engine)]
MarketDataDep = Annotated[MarketDataService, Depends(get_market_data)]
StrategyDep = Annotated[StrategyEngine, Depends(get_strategy_engine)]
