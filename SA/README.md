# Warehouse Bay Placement Solver (Simulated Annealing)

**HackUPC 2026 – Mecalux Challenge**

## Quick Start

### Solve a case

```bash
# Case 0 (L-shaped warehouse, 3 obstacles)
python3 solver.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv

# Case 1 (square, no obstacles)
python3 solver.py ../PublicTestCases/Case1/warehouse.csv ../PublicTestCases/Case1/obstacles.csv ../PublicTestCases/Case1/ceiling.csv ../PublicTestCases/Case1/types_of_bays.csv output_case1.csv

# Case 3 (plus-shaped, complex)
python3 solver.py ../PublicTestCases/Case3/warehouse.csv ../PublicTestCases/Case3/obstacles.csv ../PublicTestCases/Case3/ceiling.csv ../PublicTestCases/Case3/types_of_bays.csv output_case3.csv
```

### Validate a solution

```bash
# Validate Case 0 output
python3 validator.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv

# Validate Case 3 output
python3 validator.py ../PublicTestCases/Case3/warehouse.csv ../PublicTestCases/Case3/obstacles.csv ../PublicTestCases/Case3/ceiling.csv ../PublicTestCases/Case3/types_of_bays.csv output_case3.csv
```

### Visualize a solution (opens in browser)

```bash
# Visualize Case 0 → opens viz_case0.html
python3 visualize.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv viz_case0.html

# Visualize Case 3
python3 visualize.py ../PublicTestCases/Case3/warehouse.csv ../PublicTestCases/Case3/obstacles.csv ../PublicTestCases/Case3/ceiling.csv ../PublicTestCases/Case3/types_of_bays.csv output_case3.csv viz_case3.html
```

### Convenience scripts

```bash
bash run.sh 0              # Solve Case 0 → output_case0.csv
bash run.sh 2 my.csv       # Solve Case 2 → my.csv
bash run_all.sh            # Solve all 4 cases sequentially
```

### Full pipeline (solve → validate → visualize)

```bash
# Solve, then validate, then visualize Case 0
python3 solver.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv
python3 validator.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv
python3 visualize.py ../PublicTestCases/Case0/warehouse.csv ../PublicTestCases/Case0/obstacles.csv ../PublicTestCases/Case0/ceiling.csv ../PublicTestCases/Case0/types_of_bays.csv output_case0.csv viz_case0.html
```

## Files

| File | Description |
|------|-------------|
| `solver.py` | SA solver (~770 lines) — greedy init + simulated annealing |
| `validator.py` | Standalone constraint checker with Q score calculation |
| `visualize.py` | Generates interactive HTML visualization (zero dependencies) |
| `run.sh` | Run solver on a single case |
| `run_all.sh` | Run solver on all test cases |

## Algorithm Overview

### Phase 1: Greedy Strip Packing (~40% of time budget)

1. **Sort bay types** by efficiency (`Price/nLoads`, ascending = best first)
2. **Strip packing**: Scan row-by-row, place bays left-to-right with 50-unit step
3. **Candidate filling**: Collect X/Y coords from placed bay corners, retry placement at these intersection points (up to 5 passes)

### Phase 2: Simulated Annealing (~60% of time budget)

| Move | Prob | Description |
|------|------|-------------|
| Add | 50% | Place a new bay (adjacent to existing → random → base coords) |
| Remove | 8% | Remove a random bay |
| Move | 27% | Relocate a bay (adjacent-based or ±1000 perturbation) |
| Swap | 15% | Change a bay's type at same position |

- **Cooling**: Geometric (α=0.99997), reheat after 20k moves without improvement
- **Bay type selection**: Weighted by `nLoads/Price` (most efficient preferred)
- **All moves maintain feasibility** — rejected moves undone in O(1)

## Constraints Enforced

| Constraint | Method |
|------------|--------|
| Warehouse containment | Slab decomposition of axis-aligned polygon |
| Obstacle avoidance | Spatial grid query + strict rect overlap (touching OK) |
| Bay-bay non-overlap | Same spatial grid + strict overlap check |
| Ceiling height | **Step function** — each `(x, h)` defines constant height from x onward |
| Rotation | Only 0°, 90°, 180°, 270° |

### Ceiling Model

The ceiling is a **step function** (piecewise constant), not linearly interpolated. Each `(Coord X, Height)` entry defines the ceiling height from that X coordinate until the next breakpoint:

```
Input: (0, 3000), (3000, 2000), (6000, 3000)

Height: 3000 ─────┐
                   │ 2000 ─────┐
                   └───────────┘ 3000 ──────
        0        3000        6000
```

## Quality Formula

```
Q = (Σ Price/nLoads)^(2-(Σ Width×Depth / Area_warehouse))
```

## Performance Optimizations

- **Spatial grid**: O(1) amortized overlap queries
- **Slab decomposition**: Axis-aligned polygon containment in O(slabs)
- **Incremental Q**: Running sums, no recomputation
- **Tuple-based data**: Tuples + `__slots__` instead of objects
- **Integer snapping**: Random positions snapped to int to avoid FP issues

## Validator

The validator (`validator.py`) independently checks a solution against all constraints:

```bash
python3 validator.py ../PublicTestCases/Case0/warehouse.csv \
  ../PublicTestCases/Case0/obstacles.csv \
  ../PublicTestCases/Case0/ceiling.csv \
  ../PublicTestCases/Case0/types_of_bays.csv \
  output_case0.csv
```

**Output example:**
```
VALIDATION REPORT
=================
Input files:
  warehouse.csv: OK (6 points)
  obstacles.csv: OK (3 obstacles)
  ceiling.csv:   OK (3 points)
  bays.csv:      OK (6 types)
  solution.csv:  OK (36 bays placed)

Checking constraints...
  All bays inside warehouse: PASS
  No bay overlaps obstacles: PASS
  No bays overlap each other: PASS
  Ceiling constraints satisfied: PASS

STATUS: VALID
  Quality score Q = 263373281.26
  Bays placed = 36
```

Exit code: `0` = valid, `1` = invalid.

## Visualizer

The visualizer (`visualize.py`) generates a standalone HTML file with:

- **Interactive canvas**: Pan (drag), zoom (scroll), hover tooltips
- **Ceiling heatmap**: Color-coded overlay (red=low, green=high) with step transitions
- **Cross-section chart**: Bottom panel showing ceiling profile as step function with bay height thresholds
- **Per-bay ceiling margin**: Colored indicators (🟢 comfy, 🟡 OK, 🟠 tight, 🔴 none)
- **Sidebar**: Display toggles, legend, scrollable bay list

```bash
python3 visualize.py ../PublicTestCases/Case0/warehouse.csv \
  ../PublicTestCases/Case0/obstacles.csv \
  ../PublicTestCases/Case0/ceiling.csv \
  ../PublicTestCases/Case0/types_of_bays.csv \
  output_case0.csv viz.html
```

## Test Results

| Case | Geometry | Bays | Quality Q | Coverage |
|------|----------|------|-----------|----------|
| 0 | L-shaped, 3 obstacles, variable ceiling | 36 | 263M | 61.5% |
| 1 | Square, no obstacles, 2-step ceiling | 45 | 801M | 62.5% |
| 2 | Square, 1 obstacle, 2-step ceiling | 37 | 520M | 52.1% |
| 3 | Plus-shaped, 1 obstacle, 3-step ceiling | 82 | 1.78B | 55.4% |

All cases validated ✅, run within 28s on Apple M-series / Python 3.12.

## Dependencies

**None** — Python 3.6+ standard library only.
