@echo off
REM Monthly report export - ensure reports dir, init conda, run export and exit
cd /d "D:\数据备份\量化交易\《期末综合实验报告》"
if not exist "reports" mkdir "reports"
if not exist "logs" mkdir "logs"

REM === Your Conda base (custom, non-C drive) ===
set "CONDA_BAT=D:\Anaconda\condabin\conda.bat"

if exist "%CONDA_BAT%" (
  call "%CONDA_BAT%" run -n ai-etf-trader python -m src.export_report >> logs\export.log 2>&1
) else (
  echo [WARN] %CONDA_BAT% not found. Trying "conda run" on PATH... >> logs\export.log 2>&1
  conda run -n ai-etf-trader python -m src.export_report >> logs\export.log 2>&1
)

