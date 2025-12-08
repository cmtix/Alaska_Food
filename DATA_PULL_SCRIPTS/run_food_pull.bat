@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ===============================================================
REM ISER FOOD DATA PIPELINE - MASTER SCRAPE LAUNCHER (PYTHON)
REM - Activates FP_env
REM - Sets store toggles (RUN_ACC / RUN_CS / RUN_FM / RUN_WM)
REM - Injects Kroger + Bright Data credentials
REM - Defines RAW_DATA output roots for each store
REM - Logs to run_food_pull_master.log
REM ===============================================================

REM ---------- PATH SETUP ----------------------------------------
set "GROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
set "PROJ=%GROOT%\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
set "PY_SETUP=%PROJ%\DATA_PULL_SCRIPTS\"
set "CENTRAL_PY=%PY_SETUP%\central_food_pull.py"

REM Master log for this BAT (central_food_pull.py writes per-store logs)
set "RUN_LOG=%PY_SETUP%\run_food_pull_master.log"

REM Scraping logs directory used by central_food_pull.py
set "SCRAPE_LOG_DIR=%PROJ%\DATA_PULL_SCRIPTS\Scraping_Logs"
if not exist "%SCRAPE_LOG_DIR%" (
    mkdir "%SCRAPE_LOG_DIR%"
)

echo ==== run_food_pull.bat started at %DATE% %TIME% ====>>"%RUN_LOG%"
echo PROJ=%PROJ%>>"%RUN_LOG%"
echo PY_SETUP=%PY_SETUP%>>"%RUN_LOG%"
echo SCRAPE_LOG_DIR=%SCRAPE_LOG_DIR%>>"%RUN_LOG%"

REM ---------- PYTHON VENV ACTIVATION ----------------------------
echo [BAT] Activating FP_env virtualenv...>>"%RUN_LOG%"
call "%USERPROFILE%\.venvs\FP_env\Scripts\activate.bat"
if errorlevel 1 (
    echo [BAT-ERROR] Failed to activate FP_env virtualenv.>>"%RUN_LOG%"
    echo Failed to activate FP_env. Aborting.
    echo.
    pause
    goto :EOF
)

REM ---------- STORE SWITCHES ------------------------------------
REM These are read by central_food_pull.py (parse_bool).
REM Set to TRUE/FALSE (or 1/0) as needed.
set "RUN_ACC=TRUE"
set "RUN_CS=TRUE"
set "RUN_FM=TRUE"
set "RUN_WM=TRUE"

echo RUN_ACC=%RUN_ACC%, RUN_CS=%RUN_CS%, RUN_FM=%RUN_FM%, RUN_WM=%RUN_WM%>>"%RUN_LOG%"

REM ---------- RAW OUTPUT ROOTS ----------------------------------
REM Single source of truth for where raw files are written.

set "ACC_OUT_DIR=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\ACC_RAW"
set "CS_OUT_DIR=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\CS_RAW"
set "FM_OUT_DIR=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\FM_RAW"
set "BRIGHTDATA_OUT_DIR=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\WM_RAW"

echo [BAT] ACC_OUT_DIR=%ACC_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] CS_OUT_DIR=%CS_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] FM_OUT_DIR=%FM_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] BRIGHTDATA_OUT_DIR=%BRIGHTDATA_OUT_DIR%>>"%RUN_LOG%"

REM ---------- KROGER / FRED MEYER CREDENTIALS (FM) --------------
REM TODO: put your real values here.
set "KROGER_CLIENT_ID=uaaeconomicresearch-1c9930e136aa1ca8bdee7c8f336ed77a5021264682018960484"
set "KROGER_CLIENT_SECRET=gUnOOBLmuXR0zSIc8NhUMsL2db3ODrxES9vk9Tv4"

echo [BAT] KROGER_CLIENT_ID (masked) = !KROGER_CLIENT_ID:~0,6!?>>"%RUN_LOG%"

REM ---------- WALMART / BRIGHT DATA CREDENTIALS (WM) ------------
REM TODO: Bright Data API key
set "BRIGHTDATA_API_KEY=5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"

REM Walmart tuning overrides
set "BRIGHTDATA_USE_LAST=0"
set "BRIGHTDATA_MAX_WAIT_MIN=360"
set "BRIGHTDATA_POLL_EVERY_S=120"
set "BRIGHTDATA_DATASET_ID=gd_m693oc1r1gebnayxq"

REM WM_search_list.txt is a SEARCH FILE, not a ready-made CSV.
REM Tell Walmart_Bright_Data11.py to use it for building data_from_search_file.csv:
set "BRIGHTDATA_SEARCH_FILE=%PROJ%\DATA_PULL_SCRIPTS\WM\WM_search_list.txt"
REM DO NOT SET BRIGHTDATA_INPUT_CSV WHEN USING SEARCH LISTS



echo [BAT] BRIGHTDATA_API_KEY (masked) = !BRIGHTDATA_API_KEY:~0,6!?>>"%RUN_LOG%"
echo [BAT] WM tuning: SNAPSHOT_ID=%BRIGHTDATA_SNAPSHOT_ID%, USE_LAST=%BRIGHTDATA_USE_LAST%>>"%RUN_LOG%"
echo [BAT]   MAX_WAIT_MIN=%BRIGHTDATA_MAX_WAIT_MIN%, POLL_EVERY_S=%BRIGHTDATA_POLL_EVERY_S%>>"%RUN_LOG%"
echo [BAT]   DATASET_ID=%BRIGHTDATA_DATASET_ID%>>"%RUN_LOG%"


REM ---------- RUN CENTRAL PYTHON RUNNER -------------------------
echo [BAT] Launching central_food_pull.py>>"%RUN_LOG%"
echo.>>"%RUN_LOG%"

python "%CENTRAL_PY%"
set "PY_EXIT=%ERRORLEVEL%"

echo [BAT] central_food_pull.py ERRORLEVEL=%PY_EXIT%>>"%RUN_LOG%"

echo.
echo Batch finished with ERRORLEVEL %PY_EXIT%
echo Logs:
echo   Master: %RUN_LOG%
echo   Store logs: %SCRAPE_LOG_DIR%
echo.
pause

endlocal & exit /b %PY_EXIT%
