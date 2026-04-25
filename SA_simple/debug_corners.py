import csv
with open('output_flex.csv') as f:
    r = csv.reader(f)
    next(r)
    for i, row in enumerate(r):
        print(f"Bay {i}: X={float(row[1])}, Y={float(row[2])}, Rot={float(row[3])}")
        if i in [2, 3]:
            # recalculate
            pass
