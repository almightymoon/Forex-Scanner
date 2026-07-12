"""Historical regression dashboard (Sprint 3, Priority 4).

Every benchmark run appends a row to a JSONL history file so we can see whether
each engine version actually improves precision/recall/delay over time:

    v1.0  Precision 0.81  Recall 0.79  Delay 3.2 ↓
    v1.1  Precision 0.86  Recall 0.84  Delay 2.4 ↓
    v1.2  Precision 0.89  Recall 0.87  Delay 2.0

The dashboard renders these entries as an HTML table with trend arrows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from swing_engine.models import EvaluationReport

DEFAULT_HISTORY = Path("benchmarks/history/regression_history.jsonl")


@dataclass
class RegressionEntry:
    timestamp: str
    engine_version: str
    symbol: str
    regime: str
    precision: float
    recall: float
    f1_score: float
    average_detection_delay_bars: float
    average_price_error_pips: float
    repainting_rate: float
    commit_hash: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "engine_version": self.engine_version,
            "symbol": self.symbol,
            "regime": self.regime,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "average_detection_delay_bars": round(self.average_detection_delay_bars, 2),
            "average_price_error_pips": round(self.average_price_error_pips, 2),
            "repainting_rate": round(self.repainting_rate, 4),
            "commit_hash": self.commit_hash,
            **self.extra,
        }


def entry_from_report(report: EvaluationReport) -> RegressionEntry:
    meta = report.metadata
    extra = {
        "major_precision": round(report.major_precision, 4),
        "major_recall": round(report.major_recall, 4),
        "major_f1": meta.get("major_f1", 0.0),
        "false_positives": report.false_positives,
        "false_negatives": report.false_negatives,
        "dataset_id": meta.get("dataset_id"),
        "human_review": meta.get("human_review", False),
        "label_source": meta.get("label_source"),
    }
    return RegressionEntry(
        timestamp=datetime.utcnow().isoformat(timespec="seconds"),
        engine_version=str(meta.get("engine_version") or "unknown"),
        symbol=str(meta.get("symbol") or "unknown"),
        regime=str(meta.get("regime") or "unknown"),
        precision=report.precision,
        recall=report.recall,
        f1_score=report.f1_score,
        average_detection_delay_bars=report.average_detection_delay_bars,
        average_price_error_pips=report.average_price_error_pips,
        repainting_rate=report.repainting_rate,
        commit_hash=meta.get("commit_hash"),
        extra=extra,
    )


def append_history(report: EvaluationReport, path: Path = DEFAULT_HISTORY) -> RegressionEntry:
    entry = entry_from_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict()) + "\n")
    return entry


def load_history(path: Path = DEFAULT_HISTORY) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def write_regression_dashboard(
    entries: list[dict[str, Any]],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_benchmark_dashboard_html(entries), encoding="utf-8")
    return path


def write_benchmark_dashboard(entries: list[dict[str, Any]], path: Path) -> Path:
    """Alias for the filterable benchmark dashboard (Sprint 4)."""
    return write_regression_dashboard(entries, path)


def _benchmark_dashboard_html(entries: list[dict[str, Any]]) -> str:
    data_js = json.dumps(entries)
    return (
        """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Swing Benchmark Dashboard</title>
<style>
body{font-family:system-ui,sans-serif;background:#0b1220;color:#e2e8f0;margin:0;padding:20px}
h1{font-size:18px;margin:0 0 4px}.sub{color:#94a3b8;font-size:12px;margin:0 0 16px}
.filters{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;font-size:12px}
.filters select{background:#1e293b;color:#e2e8f0;border:1px solid #334155;padding:6px 10px;border-radius:6px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.card{background:#111a2e;border:1px solid #1e293b;border-radius:8px;padding:12px}
.card .label{color:#94a3b8;font-size:11px}.card .val{font-size:20px;font-weight:700;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid #1e293b}
th{color:#94a3b8;position:sticky;top:0;background:#0b1220}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
.up{color:#22c55e}.down{color:#ef4444}.badge{background:#1e293b;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:11px}
</style></head><body>
<h1>Swing Benchmark Dashboard</h1>
<p class="sub">Filter by symbol, regime, version. Aggregates precision, recall, delay, repainting, confidence.</p>
<div class="filters">
  <label>Symbol <select id="fSymbol"><option value="">All</option></select></label>
  <label>Regime <select id="fRegime"><option value="">All</option></select></label>
  <label>Version <select id="fVersion"><option value="">All</option></select></label>
</div>
<div class="cards" id="cards"></div>
<div id="versionTable" style="margin-bottom:20px"></div>
<table><thead><tr>
<th>Time</th><th>Symbol</th><th>Version</th><th>Regime</th>
<th>Precision</th><th>Recall</th><th>F1</th><th>Major F1</th><th>Delay</th><th>FP</th><th>FN</th><th>Repaint</th><th>Commit</th>
</tr></thead><tbody id="tbody"></tbody></table>
<script>
const ALL = """
        + data_js
        + """;
function uniq(arr, key){ return [...new Set(arr.map(e=>e[key]).filter(Boolean))].sort(); }
function fillSelect(id, values){ const s=document.getElementById(id); values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o);}); }
fillSelect('fSymbol', uniq(ALL,'symbol'));
fillSelect('fRegime', uniq(ALL,'regime'));
fillSelect('fVersion', uniq(ALL,'engine_version'));
function filtered(){
  const sym=document.getElementById('fSymbol').value;
  const reg=document.getElementById('fRegime').value;
  const ver=document.getElementById('fVersion').value;
  return ALL.filter(e=>(!sym||e.symbol===sym)&&(!reg||e.regime===reg)&&(!ver||e.engine_version===ver));
}
function versionSummary(rows){
  const by={};
  rows.forEach(e=>{
    const v=e.engine_version||'?';
    if(!by[v]) by[v]={n:0,p:0,r:0,f:0,mf:0,d:0};
    by[v].n++; by[v].p+=e.precision||0; by[v].r+=e.recall||0; by[v].f+=e.f1_score||0;
    by[v].mf+=(e.major_f1||e.extra?.major_f1||0); by[v].d+=e.average_detection_delay_bars||0;
  });
  let html='<h3 style="font-size:13px;color:#94a3b8">Version Comparison</h3><table style="margin-bottom:12px"><tr><th>Version</th><th>Runs</th><th>Precision</th><th>Recall</th><th>F1</th><th>Major F1</th><th>Delay</th></tr>';
  Object.keys(by).sort().forEach(v=>{
    const x=by[v], n=x.n||1;
    html+='<tr><td style="text-align:left"><span class="badge">v'+v+'</span></td><td>'+x.n+'</td>'
      +'<td>'+(x.p/n).toFixed(3)+'</td><td>'+(x.r/n).toFixed(3)+'</td><td>'+(x.f/n).toFixed(3)+'</td>'
      +'<td>'+(x.mf/n).toFixed(3)+'</td><td>'+(x.d/n).toFixed(2)+'</td></tr>';
  });
  return html+'</table>';
}
function render(){
  const rows=filtered();
  const n=rows.length||1;
  const avg=k=>rows.reduce((s,e)=>s+(e[k]||0),0)/n;
  document.getElementById('versionTable').innerHTML=versionSummary(ALL);
  document.getElementById('cards').innerHTML=[
    ['Precision',avg('precision').toFixed(3)],
    ['Recall',avg('recall').toFixed(3)],
    ['F1',avg('f1_score').toFixed(3)],
    ['Major F1',avg('major_f1').toFixed(3)],
    ['Delay',avg('average_detection_delay_bars').toFixed(2)+' bars'],
    ['Repaint',avg('repainting_rate').toFixed(3)],
    ['Runs',rows.length],
  ].map(([l,v])=>'<div class="card"><div class="label">'+l+'</div><div class="val">'+v+'</div></div>').join('');
  const tb=document.getElementById('tbody'); tb.innerHTML='';
  rows.slice().reverse().forEach(e=>{
    const tr=document.createElement('tr');
    const mf=e.major_f1||e.extra?.major_f1||0;
    const fp=e.false_positives??e.extra?.false_positives??'-';
    const fn=e.false_negatives??e.extra?.false_negatives??'-';
    tr.innerHTML='<td>'+(e.timestamp||'')+'</td><td>'+e.symbol+'</td><td><span class="badge">v'+e.engine_version+'</span></td><td>'+e.regime+'</td>'
      +'<td>'+e.precision.toFixed(3)+'</td><td>'+e.recall.toFixed(3)+'</td><td>'+e.f1_score.toFixed(3)+'</td>'
      +'<td>'+Number(mf).toFixed(3)+'</td><td>'+e.average_detection_delay_bars.toFixed(2)+'</td>'
      +'<td>'+fp+'</td><td>'+fn+'</td><td>'+e.repainting_rate.toFixed(3)+'</td>'
      +'<td><span class="badge">'+(e.commit_hash||'-')+'</span></td>';
    tb.appendChild(tr);
  });
  if(!rows.length) tb.innerHTML='<tr><td colspan="13" style="text-align:center;color:#64748b;padding:32px">No data — run scripts/run_benchmark_suite.py</td></tr>';
}
['fSymbol','fRegime','fVersion'].forEach(id=>document.getElementById(id).onchange=render);
render();
</script></body></html>"""
    )
