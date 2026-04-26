# Simulated Annealing Solvers

This directory contains the suite of Simulated Annealing (SA) based optimization engines built to solve the Mecalux Warehouse Bay Placement challenge. The algorithms search for an optimal layout that minimizes the cost-to-efficiency ratio while satisfying complex spatial constraints (warehouse footprint, ceiling heights, internal obstacles, and non-overlapping restrictions).

## 1. Base Orthogonal Solver (`solver.py`)
The base solver is optimized for speed and strict orthogonal placements.
- **Orientation Constraints:** Limits bay rotation to strict orthogonal angles (0°, 90°, 180°, and 270°).
- **Collision Detection:** Utilizes Axis-Aligned Bounding Boxes (AABB) along with a coarse spatial hashing grid to quickly discard overlap checks.
- **Containment Validation:** Models the warehouse footprint as a slab-decomposed axis-aligned polygon.
- **Initialization:** Employs a multi-pass, dense greedy packing heuristic that scans the warehouse in strips.
- **Optimization Strategy:** Standard Simulated Annealing applying four structural operators: `ADD`, `REMOVE`, `MOVE`, and `SWAP` (changing bay types). 

## 2. Flexible SAT Solver (`solver_flex.py` / `solver_flex.cpp`)
The flexible solver lifts the orthogonal constraint, enabling dense geometric packing along angled walls and within irregular footprints.
- **Orientation Capabilities:** Supports continuous angular rotations beyond 0° and 90° (often snapping to dominant wall angles).
- **Collision Detection:** Replaces AABB with Oriented Bounding Boxes (OBB) and implements the **Separating Axis Theorem (SAT)** for exact convex polygon overlap detection.
- **Optimization Strategy:** Implements dynamic window probabilities for the SA moves, actively tuning the ratio of `ADD`, `REMOVE`, `MOVE`, `SWAP`, and `REPACK` operations based on real-time acceptance rates.
- **Post-Processing:** Applies a localized *Shrink & Shift* micro-optimization pass. It temporarily lifts placed bays to test minor translations (±10 to 100 units) and minor rotations (±3° to ±30°) to squeeze items closer together without altering their type.

## 3. Hybrid Orchestrator (`solver_hybrid.py`)
A parallel execution wrapper designed to exploit the differing strengths of the Orthogonal and SAT models.
- **Parallel Execution:** Forks two parallel subprocesses: one executing the fast `solver.py` (Ortho) and one executing `solver_flex.py` (SAT).
- **Telemetry Aggregation:** Both models emit standardized metrics (`[METRIC]`). The orchestrator aggregates these streams in real-time.
- **Selection:** Upon termination (due to time limit or convergence), it compares the global best quality (Q) metric achieved by each solver and automatically commits the winning configuration to the final output file.

## 4. Ensemble Orchestrator (`solver_ensemble.py`)
An aggressively parallel execution engine that scales the Hybrid approach to maximize hardware utilization.
- **Core Distribution:** Detects the host machine's total logical CPU cores and evenly splits them between multiple Orthogonal and Flexible SAT instances.
- **Diverse Search:** By launching N/2 instances of each solver type, it benefits from the stochastic nature of the greedy initialization and the simulated annealing random seed, greatly increasing the probability of finding a global minimum compared to a single run.
- **Aggregation:** Similar to the hybrid solver, it merges real-time telemetry from all parallel threads and dumps the best overall solution on completion.