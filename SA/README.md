# Warehouse Bay Placement Solver (Simulated Annealing)

**HackUPC 2026 – Mecalux Challenge**

## Quick Start

```bash
python3 solver.py <warehouse.csv> <obstacles.csv> <ceiling.csv> <types_of_bays.csv> <output.csv>
```

### Run on a specific test case
```bash
bash run.sh 0           # Run Case 0, output to output_case0.csv
bash run.sh 2 my.csv    # Run Case 2, output to my.csv
```

### Run all test cases
```bash
bash run_all.sh
```

## Algorithm Overview

The solver uses a two-phase approach:

### Phase 1: Greedy Strip Packing (~40% of time budget)

1. **Sort bay types** by efficiency (`Price/nLoads`, ascending = best first)
2. **Strip packing**: For each bay type and rotation (0°, 90°), scan the warehouse
   row by row, placing bays left-to-right with a 50-unit step for finding gaps
3. **Candidate filling**: After the strip pass, collect all X/Y coordinates from
   placed bay corners and retry placement at these intersection points
4. Repeat candidate filling up to 5 passes until no more bays can be added

### Phase 2: Simulated Annealing (~60% of time budget)

**Neighbor moves** (weighted random selection):
| Move | Probability | Description |
|------|-------------|-------------|
| Add | 50% | Place a new bay (adjacent to existing, random, or at base coordinates) |
| Remove | 8% | Remove a random bay |
| Move | 27% | Relocate a bay (adjacent-based or random perturbation ±1000 units) |
| Swap | 15% | Change a bay's type while keeping its position |

**Bay type selection** is weighted by `nLoads/Price` (most efficient types selected more often).

**Position selection** for Add/Move uses three strategies:
1. **Adjacent placement** (75%): Try 8 positions touching an existing bay
2. **Random position** (if adjacent fails): Random coordinates within warehouse
3. **Base candidates** (fallback): Warehouse vertices and obstacle corners

**Cooling schedule**: Geometric cooling with α=0.99997, reheat after 20000 moves without improvement.

All moves maintain feasibility. Rejected moves are undone in O(1) using undo records.

## SA Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Initial T | max(1, 0.3 × Q₀) | Scaled to initial quality |
| Cooling α | 0.99997 | Slow enough for 28s of fine-tuning |
| Reheat trigger | 20000 moves | Restart from best on stagnation |
| Reheat T | max(0.5, 0.05 × Q_best) | Warm restart |
| Time limit | 28s | 2s safety margin |

## Performance Optimizations

- **Spatial grid**: O(1) amortized overlap queries via grid-based spatial index
- **Slab decomposition**: Axis-aligned polygon containment in O(slabs) per query
- **Incremental Q**: Running sums of efficiency and area, no recomputation
- **Tuple-based data**: All structures use tuples instead of objects for speed
- **Integer snapping**: Random positions snapped to integers to avoid FP issues

## Quality Formula

```
Q = (Σ Price/nLoads)² × (Σ Width×Depth) / Area_warehouse
```

## Constraints Enforced

1. **Warehouse containment**: Bay rectangle fully inside polygon (slab-based check)
2. **Obstacle avoidance**: No overlap with obstacles (touching allowed, area > ε rejected)
3. **Bay-bay non-overlap**: No overlap between bays (touching allowed)
4. **Ceiling**: `min_ceiling(x_span) ≥ Height + Gap` (piecewise linear interpolation)
5. **Rotation**: Only 0°, 90°, 180°, 270° (axis-aligned)

## Test Results (Apple M-series, Python 3.12)

| Case | Bays | Quality Q | Iters/s |
|------|------|-----------|---------|
| 0 | 34 | ~224M | ~1400 |
| 1 | 50 | ~1.1B | ~1300 |
| 2 | 42 | ~729M | ~950 |
| 3 | 84 | ~1.9B | ~2500 |

## Trade-offs for 30s Limit

- **Python over C++**: Easier to iterate on, fewer bugs, ~10× slower but sufficient
- **Grid cell size**: Tuned to warehouse size / 80 for good balance
- **Greedy step**: 50 units is small enough to find gaps, large enough to be fast
- **SA attempts per move**: Limited to 6-8 random tries to keep iteration rate high
- **No full recomputation**: Incremental everything prevents O(n) per iteration

## Dependencies

Python 3.6+ (standard library only, no external packages).
