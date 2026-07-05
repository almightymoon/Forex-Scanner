"""FX Navigators API Gateway."""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.api.deps import (
    BillingDep,
    DashboardDep,
    MarketDataDep,
    PipelineDep,
    ReplayDep,
    ScannerDep,
    StrategyDep,
    get_pipeline,
)
from shared.configs.settings import get_settings
from shared.types.models import Timeframe, to_dict

settings = get_settings()

_connected_ws: list[WebSocket] = []
_daemon_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    global _daemon_task
    pipeline = get_pipeline()
    if os.getenv("ENABLE_SCANNER_DAEMON", "false").lower() == "true":
        _daemon_task = asyncio.create_task(pipeline.run_continuous(
            interval=settings.SCAN_INTERVAL_SECONDS,
            min_score=settings.MIN_ALERT_SCORE,
        ))
    yield
    if _daemon_task:
        get_pipeline().stop()
        _daemon_task.cancel()


app = FastAPI(
    title="FX Navigators Scanner API",
    description="Project Atlas — Institutional-quality forex scanner",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Models ---

class UserRegister(BaseModel):
    name: str
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AlertCreate(BaseModel):
    symbol: Optional[str] = None
    timeframe: Optional[Timeframe] = None
    min_score: int = 80
    delivery_method: list[str] = ["push"]


class WatchlistUpdate(BaseModel):
    symbols: list[str]


class StrategyRuleCreate(BaseModel):
    field: str
    operator: str
    value: Optional[str | float] = None
    label: str = ""


class StrategyCreate(BaseModel):
    name: str
    rules: list[StrategyRuleCreate]
    combinator: str = "AND"
    action: str = "buy"
    symbols: list[str] = []
    min_score: int = 0


def _parse_symbols_param(symbols: Optional[str]) -> list[str] | None:
    if not symbols:
        return None
    from services.market_data_service.catalog import merge_scan_symbols
    from services.market_data_service.provider import FOREX_PAIRS

    extra = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    return merge_scan_symbols(FOREX_PAIRS, extra) if extra else None


# --- In-memory stores (replace with DB in production) ---

_users_db: dict[str, dict] = {}
_alerts_db: list[dict] = []
_watchlists_db: dict[str, list[str]] = {}


def create_token(data: dict) -> str:
    import hashlib, json
    payload = json.dumps({**data, "ts": datetime.now(timezone.utc).isoformat()})
    return hashlib.sha256(f"{payload}:{settings.JWT_SECRET}".encode()).hexdigest()


# --- Routes ---

@app.get("/health")
async def health(pipeline: PipelineDep):
    stats = pipeline.db.get_stats()
    provider = getattr(pipeline.market_data, "name", "unknown")
    return {
        "status": "ok",
        "service": "fx-navigators-api",
        "version": "1.0.0",
        "stats": stats,
        "market_data_provider": provider,
    }


@app.get("/api/v1/market/live")
async def live_prices(market_data: MarketDataDep):
    prices = await market_data.get_live_prices()
    source = getattr(market_data, "name", "unknown")
    return {"prices": prices, "source": source, "count": len(prices)}


@app.get("/api/v1/scanner/history")
async def scanner_history(
    pipeline: PipelineDep,
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(60, ge=0, le=100),
    symbol: Optional[str] = None,
):
    results = pipeline.db.get_recent_results(limit=limit, min_score=min_score, symbol=symbol)
    return {"signals": results, "count": len(results)}


@app.post("/api/v1/auth/register", response_model=TokenResponse)
async def register(user: UserRegister):
    if user.email in _users_db:
        raise HTTPException(400, "Email already registered")
    _users_db[user.email] = {
        "name": user.name,
        "email": user.email,
        "password": user.password,
        "plan": "free",
    }
    token = create_token({"sub": user.email})
    return TokenResponse(access_token=token)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = _users_db.get(credentials.email)
    if not user or user["password"] != credentials.password:
        raise HTTPException(401, "Invalid credentials")
    return TokenResponse(access_token=create_token({"sub": credentials.email}))


@app.get("/api/v1/symbols/search")
async def search_symbols(q: str = Query("", max_length=50), limit: int = Query(12, ge=1, le=50)):
    from services.market_data_service.catalog import search_symbols as catalog_search

    return {"results": catalog_search(q, limit=limit), "query": q}


@app.get("/api/v1/symbols")
async def get_symbols(market_data: MarketDataDep):
    from services.market_data_service.catalog import CATALOG, entry_to_dict
    from services.market_data_service.provider import FOREX_PAIRS

    prices = await market_data.get_live_prices()

    return [
        entry_to_dict(
            entry,
            in_default=sym in FOREX_PAIRS,
            price=prices.get(sym, 0),
            live=sym in prices,
        )
        for sym, entry in sorted(CATALOG.items(), key=lambda x: (x[1].category, x[0]))
    ]


@app.get("/api/v1/dashboard")
async def get_dashboard(
    dashboard: DashboardDep,
    min_score: int = Query(60, ge=0, le=100),
    timeframe: Timeframe = Timeframe.H1,
    symbols: Optional[str] = Query(None, description="Comma-separated extra symbols to scan"),
    limit: int = Query(30, ge=1, le=100),
):
    scan_list = _parse_symbols_param(symbols)
    return await dashboard.get_dashboard(
        min_score=min_score,
        timeframe=timeframe,
        symbols=scan_list,
        signal_limit=limit,
    )


@app.get("/api/v1/scanner/live")
async def scanner_live(
    scanner: ScannerDep,
    min_score: int = Query(60, ge=0, le=100),
    timeframe: Timeframe = Timeframe.H1,
    limit: int = Query(20, ge=1, le=100),
    symbols: Optional[str] = Query(None, description="Comma-separated extra symbols to scan"),
):
    scan_list = _parse_symbols_param(symbols)
    return await scanner.scan_live(
        min_score=min_score, timeframe=timeframe, symbols=scan_list, limit=limit
    )


@app.get("/api/v1/scanner/heatmap")
async def scanner_heatmap(
    scanner: ScannerDep,
    timeframe: Timeframe = Timeframe.H1,
    symbols: Optional[str] = Query(None, description="Comma-separated extra symbols to scan"),
):
    scan_list = _parse_symbols_param(symbols)
    heatmap = await scanner.get_heatmap(timeframe=timeframe, symbols=scan_list)
    return {"heatmap": heatmap, "count": len(heatmap)}


@app.get("/api/v1/backtest/{symbol}")
async def run_backtest(
    pipeline: PipelineDep,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    min_score: int = Query(70, ge=50, le=95),
):
    result = await pipeline.run_backtest(symbol.upper(), timeframe, min_score)
    return result


@app.get("/api/v1/validation")
async def validation_report(symbol: str | None = Query(None)):
    from services.validation_engine import SignalValidator
    return SignalValidator().report(symbol)


@app.get("/api/v1/scanner/{symbol}")
async def scanner_symbol(
    pipeline: PipelineDep,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    include_backtest: bool = Query(True),
):
    signal = await pipeline.scan_symbol(symbol.upper(), timeframe, with_ai=True)
    if not signal:
        raise HTTPException(404, f"No data for {symbol}")
    data = to_dict(signal)
    if include_backtest:
        bt = await pipeline.get_backtest(symbol.upper(), timeframe.value)
        if bt:
            data["backtest"] = bt
    return data


@app.get("/api/v1/market/{symbol}/candles")
async def get_candles(
    market_data: MarketDataDep,
    symbol: str,
    timeframe: Timeframe = Timeframe.H1,
    count: int = Query(200, ge=10, le=1000),
):
    candles = await market_data.get_candles(symbol.upper(), timeframe, count)
    return {"symbol": symbol.upper(), "timeframe": timeframe.value, "candles": [to_dict(c) for c in candles]}


@app.get("/api/v1/calendar")
async def economic_calendar(scanner: ScannerDep):
    events = await scanner.get_calendar()
    return {"events": events, "count": len(events)}


@app.get("/api/v1/alerts")
async def get_alerts():
    return {"alerts": _alerts_db}


@app.post("/api/v1/alerts")
async def create_alert(alert: AlertCreate):
    entry = {"id": len(_alerts_db) + 1, **alert.__dict__, "active": True}
    _alerts_db.append(entry)
    return entry


@app.delete("/api/v1/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    global _alerts_db
    _alerts_db = [a for a in _alerts_db if a.get("id") != alert_id]
    return {"deleted": alert_id}


@app.get("/api/v1/watchlist")
async def get_watchlist():
    from services.market_data_service.provider import FOREX_PAIRS
    custom = _watchlists_db.get("default", [])
    return {"default": FOREX_PAIRS, "custom": custom, "symbols": merge_watchlist(FOREX_PAIRS, custom)}


@app.post("/api/v1/watchlist")
async def update_watchlist(body: WatchlistUpdate):
    from services.market_data_service.catalog import CATALOG

    valid = [s.upper() for s in body.symbols if s.upper() in CATALOG]
    _watchlists_db["default"] = valid
    return {"symbols": valid}


def merge_watchlist(default: list[str], custom: list[str]) -> list[str]:
    from services.market_data_service.catalog import merge_scan_symbols
    return merge_scan_symbols(default, custom)


class CheckoutRequest(BaseModel):
    plan_id: str
    email: str


@app.get("/api/v1/billing/plans")
async def get_plans(billing: BillingDep):
    return {"plans": billing.get_plans()}


@app.post("/api/v1/billing/checkout")
async def create_checkout(req: CheckoutRequest, billing: BillingDep):
    result = billing.create_checkout_session(
        plan_id=req.plan_id,
        user_email=req.email,
        success_url="http://localhost:3000?subscribed=true",
        cancel_url="http://localhost:3000?cancelled=true",
    )
    return result


@app.get("/api/v1/strategies")
async def list_strategies(strategies: StrategyDep):
    return {"strategies": strategies.list_strategies()}


@app.post("/api/v1/strategies")
async def create_strategy(body: StrategyCreate, strategies: StrategyDep):
    from services.strategy_engine import Combinator, RuleOperator, Strategy, StrategyRule

    rules = [
        StrategyRule(
            field=r.field,
            operator=RuleOperator(r.operator),
            value=r.value,
            label=r.label,
        )
        for r in body.rules
    ]
    strategy = Strategy.create(body.name, rules, action=body.action)
    strategy.combinator = Combinator(body.combinator)
    strategy.symbols = [s.upper() for s in body.symbols]
    strategy.min_score = body.min_score
    return strategies.create_strategy(strategy)


@app.delete("/api/v1/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, strategies: StrategyDep):
    if not strategies.storage.delete(strategy_id):
        raise HTTPException(404, "Strategy not found")
    return {"deleted": strategy_id}


@app.get("/api/v1/replay/{symbol}")
async def market_replay(
    replay: ReplayDep,
    symbol: str,
    date: str = Query(..., description="YYYY-MM-DD"),
    timeframe: Timeframe = Timeframe.H1,
    session: str = Query("london", pattern="^(asia|london|new_york|full)$"),
):
    session_data = await replay.build_session(symbol.upper(), date, timeframe, session)
    return replay.session_to_dict(session_data)


@app.websocket("/ws/scanner")
async def scanner_websocket(websocket: WebSocket):
    pipeline = get_pipeline()
    await websocket.accept()
    _connected_ws.append(websocket)
    try:
        while True:
            signals = await pipeline.scan_all(min_score=70)
            await websocket.send_json({
                "type": "scan_update",
                "signals": [to_dict(s) for s in signals[:10]],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            import asyncio
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        _connected_ws.remove(websocket)
