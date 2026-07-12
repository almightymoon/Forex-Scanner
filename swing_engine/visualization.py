"""Interactive HTML visual debugger for swing detection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.types.models import Candle

from swing_engine.models import DetectedSwing, DetectionResult, PipelineArtifacts, SwingDirection, SwingScope, SwingTier


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
            "confirmation_markers": self._confirm_markers(visible_swings, bars),
            "window": {
                "start": window_start.isoformat() if window_start else None,
                "end": window_end.isoformat() if window_end else None,
            },
        }

        if artifacts:
            payload["candidates"] = [p.to_dict() for p in artifacts.pivot_candidates]
            payload["filtered"] = [p.to_dict() for p in artifacts.noise_filtered]
            payload["timeline"] = artifacts.decision_timeline
            payload["market_context"] = (
                artifacts.market_context.to_dict() if artifacts.market_context else None
            )
            if include_rejected:
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
        show_timeline: bool = True,
    ) -> Path:
        data = self.build(
            bars, result.swings, artifacts=result.artifacts,
            include_unconfirmed=True, include_rejected=show_rejected,
        )
        data["meta"] = {
            "symbol": result.symbol,
            "timeframe": result.timeframe.value,
            "version": result.version,
            "performance": result.performance.to_dict() if result.performance else None,
            "show_atr": show_atr,
            "show_timeline": show_timeline,
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
        return {
            "time": c.timestamp.isoformat(), "open": c.open, "high": c.high,
            "low": c.low, "close": c.close, "index": i,
        }

    def _swing_marker(self, s: DetectedSwing) -> dict:
        return {
            "time": s.timestamp.isoformat(), "price": s.price, "index": s.pivot_index,
            "direction": s.direction.value, "tier": s.tier.value, "scope": s.scope.value,
            "strength": s.strength, "score": s.score,
            "normalized_score": s.normalized_score, "confidence": s.confidence,
            "quality_score": s.quality_score,
            "quality_factors": s.quality_factors,
            "confirmed": s.confirmed,
            "confirmation_delay": s.confirmation_delay,
            "confirmation_index": s.confirmation_index,
            "reasoning": s.reasoning,
            "explanation": s.explanation.to_dict() if s.explanation else None,
            "color": self._color(s), "label": f"{s.tier.value} {s.scope.value} {s.direction.value}",
        }

    def _confirm_markers(self, swings: list[DetectedSwing], bars: list[Candle]) -> list[dict]:
        out = []
        for s in swings:
            if not s.confirmed or s.confirmation_index is None:
                continue
            c = bars[s.confirmation_index]
            out.append({
                "time": c.timestamp.isoformat(), "price": c.close,
                "delay": s.confirmation_delay, "index": s.confirmation_index,
                "pivot_index": s.pivot_index, "direction": s.direction.value,
            })
        return out

    def _zigzag(self, swings: list[DetectedSwing]) -> list[dict]:
        lines = []
        for i in range(1, len(swings)):
            a, b = swings[i - 1], swings[i]
            lines.append({
                "x0": a.timestamp.isoformat(), "y0": a.price,
                "x1": b.timestamp.isoformat(), "y1": b.price,
            })
        return lines

    def _color(self, s: DetectedSwing) -> str:
        if not s.confirmed:
            return "#94a3b8"
        if s.scope == SwingScope.INTERNAL:
            return "#a78bfa" if s.direction == SwingDirection.HIGH else "#818cf8"
        if s.scope == SwingScope.EXTERNAL:
            return "#ef4444" if s.direction == SwingDirection.HIGH else "#22c55e"
        if s.tier == SwingTier.MAJOR:
            return "#f97316" if s.direction == SwingDirection.HIGH else "#14b8a6"
        return "#fca5a5" if s.direction == SwingDirection.HIGH else "#86efac"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><title>Swing Debug</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;display:flex;flex-direction:column;height:100vh}
  #header{padding:10px 16px;border-bottom:1px solid #334155;display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:12px}
  #main{display:flex;flex:1;overflow:hidden}
  #chart{flex:1;min-width:0}
  #sidebar{width:320px;border-left:1px solid #334155;overflow-y:auto;font-size:11px;padding:8px}
  .legend{display:flex;gap:8px;flex-wrap:wrap}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
  label{cursor:pointer}
  #tooltip{position:fixed;background:#1e293b;border:1px solid #475569;padding:8px 12px;border-radius:6px;font-size:11px;display:none;pointer-events:none;z-index:99;max-width:280px}
  .tl-item{padding:6px 8px;border-bottom:1px solid #1e293b;cursor:pointer}
  .tl-item:hover{background:#1e293b}
  .tl-rejected{color:#f97316}
  .tl-accepted{color:#22c55e}
  h3{margin:8px 0 4px;font-size:12px;color:#94a3b8}
</style></head><body>
<div id="header">
  <strong>Swing Debugger</strong>
  <span id="meta"></span>
  <div class="legend">
    <span><span class="dot" style="background:#22c55e"></span>Ext Low</span>
    <span><span class="dot" style="background:#ef4444"></span>Ext High</span>
    <span><span class="dot" style="background:#818cf8"></span>Int Low</span>
    <span><span class="dot" style="background:#a78bfa"></span>Int High</span>
    <span><span class="dot" style="background:#64748b"></span>Candidate</span>
    <span><span class="dot" style="background:#f97316"></span>Rejected</span>
  </div>
  <label><input type="checkbox" id="showRejected" checked> Rejected</label>
  <label><input type="checkbox" id="showCandidates" checked> Candidates</label>
  <label><input type="checkbox" id="showATR" checked> ATR</label>
  <label><input type="checkbox" id="showZigzag" checked> Zigzag</label>
</div>
<div id="main">
  <div id="chart"></div>
  <div id="sidebar"><div id="context"></div><h3>Decision Timeline</h3><div id="timeline"></div></div>
</div>
<div id="tooltip"></div>
<script>
const DATA = __DATA__;
document.getElementById('meta').textContent =
  `${DATA.meta?.symbol||''} ${DATA.meta?.timeframe||''} v${DATA.meta?.version||''}` +
  (DATA.meta?.performance ? ` | ${DATA.meta.performance.runtime_ms}ms` : '');

const chart = LightweightCharts.createChart(document.getElementById('chart'), {
  layout:{background:{color:'#0f172a'},textColor:'#94a3b8'},
  grid:{vertLines:{color:'#1e293b'},horzLines:{color:'#1e293b'}},
});
const cs = chart.addCandlestickSeries({upColor:'#22c55e',downColor:'#ef4444',borderVisible:false,
  wickUpColor:'#22c55e',wickDownColor:'#ef4444'});
const candleData = DATA.candlesticks.map(c=>({time:c.time.slice(0,19),open:c.open,high:c.high,low:c.low,close:c.close}));
cs.setData(candleData);

let atrSeries=null, zigzagSeries=null;
function toggleATR(show){
  if(show && DATA.atr?.length && !atrSeries){
    atrSeries=chart.addLineSeries({color:'#a78bfa',lineWidth:1,priceScaleId:'atr',title:'ATR'});
    chart.priceScale('atr').applyOptions({scaleMargins:{top:0.8,bottom:0}});
    atrSeries.setData(DATA.atr.map(a=>({time:a.x.slice(0,19),value:a.y})));
  } else if(!show && atrSeries){chart.removeSeries(atrSeries);atrSeries=null;}
}
function toggleZigzag(show){
  if(show && DATA.lines?.length && !zigzagSeries){
    zigzagSeries=chart.addLineSeries({color:'#64748b',lineWidth:1,lineStyle:2,title:'Zigzag'});
    const pts=[];
    DATA.lines.forEach(l=>{pts.push({time:l.x0.slice(0,19),value:l.y0});pts.push({time:l.x1.slice(0,19),value:l.y1});});
    zigzagSeries.setData(pts.sort((a,b)=>a.time.localeCompare(b.time)));
  } else if(!show && zigzagSeries){chart.removeSeries(zigzagSeries);zigzagSeries=null;}
}
toggleATR(DATA.meta?.show_atr!==false);
toggleZigzag(true);
document.getElementById('showATR').onchange=e=>toggleATR(e.target.checked);
document.getElementById('showZigzag').onchange=e=>toggleZigzag(e.target.checked);

const swingMap={};
(DATA.swings||[]).forEach(s=>{swingMap[s.time.slice(0,19)]=s;});

let allMarkers=[];
function rebuildMarkers(){
  allMarkers=[];
  if(document.getElementById('showCandidates').checked){
    (DATA.candidates||[]).forEach(c=>{
      allMarkers.push({time:c.timestamp.slice(0,19),position:c.direction==='HIGH'?'aboveBar':'belowBar',
        color:'#64748b',shape:c.direction==='HIGH'?'arrowDown':'arrowUp',text:'?'});
    });
  }
  DATA.swings.forEach(s=>{
    allMarkers.push({time:s.time.slice(0,19),position:s.direction==='HIGH'?'aboveBar':'belowBar',
      color:s.color,shape:s.direction==='HIGH'?'arrowDown':'arrowUp',
      text:`${s.tier[0]}${s.scope[0]} S${s.strength}`});
  });
  if(document.getElementById('showRejected').checked){
    (DATA.rejected||[]).forEach(r=>{
      allMarkers.push({time:r.timestamp.slice(0,19),position:r.direction==='HIGH'?'aboveBar':'belowBar',
        color:'#f97316',shape:'circle',text:'X'});
    });
  }
  (DATA.confirmation_markers||[]).forEach(m=>{
    allMarkers.push({time:m.time.slice(0,19),position:'inBar',color:'#fbbf24',shape:'circle',text:`C+${m.delay}`});
  });
  allMarkers.sort((a,b)=>a.time.localeCompare(b.time));
  cs.setMarkers(allMarkers);
}
rebuildMarkers();
document.getElementById('showRejected').onchange=rebuildMarkers;
document.getElementById('showCandidates').onchange=rebuildMarkers;

const tip=document.getElementById('tooltip');
chart.subscribeCrosshairMove(param=>{
  if(!param.time){tip.style.display='none';return;}
  const t=typeof param.time==='string'?param.time:param.time;
  const s=swingMap[t];
  if(s){
    tip.style.display='block';
    tip.style.left=(param.point?.x||0)+12+'px';
    tip.style.top=(param.point?.y||0)+12+'px';
    const q=(s.quality_score!=null)?s.quality_score.toFixed(0):'-';
    const factors=(s.explanation&&s.explanation.factors)?s.explanation.factors:(s.reasoning||[]).slice(0,3);
    tip.innerHTML=`<b>${s.label}</b><br>`+
      `Quality: <b>${q}/100</b> | Confidence: ${(s.confidence*100).toFixed(0)}%<br>`+
      `Strength: ${s.strength} | Score: ${s.normalized_score} | Delay: ${s.confirmation_delay} bars<br>`+
      `<span style="color:#94a3b8">${factors.map(f=>'• '+f).join('<br>')}</span>`;
  } else {tip.style.display='none';}
});

const ctxEl=document.getElementById('context');
if(DATA.market_context){
  const c=DATA.market_context;
  ctxEl.innerHTML='<h3>Market Context</h3>'+
    '<div style="line-height:1.6">'+
    'Volatility: <b>'+c.volatility_regime+'</b> ('+c.atr_percentile+'%ile)<br>'+
    'Structure: <b>'+c.structure_regime+'</b> (ER '+c.efficiency_ratio+')<br>'+
    'Session: <b>'+c.session+'</b><br>'+
    'Spread/ATR: '+c.spread_atr_ratio+'</div>';
}

const tl=document.getElementById('timeline');
(DATA.timeline||[]).forEach(item=>{
  const div=document.createElement('div');
  div.className='tl-item '+(item.status==='accepted'?'tl-accepted':'tl-rejected');
  div.textContent=`#${item.pivot_index} ${item.direction} ${item.status}` +
    (item.rejection_reason?` — ${item.rejection_stage}: ${item.rejection_reason}`:'');
  div.title=item.explanation || (item.events||[]).join(' → ');
  tl.appendChild(div);
});

chart.timeScale().fitContent();
</script></body></html>"""
