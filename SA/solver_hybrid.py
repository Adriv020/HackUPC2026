#!/usr/bin/env python3
import sys
import subprocess
import threading
import time
import os
import shutil

global_best_q = float('inf')
global_last_temp = 0.0
global_last_cur_q = float('inf')
global_start_time = time.time()
metrics_lock = threading.Lock()

def monitor_process(proc, name, out_csv_tmp, result_dict):
    global global_best_q, global_last_temp, global_last_cur_q
    best_q_local = float('inf')
    
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("[METRIC]"):
            parts = line[8:].split(',')
            if len(parts) >= 5 and parts[0] != 'FINAL':
                try:
                    temp  = float(parts[2])
                    cur_q = float(parts[3])
                    q     = float(parts[4])
                    best_q_local = min(best_q_local, q)
                    with metrics_lock:
                        if q < global_best_q:
                            global_best_q = q
                        global_last_temp  = temp
                        global_last_cur_q = cur_q
                except ValueError:
                    pass
        else:
            print(f"[{name}] {line}", file=sys.stderr, flush=True)
            
    proc.wait()
    result_dict[name] = {'q': best_q_local, 'file': out_csv_tmp}

def main():
    if len(sys.argv) < 6:
        print("Usage: python solver_hybrid.py <warehouse> <obstacles> <ceiling> <types_of_bays> <output>")
        sys.exit(1)

    args = sys.argv[1:5]
    final_out = sys.argv[5]

    solvers = {
        'Ortho': 'solver.py',
        'SAT': 'solver_flex.py'
    }

    procs = {}
    threads = []
    results = {}
    
    pid = os.getpid()
    
    for name, script in solvers.items():
        tmp_out = f"{final_out}_{name.lower()}_{pid}.tmp.csv"
        if script.endswith('.py'):
            cmd = ["python3", "-u", script] + args + [tmp_out]
        else:
            cmd = [script] + args + [tmp_out]
        
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            procs[name] = proc
            t = threading.Thread(target=monitor_process, args=(proc, name, tmp_out, results))
            t.start()
            threads.append(t)
        except Exception as e:
            print(f"[{name}] Failed to start: {e}", file=sys.stderr)

    # Main loop to emit unified metrics
    running = True
    iters = 0
    while running:
        running = any(t.is_alive() for t in threads)
        time.sleep(0.1)
        iters += 10
        with metrics_lock:
            q_to_report    = global_best_q   if global_best_q   != float('inf') else 0.0
            cur_q_to_report = global_last_cur_q if global_last_cur_q != float('inf') else q_to_report
            temp_to_report = global_last_temp
            print(f"[METRIC] {iters},{time.time() - global_start_time:.3f},{temp_to_report:.2f},{cur_q_to_report:.2f},{q_to_report:.2f}", flush=True)

    for t in threads:
        t.join()

    # Determine winner
    best_name = None
    best_q = float('inf')
    for name, res in results.items():
        if res['q'] < best_q and os.path.exists(res['file']):
            best_q = res['q']
            best_name = name

    if best_name:
        print(f"Hybrid Winner: {best_name} with Q={best_q:.2f}", file=sys.stderr)
        shutil.copy2(results[best_name]['file'], final_out)
    else:
        print("Hybrid Failed: No valid output found.", file=sys.stderr)

    # Cleanup
    for name, res in results.items():
        if os.path.exists(res['file']):
            try:
                os.remove(res['file'])
            except:
                pass

if __name__ == '__main__':
    main()
