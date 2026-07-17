#!/usr/bin/env python3
"""Launch the dependency-free blind swing annotation studio.

The server binds to localhost only.  It never displays engine predictions and
writes labels back to the selected HUMAN_DRAFT JSON file with timestamped
backups.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_engine.annotations import load_annotation_document, resolve_dataset_path
from swing_engine.benchmark_data import load_candles_csv

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>FX Navigators Blind Swing Labeler</title>
<style>
:root{color-scheme:dark}body{margin:0;background:#0b1220;color:#e5e7eb;font:14px system-ui}
header{padding:12px 16px;background:#111827;display:flex;gap:12px;align-items:center;position:sticky;top:0;z-index:3}
button,select,input,textarea{background:#1f2937;color:#e5e7eb;border:1px solid #475569;border-radius:5px;padding:7px}
button{cursor:pointer}button.primary{background:#14532d}.grid{display:grid;grid-template-columns:minmax(600px,1fr) 360px;height:calc(100vh - 58px)}
.chart-wrap{padding:12px;overflow:hidden}canvas{width:100%;height:100%;background:#07101e;border:1px solid #334155}
aside{border-left:1px solid #334155;padding:12px;overflow:auto}.row{display:flex;gap:7px;margin:8px 0;align-items:center}.row>*{flex:1}
label{color:#94a3b8;font-size:12px}.card{border:1px solid #334155;border-radius:6px;padding:9px;margin:7px 0;background:#111827}.selected{outline:2px solid #eab308}
small{color:#94a3b8}.status{margin-left:auto}.high{color:#f87171}.low{color:#4ade80}.error{color:#fca5a5}
</style></head><body>
<header><strong>FX Navigators — Blind Swing Labeler</strong><select id="sample"></select><button id="prev">←</button><button id="next">→</button><button id="save" class="primary">Save draft</button><span class="status" id="status">Loading…</span></header>
<div class="grid"><div class="chart-wrap"><canvas id="chart"></canvas></div><aside>
<div><strong id="sampleTitle"></strong><br><small id="sampleMeta"></small></div>
<hr><div class="row"><button id="pivotMode" class="primary">1. Select pivot</button><button id="confirmMode">2. Select confirmation</button></div>
<div class="row"><div><label>Pivot index</label><input id="pivot" readonly></div><div><label>Confirmation index</label><input id="confirm" readonly></div></div>
<div class="row"><div><label>Direction</label><select id="direction"><option>HIGH</option><option>LOW</option></select></div><div><label>Tier</label><select id="tier"><option>MAJOR</option><option>MINOR</option></select></div></div>
<div class="row"><div><label>Scope</label><select id="scope"><option>EXTERNAL</option><option>INTERNAL</option></select></div><div><label>Status</label><select id="confirmationStatus"><option>CONFIRMED</option><option>CANDIDATE</option><option>UNCONFIRMED_AT_WINDOW_END</option><option>DISPUTED</option></select></div></div>
<div class="row"><div><label>Strength 1–5</label><input id="strength" type="number" min="1" max="5" value="3"></div><div><label>Quality 0–100</label><input id="quality" type="number" min="0" max="100" value="80"></div><div><label>Confidence 0–1</label><input id="confidence" type="number" min="0" max="1" step="0.01" value="0.85"></div></div>
<label>Tags, comma-separated</label><input id="tags" style="width:96%" placeholder="LIQUIDITY_SWEEP, NEWS_SPIKE">
<label>Notes</label><textarea id="notes" rows="3" style="width:96%"></textarea>
<div class="row"><button id="add" class="primary">Add label</button><button id="clear">Clear form</button></div>
<hr><strong>Labels in this sample</strong><div id="labels"></div>
</aside></div>
<script>
let doc=null,bars=[],sample=null,mode='pivot',selected=-1;
const $=id=>document.getElementById(id), canvas=$('chart'), ctx=canvas.getContext('2d');
async function init(){doc=await (await fetch('/api/document')).json(); const sel=$('sample'); doc.samples.forEach(s=>{let o=document.createElement('option');o.value=s.sample_id;o.textContent=s.sample_id+' — '+s.primary_regime;sel.appendChild(o)}); sel.onchange=()=>loadSample(sel.value); $('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);$('save').onclick=save;$('pivotMode').onclick=()=>setMode('pivot');$('confirmMode').onclick=()=>setMode('confirm');$('add').onclick=addLabel;$('clear').onclick=clearForm;canvas.onclick=chartClick;window.onresize=draw;await loadSample(sel.value)}
function step(d){let s=$('sample'),i=Math.max(0,Math.min(s.options.length-1,s.selectedIndex+d));s.selectedIndex=i;loadSample(s.value)}
async function loadSample(id){sample=doc.samples.find(x=>x.sample_id===id); bars=await (await fetch('/api/sample?id='+encodeURIComponent(id))).json(); $('sampleTitle').textContent=id;$('sampleMeta').textContent=sample.primary_regime+' | source '+sample.source_start_index+'…'+sample.source_end_index+' | labelable '+sample.labelable_start_index+'…'+sample.labelable_end_index;clearForm();renderLabels();draw()}
function setMode(m){mode=m;$('pivotMode').className=m==='pivot'?'primary':'';$('confirmMode').className=m==='confirm'?'primary':''}
function chartClick(e){const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*canvas.width/r.width;let i=Math.round((x-50)/(canvas.width-70)*(bars.length-1));i=Math.max(0,Math.min(bars.length-1,i));selected=i;if(mode==='pivot')$('pivot').value=i;else $('confirm').value=i;draw()}
function clearForm(){$('pivot').value='';$('confirm').value='';$('notes').value='';$('tags').value='';selected=-1;setMode('pivot');draw()}
function addLabel(){let p=Number($('pivot').value),c=$('confirm').value===''?null:Number($('confirm').value);if(!Number.isInteger(p)){alert('Select a pivot candle first.');return}let status=$('confirmationStatus').value;if(status==='CONFIRMED' && (!Number.isInteger(c)||c<=p)){alert('A confirmed swing needs a later confirmation candle.');return}if(p<sample.labelable_start_index||p>sample.labelable_end_index){alert('Pivot must be inside the labelable region.');return}let b=bars[p],dir=$('direction').value,used=new Set(doc.swings.filter(x=>x.sample_id===sample.sample_id).map(x=>x.label_id));let count=1,labelId='';do{labelId=sample.sample_id+'_SWG_'+String(count++).padStart(3,'0')}while(used.has(labelId));doc.swings.push({label_id:labelId,sample_id:sample.sample_id,pivot_index:p,source_bar_index:sample.source_start_index+p,timestamp:b.timestamp,price:dir==='HIGH'?b.high:b.low,price_field:dir,direction:dir,tier:$('tier').value,scope:$('scope').value,confirmation_status:status,confirmed_at_index:c,confirmed_at_timestamp:c===null?null:bars[c].timestamp,strength:Number($('strength').value),quality_score:Number($('quality').value),confidence:Number($('confidence').value),tags:$('tags').value.split(',').map(x=>x.trim()).filter(Boolean),annotator_id:'ANALYST_A',review_status:'RAW',notes:$('notes').value});clearForm();renderLabels();draw();setStatus('Unsaved changes')}
function renderLabels(){let root=$('labels');root.innerHTML='';doc.swings.filter(x=>x.sample_id===sample.sample_id).sort((a,b)=>a.pivot_index-b.pivot_index).forEach(l=>{let d=document.createElement('div');d.className='card';d.innerHTML='<b class="'+l.direction.toLowerCase()+'">'+l.direction+'</b> #'+l.pivot_index+' — '+l.tier+' '+l.scope+'<br><small>'+l.price+' | confirm '+(l.confirmed_at_index??'—')+' | Q'+l.quality_score+' C'+l.confidence+'</small><br><button>Delete</button>';d.querySelector('button').onclick=()=>{doc.swings=doc.swings.filter(x=>x!==l);renderLabels();draw();setStatus('Unsaved changes')};root.appendChild(d)})}
async function save(){setStatus('Saving…');let r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(doc)});let out=await r.json();setStatus(r.ok?'Saved '+out.saved_at:'Save failed: '+out.error)}
function setStatus(t){$('status').textContent=t}
function draw(){let box=canvas.getBoundingClientRect();canvas.width=Math.max(800,Math.floor(box.width*devicePixelRatio));canvas.height=Math.max(500,Math.floor(box.height*devicePixelRatio));ctx.clearRect(0,0,canvas.width,canvas.height);if(!bars.length)return;let padL=50,padR=20,padT=20,padB=30,w=canvas.width-padL-padR,h=canvas.height-padT-padB,min=Math.min(...bars.map(x=>x.low)),max=Math.max(...bars.map(x=>x.high)),x=i=>padL+i/(bars.length-1)*w,y=p=>padT+(max-p)/(max-min)*h;ctx.strokeStyle='#334155';ctx.fillStyle='#94a3b8';ctx.font=(11*devicePixelRatio)+'px system-ui';for(let k=0;k<=5;k++){let yy=padT+k*h/5;ctx.beginPath();ctx.moveTo(padL,yy);ctx.lineTo(canvas.width-padR,yy);ctx.stroke();ctx.fillText((max-k*(max-min)/5).toFixed(2),2,yy+4)}let ls=x(sample.labelable_start_index),le=x(sample.labelable_end_index);ctx.fillStyle='rgba(59,130,246,.06)';ctx.fillRect(ls,padT,le-ls,h);let cw=Math.max(1,w/bars.length*.55);bars.forEach((b,i)=>{let xx=x(i),up=b.close>=b.open;ctx.strokeStyle=up?'#22c55e':'#ef4444';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(xx,y(b.high));ctx.lineTo(xx,y(b.low));ctx.stroke();let top=Math.min(y(b.open),y(b.close)),bh=Math.max(1,Math.abs(y(b.open)-y(b.close)));ctx.fillRect(xx-cw/2,top,cw,bh)});doc.swings.filter(l=>l.sample_id===sample.sample_id).forEach(l=>{let xx=x(l.pivot_index),yy=y(l.price);ctx.fillStyle=l.direction==='HIGH'?'#fbbf24':'#38bdf8';ctx.beginPath();if(l.direction==='HIGH'){ctx.moveTo(xx,yy-12);ctx.lineTo(xx-7,yy-2);ctx.lineTo(xx+7,yy-2)}else{ctx.moveTo(xx,yy+12);ctx.lineTo(xx-7,yy+2);ctx.lineTo(xx+7,yy+2)}ctx.closePath();ctx.fill()});if(selected>=0){ctx.strokeStyle='#facc15';ctx.beginPath();ctx.moveTo(x(selected),padT);ctx.lineTo(x(selected),padT+h);ctx.stroke();ctx.fillStyle='#facc15';ctx.fillText('#'+selected+' '+bars[selected].timestamp,Math.min(x(selected)+5,canvas.width-300),padT+15)}}
init().catch(e=>setStatus('Error: '+e));
</script></body></html>"""


class App:
    def __init__(self, labels_path: Path):
        self.labels_path = labels_path.resolve()
        self.document = load_annotation_document(self.labels_path)
        dataset = self.document["dataset"]
        self.candles = load_candles_csv(
            resolve_dataset_path(self.labels_path, self.document),
            symbol=dataset["symbol"],
            timeframe=dataset["timeframe"],
            expected_sha256=dataset.get("data_sha256"),
        )
        self.samples = {item["sample_id"]: item for item in self.document.get("samples", [])}

    def sample_bars(self, sample_id: str) -> list[dict]:
        sample = self.samples[sample_id]
        start, end = int(sample["source_start_index"]), int(sample["source_end_index"])
        result = []
        for local_index, candle in enumerate(self.candles[start : end + 1]):
            result.append(
                {
                    "index": local_index,
                    "timestamp": candle.timestamp.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "tick_volume": candle.tick_volume,
                    "spread": candle.spread,
                }
            )
        return result

    def save(self, document: dict) -> str:
        if document.get("label_origin") not in {"HUMAN_DRAFT", "HUMAN"}:
            raise ValueError("The annotation studio only edits human draft files")
        if document.get("dataset", {}).get("data_sha256") != self.document.get("dataset", {}).get("data_sha256"):
            raise ValueError("Dataset checksum cannot be changed in the annotation studio")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.labels_path.with_suffix(self.labels_path.suffix + f".{stamp}.bak")
        shutil.copy2(self.labels_path, backup)
        self.labels_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        self.document = document
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._send(200, HTML.encode(), "text/html; charset=utf-8")
            if parsed.path == "/api/document":
                return self._send(200, json.dumps(app.document).encode(), "application/json")
            if parsed.path == "/api/sample":
                sample_id = parse_qs(parsed.query).get("id", [""])[0]
                if sample_id not in app.samples:
                    return self._send(404, b'{"error":"unknown sample"}', "application/json")
                return self._send(200, json.dumps(app.sample_bars(sample_id)).encode(), "application/json")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/api/save":
                return self._send(404, b'{"error":"not found"}', "application/json")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 10_000_000:
                    raise ValueError("Payload is too large")
                document = json.loads(self.rfile.read(size))
                saved_at = app.save(document)
                payload = json.dumps({"saved_at": saved_at}).encode()
                return self._send(200, payload, "application/json")
            except Exception as exc:  # local annotation tool: return useful error to UI
                payload = json.dumps({"error": str(exc)}).encode()
                return self._send(400, payload, "application/json")

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch blind human swing annotation studio")
    parser.add_argument(
        "labels",
        nargs="?",
        type=Path,
        default=Path("benchmarks/labels/XAUUSD_H1.human.json"),
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = App(args.labels)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Blind labeler: {url}")
    print(f"Labels file:  {app.labels_path}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
