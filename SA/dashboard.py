#!/usr/bin/env python3
"""
Dashboard server for the Mecalux Warehouse Bay Placement challenge.
Runs a local web server to manage training (solving), validating, and visualizing cases.
"""

import sys
import os
import json
import subprocess
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
import threading
from csv_to_world import build_world_response

PORT = 8000
PUBLIC_CASES_DIR = "../PublicTestCases"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Warehouse App Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
  
  * { margin: 0; padding: 0; box-sizing: border-box; }
  
  body {
    font-family: 'Inter', sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  .header {
    background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
    border-bottom: 1px solid rgba(99, 102, 241, 0.2);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  
  .header h1 {
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #818cf8, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  
  .main {
    display: flex;
    flex: 1;
    min-height: 0;
    position: relative;
  }
  
  .sidebar {
    width: 260px;
    background: #13151f;
    border-right: 1px solid rgba(99, 102, 241, 0.15);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  
  .sidebar-header {
    padding: 16px;
    font-size: 13px;
    font-weight: 600;
    color: #818cf8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  }
  
  .case-list {
    overflow-y: auto;
    flex: 1;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  
  .case-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    color: #9ca3af;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .case-item:hover {
    background: rgba(99, 102, 241, 0.1);
    color: #e0e0e0;
  }
  
  .case-item.active {
    background: rgba(99, 102, 241, 0.2);
    color: #818cf8;
    font-weight: 500;
    border-left: 3px solid #6366f1;
  }
  
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 24px;
    gap: 20px;
    overflow: hidden;
  }
  
  .actions {
    display: flex;
    gap: 12px;
  }
  
  .btn {
    padding: 10px 20px;
    border-radius: 6px;
    border: none;
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
    outline: none;
  }
  
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .btn-solve {
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
  }
  
  .btn-solve:hover:not(:disabled) {
    box-shadow: 0 0 15px rgba(16, 185, 129, 0.3);
  }
  
  .btn-validate {
    background: linear-gradient(135deg, #6366f1, #4f46e5);
    color: white;
  }
  
  .btn-validate:hover:not(:disabled) {
    box-shadow: 0 0 15px rgba(99, 102, 241, 0.3);
  }
  
  .btn-visualize {
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: white;
  }
  
  .btn-visualize:hover:not(:disabled) {
    box-shadow: 0 0 15px rgba(245, 158, 11, 0.3);
  }
  
  .btn-3d {
    background: linear-gradient(135deg, #e8621a, #b84d10);
    color: white;
  }

  .btn-3d:hover:not(:disabled) {
    box-shadow: 0 0 15px rgba(232, 98, 26, 0.4);
  }

  .viewer-overlay {
    display: none;
    position: absolute;
    inset: 0;
    z-index: 50;
    flex-direction: column;
    background: #0f1117;
  }

  .viewer-overlay.active {
    display: flex;
  }

  .viewer-topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: #13151f;
    border-bottom: 1px solid rgba(232, 98, 26, 0.3);
    flex-shrink: 0;
  }

  .viewer-topbar span {
    font-size: 14px;
    color: #9ca3af;
  }

  .viewer-frame {
    flex: 1;
    border: none;
    width: 100%;
  }
  
  .console-panel {
    flex: 1;
    background: #0a0c14;
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  
  .console-header {
    background: #13151f;
    padding: 10px 16px;
    font-size: 12px;
    color: #6b7280;
    border-bottom: 1px solid rgba(99, 102, 241, 0.1);
    display: flex;
    justify-content: space-between;
  }
  
  pre {
    flex: 1;
    padding: 16px;
    margin: 0;
    overflow-y: auto;
    font-family: 'Fira Code', monospace;
    font-size: 13px;
    line-height: 1.5;
    color: #a5b4fc;
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .loading {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 1s ease-in-out infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .badge {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 12px;
    background: rgba(99, 102, 241, 0.2);
    color: #818cf8;
  }
  
  .graph-panel {
    background: #0a0c14;
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 8px;
    display: none;
    flex-direction: column;
    margin-top: 16px;
    padding: 16px;
    height: 350px;
  }
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>

<div class="header">
  <h1>🏭 Mecalux SA Dashboard</h1>
  <div style="font-size: 13px; color: #6b7280;">Run on local Python server</div>
</div>

<div class="main">
  <div class="sidebar">
    <div class="sidebar-header">Test Cases</div>
    <div class="case-list" id="caseList">
      <!-- Populated via JS -->
    </div>
  </div>
  
  <div class="content">
    <div style="display: flex; justify-content: space-between; align-items: flex-end;">
      <div style="display: flex; gap: 24px;">
        <div>
          <h2 id="currentCaseName" style="color: #e0e0e0; margin-bottom: 6px;">Select a Case</h2>
          <div style="font-size: 13px; color: #9ca3af;">Manage training, validation, and visualization</div>
        </div>
        <div style="display: flex; flex-direction: column; justify-content: flex-end;">
          <label for="modelSelect" style="font-size: 12px; color: #9ca3af; margin-bottom: 4px;">Solver Engine:</label>
          <select id="modelSelect" style="background: #13151f; color: #e0e0e0; border: 1px solid rgba(99, 102, 241, 0.3); padding: 6px 10px; border-radius: 4px; outline: none; font-family: inherit; font-size: 13px; cursor: pointer;">
            <option value="solver.py">Orthogonal (solver.py)</option>
            <option value="solver_flex">Continuous SAT C++ (solver_flex)</option>
            <option value="solver_flex.py">Continuous SAT (solver_flex.py)</option>
            <option value="solver_hybrid.py">Hybrid (Ortho + SAT) (solver_hybrid.py)</option>
            <option value="solver_ensemble.py">Ensemble All-Cores (solver_ensemble.py)</option>

          </select>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-solve" id="btnSolve" disabled onclick="runSolve()">
          <span>⚡</span> <span id="lblSolve">Train (Solve)</span>
        </button>
        <button class="btn btn-validate" id="btnValidate" disabled onclick="runValidate()">
          <span>✓</span> <span id="lblValidate">Validate</span>
        </button>
        <button class="btn btn-visualize" id="btnVisualize" disabled onclick="runVisualize()">
          <span>👁</span> <span id="lblVisualize">Visualize</span>
        </button>
        <button class="btn btn-3d" id="btn3D" disabled onclick="run3DView()">
          <span>🧊</span> <span id="lbl3D">3D View</span>
        </button>
      </div>
    </div>
    
    <div class="console-panel">
      <div class="console-header">
        <span id="consoleStatus">Console Output</span>
        <div style="display: flex; gap: 16px; align-items: center;">
            <label style="cursor: pointer; display: flex; align-items: center; gap: 4px; color: #a5b4fc;">
                <input type="checkbox" id="showGraph" checked> Show Optimization Graph
            </label>
            <span id="btnCls" style="cursor: pointer; opacity: 0.7;" onclick="document.getElementById('console').textContent=''">Clear</span>
        </div>
      </div>
      <pre id="console"></pre>
    </div>
    
    <div class="graph-panel" id="graphPanel">
        <canvas id="saChart"></canvas>
    </div>
  </div>

  <!-- 3D Viewer overlay (covers the whole .main area) -->
  <div class="viewer-overlay" id="viewerOverlay">
    <div class="viewer-topbar">
      <button class="btn btn-3d" style="padding:6px 14px; font-size:13px;" onclick="closeViewer()">
        ← Back
      </button>
      <span id="viewerLabel">3D View</span>
    </div>
    <iframe class="viewer-frame" id="viewerFrame" src="about:blank"></iframe>
  </div>
</div>

<script>
let currentCase = null;
let eventSource = null;
let saChart = null;
let chartLabels = [];
let chartQData = [];
let chartBestQData = [];
let chartTempData = [];

function initChart() {
    if (saChart) {
        saChart.destroy();
    }
    chartLabels = [];
    chartQData = [];
    chartBestQData = [];
    chartTempData = [];
    
    const ctx = document.getElementById('saChart').getContext('2d');
    saChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [
                {
                    label: 'Current Q',
                    data: chartQData,
                    borderColor: 'rgba(99, 102, 241, 0.5)',
                    borderWidth: 1,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'Best Q',
                    data: chartBestQData,
                    borderColor: '#10b981',
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'Temperature',
                    data: chartTempData,
                    borderColor: '#ef4444',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { title: { display: true, text: 'Iterations / Time' } },
                y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Q-Score' } },
                y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Temperature' } }
            }
        }
    });
}

async function loadCases() {
  try {
    const res = await fetch('/api/cases');
    const cases = await res.json();
    
    const list = document.getElementById('caseList');
    list.innerHTML = '';
    
    cases.forEach(name => {
      const div = document.createElement('div');
      div.className = 'case-item';
      div.innerHTML = `📁 ${name}`;
      div.onclick = () => selectCase(name, div);
      list.appendChild(div);
    });
    
    if (cases.length > 0) {
      selectCase(cases[0], list.children[0]);
    }
  } catch (err) {
    appendConsole(`Error loading cases: ${err}\\n`, 'red');
  }
}

function selectCase(name, el) {
  document.querySelectorAll('.case-item').forEach(d => d.classList.remove('active'));
  if (el) el.classList.add('active');
  
  currentCase = name;
  document.getElementById('currentCaseName').textContent = name;
  document.getElementById('btnSolve').disabled = false;
  document.getElementById('btnValidate').disabled = false;
  document.getElementById('btnVisualize').disabled = false;
  document.getElementById('btn3D').disabled = false;
  
  if (eventSource) {
    eventSource.close();
    eventSource = null;
    resetButtons();
  }
}

function appendConsole(text, color) {
  const c = document.getElementById('console');
  const span = document.createElement('span');
  if (color) span.style.color = color;
  span.textContent = text;
  c.appendChild(span);
  c.scrollTop = c.scrollHeight;
}

function resetButtons() {
  document.getElementById('btnSolve').disabled = false;
  document.getElementById('lblSolve').innerHTML = 'Train (Solve)';
  document.getElementById('btnValidate').disabled = false;
  document.getElementById('lblValidate').innerHTML = 'Validate';
  document.getElementById('btnVisualize').disabled = false;
  if (currentCase) document.getElementById('btn3D').disabled = false;
  document.getElementById('lbl3D').innerHTML = '3D View';
  document.getElementById('consoleStatus').textContent = 'Console Output';
}

function runSolve() {
  if (!currentCase) return;
  
  if (eventSource) eventSource.close();
  
  document.getElementById('console').textContent = '';
  document.getElementById('btnSolve').disabled = true;
  document.getElementById('lblSolve').innerHTML = '<span class="loading"></span> Solving...';
  document.getElementById('btnValidate').disabled = true;
  document.getElementById('btnVisualize').disabled = true;
  document.getElementById('consoleStatus').textContent = `Running Simulated Annealing on ${currentCase}...`;
  
  const selectedModel = document.getElementById('modelSelect').value;
  const showGraph = document.getElementById('showGraph').checked;
  const graphPanel = document.getElementById('graphPanel');
  
  if (showGraph) {
      graphPanel.style.display = 'flex';
      initChart();
  } else {
      graphPanel.style.display = 'none';
  }

  eventSource = new EventSource(`/api/solve?case=${currentCase}&model=${selectedModel}`);
  
  eventSource.onmessage = function(e) {
    if (e.data === 'DONE') {
      eventSource.close();
      eventSource = null;
      resetButtons();
      appendConsole('\\n✓ Process completed.\\n', '#10b981');
    } else if (e.data.startsWith('[METRIC]')) {
      if (saChart) {
          // Format expected: [METRIC] iters,elapsed,T,cur_q,best_q
          const parts = e.data.substring(8).trim().split(',');
          if (parts.length >= 5) {
              const elapsed = parseFloat(parts[1]);
              const temp    = parseFloat(parts[2]);
              const curQ    = parseFloat(parts[3]);
              const bestQ   = parseFloat(parts[4]);
              // Guard: skip any point with NaN fields (e.g. if 'FINAL' ever slips through)
              if (!isNaN(elapsed) && !isNaN(temp) && !isNaN(curQ) && !isNaN(bestQ)) {
                  chartLabels.push(elapsed.toFixed(1) + 's');
                  chartTempData.push(temp);
                  chartQData.push(curQ);
                  chartBestQData.push(bestQ);
                  saChart.update();
              }
          }
      }
    } else {
      appendConsole(e.data + '\\n');
    }
  };
  
  eventSource.onerror = function() {
    eventSource.close();
    eventSource = null;
    resetButtons();
    appendConsole('\\nConnection lost or process crashed.\\n', '#ef4444');
  };
}

async function runValidate() {
  if (!currentCase) return;
  
  document.getElementById('btnValidate').disabled = true;
  document.getElementById('lblValidate').innerHTML = '<span class="loading"></span> Validating...';
  document.getElementById('btnSolve').disabled = true;
  document.getElementById('btnVisualize').disabled = true;
  document.getElementById('consoleStatus').textContent = `Validating output for ${currentCase}...`;
  document.getElementById('console').textContent = '';
  
  try {
    const res = await fetch(`/api/validate?case=${currentCase}`);
    const text = await res.text();
    appendConsole(text);
  } catch (err) {
    appendConsole(`Error: ${err}\\n`, '#ef4444');
  } finally {
    resetButtons();
  }
}

async function runVisualize() {
  if (!currentCase) return;
  
  document.getElementById('btnVisualize').disabled = true;
  document.getElementById('lblVisualize').innerHTML = '<span class="loading"></span> Opening...';
  
  try {
    // This endpoint runs visualize.py which automatically spawns the browser
    const res = await fetch(`/api/visualize?case=${currentCase}`);
    const text = await res.text();
    appendConsole(`Visualizer generated: ${text}\\n`);
    appendConsole('Browser tab should open automatically.\\n');
  } catch (err) {
    appendConsole(`Error: ${err}\\n`, '#ef4444');
  } finally {
    resetButtons();
  }
}

function run3DView() {
  if (!currentCase) return;

  document.getElementById('viewerLabel').textContent = `3D View — ${currentCase}`;
  document.getElementById('viewerFrame').src = `http://localhost:3000/warehouse?preload=${encodeURIComponent(currentCase)}`;
  document.getElementById('viewerOverlay').classList.add('active');
}

function closeViewer() {
  document.getElementById('viewerOverlay').classList.remove('active');
  // Blank the iframe so the Next.js app unmounts cleanly
  document.getElementById('viewerFrame').src = 'about:blank';
}

// Init
window.onload = loadCases;
</script>
</body>
</html>
"""

class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Prevent caching for dynamic requests
        if self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
            return

        if path == '/api/cases':
            cases = []
            if os.path.exists(PUBLIC_CASES_DIR):
                cases = [d for d in os.listdir(PUBLIC_CASES_DIR) if os.path.isdir(os.path.join(PUBLIC_CASES_DIR, d)) and d.startswith('Case')]
                # Sort logically (Case0, Case1, Case2, ...)
                cases.sort(key=lambda x: int(x.replace('Case', '')) if x.replace('Case', '').isdigit() else x)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(cases).encode('utf-8'))
            return

        if path == '/api/solve':
            case_name = query.get('case', [''])[0]
            model_name = query.get('model', ['solver.py'])[0]
            if model_name not in ['solver.py', 'solver_flex.py', 'solver_hybrid.py', 'solver_ensemble.py']:
                model_name = 'solver.py'
            if not case_name:
                self.send_response(400)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            p_wh = os.path.join(PUBLIC_CASES_DIR, case_name, 'warehouse.csv')
            p_obs = os.path.join(PUBLIC_CASES_DIR, case_name, 'obstacles.csv')
            p_ceil = os.path.join(PUBLIC_CASES_DIR, case_name, 'ceiling.csv')
            p_bays = os.path.join(PUBLIC_CASES_DIR, case_name, 'types_of_bays.csv')
            out_csv = f"output_{case_name.lower()}.csv"

            # Use unbuffered output (-u) for real-time streaming
            # Dynamic execution based on extension
            if model_name.endswith('.py'):
                cmd = ["python3", "-u", model_name, p_wh, p_obs, p_ceil, p_bays, out_csv]
            else:
                cmd = [f"./{model_name}", p_wh, p_obs, p_ceil, p_bays, out_csv]     
                   
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:
                    # Escape newlines for SSE format
                    safe_line = line.replace('\\n', '').replace('\\r', '')
                    self.wfile.write(f"data: {safe_line}\n\n".encode('utf-8'))
                    self.wfile.flush()
                proc.wait()
                self.wfile.write(b"data: DONE\n\n")
                self.wfile.flush()
            except broken_pipe_error_classes():
                # Client disconnected
                if 'proc' in locals():
                    proc.kill()
            except Exception as e:
                if 'proc' in locals():
                    proc.kill()
            return
            
        if path == '/api/validate':
            case_name = query.get('case', [''])[0]
            if not case_name:
                self.send_response(400)
                self.end_headers()
                return
            
            p_wh = os.path.join(PUBLIC_CASES_DIR, case_name, 'warehouse.csv')
            p_obs = os.path.join(PUBLIC_CASES_DIR, case_name, 'obstacles.csv')
            p_ceil = os.path.join(PUBLIC_CASES_DIR, case_name, 'ceiling.csv')
            p_bays = os.path.join(PUBLIC_CASES_DIR, case_name, 'types_of_bays.csv')
            out_csv = f"output_{case_name.lower()}.csv"

            if not os.path.exists(out_csv):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(f"Error: Solution file {out_csv} not found.\nPlease run Train (Solve) first.".encode('utf-8'))
                return

            cmd = ["python3", "validator.py", p_wh, p_obs, p_ceil, p_bays, out_csv]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(proc.stdout.encode('utf-8'))
            return
            
        if path == '/api/visualize':
            case_name = query.get('case', [''])[0]
            if not case_name:
                self.send_response(400)
                self.end_headers()
                return
            
            p_wh = os.path.join(PUBLIC_CASES_DIR, case_name, 'warehouse.csv')
            p_obs = os.path.join(PUBLIC_CASES_DIR, case_name, 'obstacles.csv')
            p_ceil = os.path.join(PUBLIC_CASES_DIR, case_name, 'ceiling.csv')
            p_bays = os.path.join(PUBLIC_CASES_DIR, case_name, 'types_of_bays.csv')
            out_csv = f"output_{case_name.lower()}.csv"
            out_html = f"viz_{case_name.lower()}.html"

            if not os.path.exists(out_csv):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(f"Error: Solution file {out_csv} not found.\nPlease run Train (Solve) first.".encode('utf-8'))
                return

            cmd = ["python3", "visualize.py", p_wh, p_obs, p_ceil, p_bays, out_csv, out_html]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(out_html.encode('utf-8'))
            return

        if path == '/api/3dview':
            case_name = query.get('case', [''])[0]
            if not case_name:
                self.send_response(400)
                self.end_headers()
                return

            p_wh   = os.path.join(PUBLIC_CASES_DIR, case_name, 'warehouse.csv')
            p_obs  = os.path.join(PUBLIC_CASES_DIR, case_name, 'obstacles.csv')
            p_ceil = os.path.join(PUBLIC_CASES_DIR, case_name, 'ceiling.csv')
            p_bays = os.path.join(PUBLIC_CASES_DIR, case_name, 'types_of_bays.csv')
            out_csv = f"output_{case_name.lower()}.csv"

            if not os.path.exists(out_csv):
                self.send_response(400)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(
                    f"Solution file {out_csv} not found. Please run Train (Solve) first.".encode('utf-8')
                )
                return

            try:
                world = build_world_response(p_wh, p_obs, p_ceil, p_bays, out_csv)
                payload = json.dumps(world).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self.send_response(500)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(str(exc).encode('utf-8'))
            return

        # Fallback to SimpleHTTPRequestHandler for serving static files
        return super().do_GET()

def broken_pipe_error_classes():
    try:
        return (BrokenPipeError, ConnectionResetError)
    except NameError:
        return Exception

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"Dashboard server running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    
    # Automatically open browser
    def open_browser():
        webbrowser.open(f"http://localhost:{PORT}")
        
    threading.Timer(0.5, open_browser).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()
        sys.exit(0)

if __name__ == '__main__':
    run_server()
