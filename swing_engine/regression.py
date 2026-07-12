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
    path.write_text(_dashboard_html(entries), encoding="utf-8")
    return path


def _dashboard_html(entries: list[dict[str, Any]]) -> str:
    data_js = json.dumps(entries)
    return (
        """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Swing Engine — Regression Dashboard</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e2e8f0;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}p.sub{color:#94a3b8;margin:0 0 20px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:8px 12px;text-align:right;border-bottom:1px solid #1e293b}
th{color:#94a3b8;font-weight:600;text-align:right;position:sticky;top:0;background:#0b1220}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2),td:nth-child(3),th:nth-child(3){text-align:left}
tr:hover{background:#111a2e}
.up{color:#22c55e}.down{color:#ef4444}.flat{color:#64748b}
.badge{background:#1e293b;padding:2px 8px;border-radius:6px;font-family:monospace}
.f1{font-weight:700;color:#38bdf8}
</style></head><body>
<h1>Swing Detection Engine — Historical Regression</h1>
<p class="sub">Each row is a benchmark run. Arrows compare against the previous run of the same symbol+regime.</p>
<table id="tbl"><thead><tr>
<th>Timestamp</th><th>Version</th><th>Symbol / Regime</th>
<th>Precision</th><th>Recall</th><th>F1</th><th>Delay (bars)</th><th>Price err (pips)</th><th>Repaint</th><th>Commit</th>
</tr></thead><tbody></tbody></table>
<script>
const DATA = """
        + data_js
        + """;
function arrow(cur, prev, invert=false){
  if(prev===undefined||prev===null) return '';
  const d = cur - prev; const eps=1e-6;
  if(Math.abs(d)<eps) return ' <span class="flat">→</span>';
  let good = d>0; if(invert) good=d<0;
  return good? ' <span class="up">↑</span>' : ' <span class="down">↓</span>';
}
const prevByKey = {};
const tbody = document.querySelector('#tbl tbody');
DATA.forEach(e=>{
  const key = e.symbol+'|'+e.regime;
  const p = prevByKey[key];
  const tr = document.createElement('tr');
  tr.innerHTML =
    '<td>'+(e.timestamp||'')+'</td>'+
    '<td><span class="badge">v'+e.engine_version+'</span></td>'+
    '<td>'+e.symbol+' / '+e.regime+'</td>'+
    '<td>'+e.precision.toFixed(3)+arrow(e.precision, p&&p.precision)+'</td>'+
    '<td>'+e.recall.toFixed(3)+arrow(e.recall, p&&p.recall)+'</td>'+
    '<td class="f1">'+e.f1_score.toFixed(3)+arrow(e.f1_score, p&&p.f1_score)+'</td>'+
    '<td>'+e.average_detection_delay_bars.toFixed(2)+arrow(e.average_detection_delay_bars, p&&p.average_detection_delay_bars, true)+'</td>'+
    '<td>'+e.average_price_error_pips.toFixed(2)+arrow(e.average_price_error_pips, p&&p.average_price_error_pips, true)+'</td>'+
    '<td>'+e.repainting_rate.toFixed(3)+arrow(e.repainting_rate, p&&p.repainting_rate, true)+'</td>'+
    '<td><span class="badge">'+(e.commit_hash||'-')+'</span></td>';
  tbody.appendChild(tr);
  prevByKey[key] = e;
});
if(!DATA.length){ tbody.innerHTML='<tr><td colspan="10" style="color:#64748b;text-align:center;padding:40px">No history yet. Run scripts/benchmark_swings.py to populate.</td></tr>'; }
</script></body></html>"""
    )
