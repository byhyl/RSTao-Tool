@echo off
setlocal

if "%CONDA_PREFIX%"=="" (
    echo [ERROR] CONDA_PREFIX is not set. Activate the RSTao_tool conda environment first.
    exit /b 1
)

set "QT_BIN=%CONDA_PREFIX%\Library\bin"
set "QT_LIBEXEC=%CONDA_PREFIX%\Library\lib\qt6"
set "PATH=%QT_BIN%;%PATH%"

if exist "%QT_LIBEXEC%\%~n0.exe" (
    "%QT_LIBEXEC%\%~n0.exe" %*
    exit /b %ERRORLEVEL%
)

if exist "%QT_BIN%\%~n0.exe" (
    "%QT_BIN%\%~n0.exe" %*
    exit /b %ERRORLEVEL%
)

echo [ERROR] Qt tool not found: %~n0.exe
exit /b 1
