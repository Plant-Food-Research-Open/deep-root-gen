"""Build a portable, offline two-panel root architecture comparison.

The only public entry point is ``build_comparison_html(payload, destination)``.
The payload contains display text and literal geometry only::

    {"title": "Architecture comparison", "subtitle": "An invented example",
     "panels": [
       {"title": "Observed", "description": "Example A", "polylines": [
         {"order": 1, "points": [[0, 0, 0], [2, 4, 8]]}]},
       {"title": "Generated", "description": "Example B", "polylines": [
         {"order": 1, "points": [[0, 0, 0], [3, 4, 9]]}]}],
     "summary_rows": [{"label": "Length", "observed": "9.2",
                       "generated": "10.3", "unit": "input units"}],
     "footer": "Illustrative geometry only."}

Coordinates are [across, along, depth], in one caller-defined physical unit,
with positive depth down. No coordinates are translated, rotated, rescaled,
reordered, or joined between polylines. The shared display ranges include the
soil plane at depth zero. The shared aspect ratio is fixed from those physical
axis spans, so hiding orders or the soil plane cannot alter relative scale.
Fixed line widths distinguish order, not diameter.
All camera presets, including the default oblique view, are orthographic for
comparable physical scale and to avoid Plotly 5.23 projection-switch scene
recreation. The historical ``camera-perspective`` control ID is retained for
automation compatibility; its visible label is "Oblique".
Linked views share orthographic wheel zoom; camera presets and Reset restore
the original physical aspect ratio as well as their camera orientation.
Supply anonymized prose: this API deliberately has no identifiers, file paths,
source metadata, or external-resource fields. Unknown fields are rejected.
The output embeds the installed Plotly JavaScript and needs no server/network.
"""

from __future__ import annotations

import html
import json
import math
import numbers
import re
from pathlib import Path
from typing import Any

from plotly.offline import get_plotlyjs


def _fields(value: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    if set(value) - required - optional or required - set(value):
        raise ValueError(f"{where} has missing or unsupported fields")


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{where} must be a display string")
    return value


def _prepare(payload: dict) -> tuple[dict, dict]:
    """Validate and copy allowed values; compute display limits only."""
    _fields(
        payload, {"title", "panels"}, {"subtitle", "summary_rows", "footer"}, "payload"
    )
    data = {
        key: _text(payload.get(key, ""), key) for key in ("title", "subtitle", "footer")
    }
    panels = payload["panels"]
    if not isinstance(panels, list) or len(panels) != 2:
        raise ValueError("panels must contain exactly two panels")
    data["panels"] = []
    axes: list[list[float]] = [[], [], [0.0]]
    for index, panel in enumerate(panels):
        _fields(
            panel, {"title", "description", "polylines"}, set(), f"panel {index + 1}"
        )
        clean = {key: _text(panel[key], key) for key in ("title", "description")}
        lines = panel["polylines"]
        if not isinstance(lines, list) or not lines:
            raise ValueError("each panel must contain at least one polyline")
        clean["polylines"] = []
        for line in lines:
            _fields(line, {"order", "points"}, set(), "polyline")
            order = line["order"]
            if type(order) is not int or order not in range(1, 6):
                raise ValueError("polyline order must be an integer from 1 to 5")
            points = line["points"]
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError("each polyline needs at least two points")
            clean_points = []
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 3:
                    raise ValueError("points must contain exactly three coordinates")
                coords = []
                for axis, value in enumerate(point):
                    if isinstance(value, bool) or not isinstance(value, numbers.Real):
                        raise ValueError("coordinates must be finite real numbers")
                    try:
                        value = float(value)
                    except (OverflowError, ValueError) as error:
                        raise ValueError(
                            "coordinates must be finite real numbers"
                        ) from error
                    if not math.isfinite(value):
                        raise ValueError("coordinates must be finite real numbers")
                    coords.append(value)
                    axes[axis].append(value)
                clean_points.append(coords)
            clean["polylines"].append({"order": order, "points": clean_points})
        data["panels"].append(clean)
    rows = payload.get("summary_rows", [])
    if not isinstance(rows, list):
        raise ValueError("summary_rows must be a list")
    data["summary_rows"] = []
    for row in rows:
        _fields(row, {"label", "observed", "generated", "unit"}, set(), "summary row")
        data["summary_rows"].append({key: _text(row[key], key) for key in row})
    return data, _display_config(axes)


def _display_config(axes: list[list[float]]) -> dict:
    """Fix physical extents independently of visible traces and camera state."""
    ranges = []
    for values in axes:
        low, high = min(values), max(values)
        span = high - low
        pad = span * 0.07 if span else 1.0
        bounds = [low - pad, high + pad]
        if not all(math.isfinite(value) for value in bounds) or bounds[0] >= bounds[1]:
            raise ValueError("coordinate extent is too large for finite display ranges")
        ranges.append(bounds)
    spans = [high - low for low, high in ranges]
    if not all(math.isfinite(span) for span in spans):
        raise ValueError("coordinate extent is too large for finite display ranges")
    longest = max(spans)
    aspectratio = dict(zip(("x", "y", "z"), (span / longest for span in spans)))
    if not all(value > 0 for value in aspectratio.values()):
        raise ValueError(
            "coordinate extents are too disparate for a physical display scale"
        )
    return {"ranges": ranges, "aspectratio": aspectratio}


def _safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_comparison_html(payload: dict, destination: Path) -> Path:
    """Write one standalone HTML; invalid payloads fail before writing anything.

    ``summary_rows`` are display strings only: this function neither computes
    comparisons nor interprets thresholds. Returns the destination Path.
    """
    data, display = _prepare(payload)
    esc = html.escape
    cards = []
    for index, panel in enumerate(data["panels"]):
        cards.append(
            f"""<section class="panel" aria-labelledby="panel-title-{index}">
          <header class="panel-heading"><span class="panel-index">0{index + 1}</span>
            <div><h2 id="panel-title-{index}">{esc(panel['title'])}</h2>
            <p>{esc(panel['description'])}</p></div><span class="panel-tag">3D architecture</span></header>
          <div id="plot-{index}" class="plot" role="img" aria-label="{esc(panel['title'], quote=True)} root architecture. Use the camera buttons to change view."></div>
          <div class="panel-bottom"><span>Across × Along × Depth</span><span>Positive depth ↓</span></div>
        </section>"""
        )
    summary = ""
    if data["summary_rows"]:
        rows = "".join(
            "<tr>"
            + "".join(
                f"<{tag}>{esc(row[key])}</{tag}>"
                for key, tag in (
                    ("label", "th"),
                    ("observed", "td"),
                    ("generated", "td"),
                    ("unit", "td"),
                )
            )
            + "</tr>"
            for row in data["summary_rows"]
        )
        summary = f"""<section class="summary" aria-labelledby="summary-title"><div class="section-label">COMPARISON NOTES</div>
          <h2 id="summary-title">At a glance</h2><div class="table-wrap"><table><thead><tr><th scope="col">Trait</th>
          <th scope="col">{esc(data['panels'][0]['title'])}</th><th scope="col">{esc(data['panels'][1]['title'])}</th>
          <th scope="col">Unit</th></tr></thead><tbody>{rows}</tbody></table></div></section>"""
    filters = "".join(
        f"""<label class="order-filter" style="--order-color:{color}"><input id="order-{i}" type="checkbox" data-order="{i}" checked>
      <span class="order-dot" aria-hidden="true"></span>Order {i}</label>"""
        for i, color in enumerate(
            ("#8c4f22", "#167d8d", "#648c42", "#d78932", "#6c73b0"), 1
        )
    )
    replacements = {
        "{{TITLE}}": esc(data["title"]),
        "{{SUBTITLE}}": esc(data["subtitle"]),
        "{{PANELS}}": "".join(cards),
        "{{FILTERS}}": filters,
        "{{SUMMARY}}": summary,
        "{{FOOTER}}": esc(data["footer"]),
        "{{PAYLOAD}}": _safe_json(data),
        "{{CONFIG}}": _safe_json(display),
        "{{PLOTLY}}": get_plotlyjs().replace("</script", "<\\/script"),
    }
    # Replace template tokens once: user prose can itself contain token text.
    markup = re.sub(
        r"\{\{(?:TITLE|SUBTITLE|PANELS|FILTERS|SUMMARY|FOOTER|PAYLOAD|CONFIG|PLOTLY)\}\}",
        lambda match: replacements[match.group()],
        _TEMPLATE,
    )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(markup, encoding="utf-8")
    return destination


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; worker-src blob:;">
<meta name="color-scheme" content="light"><title>{{TITLE}}</title>
<style>
:root{--ink:#173247;--muted:#647886;--line:#dce5e9;--paper:#fff;--accent:#167b80;--soft:#f1f6f7}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f5f8fa;font:14px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
button,input{font:inherit}button,label{touch-action:manipulation}button{cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #2d9ca2;outline-offset:4px}
.shell{max-width:1660px;margin:auto;padding:44px 36px 30px}.masthead{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;margin-bottom:27px}
.eyebrow,.section-label{font-size:10px;letter-spacing:.16em;font-weight:750;color:var(--accent)}.eyebrow{display:flex;align-items:center;gap:9px;margin-bottom:10px}.eyebrow:before{content:"";display:block;width:25px;height:2px;background:var(--accent)}
h1{font-size:clamp(27px,3.3vw,43px);line-height:1.14;letter-spacing:-.045em;margin:0 0 12px;font-weight:650;max-width:1050px}p{margin:0}.subtitle{color:var(--muted);max-width:950px;font-size:14px}.offline{white-space:nowrap;display:flex;align-items:center;gap:7px;border:1px solid var(--line);border-radius:25px;padding:7px 12px;font-size:11px;color:var(--muted);background:#fff}.offline:before{content:"";width:6px;height:6px;border-radius:50%;background:#4c9e83}
.toolbar{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:15px 18px;margin-bottom:18px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px;box-shadow:0 3px 12px #17324703}
.control-group{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.control-caption{font-size:10px;letter-spacing:.09em;font-weight:700;color:var(--muted);margin-right:7px}.camera-button{border:1px solid transparent;background:var(--soft);color:var(--ink);border-radius:7px;padding:7px 11px;font-size:12px}.camera-button:hover{background:#e5eff1}.camera-button[aria-pressed=true]{background:var(--ink);color:#fff}.camera-button.reset{background:#fff;border-color:var(--line)}
.switch{display:flex;align-items:center;gap:7px;font-size:12px;cursor:pointer;white-space:nowrap}.switch input,.order-filter input{accent-color:var(--accent);width:14px;height:14px;margin:0}.divider{height:22px;width:1px;background:var(--line);margin:0 5px}.plot-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:0 7px 28px #17324704}.panel-heading{display:flex;align-items:flex-start;gap:12px;padding:21px 21px 12px;min-height:105px}.panel-index{font-size:12px;color:#8497a1;border:1px solid var(--line);border-radius:7px;padding:4px 7px;margin-top:2px}h2{font-size:18px;line-height:1.3;margin:0 0 5px;font-weight:650;letter-spacing:-.02em}.panel-heading p{font-size:12px;color:var(--muted);max-width:530px}.panel-tag{margin-left:auto;white-space:nowrap;font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:#6f8e92;background:#f1f7f6;padding:4px 7px;border-radius:4px}.plot{height:clamp(430px,43vw,650px);width:100%}.panel-bottom{padding:12px 21px;border-top:1px solid #edf1f3;display:flex;justify-content:space-between;color:var(--muted);font-size:11px;letter-spacing:.02em}
.legend{display:flex;align-items:center;flex-wrap:wrap;gap:18px;padding:19px 5px 15px}.order-filter{display:flex;align-items:center;gap:7px;font-size:12px;cursor:pointer}.order-dot{width:18px;height:3px;border-radius:4px;background:var(--order-color)}.legend .control-caption{margin-right:0}.geometry-note{font-size:11px;color:var(--muted);margin:0 5px;max-width:1150px}.status{font-size:11px;color:var(--muted);min-height:19px;margin:10px 5px 0}.status.error{padding:12px;background:#fff0e8;border:1px solid #e4c7b5;border-radius:7px;color:#813c1b}
.summary{margin-top:28px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:23px 24px}.summary h2{margin:6px 0 17px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;padding:11px 13px;border-bottom:1px solid #edf1f3;white-space:pre-wrap}thead th{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:650;background:#f6f9fa}tbody th{font-weight:550}tbody tr:last-child>*{border-bottom:0}td:nth-child(2),td:nth-child(3){font-variant-numeric:tabular-nums}td:last-child{color:var(--muted)}footer{margin-top:24px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;white-space:pre-wrap}
@media(max-width:1100px){.panel-tag{display:none}.shell{padding:30px 22px}.toolbar{gap:12px}}@media(max-width:760px){.shell{padding:24px 12px}.masthead{display:block}.offline{display:inline-flex;margin-top:15px}.plot-grid{grid-template-columns:minmax(0,1fr)}.plot{height:460px}.toolbar{padding:13px}.control-group{gap:6px}.camera-button{padding:7px 9px}.legend{gap:13px}.panel-heading{min-height:90px}.summary{padding:18px 14px}.panel-bottom{padding:11px 15px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head><body><main class="shell">
<header class="masthead"><div><div class="eyebrow">ROOT ARCHITECTURE / COMPARATIVE VIEW</div><h1>{{TITLE}}</h1><p class="subtitle">{{SUBTITLE}}</p></div><span class="offline">Self-contained · Offline</span></header>
<div class="toolbar" role="region" aria-label="Shared view controls"><div class="control-group"><span class="control-caption">CAMERA</span>
<button id="camera-perspective" class="camera-button" data-camera="perspective" aria-pressed="true">Oblique</button><button id="camera-front" class="camera-button" data-camera="front" aria-pressed="false">Front</button><button id="camera-side" class="camera-button" data-camera="side" aria-pressed="false">Side</button><button id="camera-top" class="camera-button" data-camera="top" aria-pressed="false">Top</button><button id="camera-reset" class="camera-button reset" data-camera="reset">↺ Reset</button></div>
<div class="control-group"><label class="switch"><input id="sync-camera" type="checkbox" checked>Sync cameras</label><span class="divider" aria-hidden="true"></span><label class="switch"><input id="show-soil" type="checkbox" checked>Soil surface</label></div></div>
<div class="plot-grid">{{PANELS}}</div>
<div class="legend" role="group" aria-label="Visible root orders"><span class="control-caption">ROOT ORDER</span>{{FILTERS}}</div>
<p class="geometry-note">Literal polylines in the supplied coordinate frame; no inferred connectors, alignment, rotation or scale changes. Both panels share fixed physical axis ranges, equal spatial units and orthographic cameras. Line widths distinguish root order only; measured diameters are not represented. Translucent plane: depth 0. Coordinate units are those of the supplied geometry.</p>
<p class="status" id="viewer-status" role="status" aria-live="polite">Preparing the interactive views…</p>
{{SUMMARY}}<footer>{{FOOTER}}</footer>
</main><noscript>This comparison needs JavaScript enabled. The viewer is fully offline.</noscript>
<script type="application/json" id="comparison-data">{{PAYLOAD}}</script>
<script type="application/json" id="display-config">{{CONFIG}}</script>
<script>{{PLOTLY}}</script>
<script>
"use strict";
(() => {
const payload = JSON.parse(document.getElementById("comparison-data").textContent);
const display = JSON.parse(document.getElementById("display-config").textContent);
const plots = [document.getElementById("plot-0"), document.getElementById("plot-1")];
const status = document.getElementById("viewer-status");
const colors = ["#8c4f22", "#167d8d", "#648c42", "#d78932", "#6c73b0"];
const widths = [5.5, 4, 2.8, 2.1, 1.5];
const ranges = display.ranges;
const clone = value => JSON.parse(JSON.stringify(value));
const cameras = {
 perspective:{eye:{x:1.5,y:1.65,z:1.15},up:{x:0,y:0,z:1},center:{x:0,y:0,z:0},projection:{type:"orthographic"}},
 front:{eye:{x:0,y:-2.35,z:0},up:{x:0,y:0,z:1},center:{x:0,y:0,z:0},projection:{type:"orthographic"}},
 side:{eye:{x:2.35,y:0,z:0},up:{x:0,y:0,z:1},center:{x:0,y:0,z:0},projection:{type:"orthographic"}},
 top:{eye:{x:0,y:0,z:2.35},up:{x:0,y:1,z:0},center:{x:0,y:0,z:0},projection:{type:"orthographic"}}
};
let applying = false;
let ready = false;
function showStatus(message, error=false) {status.textContent=message;status.classList.toggle("error",error);}
function announce() {
 const selected = [...document.querySelectorAll("[data-order]:checked")].map(input=>Number(input.dataset.order));
 const counts = payload.panels.map(panel=>panel.polylines.filter(line=>selected.includes(line.order)).length);
 showStatus(`${counts[0].toLocaleString()} / ${counts[1].toLocaleString()} polylines visible · ${document.getElementById("sync-camera").checked ? "Cameras linked" : "Cameras independent"} · Drag to orbit, scroll to zoom. Camera presets also work with the keyboard.`);
}
function traces(panel) {
 const result = [];
 for (let order=1;order<=5;order++) {
  const x=[],y=[],z=[];
  panel.polylines.filter(line=>line.order===order).forEach(line=>{
   line.points.forEach(point=>{x.push(point[0]);y.push(point[1]);z.push(point[2]);});
   x.push(null);y.push(null);z.push(null);
  });
  result.push({type:"scatter3d",mode:"lines",name:`Order ${order}`,x,y,z,connectgaps:false,
   line:{color:colors[order-1],width:widths[order-1]},showlegend:false,
   hovertemplate:`Order ${order}<br>Across: %{x:.3f}<br>Along: %{y:.3f}<br>Depth: %{z:.3f}<extra></extra>`});
 }
 result.push({type:"surface",name:"Soil surface",x:ranges[0],y:ranges[1],z:[[0,0],[0,0]],
  opacity:.12,colorscale:[[0,"#8ba3a0"],[1,"#8ba3a0"]],showscale:false,showlegend:false,
  hoverinfo:"skip",contours:{x:{show:false},y:{show:false},z:{show:false}}});
 return result;
}
function layout() {
 const axis=(title,range)=>({title:{text:title,font:{size:11,color:"#526c7e"}},range:clone(range),autorange:false,
  showbackground:true,backgroundcolor:"#fafcfd",gridcolor:"#e3eaed",zerolinecolor:"#ccd9df",
  showline:true,linecolor:"#d8e2e7",tickfont:{size:10,color:"#748793"},nticks:5,showspikes:false});
 return {margin:{l:5,r:5,t:0,b:0},paper_bgcolor:"#ffffff",font:{family:"system-ui, sans-serif",color:"#173247"},
  showlegend:false,uirevision:"literal-geometry",scene:{aspectmode:"manual",aspectratio:clone(display.aspectratio),camera:clone(cameras.perspective),
  xaxis:axis("Across",ranges[0]),yaxis:axis("Along",ranges[1]),zaxis:axis("Depth ↓",[ranges[2][1],ranges[2][0]]),
  bgcolor:"#ffffff",dragmode:"orbit"}};
}
const config={responsive:true,displaylogo:false,displayModeBar:false,scrollZoom:true,showTips:false,
 plotGlPixelRatio:Math.min(window.devicePixelRatio||1,2),topojsonURL:"",mapboxAccessToken:""};
function selectedCamera(name) {document.querySelectorAll("[data-camera][aria-pressed]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.camera===name)));}
async function setCamera(camera, targets=plots, aspectratio=null) {
 if (!ready || applying) return;
 applying=true;
 const update={};
 if(camera) update["scene.camera"]=clone(camera);
 if(aspectratio) update["scene.aspectratio"]=clone(aspectratio);
 try {await Promise.all(targets.map(plot=>Plotly.relayout(plot,clone(update))));}
 finally {applying=false;}
}
async function start() {
 await Promise.all(plots.map((plot,index)=>Plotly.newPlot(plot,traces(payload.panels[index]),layout(),config)));
 ready=true;
 plots.forEach((plot,index)=>{
  plot.on("plotly_relayout",event=>{
   const cameraChanged = Object.keys(event).some(key=>key==="scene.camera"||key.startsWith("scene.camera."));
   const zoomChanged = Object.keys(event).some(key=>key==="scene.aspectratio"||key.startsWith("scene.aspectratio."));
   if ((!cameraChanged&&!zoomChanged) || applying) return;
   selectedCamera(null);
   if(document.getElementById("sync-camera").checked) {
    const camera=cameraChanged?(event["scene.camera"]||plot.layout.scene.camera):null;
    const aspectratio=zoomChanged?(event["scene.aspectratio"]||plot.layout.scene.aspectratio):null;
    setCamera(camera,[plots[1-index]],aspectratio).catch(()=>showStatus("View synchronization failed. Use a camera preset to reset both views.",true));
   }
  });
  plot.on("plotly_webglcontextlost",()=>showStatus("The 3D graphics context was lost. Reload this local file to restore the views.",true));
 });
 document.querySelectorAll("[data-camera]").forEach(button=>button.addEventListener("click",()=>{
  const name=button.dataset.camera==="reset"?"perspective":button.dataset.camera;
  selectedCamera(name);setCamera(cameras[name],plots,display.aspectratio).catch(()=>showStatus("Unable to update the camera.",true));
 }));
 document.getElementById("sync-camera").addEventListener("change",event=>{
  if(event.target.checked) setCamera(plots[0].layout.scene.camera,plots,plots[0].layout.scene.aspectratio).catch(()=>showStatus("Unable to link the cameras.",true));
  announce();
 });
 document.getElementById("show-soil").addEventListener("change",async event=>{
  try {await Promise.all(plots.map(plot=>Plotly.restyle(plot,{visible:event.target.checked},[5])));}
  catch(error){showStatus("Unable to update the soil surface.",true);}
 });
 document.querySelectorAll("[data-order]").forEach(input=>input.addEventListener("change",async()=>{
  try {await Promise.all(plots.map(plot=>Plotly.restyle(plot,{visible:input.checked},[Number(input.dataset.order)-1])));announce();}
  catch(error){showStatus("Unable to update the root order filter.",true);}
 }));
 announce();
 const observer=new ResizeObserver(()=>{plots.forEach(plot=>Plotly.Plots.resize(plot));});
 plots.forEach(plot=>observer.observe(plot));
}
const readiness=start();
window.rootViewer={
 ready:readiness,
 get plots(){return plots.slice();},
 get state(){return {ready,sync:document.getElementById("sync-camera").checked,
  soil:document.getElementById("show-soil").checked,
  orders:[...document.querySelectorAll("[data-order]:checked")].map(input=>Number(input.dataset.order)),
  ranges:clone(ranges),baseAspectratio:clone(display.aspectratio),
  aspectratios:plots.map(plot=>plot.layout&&plot.layout.scene?clone(plot.layout.scene.aspectratio):null),
  cameras:plots.map(plot=>plot.layout&&plot.layout.scene?clone(plot.layout.scene.camera):null)};}
};
readiness.catch(()=>showStatus("The interactive 3D views could not initialize. Enable JavaScript and WebGL, then reopen this local file.",true));
})();
</script></body></html>"""
