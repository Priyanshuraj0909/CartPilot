#!/usr/bin/env python3
"""CLI wrapper to run the database seeder from project root."""

import asyncio
import os
import sys

# Ensure backend directory is in python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.seed import main

if __name__ == "__main__":
    asyncio.run(main())
