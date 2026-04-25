#!/bin/bash
# Run all test cases and report results
echo "=== Running all test cases ==="
echo ""

for i in 0 1 2 3; do
    echo "--- Case $i ---"
    python3 solver.py \
        "../PublicTestCases/Case${i}/warehouse.csv" \
        "../PublicTestCases/Case${i}/obstacles.csv" \
        "../PublicTestCases/Case${i}/ceiling.csv" \
        "../PublicTestCases/Case${i}/types_of_bays.csv" \
        "output_case${i}.csv" 2>&1
    echo ""
done

echo "=== All cases complete ==="
