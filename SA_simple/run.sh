#!/bin/bash
# Run the SA solver on a specific test case
# Usage: ./run.sh <case_number> [output_file]
# Example: ./run.sh 0 output.csv

CASE=${1:-0}
OUTPUT=${2:-"output_case${CASE}.csv"}
BASE="../PublicTestCases/Case${CASE}"

if [ ! -d "$BASE" ]; then
    echo "Error: Test case directory $BASE not found"
    exit 1
fi

echo "Running solver on Case ${CASE}..."
python3 solver.py \
    "${BASE}/warehouse.csv" \
    "${BASE}/obstacles.csv" \
    "${BASE}/ceiling.csv" \
    "${BASE}/types_of_bays.csv" \
    "${OUTPUT}"

echo ""
echo "Output written to ${OUTPUT}"
