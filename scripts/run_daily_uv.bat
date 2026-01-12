@echo off
REM AI ETF Trader - Daily Task Runner (UV Version)
REM This script runs the daily ETF trading task using UV package manager

setlocal enabledelayedexpansion

REM Get the project root directory
cd /d "%~dp0.."

REM Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: UV is not installed or not in PATH
    echo Please install UV from: https://astral.sh/uv/install.ps1
    exit /b 1
)

REM Check if virtual environment exists
if not exist ".venv" (
    echo Virtual environment not found. Creating...
    call uv sync
    if !errorlevel! neq 0 (
        echo Error: Failed to create virtual environment
        exit /b 1
    )
)

REM Run the daily task
echo Running daily ETF trading task...
call uv run python -m src.daily_once

if %errorlevel% neq 0 (
    echo Error: Daily task failed with exit code %errorlevel%
    exit /b %errorlevel%
)

echo Daily task completed successfully
exit /b 0

