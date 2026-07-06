"""Internal Market Data API — dedicated endpoints for validated candle reads."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services.data_collector.auth import verify_market_api_key
from services.data_collector.market_service import get_market_data_service
from shared.types.models import Timeframe

router = APIRouter(
    prefix="/market",
    tags=["market-data"],
    dependencies=[Depends(verify_market_api_key)],
)


@router.get("/candles")
def get_candles(
    symbol: str = Query(..., min_length=3),
    timeframe: str = Query("H1"),
    limit: int = Query(200, ge=1, le=5000),
    since: Optional[str] = Query(None, description="ISO timestamp — return candles after this time"),
):
    """Return validated OHLC candles from the collector database."""
    try:
        tf = Timeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(400, f"Invalid timeframe: {timeframe}")

    since_dt = datetime.fromisoformat(since) if since else None
    service = get_market_data_service()
    candles = service.get_candles(symbol.upper(), tf, limit=limit, since=since_dt)
    return {"symbol": symbol.upper(), "timeframe": tf.value, "count": len(candles), "candles": candles}


@router.get("/latest")
def get_latest(
    symbol: str = Query(..., min_length=3),
    timeframe: str = Query("H1"),
):
    """Return the most recent validated candle."""
    try:
        tf = Timeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(400, f"Invalid timeframe: {timeframe}")

    latest = get_market_data_service().get_latest(symbol.upper(), tf)
    if not latest:
        raise HTTPException(404, f"No candles for {symbol.upper()} {timeframe}")
    return latest


@router.get("/symbols")
def get_symbols():
    """Return the configured symbol registry."""
    return {"symbols": get_market_data_service().get_symbols()}


@router.get("/status")
def get_status():
    """Collector health, gap count, and metrics snapshot."""
    return get_market_data_service().get_status()


@router.get("/gaps")
def get_gaps(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    tf = None
    if timeframe:
        try:
            tf = Timeframe(timeframe.upper())
        except ValueError:
            raise HTTPException(400, f"Invalid timeframe: {timeframe}")
    return {
        "gaps": get_market_data_service().get_gaps(symbol, tf, limit=limit),
    }


@router.get("/providers")
def get_providers():
    """Provider synchronization status for all registered providers."""
    return {"providers": get_market_data_service().get_providers()}


@router.get("/metrics")
def get_metrics():
    """Prometheus-compatible metrics exposition."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        get_market_data_service().get_metrics_prometheus(),
        media_type="text/plain; version=0.0.4",
    )
