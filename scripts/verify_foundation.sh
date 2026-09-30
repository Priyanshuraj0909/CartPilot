#!/bin/bash
set -e

echo "=========================================="
echo "CartPilot Phase 1 Foundation Verification"
echo "=========================================="

echo ""
echo "1. Checking Python Environment..."
python3 -c "import sys; print(f'Python version: {sys.version}')"

echo ""
echo "2. Running Backend Tests..."
./backend/venv/bin/pytest backend/tests -v

echo ""
echo "3. Running Frontend Tests..."
npm --prefix frontend run test:run

echo ""
echo "4. Checking Frontend Build..."
npm --prefix frontend run build

echo ""
echo "=========================================="
echo "All Phase 1 Foundation Tests Passed!"
echo "=========================================="
