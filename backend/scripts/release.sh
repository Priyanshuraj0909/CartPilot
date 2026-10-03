#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec python -m alembic upgrade head
