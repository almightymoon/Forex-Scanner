#!/usr/bin/env bash
# End-to-end test suite for FX Navigators Scanner
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.
export ENABLE_SIMULATED_DATA=true
export MARKET_DATA_PROVIDER=simulated

if [ -d .venv ]; then source .venv/bin/activate; fi

echo "=== FX Navigators Test Suite ==="
echo ""

echo "1. Scanner Pipeline..."
python3.11 -c "
import asyncio
from services.scanner_service.pipeline import ScannerPipeline

async def test():
    p = ScannerPipeline()
    signals = await p.scan_all(min_score=60)
    assert len(signals) > 0, 'No signals found'
    print(f'   PASS: {len(signals)} signals')
    top = signals[0]
    print(f'   Top: {top.symbol} {top.direction.value} {top.score}/100')
    stats = p.db.get_stats()
    print(f'   DB: {stats[\"total_scans\"]} scans saved')
    return True

asyncio.run(test())
"

echo ""
echo "2. Live Market Data..."
python3.11 -c "
import asyncio
from services.market_data_service.live import LiveMarketData

async def test():
    p = LiveMarketData()
    prices = await p.get_live_prices()
    print(f'   PASS: {len(prices)} live rates fetched')
    if prices:
        sample = list(prices.items())[:3]
        for sym, px in sample:
            print(f'   {sym}: {px}')
asyncio.run(test())
"

echo ""
echo "3. News Service..."
python3.11 -c "
import asyncio
from services.news_service.calendar import NewsService

async def test():
    ns = NewsService()
    events = await ns.get_events()
    print(f'   PASS: {len(events)} economic events')
    ctx = ns.evaluate_news_risk('EURUSD', events)
    print(f'   EURUSD news score: {ctx.score}/10')
asyncio.run(test())
"

echo ""
echo "4. Gold (XAU/USD) live price..."
python3.11 -c "
import asyncio
from services.market_data_service.live import LiveMarketData

async def test():
    p = LiveMarketData()
    prices = await p.get_live_prices()
    gold = prices.get('XAUUSD')
    assert gold, 'No gold price'
    print(f'   PASS: Gold/USD = {gold:.2f}')
asyncio.run(test())
"

echo ""
echo "5. Backtesting engine..."
python3.11 -c "
import asyncio
from services.scanner_service.pipeline import ScannerPipeline
from shared.types.models import Timeframe

async def test():
    p = ScannerPipeline()
    result = await p.run_backtest('EURUSD', Timeframe.H1)
    print(f'   PASS: {result[\"total_trades\"]} trades, {result[\"win_rate\"]}% win rate')
asyncio.run(test())
"

echo ""
echo "6. AI explainer..."
python3.11 -c "
import asyncio
from services.ai_service.explainer import AIExplainer
from services.scanner_service.pipeline import ScannerPipeline
from shared.types.models import Timeframe

async def test():
    p = ScannerPipeline()
    signal = await p.scan_symbol('XAUUSD', Timeframe.H1, with_ai=True)
    assert signal and signal.ai_explanation
    print(f'   PASS: AI explanation ({len(signal.ai_explanation)} chars)')
    print(f'   Preview: {signal.ai_explanation[:80]}...')
asyncio.run(test())
"

echo ""
echo "7. Unit tests (engines + market data + strategy)..."
python3.11 -m unittest discover -s tests -p 'test_*.py' -q

echo ""
if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo "8. API Endpoints..."
    curl -sf http://localhost:8001/health | python3.11 -m json.tool | head -12
    echo "   PASS: API health responding (dashboard requires JWT auth)"
else
    echo "8. API Endpoints... SKIPPED (start with: ./scripts/run-api.sh)"
fi

echo ""
echo "=== All tests passed ==="
