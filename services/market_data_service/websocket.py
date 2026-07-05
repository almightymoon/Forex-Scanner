"""WebSocket broadcasting for live market data ticks and candles."""

import asyncio
from typing import Callable, Optional

from fastapi import WebSocket

from shared.types.models import Candle, Tick, Timeframe

from .provider import MarketDataProvider


class MarketDataWebSocket:
    """Streams validated ticks to connected clients; builds candles on the fly."""

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider
        self._clients: list[WebSocket] = []
        self._running = False

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._clients:
            self._clients.remove(websocket)

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def stream_symbols(
        self,
        symbols: list[str],
        on_candle: Optional[Callable[[Candle], None]] = None,
        interval_seconds: float = 1.0,
    ) -> None:
        processor = TickProcessor(Timeframe.M1)

        self._running = True
        try:
            async for tick in self.provider.stream_ticks(symbols):
                if not self._running:
                    break
                completed = processor.process_tick(tick)
                await self.broadcast({"type": "tick", "tick": _tick_dict(tick)})
                if completed:
                    payload = {"type": "candle", "candle": _candle_dict(completed)}
                    await self.broadcast(payload)
                    if on_candle:
                        on_candle(completed)
                await asyncio.sleep(0)
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False


def _tick_dict(tick: Tick) -> dict:
    return {
        "symbol": tick.symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "timestamp": tick.timestamp.isoformat(),
    }


def _candle_dict(candle: Candle) -> dict:
    return {
        "symbol": candle.symbol,
        "timeframe": candle.timeframe.value,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "timestamp": candle.timestamp.isoformat(),
    }
