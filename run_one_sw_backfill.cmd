@echo off
setlocal

set "SCRIPT_DIR=D:\CC\INDUST~1"
set "LOG_PATH=%SCRIPT_DIR%\sw_backfill_scheduler.log"

>>"%LOG_PATH%" echo [scheduled backfill start]
py "%SCRIPT_DIR%\backfill_sw_daily_history.py" --start-date 20240101 --end-date 20260630 --chunk-open-days 5 --max-new-fetches 1 --sleep-seconds 0 >>"%LOG_PATH%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
>>"%LOG_PATH%" echo [scheduled backfill exit_code=%EXIT_CODE%]
exit /b %EXIT_CODE%
