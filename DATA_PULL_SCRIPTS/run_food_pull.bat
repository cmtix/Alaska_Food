@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ===============================================================
REM ISER / Alaska_Food – MASTER FOOD SCRAPE LAUNCHER (PYTHON)
REM ===============================================================

REM ---------- PATH SETUP ----------------------------------------

set "REPO_ROOT=C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food"
set "DATA_PULL=%REPO_ROOT%\DATA_PULL_SCRIPTS"
set "CENTRAL_PY=%DATA_PULL%\central_food_pull.py"



REM Master log
set "RUN_LOG=%DATA_PULL%\run_food_pull_master.log"

REM Scraping logs directory
set "SCRAPE_LOG_DIR=%DATA_PULL%\Scraping_Logs"
if not exist "%SCRAPE_LOG_DIR%" mkdir "%SCRAPE_LOG_DIR%"

echo ==== run_food_pull.bat started at %DATE% %TIME% ====>>"%RUN_LOG%"
echo PROJ=%PROJ%>>"%RUN_LOG%"
echo CENTRAL_PY=%CENTRAL_PY%>>"%RUN_LOG%"

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
set "RUN_CS=TRUE"
set "RUN_FM=TRUE"
set "RUN_WM=TRUE"

REM ---------- RAW OUTPUT ROOTS (CANONICAL) ----------------------

set "RAW_ROOT=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA"

set "ACC_OUT_DIR=%RAW_ROOT%\ACC_RAW"
set "CS_OUT_DIR=%RAW_ROOT%\CS_RAW"
set "FM_OUT_DIR=%RAW_ROOT%\FM_RAW"
set "WM_OUT_DIR=%RAW_ROOT%\WM_RAW"

echo [BAT] RAW_ROOT=%RAW_ROOT%>>"%RUN_LOG%"
echo [BAT] ACC_OUT_DIR=%ACC_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] CS_OUT_DIR=%CS_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] FM_OUT_DIR=%FM_OUT_DIR%>>"%RUN_LOG%"
echo [BAT] WM_OUT_DIR=%WM_OUT_DIR%>>"%RUN_LOG%"


REM ---------- KROGER CREDENTIALS --------------------------------
set "KROGER_CLIENT_ID=uaaeconomicresearch-1c9930e136aa1ca8bdee7c8f336ed77a5021264682018960484"
set "KROGER_CLIENT_SECRET=gUnOOBLmuXR0zSIc8NhUMsL2db3ODrxES9vk9Tv4"

REM ---------- BRIGHT DATA (WALMART) -----------------------------
set "WM_API_KEY=5470de471903618d2dd462633e022234e47d1a8257a1db9f615abda30cb047d3"
set "WM_USE_LAST=0"
set "WM_MAX_WAIT_MIN=360"
set "WM_POLL_EVERY_S=120"
set "WM_DATASET_ID=gd_m693oc1r1gebnayxq"
set "WM_SEARCH_FILE=%DATA_PULL%\WM\WM_search_list.txt"

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

