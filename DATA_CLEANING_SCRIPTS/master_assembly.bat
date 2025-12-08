@echo off
setlocal

REM ==== CONFIGURATION ====
set "SCRIPT_DIR=G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA_CLEANING_SCRIPTS"
set "PREBUILD_SCRIPT=%SCRIPT_DIR%\prebuild_missing_store_months.py"
set "PYTHON_SCRIPT=%SCRIPT_DIR%\master_assembly.py"
set "PYTHON_EXE=C:\Users\vlcollier\env\Scripts\python.exe"
set "LOG_FILE=%SCRIPT_DIR%\Cleaning_Logs\pipeline_log.txt"

REM ==== ALL OUTPUT REDIRECTED INTO LOG_FILE ====
(
  echo ==== Pipeline run started at %DATE% %TIME%
  echo [DEBUG] Changing directory to %SCRIPT_DIR%

  cd /d "%SCRIPT_DIR%" || (
    echo ERROR: Cannot cd to %SCRIPT_DIR%
    exit /b 1
  )

  echo [DEBUG] Current dir: %CD%
  echo [DEBUG] Calling PYTHON: %PYTHON_EXE%

  REM ---- 1) Prebuild missing ACC/FM/WM months ----
  echo [DEBUG] Running prebuild script: %PREBUILD_SCRIPT%
  "%PYTHON_EXE%" "%PREBUILD_SCRIPT%"
  echo [DEBUG] Prebuild return code: %ERRORLEVEL%

  REM ---- 2) Run the existing master assembly ----
  echo [DEBUG] Running script: %PYTHON_SCRIPT%
  "%PYTHON_EXE%" "%PYTHON_SCRIPT%"
  echo [DEBUG] Python return code: %ERRORLEVEL%

  echo ==== Pipeline run ended at   %DATE% %TIME%
) > "%LOG_FILE%" 2>&1

endlocal
exit /b 0
