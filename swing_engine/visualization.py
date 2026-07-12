"""Interactive HTML visual debugger for swing detection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.types.models import Candle

from swing_engine.models import DetectedSwing, DetectionResult, PipelineArtifacts, RejectedCandidate, SwingDirection, SwingScope, SwingTier


class SwingVisualizer:
    """Generate static and interactive chart data."""

    def build(
        self,
        bars: list[Candle],
        swings: list[DetectedSwing],
        *,
        artifacts: PipelineArtifacts | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        include_unconfirmed: bool = True,
        include_rejected: bool = True,
    ) -> dict[str, Any]:
        visible_bars = self._filter_bars(bars, window_start, window_end)
        visible_swings = self._filter_swings(swings, window_start, window_end, include_unconfirmed)

        payload: dict[str, Any] = {
            "candlesticks": [self._candle(c, i) for i, c in enumerate(visible_bars)],
            "swings": [self._swing_marker(s) for s in visible_swings],
            "lines": self._zigzag(visible_swings),
            "confirmation_markers": self._confirm_markers(visible_swings),
            "window": {"start": window_start.isoformat() if window_start else None,
                       "end": window_end.isoformat() if window_end else None},
        }

        if artifacts and include_rejected:
            payload["candidates"] = [p.to_dict() for p in artifacts.pivot_candidates]
            payload["rejected"] = [r.to_dict() for r in (
                artifacts.noise_rejected + artifacts.atr_rejected + artifacts.leg_rejected
            )]
            if artifacts.atr_series and visible_bars:
                payload["atr"] = [
                    {"x": visible_bars[i].timestamp.isoformat(), "y": artifacts.atr_series[i]}
                    for i in range(min(len(visible_bars), len(artifacts.atr_series)))
                ]

        return payload

    def render_debug_html(
        self,
        result: DetectionResult,
        bars: list[Candle],
        output_path: Path,
        *,
        show_rejected: bool = True,
        show_atr: bool = True,
    ) -> Path:
        """Write interactive HTML debugger to disk."""
        data = self.build(
            bars, result.swings, artifacts=result.artifacts,
            include_unconfirmed=True, include_rejected=show_rejected,
        )
        data["meta"] = {
            "symbol": result.symbol,
            "timeframe": result.timeframe.value,
            "version": result.version,
            "performance": result.performance.to_dict() if result.performance else None,
        }

        html = _HTML_TEMPLATE.replace("__DATA__", json.dumps(data))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _filter_bars(self, bars, start, end):
        if not start and not end:
            return bars
        return [c for c in bars if (not start or c.timestamp >= start) and (not end or c.timestamp <= end)]

    def _filter_swings(self, swings, start, end, include_unconfirmed):
        out = []
        for s in swings:
            if not include_unconfirmed and not s.confirmed:
                continue
            if start and s.timestamp < start:
                continue
            if end and s.timestamp > end:
                continue
            out.append(s)
        return out

    def _candle(self, c: Candle, i: int) -> dict:
        return {"time": c.timestamp.isoformat(), "open": c.open, "high": c.high,
                "low": c.low, "close": c.close, "index": i}

    def _swing_marker(self, s: DetectedSwing) -> dict:
        return {
            "time": s.timestamp.isoformat(), "price": s.price, "index": s.pivot_index,
            "direction": s.direction.value, "tier": s.tier.value, "scope": s.scope.value,
            "strength": s.strength, "confidence": s.confidence, "confirmed": s.confirmed,
            "color": self._color(s), "label": f"{s.tier.value} {s.scope.value} {s.direction.value}",
        }

    def _confirm_markers(self, swings: list[DetectedSwing]) -> list[dict]:
        return [
            {"time": s.confirmed_timestamp.isoformat(), "price": s.price,
             "delay": s.confirmation_delay, "index": s.confirmation_index}
            for s in swings if s.confirmed and s.confirmed_timestamp
        ]

    def _zigzag(self, swings: list[DetectedSwing]) -> list[dict]:
        lines = []
        for i in range(1, len(swings)):
            a, b = swings[i - 1], swings[i]
            lines.append({"x0": a.timestamp.isoformat(), "y0": a.price,
                          "x1": b.timestamp.isoformat(), "y1": b.price})
        return lines

    def _color(self, s: DetectedSwing) -> str:
        if not s.confirmed:
            return "#94a3b8"
        if s.tier == SwingTier.MAJOR:
            return "#ef4444" if s.direction == SwingDirection.HIGH else "#22c55e"
        return "#fca5a5" if s.direction == SwingDirection.HIGH else "#86efac"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><title>Swing Debug — __SYMBOL__</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif}
  #header{padding:12px 16px;border-bottom:1px solid #334155;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
  #chart{height:calc(100vh - 120px)}
  .legend{display:flex;gap:12px;font-size:12px}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  label{font-size:12px;cursor:pointer}
  #tooltip{position:fixed;background:#1e293b;border:1px solid #475569;padding:8px 12px;
    border-radius:6px;font-size:12px;display:none;pointer-events:none;z-index:99}
</style></head><body>
<div id="header">
  <strong id="title">Swing Detection Debugger</strong>
  <span id="meta"></span>
  <div class="legend">
    <span><span class="dot" style="background:#22c55e"></span> Major Low</span>
    <span><span class="dot" style="background:#ef4444"></span> Major High</span>
    <span><span class="dot" style="background:#86efac"></span> Minor Low</span>
    <span><span class="dot" style="background:#fca5a5"></span> Minor High</span>
    <span><span class="dot" style="background:#64748b"></span> Candidate</span>
    <span><span class="dot" style="background:#f97316"></span> Rejected</span>
  </div>
  <label><input type="checkbox" id="showRejected" checked> Rejected</label>
  <label><input type="checkbox" id="showATR" checked> ATR</label>
</div>
<div id="chart"></div>
<div id="tooltip"></div>
<script>
const DATA = __DATA__;
document.getElementById('meta').textContent =
  `${DATA.meta?.symbol||''} ${DATA.meta?.timeframe||''} v${DATA.meta?.version||''}` +
  (DATA.meta?.performance ? ` | ${DATA.meta.performance.runtime_ms}ms | ${DATA.meta.performance.bars_per_second} bars/s` : '');

const chart = LightweightCharts.createChart(document.getElementById('chart'), {
  layout:{background:{color:'#0f172a'},textColor:'#94a3b8'},
  grid:{vertLines:{color:'#1e293b'},horzLines:{color:'#1e293b'}},
  crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
});
const cs = chart.addCandlestickSeries({upColor:'#22c55e',downColor:'#ef4444',borderVisible:false,
  wickUpColor:'#22c55e',wickDownColor:'#ef4444'});
cs.setData(DATA.candlesticks.map(c=>({time:c.time.slice(0,19),open:c.open,high:c.high,low:c.low,close:c.close})));

let atrSeries=null;
function toggleATR(show){
  if(show && DATA.atr?.length && !atrSeries){
    atrSeries=chart.addLineSeries({color:'#a78bfa',lineWidth:1,priceScaleId:'atr',title:'ATR'});
    chart.priceScale('atr').applyOptions({scaleMargins:{top:0.8,bottom:0}});
    atrSeries.setData(DATA.atr.map(a=>({time:a.x.slice(0,19),value:a.y})));
  } else if(!show && atrSeries){chart.removeSeries(atrSeries);atrSeries=null;}
}
toggleATR(true);
document.getElementById('showATR').onchange=e=>toggleATR(e.target.checked);

const markers=[];
(DATA.candidates||[]).forEach(c=>{
  markers.push({time:c.timestamp.slice(0,19),position:c.direction==='HIGH'?'aboveBar':'belowBar',
    color:'#64748b',shape:c.direction==='HIGH'?'arrowDown':'arrowUp',text:'?'});
});
function addSwingMarkers(){
  DATA.swings.forEach(s=>{
    markers.push({time:s.time.slice(0,19),position:s.direction==='HIGH'?'aboveBar':'belowBar',
      color:s.color,shape:s.direction==='HIGH'?'arrowDown':'arrowUp',
      text:`${s.tier[0]}${s.scope[0]} S${s.strength} C${(s.confidence*100).toFixed(0)}%`});
  });
}
addSwingMarkers();
function addRejected(){
  (DATA.rejected||[]).forEach(r=>{
    markers.push({time:r.timestamp.slice(0,19),position:r.direction==='HIGH'?'aboveBar':'belowBar',
      color:'#f97316',shape:'circle',text:'X'});
  });
}
addRejected();
markers.sort((a,b)=>a.time.localeCompare(b.time));
cs.setMarkers(markers);
document.getElementById('showRejected').onchange=e=>{
  cs.setMarkers(e.target.checked?markers:markers.filter(m=>m.text!=='X'&&m.text!=='?'));
};

chart.timeScale().fitContent();
</script></body></html>"""
