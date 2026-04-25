import solver_flex
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

# Validate at the end
bays_list = [(idx, state.bays[idx]) for idx in state.active]
for i in range(len(bays_list)):
    for j in range(i+1, len(bays_list)):
        idi, b1 = bays_list[i]
        idj, b2 = bays_list[j]
        c1 = b1[solver_flex.PB_CORNERS]
        c2 = b2[solver_flex.PB_CORNERS]
        if solver_flex.sat_overlap(c1, c2):
            print(f"INTERNAL FAILURE! Bays {idi} and {idj} overlap natively!!!")
            
print("Done checking native memory.")
