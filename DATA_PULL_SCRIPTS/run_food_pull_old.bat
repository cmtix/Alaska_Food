@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ===============================================================
REM ISER / Alaska_Food – MASTER FOOD SCRAPE LAUNCHER (PYTHON)
REM ===============================================================

REM ---------- PATH SETUP (CODE REPO) -----------------------------

set "REPO_ROOT=C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food"
set "DATA_PULL=%REPO_ROOT%\DATA_PULL_SCRIPTS"
set "CENTRAL_PY=%DATA_PULL%\central_food_pull.py"

REM ---------- RAW DATA ROOT (NOT GIT-TRACKED) --------------------

set "RAW_DATA_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"

REM Store parent folders (must exist under RAW_DATA_ROOT)
set "ACC_RAW_ROOT=%RAW_DATA_ROOT%\ACC_RAW"
set "CS_RAW_ROOT=%RAW_DATA_ROOT%\CS_RAW"
set "FM_RAW_ROOT=%RAW_DATA_ROOT%\FM_RAW"
set "WM_RAW_ROOT=%RAW_DATA_ROOT%\WM_RAW"

if not exist "%RAW_DATA_ROOT%" mkdir "%RAW_DATA_ROOT%"
if not exist "%ACC_RAW_ROOT%" mkdir "%ACC_RAW_ROOT%"
if not exist "%CS_RAW_ROOT%" mkdir "%CS_RAW_ROOT%"
if not exist "%FM_RAW_ROOT%" mkdir "%FM_RAW_ROOT%"
if not exist "%WM_RAW_ROOT%" mkdir "%WM_RAW_ROOT%"

REM ---------- LOGS -----------------------------------------------

set "RUN_LOG=%DATA_PULL%\run_food_pull_master.log"
set "SCRAPE_LOG_DIR=%DATA_PULL%\Scraping_Logs"

if not exist "%SCRAPE_LOG_DIR%" mkdir "%SCRAPE_LOG_DIR%"

echo ==== run_food_pull.bat started at %DATE% %TIME% ====>>"%RUN_LOG%"
echo [BAT] REPO_ROOT=%REPO_ROOT%>>"%RUN_LOG%"
echo [BAT] RAW_DATA_ROOT=%RAW_DATA_ROOT%>>"%RUN_LOG%"
echo [BAT] ACC_RAW_ROOT=%ACC_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] CS_RAW_ROOT=%CS_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] FM_RAW_ROOT=%FM_RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] WM_RAW_ROOT=%WM_RAW_ROOT%>>"%RUN_LOG%"

REM ---------- PYTHON VENV ACTIVATION ----------------------------

call "%USERPROFILE%\.venvs\FP_env\Scripts\activate.bat"
if errorlevel 1 (
    echo [BAT-ERROR] Failed to activate FP_env>>"%RUN_LOG%"
    echo Failed to activate FP_env
    pause
    goto :EOF
)

REM ---------- STORE SWITCHES ------------------------------------

set "RUN_ACC=FALSE"
set "RUN_CS=FALSE"
set "RUN_FM=FALSE"
set "RUN_WM=TRUE"

REM ---------- WALMART MODE --------------------------------------
REM -----CHOOSE AN OPTION ----------------------------------------

REM ---OPTION 1: TRIGGER A NEW SNAPSHOT ------
set RUN_WM=TRUE
set WM_MODE=PULL
python central_food_pull.py

REM ---OPTION 2: DOWNLOAD A SNAPSHOT FROM API

set RUN_WM=TRUE
set WM_MODE=DOWNLOAD
set WM_SNAPSHOT_ID=sd_xxxxxxxxx
set WM_RAW_ROOT=G:\...\DATA\RAW_DATA\WM_RAW
python central_food_pull.py

REM ---OPTION 3: IMPORT MANUAL Bright Data UI Download ------
set RUN_WM=TRUE
set WM_MODE=IMPORT_MANUAL
python central_food_pull.py


REM ---------- KROGER CREDENTIALS (ONLY NEEDED IF RUN_FM=TRUE) ----
REM set "KROGER_CLIENT_ID=..."
REM set "KROGER_CLIENT_SECRET=..."

REM ---------- BRIGHT DATA (WALMART) -----------------------------

set "WM_API_KEY=5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"
set "WM_DATASET_ID=gd_m693oc1r1gebnayxq"
set "WM_SNAPSHOT_ID=sd_mjc2uwzoro56qxt8e"


REM Only needed for PULL mode
set "WM_SEARCH_FILE=C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food\DATA_PULL_SCRIPTS\WM\WM_search_list.txt"

REM ---------- RUN PIPELINE --------------------------------------

echo [BAT] Launching central_food_pull.py>>"%RUN_LOG%"
python "%CENTRAL_PY%"
set "PY_EXIT=%ERRORLEVEL%"

echo [BAT] EXIT CODE=%PY_EXIT%>>"%RUN_LOG%"

echo.
echo Batch finished with ERRORLEVEL %PY_EXIT%
echo Logs:
echo   Master: %RUN_LOG%
echo   Store logs: %SCRAPE_LOG_DIR%
pause

endlocal & exit /b %PY_EXIT%
