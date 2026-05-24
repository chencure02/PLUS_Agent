@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   PLUS Agent - Environment Setup
echo ============================================
echo.

REM Check if conda is available
where conda >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] conda not found. Please install Anaconda or Miniconda first.
    pause
    exit /b 1
)

echo [1/3] Creating conda environment 'plus-agent' with Python 3.11...
call conda create -n plus-agent python=3.11 -y
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create conda environment.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing GDAL via conda-forge...
call conda install -n plus-agent -c conda-forge gdal -y
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install GDAL.
    pause
    exit /b 1
)

echo.
echo [3/3] Installing Python dependencies via pip...
call conda run -n plus-agent python -m pip install -r "%~dp0requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install pip dependencies.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete!
echo.
echo   To start PLUS Agent:
echo     1. conda activate plus-agent
echo     2. cd /d "%~dp0"
echo     3. chainlit run agent/main.py
echo ============================================
pause
