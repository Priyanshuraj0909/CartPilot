#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "=========================================="
echo "CartPilot Final Regression Verification"
echo "=========================================="

echo ""
echo "1. Checking Python Environment..."
python3 -c "import sys; print(f'Python version: {sys.version}')"

echo ""
echo "2. Running Backend Tests..."
(cd backend && venv/bin/python -m pytest -q)

echo ""
echo "3. Running Frontend Tests..."
npm --prefix frontend run test:run

echo ""
echo "4. Checking Frontend Build..."
npm --prefix frontend run build

echo ""
echo "=========================================="
echo "Backend, frontend tests and build passed!"
echo "=========================================="
