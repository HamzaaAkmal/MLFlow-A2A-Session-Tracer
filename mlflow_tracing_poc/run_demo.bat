@echo off
REM ============================================================
REM MLflow Multi-Agent Tracing Demo - Windows Batch Script
REM ============================================================
REM This script runs the complete demo including:
REM 1. Installing dependencies
REM 2. Starting the Remote Superagent
REM 3. Running the multi-turn demo
REM 4. Starting the MLflow UI
REM ============================================================

echo.
echo ============================================================
echo   MLflow Multi-Agent Tracing - Proof of Concept
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ and try again
    pause
    exit /b 1
)

echo Step 1: Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Starting Remote Superagent in background...
start "Remote Superagent" cmd /c "python remote_superagent.py"
timeout /t 3 /nobreak >nul
echo.

echo Step 3: Running Multi-Turn Demo...
python demo_multi_turn.py
echo.

echo Step 4: Starting MLflow UI...
echo.
echo ============================================================
echo   Open your browser to: http://localhost:5000
echo   Experiment: Multi-Agent-Tracing-PoC
echo ============================================================
echo.
echo Press Ctrl+C to stop the MLflow UI when done.
echo.

mlflow ui --port 5000

pause
