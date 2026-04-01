#!/bin/bash
set -e

echo "=== black ==="
black custom_components/pumpsteer/

echo "=== ruff format ==="
ruff format custom_components/pumpsteer/ tests/

echo "=== ruff check ==="
ruff check custom_components/pumpsteer/ tests/

echo "=== pytest ==="
python3 -m pytest

echo "=== Allt klart! ==="
