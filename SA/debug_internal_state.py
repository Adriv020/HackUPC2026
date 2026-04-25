import solver_flex
import sys

import validator
wh_data = validator.parse_csv('../PublicTestCases/Case0/warehouse.csv', 2)
obs_data = validator.parse_csv('../PublicTestCases/Case0/obstacles.csv', 4)
ceil_data = validator.parse_csv('../PublicTestCases/Case0/ceiling.csv', 2)

bays_data = validator.parse_csv('../PublicTestCases/Case0/types_of_bays.csv', 7)

bay_types = {}
for row in bays_data:
    bay_types[int(row[0])] = (int(row[0]), row[1], row[2], row[3], row[4], int(row[5]), row[6])

wh = solver_flex.Warehouse(wh_data)
obs = [tuple(o) for o in obs_data]
ceil = solver_flex.Ceiling(ceil_data)
grid_res = 100

state = solver_flex.greedy_initial(wh, obs, ceil, bay_types, grid_res)
state = solver_flex.sa(wh, obs, ceil, bay_types, grid_res)
solver_flex.validate(state)

# manual ALL-PAIR SAT
active = list(state.active)
for i in range(len(active)):
    for j in range(i+1, len(active)):
        idx_i, idx_j = active[i], active[j]
        c_i = state.bays[idx_i][solver_flex.PB_CORNERS]
        c_j = state.bays[idx_j][solver_flex.PB_CORNERS]
        if solver_flex.sat_overlap(c_i, c_j):
            print(f"Bays {idx_i} and {idx_j} overlapped natively in solver memory!")

