#!/bin/bash

# AI ETF Trader - Daily Task Runner (UV Version)
# This script runs the daily ETF trading task using UV package manager

set -e

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: UV is not installed or not in PATH"
    echo "Please install UV from: https://astral.sh/uv/install.sh"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Creating..."
    uv sync
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment"
        exit 1
    fi
fi

# Run the daily task
echo "Running daily ETF trading task..."
uv run python -m src.daily_once

if [ $? -ne 0 ]; then
    echo "Error: Daily task failed"
    exit 1
fi

echo "Daily task completed successfully"
exit 0

