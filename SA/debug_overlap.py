import sys
from validator import parse_solution, parse_bay_types, get_obb_corners, sat_overlap

bays = parse_solution("output_flex.csv")
types = parse_bay_types("../PublicTestCases/Case0/types_of_bays.csv")

for pair in [(2,3), (7,13)]:
    idx1, idx2 = pair
    b1, b2 = bays[idx1], bays[idx2]
    t1, t2 = types[b1['typeId']], types[b2['typeId']]
    c1 = get_obb_corners(b1['x'], b1['y'], t1['width'], t1['depth']+t1['gap'], b1['rotation'])
    c2 = get_obb_corners(b2['x'], b2['y'], t2['width'], t2['depth']+t2['gap'], b2['rotation'])
    
    # Internal logic of SAT
    def debug_sat(c1, c2):
        for poly_idx, poly in enumerate((c1, c2)):
            for i in range(4):
                p1 = poly[i]; p2 = poly[(i+1)%4]
                nx = p2[1] - p1[1]
                ny = p1[0] - p2[0]
                m1 = min(p[0]*nx + p[1]*ny for p in c1)
                M1 = max(p[0]*nx + p[1]*ny for p in c1)
                m2 = min(p[0]*nx + p[1]*ny for p in c2)
                M2 = max(p[0]*nx + p[1]*ny for p in c2)
                if M1 <= m2 + 1e-6 or M2 <= m1 + 1e-6:
                    print(f"Separated by poly {poly_idx} edge {i}!")
                    return False
        return True
    
    print(f"Pair {idx1} and {idx2}: overlaps? {debug_sat(c1, c2)}")

    print(c1)
    print(c2)
