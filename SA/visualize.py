#!/usr/bin/env python3
"""
Generate an interactive HTML visualization of a warehouse bay placement solution.

Usage:
    python visualize.py <warehouse.csv> <obstacles.csv> <ceiling.csv> <types_of_bays.csv> <output.csv> [viz.html]

Opens the result in the default browser automatically.
"""

import sys
import json
import os
import webbrowser


def parse_csv(path, min_cols):
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln:
                continue
            p = ln.split(',')
            if len(p) >= min_cols:
                try:
                    rows.append([float(x.strip()) for x in p[:min_cols]])
                except ValueError:
                    continue
    return rows


def polygon_area(verts):
    n = len(verts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += verts[i][0] * verts[j][1] - verts[j][0] * verts[i][1]
    return abs(a) * 0.5

def get_obb_corners(x_bl, y_bl, w, h, angle_deg):
    import math
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return [
        [x_bl, y_bl],
        [x_bl + w * cos_a, y_bl + w * sin_a],
        [x_bl + w * cos_a - h * sin_a, y_bl + w * sin_a + h * cos_a],
        [x_bl - h * sin_a, y_bl + h * cos_a]
    ]

def get_gap_corners(x_bl, y_bl, w, d, g, angle_deg):
    import math
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    px = x_bl - d * sin_a
    py = y_bl + d * cos_a
    return [
        [px, py],
        [px + w * cos_a, py + w * sin_a],
        [px + w * cos_a - g * sin_a, py + w * sin_a + g * cos_a],
        [px - g * sin_a, py + g * cos_a]
    ]


def ceiling_at(ceil_data, x):
    """Step function: find last breakpoint <= x, return its height."""
    if not ceil_data:
        return 1e18
    if x < ceil_data[0][0]:
        return ceil_data[0][1]
    result = ceil_data[0][1]
    for cx, ch in ceil_data:
        if cx <= x:
            result = ch
        else:
            break
    return result


def min_ceiling(ceil_data, x1, x2):
    """Minimum ceiling height over [x1, x2] using step function."""
    h = ceiling_at(ceil_data, x1)
    for cx, ch in ceil_data:
        if cx > x2:
            break
        if cx > x1:
            h = min(h, ch)
    return h


def main():
    if len(sys.argv) < 6:
        print("Usage: python visualize.py <warehouse> <obstacles> <ceiling> <types_of_bays> <output> [viz.html]")
        sys.exit(1)

    wh_data = parse_csv(sys.argv[1], 2)
    obs_data = parse_csv(sys.argv[2], 4)
    ceil_data = sorted(parse_csv(sys.argv[3], 2), key=lambda c: c[0])
    bays_data = parse_csv(sys.argv[4], 7)
    out_data = parse_csv(sys.argv[5], 4)
    html_path = sys.argv[6] if len(sys.argv) > 6 else "visualization.html"

    bay_types = {}
    for row in bays_data:
        tid = int(row[0])
        bay_types[tid] = {
            "id": tid, "width": row[1], "depth": row[2],
            "height": row[3], "gap": row[4],
            "nLoads": int(row[5]), "price": row[6],
            "efficiency": row[6] / row[5] if row[5] > 0 else 1e18
        }

    placed = []
    for row in out_data:
        tid = int(row[0])
        x, y = row[1], row[2]
        rot = float(row[3])
        bt = bay_types[tid]
        w_orig, d_orig, g = bt["width"], bt["depth"], bt["gap"]

        corners = get_obb_corners(x, y, w_orig, d_orig, rot)
        gap_corners = get_gap_corners(x, y, w_orig, d_orig, g, rot)
        
        # Calculate full AABB for area and ceiling check mapping
        xs = [p[0] for p in corners] + [p[0] for p in gap_corners]
        ys = [p[1] for p in corners] + [p[1] for p in gap_corners]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)

        ch = min_ceiling(ceil_data, x1, x2)
        margin = ch - bt["height"]
        placed.append({
            "typeId": tid, "x": x, "y": y, "rotation": rot,
            "corners": corners,
            "gap_corners": gap_corners,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "width": w_orig, "depth": d_orig, "gap": g,
            "efficiency": bt["efficiency"],
            "nLoads": bt["nLoads"], "price": bt["price"],
            "height": bt["height"],
            "ceilingHeight": ch,
            "ceilingMargin": margin
        })

    wh_area = polygon_area(wh_data)
    sum_eff = sum(b["efficiency"] for b in placed)
    sum_area = sum(b["width"] * (b["depth"] + b["gap"]) for b in placed)
    quality = (sum_eff ** 2) * (sum_area / wh_area) if wh_area > 0 else 0

    data = {
        "warehouse": wh_data,
        "obstacles": [{"x": o[0], "y": o[1], "w": o[2], "d": o[3]} for o in obs_data],
        "ceiling": [{"x": c[0], "h": c[1]} for c in ceil_data],
        "bayTypes": bay_types,
        "placed": placed,
        "quality": quality,
        "warehouseArea": wh_area,
        "totalBays": len(placed),
        "sumEfficiency": sum_eff,
        "coveragePercent": (sum_area / wh_area * 100) if wh_area > 0 else 0
    }

    html = generate_html(data)
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"Visualization written to {html_path}")
    abs_path = os.path.abspath(html_path)
    webbrowser.open(f"file://{abs_path}")


def generate_html(data):
    data_json = json.dumps(data)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Warehouse Bay Placement Visualization</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
    border-bottom: 1px solid rgba(99,102,241,0.2);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    flex-shrink: 0;
  }}
  .header h1 {{
    font-size: 18px; font-weight: 600;
    background: linear-gradient(135deg,#818cf8,#6366f1);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .stat {{ text-align: center; }}
  .stat-value {{ font-size: 15px; font-weight: 700; color: #818cf8; }}
  .stat-label {{ font-size: 9px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 1px; }}
  .content {{ display: flex; flex: 1; min-height: 0; }}
  .left {{ display: flex; flex-direction: column; flex: 1; min-width: 0; }}
  .canvas-container {{
    flex: 1; position: relative; overflow: hidden;
    background: #0a0c14; cursor: grab; min-height: 0;
  }}
  .canvas-container:active {{ cursor: grabbing; }}
  canvas {{ position: absolute; top: 0; left: 0; }}
  /* Bottom ceiling cross-section panel */
  .ceiling-panel {{
    height: 120px; flex-shrink: 0;
    background: #0d0f18;
    border-top: 1px solid rgba(99,102,241,0.15);
    position: relative;
  }}
  .ceiling-panel canvas {{ position: absolute; top: 0; left: 0; }}

  .sidebar {{
    width: 280px; background: #13151f;
    border-left: 1px solid rgba(99,102,241,0.15);
    overflow-y: auto; padding: 16px; flex-shrink: 0;
  }}
  .sidebar h2 {{
    font-size: 12px; font-weight: 600; color: #818cf8;
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;
  }}
  .legend {{ display: flex; flex-direction: column; gap: 5px; margin-bottom: 16px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 11px; color: #9ca3af; }}
  .legend-swatch {{ width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }}
  .tooltip {{
    position: absolute;
    background: rgba(19,21,31,0.95);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 8px; padding: 10px 14px; font-size: 12px;
    pointer-events: none; display: none; z-index: 100;
    backdrop-filter: blur(8px); max-width: 240px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }}
  .tooltip-title {{ font-weight: 600; color: #818cf8; margin-bottom: 6px; }}
  .tooltip-row {{
    display: flex; justify-content: space-between; gap: 12px;
    color: #9ca3af; line-height: 1.6;
  }}
  .tooltip-row span:last-child {{ color: #e0e0e0; font-weight: 500; }}
  .tooltip-bar {{
    height: 6px; border-radius: 3px; margin-top: 6px;
    background: rgba(255,255,255,0.08); overflow: hidden;
  }}
  .tooltip-bar-fill {{ height: 100%; border-radius: 3px; }}
  .tooltip-bar-label {{
    font-size: 10px; color: #6b7280; margin-top: 2px; text-align: right;
  }}
  .controls {{ margin-bottom: 16px; }}
  .controls input[type=checkbox] {{ accent-color: #6366f1; margin-right: 6px; }}
  .control-row {{
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 5px; font-size: 11px; color: #9ca3af; cursor: pointer;
  }}
  .control-row:hover {{ color: #e0e0e0; }}
  .bay-list {{ display: flex; flex-direction: column; gap: 3px; max-height: 260px; overflow-y: auto; }}
  .bay-list-item {{
    font-size: 10px; padding: 5px 8px;
    background: rgba(99,102,241,0.05); border-radius: 4px;
    cursor: pointer; transition: background 0.15s;
    display: flex; justify-content: space-between; align-items: center; color: #9ca3af;
  }}
  .bay-list-item:hover {{ background: rgba(99,102,241,0.15); color: #e0e0e0; }}
  .margin-dot {{
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }}
  .zoom-controls {{
    position: absolute; bottom: 12px; left: 12px;
    display: flex; gap: 4px; z-index: 10;
  }}
  .zoom-btn {{
    width: 30px; height: 30px;
    background: rgba(19,21,31,0.9);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 6px; color: #818cf8; font-size: 15px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
  }}
  .zoom-btn:hover {{ background: rgba(99,102,241,0.2); }}
</style>
</head>
<body>

<div class="header">
  <h1>🏭 Warehouse Bay Placement</h1>
  <div class="stats">
    <div class="stat"><div class="stat-value" id="stat-q"></div><div class="stat-label">Quality Score</div></div>
    <div class="stat"><div class="stat-value" id="stat-bays"></div><div class="stat-label">Bays Placed</div></div>
    <div class="stat"><div class="stat-value" id="stat-coverage"></div><div class="stat-label">Coverage</div></div>
    <div class="stat"><div class="stat-value" id="stat-area"></div><div class="stat-label">WH Area</div></div>
  </div>
</div>

<div class="content">
  <div class="left">
    <div class="canvas-container" id="canvasContainer">
      <canvas id="canvas"></canvas>
      <div class="tooltip" id="tooltip"></div>
      <div class="zoom-controls">
        <button class="zoom-btn" onclick="zoomIn()">+</button>
        <button class="zoom-btn" onclick="zoomOut()">−</button>
        <button class="zoom-btn" onclick="resetView()">⌂</button>
      </div>
    </div>
    <div class="ceiling-panel" id="ceilingPanel">
      <canvas id="ceilingCanvas"></canvas>
    </div>
  </div>
  <div class="sidebar">
    <h2>Display</h2>
    <div class="controls">
      <label class="control-row"><input type="checkbox" id="showGrid" checked onchange="draw()"> Grid</label>
      <label class="control-row"><input type="checkbox" id="showLabels" checked onchange="draw()"> Bay IDs</label>
      <label class="control-row"><input type="checkbox" id="showDims" onchange="draw()"> Dimensions</label>
      <label class="control-row"><input type="checkbox" id="showCeilingHeat" checked onchange="draw()"> Ceiling heatmap</label>
      <label class="control-row"><input type="checkbox" id="showCeilingMargin" checked onchange="draw()"> Bay ceiling margin</label>
    </div>
    <h2>Legend</h2>
    <div class="legend" id="legend"></div>
    <h2>Ceiling Scale</h2>
    <div id="ceilingLegend" style="margin-bottom:16px"></div>
    <h2>Placed Bays (<span id="bayCount"></span>)</h2>
    <div class="bay-list" id="bayList"></div>
  </div>
</div>

<script>
const DATA = {data_json};

const TYPE_COLORS = [
  '#6366f1','#8b5cf6','#a78bfa','#c084fc',
  '#f472b6','#fb7185','#f87171','#fb923c',
  '#fbbf24','#a3e635','#4ade80','#34d399',
  '#2dd4bf','#22d3ee','#38bdf8','#60a5fa',
  '#818cf8','#a5b4fc','#e879f9','#f0abfc'
];
function typeColor(tid) {{ return TYPE_COLORS[tid % TYPE_COLORS.length]; }}

// --- Ceiling helpers ---
function ceilAt(x) {{
  // Step function: find last breakpoint <= x, return its height
  const c = DATA.ceiling;
  if (!c.length) return 1e9;
  if (x < c[0].x) return c[0].h;
  let result = c[0].h;
  for (let i = 0; i < c.length; i++) {{
    if (c[i].x <= x) result = c[i].h;
    else break;
  }}
  return result;
}}

// Ceiling color: low=red, mid=yellow, high=green
function ceilColor(h, minH, maxH) {{
  if (maxH === minH) return 'rgba(52,211,153,0.12)';
  const t = (h - minH) / (maxH - minH); // 0..1
  // red(0) -> yellow(0.5) -> green(1)
  let r, g, b;
  if (t < 0.5) {{
    const s = t * 2;
    r = 255; g = Math.round(180 * s); b = 60;
  }} else {{
    const s = (t - 0.5) * 2;
    r = Math.round(255 * (1 - s)); g = 200 + Math.round(55 * s); b = 60 + Math.round(90 * s);
  }}
  return `rgba(${{r}},${{g}},${{b}},0.10)`;
}}

function marginColor(margin, totalH) {{
  if (totalH <= 0) return '#4ade80';
  const ratio = margin / totalH;
  if (ratio > 0.3) return '#4ade80';   // comfy green
  if (ratio > 0.1) return '#fbbf24';   // tight yellow
  if (ratio > 0)   return '#fb923c';   // very tight orange
  return '#ef4444';                     // no room red
}}

// --- Canvas state ---
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const container = document.getElementById('canvasContainer');
const tooltip = document.getElementById('tooltip');
const cPanel = document.getElementById('ceilingPanel');
const cCanvas = document.getElementById('ceilingCanvas');
const cCtx = cCanvas.getContext('2d');

let viewX=0, viewY=0, viewScale=1;
let dragging=false, dragStartX=0, dragStartY=0;
let hoveredBay = -1;
let W=0, H=0, CW=0, CH=0;

// Ceiling min/max
let ceilMin = Infinity, ceilMax = -Infinity;
for (const c of DATA.ceiling) {{ ceilMin = Math.min(ceilMin, c.h); ceilMax = Math.max(ceilMax, c.h); }}
if (!isFinite(ceilMin)) {{ ceilMin = 0; ceilMax = 1; }}
// Extend range slightly
const ceilRange = ceilMax - ceilMin || 1;

// World bounds
let whMinX=Infinity, whMaxX=-Infinity, whMinY=Infinity, whMaxY=-Infinity;
for (const [x,y] of DATA.warehouse) {{
  whMinX=Math.min(whMinX,x); whMaxX=Math.max(whMaxX,x);
  whMinY=Math.min(whMinY,y); whMaxY=Math.max(whMaxY,y);
}}

function worldToScreen(wx, wy) {{
  return [(wx-viewX)*viewScale+W/2, (-wy+viewY)*viewScale+H/2];
}}
function screenToWorld(sx, sy) {{
  return [(sx-W/2)/viewScale+viewX, -((sy-H/2)/viewScale-viewY)];
}}

// --- Init ---
function init() {{
  resize(); fitView();
  populateStats(); populateLegend(); populateCeilingLegend(); populateBayList();
  draw(); drawCeilingChart();
  window.addEventListener('resize', () => {{ resize(); draw(); drawCeilingChart(); }});
  container.addEventListener('wheel', onWheel, {{passive:false}});
  container.addEventListener('mousedown', onMouseDown);
  container.addEventListener('mousemove', onMouseMove);
  container.addEventListener('mouseup', onMouseUp);
  container.addEventListener('mouseleave', () => {{ tooltip.style.display='none'; }});
}}

function resize() {{
  W = container.clientWidth; H = container.clientHeight;
  canvas.width = W*devicePixelRatio; canvas.height = H*devicePixelRatio;
  canvas.style.width = W+'px'; canvas.style.height = H+'px';
  ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  CW = cPanel.clientWidth; CH = cPanel.clientHeight;
  cCanvas.width = CW*devicePixelRatio; cCanvas.height = CH*devicePixelRatio;
  cCanvas.style.width = CW+'px'; cCanvas.style.height = CH+'px';
  cCtx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
}}

function fitView() {{
  let mnx=whMinX, mxx=whMaxX, mny=whMinY, mxy=whMaxY;
  for (const b of DATA.placed) {{
    mnx=Math.min(mnx,b.x1); mxx=Math.max(mxx,b.x2);
    mny=Math.min(mny,b.y1); mxy=Math.max(mxy,b.y2);
  }}
  const pad=0.08;
  const rx=(mxx-mnx)*(1+2*pad), ry=(mxy-mny)*(1+2*pad);
  viewX=(mnx+mxx)/2; viewY=(mny+mxy)/2;
  viewScale=Math.min(W/rx, H/ry);
}}

// ============================
// MAIN DRAW
// ============================
function draw() {{
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle='#0a0c14'; ctx.fillRect(0,0,W,H);
  const showGrid = document.getElementById('showGrid').checked;
  const showLabels = document.getElementById('showLabels').checked;
  const showDims = document.getElementById('showDims').checked;
  const showHeat = document.getElementById('showCeilingHeat').checked;
  const showMargin = document.getElementById('showCeilingMargin').checked;

  if (showGrid) drawGrid();
  if (showHeat) drawCeilingHeatmap();
  drawWarehouse();
  drawObstacles();
  drawBays(showLabels, showDims, showMargin);
  drawCeilingChart();
}}

function drawGrid() {{
  const ppu = viewScale;
  let sp = 1000;
  for (const t of [100,200,500,1000,2000,5000,10000]) {{ if (t*ppu>40) {{ sp=t; break; }} }}
  ctx.strokeStyle='rgba(99,102,241,0.06)'; ctx.lineWidth=0.5;
  const [lx,ly]=screenToWorld(0,H), [rx,ry]=screenToWorld(W,0);
  const sx0=Math.floor(lx/sp)*sp, sx1=Math.ceil(rx/sp)*sp;
  const sy0=Math.floor(ly/sp)*sp, sy1=Math.ceil(ry/sp)*sp;
  ctx.beginPath();
  for (let x=sx0;x<=sx1;x+=sp) {{ const[s]=worldToScreen(x,0); ctx.moveTo(s,0); ctx.lineTo(s,H); }}
  for (let y=sy0;y<=sy1;y+=sp) {{ const[,s]=worldToScreen(0,y); ctx.moveTo(0,s); ctx.lineTo(W,s); }}
  ctx.stroke();
  ctx.fillStyle='rgba(99,102,241,0.2)'; ctx.font='9px Inter,sans-serif';
  ctx.textAlign='center';
  for (let x=sx0;x<=sx1;x+=sp) {{ const[s]=worldToScreen(x,0); if(s>30&&s<W-30) ctx.fillText(x,s,H-4); }}
  ctx.textAlign='left';
  for (let y=sy0;y<=sy1;y+=sp) {{ const[,s]=worldToScreen(0,y); if(s>10&&s<H-10) ctx.fillText(y,4,s+3); }}
}}

// --- Ceiling heatmap: vertical bands colored by height ---
function drawCeilingHeatmap() {{
  const ceil = DATA.ceiling;
  if (ceil.length < 2) return;

  // Draw vertical strips across the warehouse X range
  const [sxL] = worldToScreen(whMinX, 0);
  const [sxR] = worldToScreen(whMaxX, 0);
  const [, syT] = worldToScreen(0, whMaxY);
  const [, syB] = worldToScreen(0, whMinY);
  const stripW = Math.max(1, (sxR - sxL) / 200);

  for (let sx = sxL; sx < sxR; sx += stripW) {{
    const [wx] = screenToWorld(sx, 0);
    const h = ceilAt(wx);
    ctx.fillStyle = ceilColor(h, ceilMin, ceilMax);
    ctx.fillRect(sx, syT, stripW + 1, syB - syT);
  }}

  // Draw vertical step transition lines at each ceiling breakpoint
  ctx.setLineDash([4,4]);
  ctx.lineWidth = 1;
  ctx.strokeStyle = 'rgba(251,191,36,0.3)';
  ctx.fillStyle = 'rgba(251,191,36,0.5)';
  ctx.font = '9px Inter,sans-serif';
  ctx.textAlign = 'center';
  for (let i = 0; i < ceil.length; i++) {{
    const [sx] = worldToScreen(ceil[i].x, 0);
    // Draw dashed vertical line at breakpoint
    ctx.beginPath();
    ctx.moveTo(sx, syT); ctx.lineTo(sx, syB);
    ctx.stroke();
    // Label with height value
    ctx.fillText(`${{ceil[i].h}}`, sx, syT - 4);
  }}
  ctx.setLineDash([]);
}}

function drawWarehouse() {{
  const wh = DATA.warehouse;
  if (wh.length < 3) return;
  ctx.beginPath();
  let [sx,sy] = worldToScreen(wh[0][0], wh[0][1]);
  ctx.moveTo(sx,sy);
  for (let i=1; i<wh.length; i++) {{ [sx,sy]=worldToScreen(wh[i][0],wh[i][1]); ctx.lineTo(sx,sy); }}
  ctx.closePath();
  ctx.fillStyle='rgba(99,102,241,0.03)'; ctx.fill();
  ctx.strokeStyle='rgba(99,102,241,0.5)'; ctx.lineWidth=2; ctx.stroke();
  ctx.fillStyle='#6366f1';
  for (const [x,y] of wh) {{ const[px,py]=worldToScreen(x,y); ctx.beginPath(); ctx.arc(px,py,3,0,Math.PI*2); ctx.fill(); }}
}}

function drawObstacles() {{
  for (const obs of DATA.obstacles) {{
    const[sx1,sy1]=worldToScreen(obs.x,obs.y+obs.d);
    const[sx2,sy2]=worldToScreen(obs.x+obs.w,obs.y);
    const sw=sx2-sx1, sh=sy2-sy1;
    ctx.fillStyle='rgba(239,68,68,0.15)'; ctx.fillRect(sx1,sy1,sw,sh);
    ctx.save(); ctx.beginPath(); ctx.rect(sx1,sy1,sw,sh); ctx.clip();
    ctx.strokeStyle='rgba(239,68,68,0.25)'; ctx.lineWidth=0.5;
    ctx.beginPath();
    for (let d=-Math.max(sw,sh); d<Math.max(sw,sh)*2; d+=8) {{
      ctx.moveTo(sx1+d,sy1); ctx.lineTo(sx1+d-sh,sy1+sh);
    }}
    ctx.stroke(); ctx.restore();
    ctx.strokeStyle='rgba(239,68,68,0.6)'; ctx.lineWidth=1.5; ctx.strokeRect(sx1,sy1,sw,sh);
    if (sw > 40 && sh > 20) {{
      ctx.fillStyle='rgba(239,68,68,0.7)'; ctx.font='10px Inter,sans-serif'; ctx.textAlign='center';
      ctx.fillText('OBSTACLE',sx1+sw/2,sy1+sh/2+4);
    }}
  }}
}}

function drawBays(showLabels, showDims, showMargin) {{
  for (let i=0; i<DATA.placed.length; i++) {{
    const b = DATA.placed[i];
    const color = typeColor(b.typeId);
    const isHov = i===hoveredBay;

    // Floor width x depth calculation for labels
    const [sx1, sy1]=worldToScreen(b.x1, b.y2);
    const [sx2, sy2]=worldToScreen(b.x2, b.y1);
    const sw=sx2-sx1, sh=sy2-sy1;

    // Gap danger zone 
    ctx.fillStyle = isHov ? 'rgba(251,191,36,0.28)' : 'rgba(251,191,36,0.12)';
    ctx.strokeStyle = 'rgba(251,191,36,0.45)';
    ctx.lineWidth = 0.5;
    ctx.setLineDash([3,3]);
    ctx.beginPath();
    let [gsx, gsy] = worldToScreen(b.gap_corners[0][0], b.gap_corners[0][1]);
    ctx.moveTo(gsx, gsy);
    for (let j = 1; j < 4; j++) {{
      let [nx, ny] = worldToScreen(b.gap_corners[j][0], b.gap_corners[j][1]);
      ctx.lineTo(nx, ny);
    }}
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);

    // Fill Bay Body
    ctx.fillStyle = color + hexAlpha(isHov?0.45:0.2);
    ctx.beginPath();
    let [px, py] = worldToScreen(b.corners[0][0], b.corners[0][1]);
    ctx.moveTo(px, py);
    for (let j = 1; j < 4; j++) {{
      let [nx, ny] = worldToScreen(b.corners[j][0], b.corners[j][1]);
      ctx.lineTo(nx, ny);
    }}
    ctx.closePath();
    ctx.fill();

    // Border
    ctx.strokeStyle = isHov ? color : color+'aa';
    ctx.lineWidth = isHov ? 2.5 : 1;
    if (isHov) {{ ctx.shadowColor=color; ctx.shadowBlur=12; ctx.stroke(); ctx.shadowBlur=0; }}
    ctx.stroke();

    // Ceiling margin indicator
    if (showMargin && sw > 6 && sh > 6) {{
      const mc = marginColor(b.ceilingMargin, b.height);
      ctx.fillStyle = mc;
      const barH = Math.max(2, Math.min(4, sh * 0.08));
      ctx.fillRect(sx1+1, Math.min(sy1, sy2)+1, sw-2, barH);
    }}

    // Labels context setup via transform
    if (sw > 18 && sh > 14) {{
      const fs = Math.min(12, Math.max(8, Math.min(sw,sh)*0.3));
      ctx.save();
      ctx.font=`${{fs}}px Inter,sans-serif`;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      
      const cx_world = (b.corners[0][0] + b.corners[2][0]) / 2;
      const cy_world = (b.corners[0][1] + b.corners[2][1]) / 2;
      let [scx, scy] = worldToScreen(cx_world, cy_world);
      
      ctx.translate(scx, scy);
      ctx.rotate(-b.rotation * Math.PI / 180);

      if (showLabels) {{
        ctx.fillStyle = isHov ? '#fff' : color+'dd';
        ctx.fillText(`T${{b.typeId}}`, 0, 0);
      }}
      if (showDims && sw>45 && sh>30) {{
        ctx.font=`${{Math.max(7,fs-2)}}px Inter,sans-serif`;
        ctx.fillStyle=color+'88';
        ctx.fillText(`${{b.width}}×${{b.depth}}`, 0, fs*0.75);
      }}
      if (isHov && sw > 30 && sh > 25) {{
        ctx.font=`${{Math.max(7,fs-2)}}px Inter,sans-serif`;
        const mc = marginColor(b.ceilingMargin, b.height);
        ctx.fillStyle = mc;
        ctx.fillText(`↕${{b.ceilingMargin.toFixed(0)}}`, 0, fs*1.5);
      }}
      ctx.restore();
    }}
  }}
}}

function hexAlpha(a) {{ return Math.round(a*255).toString(16).padStart(2,'0'); }}

// ============================
// CEILING CROSS-SECTION CHART
// ============================
function drawCeilingChart() {{
  const ceil = DATA.ceiling;
  if (ceil.length < 2) return;

  cCtx.clearRect(0,0,CW,CH);
  cCtx.fillStyle='#0d0f18'; cCtx.fillRect(0,0,CW,CH);

  const padL=50, padR=16, padT=20, padB=20;
  const pw=CW-padL-padR, ph=CH-padT-padB;

  // X range: match main view
  const [wxL] = screenToWorld(0,0);
  const [wxR] = screenToWorld(W,0);

  // Y range: ceiling heights
  let hMin = ceilMin - ceilRange*0.1;
  let hMax = ceilMax + ceilRange*0.15;

  function cx(x) {{ return padL + (x-wxL)/(wxR-wxL)*pw; }}
  function cy(h) {{ return padT + (1-(h-hMin)/(hMax-hMin))*ph; }}

  // Background gradient
  const grad = cCtx.createLinearGradient(0, padT, 0, padT+ph);
  grad.addColorStop(0, 'rgba(52,211,153,0.06)');
  grad.addColorStop(1, 'rgba(239,68,68,0.06)');
  cCtx.fillStyle = grad;
  cCtx.fillRect(padL, padT, pw, ph);

  // Y axis gridlines and labels
  const steps = [500, 1000, 2000, 5000];
  let yStep = 1000;
  for (const s of steps) {{ if ((hMax-hMin)/s <= 6) {{ yStep=s; break; }} }}

  cCtx.strokeStyle='rgba(99,102,241,0.1)'; cCtx.lineWidth=0.5;
  cCtx.fillStyle='rgba(99,102,241,0.4)'; cCtx.font='9px Inter,sans-serif'; cCtx.textAlign='right';
  for (let h=Math.ceil(hMin/yStep)*yStep; h<=hMax; h+=yStep) {{
    const y = cy(h);
    if (y < padT || y > padT+ph) continue;
    cCtx.beginPath(); cCtx.moveTo(padL,y); cCtx.lineTo(padL+pw,y); cCtx.stroke();
    cCtx.fillText(h,padL-6,y+3);
  }}

  // Draw bay height requirement lines (horizontal threshold lines)
  const thresholds = new Map();
  for (const tid in DATA.bayTypes) {{
    const bt = DATA.bayTypes[tid];
    thresholds.set(bt.height, tid);
  }}
  cCtx.setLineDash([3,3]);
  for (const [th, tid] of thresholds) {{
    const y = cy(th);
    if (y < padT-5 || y > padT+ph+5) continue;
    const col = typeColor(parseInt(tid));
    cCtx.strokeStyle = col+'66'; cCtx.lineWidth=1;
    cCtx.beginPath(); cCtx.moveTo(padL,y); cCtx.lineTo(padL+pw,y); cCtx.stroke();
    cCtx.fillStyle = col+'99'; cCtx.textAlign='left'; cCtx.font='8px Inter,sans-serif';
    cCtx.fillText(`h=${{th}} (T${{tid}})`, padL+pw+2, y+3);
  }}
  cCtx.setLineDash([]);

  // Draw ceiling fill (step function area)
  // Build step path: for each breakpoint, draw horizontal then vertical
  const visibleCeil = [];
  // Add a synthetic start point extending left
  visibleCeil.push({{x: wxL, h: ceilAt(wxL)}});
  for (const c of ceil) {{
    if (c.x > wxL && c.x < wxR) visibleCeil.push(c);
  }}
  // Add a synthetic end point extending right
  visibleCeil.push({{x: wxR, h: ceilAt(wxR)}});

  // Draw filled area under step function
  cCtx.beginPath();
  cCtx.moveTo(cx(visibleCeil[0].x), cy(0));
  cCtx.lineTo(cx(visibleCeil[0].x), cy(visibleCeil[0].h));
  for (let i = 1; i < visibleCeil.length; i++) {{
    // Horizontal line at previous height to this breakpoint
    cCtx.lineTo(cx(visibleCeil[i].x), cy(visibleCeil[i-1].h));
    // Vertical line to new height
    cCtx.lineTo(cx(visibleCeil[i].x), cy(visibleCeil[i].h));
  }}
  cCtx.lineTo(cx(visibleCeil[visibleCeil.length-1].x), cy(0));
  cCtx.closePath();

  const fillGrad = cCtx.createLinearGradient(0, padT, 0, padT+ph);
  fillGrad.addColorStop(0, 'rgba(251,191,36,0.15)');
  fillGrad.addColorStop(1, 'rgba(251,191,36,0.02)');
  cCtx.fillStyle = fillGrad;
  cCtx.fill();

  // Draw step ceiling line
  cCtx.beginPath();
  cCtx.moveTo(cx(visibleCeil[0].x), cy(visibleCeil[0].h));
  for (let i = 1; i < visibleCeil.length; i++) {{
    // Horizontal to breakpoint
    cCtx.lineTo(cx(visibleCeil[i].x), cy(visibleCeil[i-1].h));
    // Vertical to new height
    cCtx.lineTo(cx(visibleCeil[i].x), cy(visibleCeil[i].h));
  }}
  cCtx.strokeStyle='#fbbf24'; cCtx.lineWidth=2; cCtx.stroke();

  // Draw vertical transition dashes at breakpoints
  cCtx.setLineDash([3,3]);
  cCtx.strokeStyle='rgba(251,191,36,0.4)'; cCtx.lineWidth=1;
  for (let i = 1; i < visibleCeil.length - 1; i++) {{
    const px = cx(visibleCeil[i].x);
    // Dashed vertical line from floor to ceiling
    cCtx.beginPath();
    cCtx.moveTo(px, cy(0));
    cCtx.lineTo(px, cy(Math.max(visibleCeil[i-1].h, visibleCeil[i].h)));
    cCtx.stroke();
  }}
  cCtx.setLineDash([]);

  // Knot points and labels
  cCtx.fillStyle='#fbbf24';
  for (const c of ceil) {{
    const px=cx(c.x), py=cy(c.h);
    if (px < padL-5 || px > padL+pw+5) continue;
    cCtx.beginPath(); cCtx.arc(px,py,4,0,Math.PI*2); cCtx.fill();
    cCtx.fillStyle='#fbbf24'; cCtx.font='10px Inter,sans-serif'; cCtx.textAlign='center';
    cCtx.fillText(`${{c.h}}`, px, py-8);
    cCtx.fillStyle='rgba(251,191,36,0.5)'; cCtx.font='8px Inter,sans-serif';
    cCtx.fillText(`x=${{c.x}}`, px, py+14);
    cCtx.fillStyle='#fbbf24';
  }}

  // Mark placed bays as X-range indicators
  for (let i=0; i<DATA.placed.length; i++) {{
    const b = DATA.placed[i];
    const px1=cx(b.x1), px2=cx(b.x2);
    if (px2 < padL || px1 > padL+pw) continue;
    const bh = cy(b.height);
    const mc = marginColor(b.ceilingMargin, b.height);

    // Draw bay height bar
    cCtx.fillStyle = mc + '30';
    cCtx.fillRect(px1, bh, px2-px1, cy(0)-bh);

    // Bay top line
    cCtx.strokeStyle = mc + '80'; cCtx.lineWidth = 1;
    cCtx.beginPath(); cCtx.moveTo(px1,bh); cCtx.lineTo(px2,bh); cCtx.stroke();

    // Highlight hovered bay
    if (i === hoveredBay) {{
      cCtx.strokeStyle = '#fff'; cCtx.lineWidth = 2;
      cCtx.strokeRect(px1, bh, px2-px1, cy(0)-bh);
    }}
  }}

  // Title
  cCtx.fillStyle='rgba(251,191,36,0.7)'; cCtx.font='10px Inter,sans-serif'; cCtx.textAlign='left';
  cCtx.fillText('Ceiling Height Cross-Section (X axis)', padL, 12);
}}

// --- Interaction ---
function onWheel(e) {{
  e.preventDefault();
  const f = e.deltaY>0 ? 0.9 : 1.1;
  const[wx,wy]=screenToWorld(e.offsetX,e.offsetY);
  viewScale*=f;
  viewX=wx-(e.offsetX-W/2)/viewScale;
  viewY=wy+(e.offsetY-H/2)/viewScale;
  draw();
}}
function onMouseDown(e) {{ dragging=true; dragStartX=e.offsetX; dragStartY=e.offsetY; }}
function onMouseMove(e) {{
  if (dragging) {{
    viewX-=(e.offsetX-dragStartX)/viewScale;
    viewY+=(e.offsetY-dragStartY)/viewScale;
    dragStartX=e.offsetX; dragStartY=e.offsetY;
    draw(); return;
  }}
  const[wx,wy]=screenToWorld(e.offsetX,e.offsetY);
  let hit=-1;
  for (let i=DATA.placed.length-1; i>=0; i--) {{
    const b=DATA.placed[i];
    if (wx>=b.x1&&wx<=b.x2&&wy>=b.y1&&wy<=b.y2) {{ hit=i; break; }}
  }}
  if (hit!==hoveredBay) {{ hoveredBay=hit; draw(); }}
  if (hit>=0) showTooltip(e.offsetX,e.offsetY,DATA.placed[hit],hit);
  else tooltip.style.display='none';
}}
function onMouseUp() {{ dragging=false; }}

function showTooltip(mx,my,b,idx) {{
  const mc = marginColor(b.ceilingMargin, b.height);
  const pct = b.height > 0 ? (b.ceilingMargin / b.height * 100).toFixed(0) : '∞';
  const barPct = Math.max(0, Math.min(100, b.height > 0 ? (b.ceilingHeight / (b.height * 1.5)) * 100 : 100));
  tooltip.style.display='block';
  tooltip.innerHTML=`
    <div class="tooltip-title">Bay #${{idx+1}} — Type ${{b.typeId}}</div>
    <div class="tooltip-row"><span>Position</span><span>(${{b.x.toFixed(0)}}, ${{b.y.toFixed(0)}})</span></div>
    <div class="tooltip-row"><span>Rotation</span><span>${{b.rotation}}°</span></div>
    <div class="tooltip-row"><span>Footprint</span><span>${{b.w}} × ${{b.d}}</span></div>
    <div class="tooltip-row"><span>Loads / Price</span><span>${{b.nLoads}} / ${{b.price}}</span></div>
    <div class="tooltip-row"><span>Efficiency</span><span>${{b.efficiency.toFixed(1)}}</span></div>
    <div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08)">
      <div class="tooltip-row"><span>Bay height</span><span>${{b.height}}</span></div>
      <div class="tooltip-row"><span>Ceiling at pos</span><span>${{b.ceilingHeight.toFixed(0)}}</span></div>
      <div class="tooltip-row"><span>Margin</span><span style="color:${{mc}};font-weight:700">${{b.ceilingMargin.toFixed(0)}} (${{pct}}%)</span></div>
      <div class="tooltip-bar"><div class="tooltip-bar-fill" style="width:${{barPct}}%;background:${{mc}}"></div></div>
      <div class="tooltip-bar-label">Ceiling clearance</div>
    </div>`;
  let tx=mx+16, ty=my-10;
  if (tx+240>W) tx=mx-250;
  if (ty+260>H) ty=my-260;
  if (ty<0) ty=4;
  tooltip.style.left=tx+'px'; tooltip.style.top=ty+'px';
}}

// --- UI ---
function populateStats() {{
  document.getElementById('stat-q').textContent=formatN(DATA.quality);
  document.getElementById('stat-bays').textContent=DATA.totalBays;
  document.getElementById('stat-coverage').textContent=DATA.coveragePercent.toFixed(1)+'%';
  document.getElementById('stat-area').textContent=formatN(DATA.warehouseArea);
}}
function formatN(n) {{
  if (n>=1e9) return (n/1e9).toFixed(2)+'B';
  if (n>=1e6) return (n/1e6).toFixed(2)+'M';
  if (n>=1e3) return (n/1e3).toFixed(1)+'K';
  return n.toFixed(0);
}}

function populateLegend() {{
  const lg=document.getElementById('legend');
  const used=new Set(DATA.placed.map(b=>b.typeId));
  const sorted=[...used].sort((a,b)=>a-b);
  lg.innerHTML=`
    <div class="legend-item"><div class="legend-swatch" style="background:rgba(99,102,241,0.5);border:1px solid #6366f1"></div>Warehouse</div>
    <div class="legend-item"><div class="legend-swatch" style="background:rgba(239,68,68,0.3);border:1px solid rgba(239,68,68,0.6)"></div>Obstacles</div>`;
  for (const tid of sorted) {{
    const bt=DATA.bayTypes[tid], c=typeColor(tid);
    const cnt=DATA.placed.filter(b=>b.typeId===tid).length;
    lg.innerHTML+=`<div class="legend-item"><div class="legend-swatch" style="background:${{c}}40;border:1px solid ${{c}}"></div>T${{tid}} (${{bt.width}}×${{bt.depth}}) ×${{cnt}}</div>`;
  }}
}}

function populateCeilingLegend() {{
  const cl = document.getElementById('ceilingLegend');
  cl.innerHTML = `
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
      <div style="width:60px;height:10px;border-radius:3px;background:linear-gradient(90deg,
        rgba(255,60,60,0.3),rgba(255,180,60,0.3),rgba(52,211,153,0.3))"></div>
      <span style="font-size:10px;color:#6b7280">Low → High ceiling</span>
    </div>
    <div style="font-size:10px;color:#6b7280;margin-bottom:4px">
      Range: ${{ceilMin}} – ${{ceilMax}}
    </div>
    <div style="font-size:10px;color:#6b7280;line-height:1.6">
      Margin indicator:
      <span style="color:#4ade80">●</span> Comfy (>30%)
      <span style="color:#fbbf24">●</span> OK (10-30%)
      <span style="color:#fb923c">●</span> Tight (<10%)
      <span style="color:#ef4444">●</span> None
    </div>`;
}}

function populateBayList() {{
  document.getElementById('bayCount').textContent=DATA.totalBays;
  const list=document.getElementById('bayList');
  list.innerHTML='';
  for (let i=0; i<DATA.placed.length; i++) {{
    const b=DATA.placed[i];
    const mc = marginColor(b.ceilingMargin, b.height);
    const div=document.createElement('div');
    div.className='bay-list-item';
    div.innerHTML=`
      <span style="color:${{typeColor(b.typeId)}}">T${{b.typeId}}</span>
      <span>(${{b.x.toFixed(0)}},${{b.y.toFixed(0)}}) ${{b.rotation}}°</span>
      <span class="margin-dot" style="background:${{mc}}" title="Ceiling margin: ${{b.ceilingMargin.toFixed(0)}}"></span>`;
    div.addEventListener('mouseenter', ()=>{{ hoveredBay=i; draw(); }});
    div.addEventListener('mouseleave', ()=>{{ hoveredBay=-1; draw(); }});
    div.addEventListener('click', ()=>{{
      viewX=(b.x1+b.x2)/2; viewY=(b.y1+b.y2)/2;
      viewScale=Math.min(W,H)/(Math.max(b.w,b.d)*4);
      draw();
    }});
    list.appendChild(div);
  }}
}}

function zoomIn() {{ viewScale*=1.3; draw(); }}
function zoomOut() {{ viewScale/=1.3; draw(); }}
function resetView() {{ fitView(); draw(); }}

init();
</script>
</body>
</html>'''


if __name__ == '__main__':
    main()
