@echo off
setlocal enabledelayedexpansion

REM === One-command build for rstao_core + RSTaoStudio ===
REM Requires: conda env RSTao_tool, OpenCV, CMake, and an MSVC generator.
REM Usage: build_all.bat [Release|Debug|both]  (default: both)
REM Optional env vars:
REM   RSTAO_CMAKE_GENERATOR  default: Visual Studio 17 2022
REM   RSTAO_CMAKE_ARCH       default: x64
REM   OPENCV_ROOT            OpenCV install root
REM   OpenCV_DIR             directory containing OpenCVConfig.cmake

set "BUILD_CONFIG=%~1"
if "%BUILD_CONFIG%"=="" set "BUILD_CONFIG=both"

set "RSTAO_CMAKE_GENERATOR=%RSTAO_CMAKE_GENERATOR%"
if "%RSTAO_CMAKE_GENERATOR%"=="" set "RSTAO_CMAKE_GENERATOR=Visual Studio 17 2022"

set "RSTAO_CMAKE_ARCH=%RSTAO_CMAKE_ARCH%"
if "%RSTAO_CMAKE_ARCH%"=="" (
    echo %RSTAO_CMAKE_GENERATOR% | findstr /i "Visual Studio" >nul 2>&1
    if not errorlevel 1 set "RSTAO_CMAKE_ARCH=x64"
)
set "RSTAO_CMAKE_ARCH_ARGS="
if not "%RSTAO_CMAKE_ARCH%"=="" set "RSTAO_CMAKE_ARCH_ARGS=-A %RSTAO_CMAKE_ARCH%"

REM --- Activate conda environment ---
call conda activate RSTao_tool 2>nul
if errorlevel 1 (
    echo [ERROR] conda environment 'RSTao_tool' not found.
    echo   Create or activate it before building this project.
    exit /b 1
)

set "PATH=%CONDA_PREFIX%\Library\bin;%PATH%"
if defined OPENCV_ROOT (
    if exist "%OPENCV_ROOT%\bin" set "PATH=%OPENCV_ROOT%\bin;%PATH%"
    if exist "%OPENCV_ROOT%\x64\vc16\bin" set "PATH=%OPENCV_ROOT%\x64\vc16\bin;%PATH%"
)
echo [INFO] CONDA_PREFIX: %CONDA_PREFIX%
echo [INFO] Generator: %RSTAO_CMAKE_GENERATOR%
if not "%RSTAO_CMAKE_ARCH%"=="" echo [INFO] Architecture: %RSTAO_CMAKE_ARCH%
if defined OPENCV_ROOT echo [INFO] OPENCV_ROOT: %OPENCV_ROOT%
if defined OpenCV_DIR echo [INFO] OpenCV_DIR: %OpenCV_DIR%

REM --- Build rstao_core ---
echo.
echo === Building rstao_core ===
cd /d "%~dp0cpp"

if exist build\CMakeCache.txt (
    findstr /c:"CMAKE_GENERATOR:INTERNAL=%RSTAO_CMAKE_GENERATOR%" build\CMakeCache.txt >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Cleaning stale rstao_core CMake cache.
        rmdir /s /q build
    )
)

cmake -B build -S . -G "%RSTAO_CMAKE_GENERATOR%" %RSTAO_CMAKE_ARCH_ARGS%
if errorlevel 1 goto :fail

if /i "%BUILD_CONFIG%"=="Release" (
    cmake --build build --config Release
    if errorlevel 1 goto :fail
) else if /i "%BUILD_CONFIG%"=="Debug" (
    cmake --build build --config Debug
    if errorlevel 1 goto :fail
) else (
    cmake --build build --config Release
    if errorlevel 1 goto :fail
    cmake --build build --config Debug
    if errorlevel 1 goto :fail
)

REM --- Build RSTaoStudio ---
echo.
echo === Building RSTaoStudio ===
cd /d "%~dp0cpp_qt"

if exist build\CMakeCache.txt (
    findstr /c:"CMAKE_GENERATOR:INTERNAL=%RSTAO_CMAKE_GENERATOR%" build\CMakeCache.txt >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Cleaning stale RSTaoStudio CMake cache.
        rmdir /s /q build
    )
)

cmake -B build -S . -G "%RSTAO_CMAKE_GENERATOR%" %RSTAO_CMAKE_ARCH_ARGS% ^
    -DCMAKE_PREFIX_PATH="%CONDA_PREFIX%\Library"
if errorlevel 1 goto :fail

if /i "%BUILD_CONFIG%"=="Release" (
    cmake --build build --config Release
    if errorlevel 1 goto :fail
) else if /i "%BUILD_CONFIG%"=="Debug" (
    cmake --build build --config Debug
    if errorlevel 1 goto :fail
) else (
    cmake --build build --config Release
    if errorlevel 1 goto :fail
    cmake --build build --config Debug
    if errorlevel 1 goto :fail
)

REM --- Run tests ---
echo.
echo === Running rstao_core tests ===
cd /d "%~dp0cpp\build"
ctest --output-on-failure -C Release 2>nul
if errorlevel 1 (
    echo [WARN] Tests failed or were not built. Install GTest in RSTao_tool to enable them.
) else (
    echo [OK] All tests passed.
)

echo.
echo [OK] Build complete.
exit /b 0

:fail
echo [ERROR] Build failed.
exit /b 1
