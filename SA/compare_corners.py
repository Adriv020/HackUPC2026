import sys
import solver_flex
from validator import parse_solution, parse_bay_types, get_obb_corners, sat_overlap

def main():
    wh_data = solver_flex.parse_csv('../PublicTestCases/Case0/warehouse.csv', 2)
    obs_data = solver_flex.parse_csv('../PublicTestCases/Case0/obstacles.csv', 4)
    ceil_data = solver_flex.parse_csv('../PublicTestCases/Case0/ceiling.csv', 2)
    bays_data = solver_flex.parse_csv('../PublicTestCases/Case0/types_of_bays.csv', 7)

    bay_types = {}
    for row in bays_data:
        bay_types[int(row[0])] = (int(row[0]), row[1], row[2], row[3], row[4], int(row[5]), row[6])

    wh = solver_flex.Warehouse(wh_data)
    obs = [tuple(o) for o in obs_data]
    ceil = solver_flex.Ceiling(ceil_data)
    grid_res = 100

    state = solver_flex.greedy_initial(wh, obs, ceil, bay_types, grid_res)
    state = solver_flex.sa(wh, obs, ceil, bay_types, grid_res)

    out_csv = "temp_out.csv"
    solver_flex.write_output(state, out_csv)
    
    # Re-read using validator
    v_bays = parse_solution(out_csv)
    v_types = parse_bay_types("../PublicTestCases/Case0/types_of_bays.csv")
    
    active_idx = sorted(state.active)
    
    print(f"Comparing {len(active_idx)} bays...")
    mismatch = False
    for i, idx in enumerate(active_idx):
        b_flex = state.bays[idx]
        c_flex = b_flex[solver_flex.PB_CORNERS]
        
        b_val = v_bays[i]
        t_val = v_types[b_val['typeId']]
        w = t_val['width']
        d = t_val['depth'] + t_val['gap']
        c_val = get_obb_corners(b_val['x'], b_val['y'], w, d, b_val['rotation'])
        
        for p1, p2 in zip(c_flex, c_val):
            if abs(p1[0] - p2[0]) > 1e-10 or abs(p1[1] - p2[1]) > 1e-10:
                print(f"MISMATCH AT BAY {i}! (Index {idx})")
                print(f"  Flex X: {b_flex[solver_flex.PB_X]}  Val X: {b_val['x']}")
                print(f"  Flex Y: {b_flex[solver_flex.PB_Y]}  Val Y: {b_val['y']}")
                print(f"  Flex R: {b_flex[solver_flex.PB_R]}  Val R: {b_val['rotation']}")
                print(f"  Flex corners: {c_flex}")
                print(f"  Val  corners: {c_val}")
                mismatch = True
    
    if not mismatch:
        print("ALL CORNERS MATCH PERFECTLY TO 1E-10!")

    solver_flex.validate(state)

    for i in range(len(v_bays)):
        for j in range(i+1, len(v_bays)):
            w1 = v_types[v_bays[i]['typeId']]['width']
            d1 = v_types[v_bays[i]['typeId']]['depth'] + v_types[v_bays[i]['typeId']]['gap']
            ca = get_obb_corners(v_bays[i]['x'], v_bays[i]['y'], w1, d1, v_bays[i]['rotation'])
            
            w2 = v_types[v_bays[j]['typeId']]['width']
            d2 = v_types[v_bays[j]['typeId']]['depth'] + v_types[v_bays[j]['typeId']]['gap']
            cb = get_obb_corners(v_bays[j]['x'], v_bays[j]['y'], w2, d2, v_bays[j]['rotation'])
            if sat_overlap(ca, cb):
                print(f"Validator logic says {i} overlaps {j}")

if __name__ == '__main__':
    main()
