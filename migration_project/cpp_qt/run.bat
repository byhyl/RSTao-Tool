@echo off
setlocal

REM === Launch RSTaoStudio ===
REM Usage: run.bat [Debug|Release]  (default: Release)

call conda activate RSTao_tool 2>nul
if errorlevel 1 (
    echo [ERROR] conda environment 'RSTao_tool' not found.
    exit /b 1
)

set "PATH=%CONDA_PREFIX%\Library\bin;%PATH%"

REM Add OpenCV DLLs to PATH when OPENCV_ROOT points to an OpenCV install root.
if defined OPENCV_ROOT (
    if exist "%OPENCV_ROOT%\bin" set "PATH=%OPENCV_ROOT%\bin;%PATH%"
    if exist "%OPENCV_ROOT%\x64\vc16\bin" set "PATH=%OPENCV_ROOT%\x64\vc16\bin;%PATH%"
)

set "BUILD_CONFIG=%~1"
if "%BUILD_CONFIG%"=="" set "BUILD_CONFIG=Release"

set "BUILD_DIR=%~dp0build"
set "APP_PATH=%BUILD_DIR%\%BUILD_CONFIG%\RSTaoStudio.exe"

if not exist "%APP_PATH%" (
    echo [ERROR] %BUILD_CONFIG% build not found. Run ..\build_all.bat %BUILD_CONFIG% first.
    exit /b 1
)

start "" "%APP_PATH%"
