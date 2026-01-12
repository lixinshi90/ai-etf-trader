@echo off
setlocal
cd /d "D:\数据备份\量化交易\《期末综合实验报告》"
if not exist "logs" mkdir "logs"
set "CONDA_BAT=D:\Anaconda\condabin\conda.bat"
set "PY_EXE=D:\Anaconda\envs\ai-etf-trader\python.exe"
echo [%%DATE%% %%TIME%%] === Scheduled run started ===>> logs\daily.log
rem 优先 conda run，其次直连 env 的 python.exe
if exist "%CONDA_BAT%" (
call "%CONDA_BAT%" run -n ai-etf-trader python -u -m src.daily_once >> logs\daily.log 2>&1
set "ERR=%ERRORLEVEL%"
) else (
if exist "%PY_EXE%" (
"%PY_EXE%" -u -m src.daily_once >> logs\daily.log 2>&1
set "ERR=%ERRORLEVEL%"
) else (
echo [%%DATE%% %%TIME%%] ERROR: conda.bat 和 python.exe 均不可用>> logs\daily.log
set "ERR=2"
)
)
echo [%%DATE%% %%TIME%%] Exit code: %ERR%>> logs\daily.log
echo.>> logs\daily.log
endlocal & exit /b %ERR%