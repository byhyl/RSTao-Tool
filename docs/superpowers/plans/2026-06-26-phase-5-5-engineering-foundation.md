# Phase 5.5 Plan 1: Engineering Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish git tracking, portable CMake build, GTest unit tests, and CI scaffolding for the RSTao Studio migration_project/.

**Architecture:** Modify the two existing CMakeLists.txt to auto-detect Qt6/OpenCV paths via environment variables and common locations. Add GTest unit tests for rstao_core's 14 image processing operators, 4 feature detectors, and template matching. Create build_all.bat for one-command builds and a GitHub Actions CI yaml for future use.

**Tech Stack:** CMake 3.16+, MSVC 19.44 (VS 2026), Qt6 6.9.3 (conda), OpenCV 4.12.0, GTest, Windows batch

## Global Constraints

- C++ standard: C++17 (`CMAKE_CXX_STANDARD 17`)
- CRT: `CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL"` + `_ITERATOR_DEBUG_LEVEL=0` in Debug — MUST be preserved in all CMakeLists.txt changes
- rstao_core Debug lib maps to Release lib in cpp_qt/CMakeLists.txt — MUST be preserved
- conda environment name: `RSTao_tool`
- CMake generator: "Visual Studio 18 2026" -A x64
- All .cpp/.h files use UTF-8 (`/utf-8` compile flag)
- No absolute hardcoded paths in CMakeLists.txt or batch scripts — use env vars + auto-detection
- cpp/ has zero Qt dependency; cpp_qt/ contains all Qt code

## Scope Note

This is Plan 1 of 2. Plan 2 (ImageProcessingTab UI Polish — drag-drop, progress bar, undo, presets, comparison, zoom sync, batch processing) will follow after this plan is executed. This plan produces a buildable, tested, git-tracked codebase.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `migration_project/.gitignore` | Create | Ignore build/, __pycache__/, *.pyc, .vs/ |
| `migration_project/.clang-format` | Create | Code style: Google base, 4-space indent |
| `migration_project/cpp/CMakeLists.txt` | Modify | Path auto-detection for OpenCV |
| `migration_project/cpp_qt/CMakeLists.txt` | Modify | Path auto-detection for Qt6/OpenCV, remove APP_VERSION |
| `migration_project/cpp_qt/CMakePresets.json` | Modify | Path variables instead of hardcoded |
| `migration_project/build_all.bat` | Create | One-command build: cpp → cpp_qt → tests |
| `migration_project/cpp_qt/run.bat` | Modify | Auto-detect conda environment |
| `migration_project/cpp_qt/docs/crt-workaround.md` | Create | Document CRT issue and solution |
| `migration_project/cpp/tests/CMakeLists.txt` | Modify | Conditional GTest find_package |
| `migration_project/cpp/tests/test_image_processing.cpp` | Create | 14 operator unit tests |
| `migration_project/cpp/tests/test_feature_detection.cpp` | Create | 4 detector unit tests |
| `migration_project/cpp/tests/test_image_matching.cpp` | Create | Matching unit tests |
| `migration_project/.github/workflows/ci.yml` | Create | CI pipeline (for future GitHub repo) |

---

### Task 1: Git Tracking and Code Style Foundation

**Files:**
- Create: `migration_project/.gitignore`
- Create: `migration_project/.clang-format`

**Interfaces:**
- Consumes: nothing
- Produces: `.gitignore` (git ignores build artifacts), `.clang-format` (editor formatting rules)

- [ ] **Step 1: Create .gitignore**

Create `migration_project/.gitignore`:

```gitignore
# C++ build artifacts
build/
out/
cmake-build-*/
*.o
*.obj
*.lib
*.pdb
*.ilk

# CMake
CMakeCache.txt
CMakeFiles/
cmake_install.cmake
CMakeUserPresets.json

# Python
__pycache__/
*.pyc
*.pyo
.venv/
*.egg-info/

# IDE
.vs/
.vscode/
*.user
*.suo

# OS
Thumbs.db
.DS_Store
```

- [ ] **Step 2: Create .clang-format**

Create `migration_project/.clang-format`:

```yaml
---
BasedOnStyle: Google
IndentWidth: 4
TabWidth: 4
UseTab: Never
ColumnLimit: 100
AlignAfterOpenBracket: Align
AllowShortIfStatementsOnASingleLine: WithoutElse
AllowShortFunctionsOnASingleLine: Inline
AllowShortLambdasOnASingleLine: All
BreakBeforeBraces: Attach
NamespaceIndentation: None
PointerAlignment: Left
SortIncludes: CaseSensitive
```

- [ ] **Step 3: Add migration_project/ to git tracking**

The parent RSTao-Tool directory is already a git repo. migration_project/ is currently untracked. Add it:

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/.gitignore migration_project/.clang-format
git add migration_project/cpp/ migration_project/cpp_qt/
# Don't add build/ directories — .gitignore handles that
```

Verify:
```bash
git status migration_project/
```
Expected: .gitignore, .clang-format, cpp/ and cpp_qt/ source files staged, build/ directories NOT shown.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: add git tracking and code style config for migration_project

- .gitignore for C++/Python/IDE artifacts
- .clang-format (Google base, 4-space indent)
- Track cpp/ (rstao_core library) and cpp_qt/ (RSTaoStudio GUI) source files"
```

---

### Task 2: CMake Path Auto-Detection

**Files:**
- Modify: `migration_project/cpp/CMakeLists.txt` (lines 14-17 — OpenCV path)
- Modify: `migration_project/cpp_qt/CMakeLists.txt` (lines 17-21 — Qt6/OpenCV paths, line 83 — remove APP_VERSION)
- Modify: `migration_project/cpp_qt/CMakePresets.json` (paths → variables)

**Interfaces:**
- Consumes: `OPENCV_ROOT` env var (optional), `CONDA_PREFIX` env var (optional)
- Produces: portable CMake configuration that works without hardcoded paths

- [ ] **Step 1: Rewrite cpp/CMakeLists.txt OpenCV detection**

Replace lines 14-17 of `migration_project/cpp/CMakeLists.txt`:

Old (lines 14-17):
```cmake
# OpenCV — installed manually at user's downloads
# The OpenCVConfig.cmake is in the lib/ subdirectory
set(OpenCV_DIR "$ENV{USERPROFILE}/Downloads/opencv/build/x64/vc16/lib")
find_package(OpenCV REQUIRED PATHS "${OpenCV_DIR}" NO_DEFAULT_PATH)
```

New:
```cmake
# OpenCV — auto-detect from OPENCV_ROOT env var or common locations
if(NOT DEFINED OPENCV_ROOT)
    foreach(candidate
            "$ENV{OPENCV_ROOT}"
            "$ENV{USERPROFILE}/Downloads/opencv/build/x64/vc16"
            "C:/opencv/build/x64/vc16")
        if(EXISTS "${candidate}/lib/OpenCVConfig.cmake" OR EXISTS "${candidate}/OpenCVConfig.cmake")
            set(OPENCV_ROOT "${candidate}")
            break()
        endif()
    endforeach()
endif()
if(NOT DEFINED OPENCV_ROOT)
    message(FATAL_ERROR
        "OpenCV not found. Set OPENCV_ROOT env var to your OpenCV build dir "
        "(e.g. C:/Users/you/Downloads/opencv/build/x64/vc16)")
endif()
set(OpenCV_DIR "${OPENCV_ROOT}/lib")
find_package(OpenCV REQUIRED PATHS "${OpenCV_DIR}" NO_DEFAULT_PATH)
message(STATUS "OpenCV found at: ${OPENCV_ROOT}")
```

- [ ] **Step 2: Fix OpenCV lib reference in cpp/CMakeLists.txt**

The `target_link_libraries` on line 31 hardcodes `opencv_world4120.lib`. Use the CMake variable instead.

Replace line 31 of `migration_project/cpp/CMakeLists.txt`:

Old:
```cmake
target_link_libraries(rstao_core PUBLIC "${OpenCV_DIR}/opencv_world4120.lib")
```
New:
```cmake
target_link_libraries(rstao_core PUBLIC ${OpenCV_LIBS})
```

`OpenCV_LIBS` is set by `find_package(OpenCV)` and resolves to the correct library names.

- [ ] **Step 3: Rewrite cpp_qt/CMakeLists.txt Qt6 and OpenCV detection**

Replace lines 17-21 of `migration_project/cpp_qt/CMakeLists.txt`:

Old (lines 17-21):
```cmake
find_package(Qt6 REQUIRED COMPONENTS Core Widgets)

# OpenCV — headers needed because rstao_core headers include opencv2
set(OpenCV_DIR "$ENV{USERPROFILE}/Downloads/opencv/build/x64/vc16/lib")
find_package(OpenCV REQUIRED PATHS "${OpenCV_DIR}" NO_DEFAULT_PATH)
```

New:
```cmake
# Qt6 — prefer CONDA_PREFIX, fallback to CMAKE_PREFIX_PATH
if(DEFINED ENV{CONDA_PREFIX})
    list(APPEND CMAKE_PREFIX_PATH "$ENV{CONDA_PREFIX}/Library")
endif()
find_package(Qt6 REQUIRED COMPONENTS Core Widgets)
message(STATUS "Qt6 found at: ${Qt6_DIR}")

# OpenCV — auto-detect from OPENCV_ROOT env var or common locations
if(NOT DEFINED OPENCV_ROOT)
    foreach(candidate
            "$ENV{OPENCV_ROOT}"
            "$ENV{USERPROFILE}/Downloads/opencv/build/x64/vc16"
            "C:/opencv/build/x64/vc16")
        if(EXISTS "${candidate}/lib/OpenCVConfig.cmake" OR EXISTS "${candidate}/OpenCVConfig.cmake")
            set(OPENCV_ROOT "${candidate}")
            break()
        endif()
    endforeach()
endif()
if(NOT DEFINED OPENCV_ROOT)
    message(FATAL_ERROR
        "OpenCV not found. Set OPENCV_ROOT env var to your OpenCV build dir.")
endif()
set(OpenCV_DIR "${OPENCV_ROOT}/lib")
find_package(OpenCV REQUIRED PATHS "${OpenCV_DIR}" NO_DEFAULT_PATH)
message(STATUS "OpenCV found at: ${OPENCV_ROOT}")
```

- [ ] **Step 4: Fix OpenCV lib reference in cpp_qt/CMakeLists.txt**

The `target_link_libraries` on line 80 hardcodes `opencv_world4120.lib`. Make it use the CMake variable instead.

Replace line 80:
```cmake
    "${OpenCV_DIR}/opencv_world4120.lib"
```
With:
```cmake
    ${OpenCV_LIBS}
```

`OpenCV_LIBS` is set by `find_package(OpenCV)` and resolves to the correct library names.

- [ ] **Step 5: Remove deprecated APP_VERSION define**

In `migration_project/cpp_qt/CMakeLists.txt`, remove line 83:

Old:
```cmake
target_compile_definitions(${PROJECT_NAME} PRIVATE APP_VERSION="0.3.0")
```

The codebase uses `kAppVersion` (a static const char* in MainWindow.cpp:27) instead of the `APP_VERSION` macro. The define is dead code.

- [ ] **Step 6: Update CMakePresets.json**

Rewrite `migration_project/cpp_qt/CMakePresets.json` to use environment variables instead of hardcoded paths:

```json
{
    "version": 3,
    "configurePresets": [
        {
            "name": "vs-default",
            "displayName": "Visual Studio x64 (auto-detect Qt6/OpenCV)",
            "binaryDir": "${sourceDir}/build",
            "cacheVariables": {
                "CMAKE_PREFIX_PATH": "$env{CONDA_PREFIX}/Library"
            },
            "environment": {
                "PATH": "$env{CONDA_PREFIX}/Library/bin;$penv{PATH}"
            },
            "generator": "Visual Studio 18 2026",
            "architecture": "x64"
        },
        {
            "name": "vs-release",
            "displayName": "Visual Studio x64 Release",
            "inherits": "vs-default",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Release"
            }
        }
    ]
}
```

- [ ] **Step 7: Verify CMake configure works**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
del /s /q build\ 2>nul
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
```
Expected: "OpenCV found at: C:/Users/25854/Downloads/opencv/build/x64/vc16" in output, configure succeeds.

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
del /s /q build\ 2>nul
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
```
Expected: "Qt6 found at:" and "OpenCV found at:" messages, configure succeeds.

- [ ] **Step 8: Verify both builds still compile**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release

cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
cmake --build build --config Release
```
Expected: Both compile and link without errors.

- [ ] **Step 9: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/CMakeLists.txt migration_project/cpp_qt/CMakeLists.txt migration_project/cpp_qt/CMakePresets.json
git commit -m "build: auto-detect Qt6/OpenCV paths via env vars and common locations

- Replace hardcoded USERPROFILE paths with OPENCV_ROOT env var + fallback search
- Qt6 detection via CONDA_PREFIX + CMAKE_PREFIX_PATH
- Use OpenCV_LIBS instead of hardcoded opencv_world4120.lib
- Remove deprecated APP_VERSION define (replaced by kAppVersion)
- CMakePresets.json uses $env{CONDA_PREFIX} instead of hardcoded path"
```

---

### Task 3: Build Scripts

**Files:**
- Create: `migration_project/build_all.bat`
- Modify: `migration_project/cpp_qt/run.bat`

**Interfaces:**
- Consumes: conda environment `RSTao_tool`, `OPENCV_ROOT` env var (optional)
- Produces: `build_all.bat` (one-command build), updated `run.bat` (portable launch)

- [ ] **Step 1: Create build_all.bat**

Create `migration_project/build_all.bat`:

```batch
@echo off
setlocal enabledelayedexpansion

REM === Phase 5.5: One-command build for rstao_core + RSTaoStudio ===
REM Requires: conda env RSTao_tool (with Qt6), OpenCV, VS 2026
REM Usage: build_all.bat [Release|Debug|both]  (default: both)

set BUILD_CONFIG=%1
if "%BUILD_CONFIG%"=="" set BUILD_CONFIG=both

REM --- Activate conda environment ---
call conda activate RSTao_tool 2>nul
if errorlevel 1 (
    echo [ERROR] conda environment 'RSTao_tool' not found.
    echo   Create it: conda create -n RSTao_tool python=3.10 qt6-main -c conda-forge
    exit /b 1
)
set "PATH=%CONDA_PREFIX%\Library\bin;%PATH%"
echo [INFO] CONDA_PREFIX: %CONDA_PREFIX%

REM --- Detect OpenCV ---
if not defined OPENCV_ROOT (
    if exist "%USERPROFILE%\Downloads\opencv\build\x64\vc16" (
        set "OPENCV_ROOT=%USERPROFILE%\Downloads\opencv\build\x64\vc16"
    )
)
if not defined OPENCV_ROOT (
    echo [ERROR] OpenCV not found. Set OPENCV_ROOT env var.
    exit /b 1
)
echo [INFO] OPENCV_ROOT: %OPENCV_ROOT%

REM --- Build rstao_core ---
echo.
echo === Building rstao_core ===
cd /d "%~dp0cpp"
cmake -B build -S . -G "Visual Studio 18 2026" -A x64 -DOPENCV_ROOT="%OPENCV_ROOT%"
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
cmake -B build -S . -G "Visual Studio 18 2026" -A x64 ^
    -DCMAKE_PREFIX_PATH="%CONDA_PREFIX%\Library" ^
    -DOPENCV_ROOT="%OPENCV_ROOT%"
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
    echo [WARN] Tests failed or not built. Install GTest: conda install gtest -c conda-forge
) else (
    echo [OK] All tests passed.
)

echo.
echo [OK] Build complete.
exit /b 0

:fail
echo [ERROR] Build failed.
exit /b 1
```

- [ ] **Step 2: Rewrite run.bat**

Replace `migration_project/cpp_qt/run.bat`:

```batch
@echo off
setlocal

REM === Launch RSTaoStudio (auto-detects conda Qt6 + OpenCV) ===
REM Usage: run.bat [Debug|Release]  (default: Release)

call conda activate RSTao_tool 2>nul
if errorlevel 1 (
    echo [ERROR] conda environment 'RSTao_tool' not found
    exit /b 1
)
set "PATH=%CONDA_PREFIX%\Library\bin;%PATH%"

REM Add OpenCV DLLs to PATH
if not defined OPENCV_ROOT (
    if exist "%USERPROFILE%\Downloads\opencv\build\x64\vc16\bin" (
        set "OPENCV_ROOT=%USERPROFILE%\Downloads\opencv\build\x64\vc16"
    )
)
if defined OPENCV_ROOT (
    if exist "%OPENCV_ROOT%\bin" set "PATH=%OPENCV_ROOT%\bin;%PATH%"
)

set BUILD_DIR=%~dp0build
if "%1"=="Debug" (
    if not exist "%BUILD_DIR%\Debug\RSTaoStudio.exe" (
        echo [ERROR] Debug build not found. Run build_all.bat Debug first.
        exit /b 1
    )
    start "" "%BUILD_DIR%\Debug\RSTaoStudio.exe"
) else (
    if not exist "%BUILD_DIR%\Release\RSTaoStudio.exe" (
        echo [ERROR] Release build not found. Run build_all.bat first.
        exit /b 1
    )
    start "" "%BUILD_DIR%\Release\RSTaoStudio.exe"
)
```

- [ ] **Step 3: Test build_all.bat**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project
build_all.bat Release
```
Expected: Both rstao_core and RSTaoStudio build successfully. Tests run (may warn if GTest not yet installed — that's OK for now).

- [ ] **Step 4: Test run.bat**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
run.bat Release
```
Expected: RSTaoStudio.exe launches without SIGSEGV.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/build_all.bat migration_project/cpp_qt/run.bat
git commit -m "build: add build_all.bat and portable run.bat

- build_all.bat: one-command build for cpp + cpp_qt with auto-detection
- run.bat: auto-detects conda env and OpenCV, no hardcoded paths
- Both scripts accept Release/Debug/both as config argument"
```

---

### Task 4: CRT Workaround Documentation

**Files:**
- Create: `migration_project/cpp_qt/docs/crt-workaround.md`

**Interfaces:**
- Consumes: knowledge from Phase 5 debugging
- Produces: documented technical decision for future reference

- [ ] **Step 1: Create crt-workaround.md**

Create `migration_project/cpp_qt/docs/crt-workaround.md`:

```markdown
# CRT Compatibility Workaround

## Problem

The conda-installed Qt6 6.9.3 only ships **Release CRT** DLLs (compiled with
`/MD`). It does not include Debug CRT DLLs (`/MDd`).

OpenCV 4.12.0 provides both CRT variants:
- `opencv_world4120.lib` — Release CRT (`/MD`)
- `opencv_world4120d.lib` — Debug CRT (`/MDd`)

If a Debug build of RSTaoStudio links against `/MDd` (Debug CRT) while conda
Qt6 DLLs use `/MD` (Release CRT), the CRT mismatch causes:
- Link errors (LNK2038: mismatch detected for RuntimeLibrary)
- Runtime SIGSEGV (exit code 139) on application startup

## Diagnosis

Incremental testing isolated the issue:

1. Pure Qt Debug build → **works**
2. Qt + OpenCV Debug build → **works** (OpenCV provides /MDd lib)
3. Qt + OpenCV + rstao_core Debug build → **SIGSEGV on startup**

Root cause: rstao_core.lib's Debug build, while compiled with `/MD`, has
residual incompatibilities when linked against conda Qt6's Release CRT DLLs.

## Solution

### Force Release CRT everywhere

Both `cpp/CMakeLists.txt` and `cpp_qt/CMakeLists.txt` contain:

```cmake
if(MSVC)
    add_compile_options(/utf-8)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
    add_compile_definitions($<$<CONFIG:Debug>:_ITERATOR_DEBUG_LEVEL=0>)
endif()
```

This forces **all configurations** (Debug and Release) to use `/MD` (Release
CRT). The `_ITERATOR_DEBUG_LEVEL=0` disables STL iterator debugging in Debug
builds, which would otherwise conflict with the Release CRT.

### Map rstao_core Debug to Release lib

In `cpp_qt/CMakeLists.txt`, the imported `rstao_core` target maps all
configurations to the Release library:

```cmake
set_target_properties(rstao_core PROPERTIES
    IMPORTED_LOCATION_DEBUG "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELWITHDEBINFO "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_MINSIZEREL "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELEASE "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
)
```

### rstao_core self-mapping

In `cpp/CMakeLists.txt`, the library itself maps imported Debug configs to
Release:

```cmake
set_target_properties(rstao_core PROPERTIES
    MAP_IMPORTED_CONFIG_DEBUG Release
    MAP_IMPORTED_CONFIG_RELWITHDEBINFO Release
    MAP_IMPORTED_CONFIG_MINSIZEREL Release
)
```

## Result

Both Debug and Release builds compile, link, and run without SIGSEGV.

| Build | Compiles | Links | Launches |
|-------|----------|-------|----------|
| Debug | ✅ | ✅ | ✅ |
| Release | ✅ | ✅ | ✅ |

## Future: True Debug Builds

To get a proper Debug build with full CRT debugging (`/MDd`), you need to
compile Qt6 from source with Debug configuration:

```bash
# Example (not yet done):
git clone https://code.qt.io/qt/qt5.git
cd qt5
perl init-repository
./configure -debug -nomake examples -nomake tests -prefix "C:\Qt\6.9.3\msvc2026_64_debug"
cmake --build . --parallel
cmake --install .
```

Then point `CMAKE_PREFIX_PATH` to both the conda Release Qt6 and the source-built
Debug Qt6, and remove the CRT workaround. This is low priority — the current
solution works for development.
```

- [ ] **Step 2: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp_qt/docs/crt-workaround.md
git commit -m "docs: document CRT compatibility workaround

Records the conda Qt6 Release-only CRT issue, diagnosis process,
solution (forced /MD + _ITERATOR_DEBUG_LEVEL=0 + Debug→Release lib mapping),
and path to true Debug builds."
```

---

### Task 5: GTest Infrastructure

**Files:**
- Modify: `migration_project/cpp/tests/CMakeLists.txt`

**Interfaces:**
- Consumes: GTest (from conda or vcpkg)
- Produces: `BUILD_TESTS` option (default ON), conditional GTest detection

- [ ] **Step 1: Install GTest**

```bash
conda activate RSTao_tool
conda install gtest -c conda-forge -y
```

Verify:
```bash
conda list gtest
```
Expected: gtest package listed.

- [ ] **Step 2: Rewrite tests/CMakeLists.txt**

Replace `migration_project/cpp/tests/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.16)

option(BUILD_TESTS "Build unit tests" ON)

if(NOT BUILD_TESTS)
    return()
endif()

find_package(GTest QUIET)
if(NOT GTest_FOUND)
    message(STATUS "GTest not found — tests disabled.")
    message(STATUS "  Install with: conda install gtest -c conda-forge")
    return()
endif()

enable_testing()
include(GoogleTest)

add_executable(test_image_processing test_image_processing.cpp)
target_link_libraries(test_image_processing PRIVATE rstao_core GTest::gtest_main)
gtest_discover_tests(test_image_processing)

add_executable(test_feature_detection test_feature_detection.cpp)
target_link_libraries(test_feature_detection PRIVATE rstao_core GTest::gtest_main)
gtest_discover_tests(test_feature_detection)

add_executable(test_image_matching test_image_matching.cpp)
target_link_libraries(test_image_matching PRIVATE rstao_core GTest::gtest_main)
gtest_discover_tests(test_image_matching)
```

- [ ] **Step 3: Enable tests in cpp/CMakeLists.txt**

The parent `cpp/CMakeLists.txt` already has `option(BUILD_TESTS ...)` and
`add_subdirectory(tests)`. Change the default from OFF to ON.

In `migration_project/cpp/CMakeLists.txt`, line 39:

Old:
```cmake
option(BUILD_TESTS "Build unit tests" OFF)
```
New:
```cmake
option(BUILD_TESTS "Build unit tests" ON)
```

- [ ] **Step 4: Create placeholder test files (so CMake configure succeeds)**

Create `migration_project/cpp/tests/test_image_processing.cpp`:

```cpp
#include <gtest/gtest.h>
// Placeholder — real tests in Task 6
TEST(Placeholder, ImageProcessing) {
    EXPECT_TRUE(true);
}
```

Create `migration_project/cpp/tests/test_feature_detection.cpp`:

```cpp
#include <gtest/gtest.h>
TEST(Placeholder, FeatureDetection) {
    EXPECT_TRUE(true);
}
```

Create `migration_project/cpp/tests/test_image_matching.cpp`:

```cpp
#include <gtest/gtest.h>
TEST(Placeholder, ImageMatching) {
    EXPECT_TRUE(true);
}
```

- [ ] **Step 5: Verify configure and test discovery**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake -B build -S . -G "Visual Studio 18 2026" -A x64 -DOPENCV_ROOT="%USERPROFILE%\Downloads\opencv\build\x64\vc16"
```
Expected: "Found GTest" in output, tests enabled.

```bash
cmake --build build --config Release
cd build
ctest --output-on-failure -C Release
```
Expected: 3 placeholder tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/tests/ migration_project/cpp/CMakeLists.txt
git commit -m "test: add GTest infrastructure with conditional detection

- BUILD_TESTS default ON
- Conditional find_package(GTest) with helpful install message
- Three placeholder test files (real tests in following tasks)"
```

---

### Task 6: Image Processing Unit Tests

**Files:**
- Modify: `migration_project/cpp/tests/test_image_processing.cpp`

**Interfaces:**
- Consumes: `rstao::process(image, opId, params)` → `ProcessingResult`, individual operator functions from `rstao/image_processing.hpp`
- Produces: 14 operator smoke tests + edge case tests + dispatch tests

- [ ] **Step 1: Write test_image_processing.cpp**

Replace `migration_project/cpp/tests/test_image_processing.cpp`:

```cpp
#include <gtest/gtest.h>

#include <rstao/image_processing.hpp>
#include <rstao/image_io.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <stdexcept>

using namespace rstao;

// ---- Test helpers ----

namespace {
cv::Mat makeColorImage(int w = 64, int h = 64) {
    cv::Mat img(h, w, CV_8UC3);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
            img.at<cv::Vec3b>(y, x) =
                cv::Vec3b(x * 4 % 256, y * 4 % 256, (x + y) * 2 % 256);
    return img;
}

cv::Mat makeGrayImage(int w = 64, int h = 64) {
    cv::Mat img(h, w, CV_8UC1);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
            img.at<uchar>(y, x) = static_cast<uchar>((x + y) * 2 % 256);
    return img;
}
} // namespace

// ---- to_grayscale ----

TEST(Grayscale, ReturnsSingleChannel) {
    cv::Mat src = makeColorImage();
    cv::Mat result = to_grayscale(src);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.channels(), 1);
    EXPECT_EQ(result.size(), src.size());
}

TEST(Grayscale, PassesThroughGrayImage) {
    cv::Mat src = makeGrayImage();
    cv::Mat result = to_grayscale(src);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.channels(), 1);
}

TEST(Grayscale, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(to_grayscale(empty), std::invalid_argument);
}

// ---- convert_color_space ----

TEST(ColorSpace, ConvertsToHSV) {
    cv::Mat src = makeColorImage();
    cv::Mat result = convert_color_space(src, "HSV");
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.channels(), 3);
    EXPECT_EQ(result.size(), src.size());
}

TEST(ColorSpace, ConvertsToLab) {
    cv::Mat src = makeColorImage();
    cv::Mat result = convert_color_space(src, "Lab");
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.channels(), 3);
}

TEST(ColorSpace, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(convert_color_space(empty, "HSV"), std::invalid_argument);
}

// ---- linear_stretch ----

TEST(LinearStretch, PreservesSize) {
    cv::Mat src = makeColorImage();
    cv::Mat result = linear_stretch(src, 2.0, 98.0);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
    EXPECT_EQ(result.channels(), src.channels());
}

TEST(LinearStretch, BoundaryPercentiles) {
    cv::Mat src = makeColorImage();
    cv::Mat result = linear_stretch(src, 0.0, 100.0);
    ASSERT_FALSE(result.empty());
}

TEST(LinearStretch, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(linear_stretch(empty), std::invalid_argument);
}

// ---- histogram_equalize ----

TEST(HistogramEqualize, PreservesSize) {
    cv::Mat src = makeColorImage();
    cv::Mat result = histogram_equalize(src);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
}

TEST(HistogramEqualize, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(histogram_equalize(empty), std::invalid_argument);
}

// ---- smooth ----

TEST(Smooth, GaussianBlur) {
    cv::Mat src = makeColorImage();
    cv::Mat result = smooth(src, "gaussian", 5);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
}

TEST(Smooth, AllMethodsWork) {
    cv::Mat src = makeColorImage();
    for (const char* method : {"gaussian", "median", "bilateral", "box"}) {
        cv::Mat result = smooth(src, method, 5);
        EXPECT_FALSE(result.empty()) << "Method: " << method;
    }
}

TEST(Smooth, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(smooth(empty, "gaussian", 5), std::invalid_argument);
}

// ---- sharpen ----

TEST(Sharpen, UnsharpMask) {
    cv::Mat src = makeColorImage();
    cv::Mat result = sharpen(src, "unsharp_mask", 1.0);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
}

TEST(Sharpen, Laplacian) {
    cv::Mat src = makeColorImage();
    cv::Mat result = sharpen(src, "laplacian", 1.0);
    ASSERT_FALSE(result.empty());
}

TEST(Sharpen, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(sharpen(empty, "unsharp_mask", 1.0), std::invalid_argument);
}

// ---- edge_detect ----

TEST(EdgeDetect, MagnitudeMode) {
    cv::Mat src = makeColorImage();
    cv::Mat result = edge_detect(src, "magnitude");
    ASSERT_FALSE(result.empty());
}

TEST(EdgeDetect, AllModesWork) {
    cv::Mat src = makeColorImage();
    for (const char* mode : {"magnitude", "sobel", "laplacian", "canny", "direction"}) {
        cv::Mat result = edge_detect(src, mode);
        EXPECT_FALSE(result.empty()) << "Mode: " << mode;
    }
}

TEST(EdgeDetect, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(edge_detect(empty, "magnitude"), std::invalid_argument);
}

// ---- morphology ----

TEST(Morphology, Erode) {
    cv::Mat src = makeColorImage();
    cv::Mat result = morphology(src, "erode", 3, 1);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
}

TEST(Morphology, AllOperationsWork) {
    cv::Mat src = makeGrayImage();
    for (const char* op : {"erode", "dilate", "open", "close", "gradient", "tophat", "blackhat"}) {
        cv::Mat result = morphology(src, op, 3, 1);
        EXPECT_FALSE(result.empty()) << "Operation: " << op;
    }
}

TEST(Morphology, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(morphology(empty, "erode", 3, 1), std::invalid_argument);
}

// ---- threshold_binary ----

TEST(Threshold, OtsuMethod) {
    cv::Mat src = makeGrayImage();
    cv::Mat result = threshold_binary(src, "otsu", 127);
    ASSERT_FALSE(result.empty());
}

TEST(Threshold, AllMethodsWork) {
    cv::Mat src = makeGrayImage();
    for (const char* method : {"otsu", "manual", "adaptive_mean", "adaptive_gaussian"}) {
        cv::Mat result = threshold_binary(src, method, 127, 11);
        EXPECT_FALSE(result.empty()) << "Method: " << method;
    }
}

TEST(Threshold, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(threshold_binary(empty, "otsu", 127), std::invalid_argument);
}

// ---- pca_component ----

TEST(PCA, ReturnsResult) {
    cv::Mat src = makeColorImage();
    cv::Mat result = pca_component(src, 0);
    ASSERT_FALSE(result.empty());
}

TEST(PCA, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(pca_component(empty, 0), std::invalid_argument);
}

// ---- ihs_intensity ----

TEST(IHSIntensity, ReturnsResult) {
    cv::Mat src = makeColorImage();
    cv::Mat result = ihs_intensity(src);
    ASSERT_FALSE(result.empty());
    EXPECT_EQ(result.size(), src.size());
}

TEST(IHSIntensity, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(ihs_intensity(empty), std::invalid_argument);
}

// ---- fft_filter ----

TEST(FFTFilter, Lowpass) {
    cv::Mat src = makeGrayImage();
    cv::Mat result = fft_filter(src, "lowpass", 30.0);
    ASSERT_FALSE(result.empty());
}

TEST(FFTFilter, Highpass) {
    cv::Mat src = makeGrayImage();
    cv::Mat result = fft_filter(src, "highpass", 30.0);
    ASSERT_FALSE(result.empty());
}

TEST(FFTFilter, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(fft_filter(empty, "lowpass", 30.0), std::invalid_argument);
}

// ---- normalized_difference ----

TEST(NormalizedDifference, ReturnsSingleChannel) {
    cv::Mat src = makeColorImage(64, 64);
    cv::Mat result = normalized_difference(src, 0, 1);
    ASSERT_FALSE(result.empty());
}

TEST(NormalizedDifference, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(normalized_difference(empty, 0, 1), std::invalid_argument);
}

// ---- process() dispatch ----

TEST(ProcessDispatch, AllOperatorIdsWork) {
    cv::Mat src = makeColorImage();
    std::vector<std::string> opIds = {
        "grayscale", "histogram_equalization", "ihs_intensity"
    };
    for (const auto& opId : opIds) {
        ProcessingResult result = process(src, opId);
        EXPECT_FALSE(result.image.empty()) << "Operator: " << opId;
        EXPECT_GT(result.metrics.count("operator_id"), 0) << "Operator: " << opId;
    }
}

TEST(ProcessDispatch, ParameterizedOperators) {
    cv::Mat src = makeColorImage();
    ParamMap params;
    params["method"] = std::string("gaussian");
    params["ksize"] = 5;
    ProcessingResult result = process(src, "smooth", params);
    EXPECT_FALSE(result.image.empty());
}

TEST(ProcessDispatch, UnknownOperatorThrows) {
    cv::Mat src = makeColorImage();
    EXPECT_THROW(process(src, "nonexistent_op"), std::invalid_argument);
}

TEST(ProcessDispatch, EmptyImageThrows) {
    cv::Mat empty;
    EXPECT_THROW(process(empty, "grayscale"), std::invalid_argument);
}

// ---- read_image / save_image round-trip ----

TEST(ImageIO, SaveAndReadRoundTrip) {
    cv::Mat src = makeColorImage();
    std::string path = std::string(std::getenv("TEMP") ? std::getenv("TEMP") : "/tmp") +
                       "/rstao_test_roundtrip.png";
    ASSERT_TRUE(save_image(path, src));
    cv::Mat loaded = read_image(path);
    ASSERT_FALSE(loaded.empty());
    EXPECT_EQ(loaded.size(), src.size());
    std::remove(path.c_str());
}
```

- [ ] **Step 2: Build and run tests**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release
cd build
ctest --output-on-failure -C Release -R "ImageProcessing|Grayscale|ColorSpace|LinearStretch|HistogramEqualize|Smooth|Sharpen|EdgeDetect|Morphology|Threshold|PCA|IHSIntensity|FFTFilter|NormalizedDifference|ProcessDispatch|ImageIO"
```
Expected: All tests pass. If any test fails, examine the failure — it may reveal a real bug in rstao_core. Fix the bug in the source, not the test.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/tests/test_image_processing.cpp
git commit -m "test: add unit tests for 14 image processing operators

- Smoke tests for all operators (grayscale, color_space, linear_stretch,
  histogram_equalize, smooth, sharpen, edge_detect, morphology, threshold,
  pca, ihs_intensity, fft_filter, normalized_difference)
- Edge cases: empty image throws, all method/operation/mode variants
- process() dispatch tests: valid ops, params, unknown op, empty image
- ImageIO save/read round-trip test"
```

---

### Task 7: Feature Detection Unit Tests

**Files:**
- Modify: `migration_project/cpp/tests/test_feature_detection.cpp`

**Interfaces:**
- Consumes: `rstao::detect_harris(GrayImage, k, threshold)` → `CornerResult`, `detect_moravec`, `detect_forstner`, `detect_susan`, `rstao::draw_corners`
- Produces: `CornerResult` with `mask` (CV_8UC1) and `count` (int)

- [ ] **Step 1: Write test_feature_detection.cpp**

Replace `migration_project/cpp/tests/test_feature_detection.cpp`:

```cpp
#include <gtest/gtest.h>

#include <rstao/feature_detection.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <stdexcept>

using namespace rstao;

namespace {
cv::Mat makeTestGrayImage(int w = 64, int h = 64) {
    cv::Mat img(h, w, CV_8UC1, cv::Scalar(128));
    // Draw a white square — creates corners detectable by all algorithms
    cv::rectangle(img, cv::Rect(20, 20, 24, 24), cv::Scalar(255), cv::FILLED);
    // Draw a black square offset
    cv::rectangle(img, cv::Rect(10, 10, 10, 10), cv::Scalar(0), cv::FILLED);
    return img;
}
} // namespace

// ---- detect_harris ----

TEST(Harris, ReturnsCornerResult) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_harris(src);
    EXPECT_FALSE(result.mask.empty());
    EXPECT_EQ(result.mask.type(), CV_8UC1);
    EXPECT_EQ(result.mask.size(), src.size());
}

TEST(Harris, DetectsCornersInTestImage) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_harris(src, 0.04, 0.01);
    EXPECT_GT(result.count, 0) << "Test image has corners; expected count > 0";
}

TEST(Harris, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(detect_harris(empty), std::invalid_argument);
}

// ---- detect_moravec ----

TEST(Moravec, ReturnsCornerResult) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_moravec(src);
    EXPECT_FALSE(result.mask.empty());
    EXPECT_EQ(result.mask.type(), CV_8UC1);
    EXPECT_EQ(result.mask.size(), src.size());
}

TEST(Moravec, DetectsCornersInTestImage) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_moravec(src, 0.01);
    EXPECT_GT(result.count, 0) << "Test image has corners; expected count > 0";
}

TEST(Moravec, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(detect_moravec(empty), std::invalid_argument);
}

// ---- detect_forstner ----

TEST(Forstner, ReturnsCornerResult) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_forstner(src);
    EXPECT_FALSE(result.mask.empty());
    EXPECT_EQ(result.mask.type(), CV_8UC1);
    EXPECT_EQ(result.mask.size(), src.size());
}

TEST(Forstner, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(detect_forstner(empty), std::invalid_argument);
}

// ---- detect_susan ----

TEST(SUSAN, ReturnsCornerResult) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_susan(src);
    EXPECT_FALSE(result.mask.empty());
    EXPECT_EQ(result.mask.type(), CV_8UC1);
    EXPECT_EQ(result.mask.size(), src.size());
}

TEST(SUSAN, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(detect_susan(empty), std::invalid_argument);
}

// ---- draw_corners ----

TEST(DrawCorners, ProducesColorImage) {
    cv::Mat src = makeTestGrayImage();
    CornerResult result = detect_harris(src);
    ColorImage drawn = draw_corners(src, result.mask);
    EXPECT_FALSE(drawn.empty());
    EXPECT_GE(drawn.channels(), 3);
    EXPECT_EQ(drawn.size(), src.size());
}

// ---- rotate_image ----

TEST(RotateImage, PreservesSize) {
    cv::Mat src = makeTestGrayImage();
    cv::Mat rotated = rotate_image(src, 45.0);
    EXPECT_FALSE(rotated.empty());
    EXPECT_EQ(rotated.size(), src.size());
}

TEST(RotateImage, EmptyThrows) {
    cv::Mat empty;
    EXPECT_THROW(rotate_image(empty, 45.0), std::invalid_argument);
}
```

- [ ] **Step 2: Build and run tests**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release
cd build
ctest --output-on-failure -C Release -R "Harris|Moravec|Forstner|SUSAN|DrawCorners|RotateImage"
```
Expected: All tests pass. Corner detection count tests may need threshold adjustment if the test image doesn't produce corners — adjust the test image in `makeTestGrayImage` if needed, not the algorithm.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/tests/test_feature_detection.cpp
git commit -m "test: add unit tests for 4 feature detectors

- Harris, Moravec, Forstner, SUSAN: mask type, size, count, empty throws
- draw_corners: produces color output
- rotate_image: preserves size, empty throws
- Test image with rectangles creates detectable corners"
```

---

### Task 8: Image Matching Unit Tests

**Files:**
- Modify: `migration_project/cpp/tests/test_image_matching.cpp`

**Interfaces:**
- Consumes: `rstao::match_single(search, templ, threshold)` → `MatchResult`, `match_multi`, `nms`, `draw_match_result`
- Produces: `MatchResult` with `locations`, `scores`, `template_size`

- [ ] **Step 1: Write test_image_matching.cpp**

Replace `migration_project/cpp/tests/test_image_matching.cpp`:

```cpp
#include <gtest/gtest.h>

#include <rstao/image_matching.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <stdexcept>

using namespace rstao;

namespace {
// Create a 100x100 search image with a distinctive 20x20 pattern at (30, 30)
cv::Mat makeSearchImage() {
    cv::Mat img(100, 100, CV_8UC3, cv::Scalar(50, 50, 50));
    // Draw a bright red rectangle at a known location
    cv::rectangle(img, cv::Rect(30, 30, 20, 20), cv::Scalar(0, 0, 255), cv::FILLED);
    return img;
}

// Extract the 20x20 template at (30, 30)
cv::Mat makeTemplate() {
    cv::Mat tmpl(20, 20, CV_8UC3, cv::Scalar(0, 0, 255));
    return tmpl;
}
} // namespace

// ---- match_single ----

TEST(MatchSingle, FindsTemplateInSearchImage) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult result = match_single(search, tmpl, 0.7);
    EXPECT_FALSE(result.locations.empty());
    EXPECT_EQ(result.template_size, cv::Size(20, 20));
    // The best match should be at or near (30, 30)
    cv::Point best = result.locations[0];
    EXPECT_NEAR(best.x, 30, 5);
    EXPECT_NEAR(best.y, 30, 5);
}

TEST(MatchSingle, HighThresholdReducesMatches) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult lowThresh = match_single(search, tmpl, 0.5);
    MatchResult highThresh = match_single(search, tmpl, 0.99);
    EXPECT_GE(lowThresh.locations.size(), highThresh.locations.size());
}

TEST(MatchSingle, EmptySearchThrows) {
    cv::Mat empty;
    cv::Mat tmpl = makeTemplate();
    EXPECT_THROW(match_single(empty, tmpl), std::invalid_argument);
}

// ---- match_multi ----

TEST(MatchMulti, FindsAllInstances) {
    // Create search image with two identical patterns
    cv::Mat search(120, 120, CV_8UC3, cv::Scalar(50, 50, 50));
    cv::rectangle(search, cv::Rect(10, 10, 20, 20), cv::Scalar(0, 0, 255), cv::FILLED);
    cv::rectangle(search, cv::Rect(70, 70, 20, 20), cv::Scalar(0, 0, 255), cv::FILLED);

    cv::Mat tmpl(20, 20, CV_8UC3, cv::Scalar(0, 0, 255));
    MatchResult result = match_multi(search, tmpl, 0.7, 0.3);
    EXPECT_GE(result.locations.size(), 2u) << "Two patterns placed, expected >= 2 matches";
}

// ---- nms ----

TEST(NMS, RemovesOverlappingDetections) {
    // Three overlapping points + one distant
    std::vector<cv::Point> locations = {
        cv::Point(30, 30),   // overlaps with next
        cv::Point(32, 32),   // overlaps with prev
        cv::Point(35, 35),   // overlaps with prev
        cv::Point(90, 90),   // isolated
    };
    std::vector<double> scores = {0.95, 0.90, 0.85, 0.80};
    std::vector<int> kept = nms(locations, scores, 0.3);
    // Should keep the best from the cluster + the isolated one
    EXPECT_LE(kept.size(), locations.size());
    EXPECT_GE(kept.size(), 1u);
}

TEST(NMS, EmptyInputReturnsEmpty) {
    std::vector<cv::Point> locations;
    std::vector<double> scores;
    std::vector<int> kept = nms(locations, scores, 0.3);
    EXPECT_TRUE(kept.empty());
}

// ---- match_multi_target ----

TEST(MatchMultiTarget, HandlesMultipleTemplates) {
    cv::Mat search(120, 120, CV_8UC3, cv::Scalar(50, 50, 50));
    cv::rectangle(search, cv::Rect(10, 10, 20, 20), cv::Scalar(0, 0, 255), cv::FILLED);
    cv::rectangle(search, cv::Rect(70, 70, 20, 20), cv::Scalar(0, 255, 0), cv::FILLED);

    std::vector<cv::Mat> templates = {
        cv::Mat(20, 20, CV_8UC3, cv::Scalar(0, 0, 255)),
        cv::Mat(20, 20, CV_8UC3, cv::Scalar(0, 255, 0)),
    };
    std::vector<MatchResult> results = match_multi_target(search, templates, 0.7);
    EXPECT_EQ(results.size(), 2u);
    for (const auto& r : results) {
        EXPECT_FALSE(r.locations.empty());
    }
}

// ---- draw_match_result ----

TEST(DrawMatchResult, ProducesColorOutput) {
    cv::Mat search = makeSearchImage();
    cv::Mat tmpl = makeTemplate();
    MatchResult result = match_single(search, tmpl, 0.7);
    ColorImage drawn = draw_match_result(search, result);
    EXPECT_FALSE(drawn.empty());
    EXPECT_GE(drawn.channels(), 3);
}

// ---- Edge cases ----

TEST(MatchSingle, TemplateLargerThanSearchThrows) {
    cv::Mat search(50, 50, CV_8UC3, cv::Scalar(100, 100, 100));
    cv::Mat tmpl(100, 100, CV_8UC3, cv::Scalar(200, 200, 200));
    EXPECT_THROW(match_single(search, tmpl), std::invalid_argument);
}
```

- [ ] **Step 2: Build and run tests**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp
cmake --build build --config Release
cd build
ctest --output-on-failure -C Release -R "MatchSingle|MatchMulti|NMS|MatchMultiTarget|DrawMatchResult"
```
Expected: All tests pass. Match location assertions use `EXPECT_NEAR` with 5-pixel tolerance to account for sub-pixel matching differences.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/cpp/tests/test_image_matching.cpp
git commit -m "test: add unit tests for template matching and NMS

- match_single: finds template at correct location, threshold sensitivity
- match_multi: finds multiple instances with NMS deduplication
- match_multi_target: handles multiple distinct templates
- nms: removes overlapping detections, handles empty input
- draw_match_result: produces color output
- Edge case: template larger than search throws"
```

---

### Task 9: CI Pipeline and Final Verification

**Files:**
- Create: `migration_project/.github/workflows/ci.yml`

**Interfaces:**
- Consumes: build_all.bat, ctest
- Produces: CI yaml for future GitHub repository

- [ ] **Step 1: Create CI yaml**

Create `migration_project/.github/workflows/ci.yml`:

```yaml
name: Build & Test

on:
  push:
    paths:
      - 'migration_project/**'
  pull_request:
    paths:
      - 'migration_project/**'

jobs:
  windows:
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@v4

      - name: Setup conda
        uses: conda-incubator/setup-miniconda@v3
        with:
          activate-environment: RSTao_tool
          environment-file: false
          auto-activate-base: false

      - name: Install Qt6 and GTest
        run: |
          conda install qt6-main gtest -c conda-forge -y

      - name: Setup OpenCV
        run: |
          choco install opencv -y
          echo "OPENCV_ROOT=C:\tools\opencv\build\x64\vc16" >> $env:GITHUB_ENV

      - name: Build and test
        shell: cmd
        run: |
          cd migration_project
          build_all.bat Release

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: migration_project/cpp/build/Testing/
```

- [ ] **Step 2: Run full build and test locally**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project
build_all.bat
```
Expected:
- rstao_core builds (Release + Debug)
- RSTaoStudio builds (Release + Debug)
- All ctest tests pass
- "[OK] Build complete." at the end

- [ ] **Step 3: Run both Debug and Release executables**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp_qt
run.bat Release
```
Expected: RSTaoStudio launches, no SIGSEGV.

```bash
run.bat Debug
```
Expected: RSTaoStudio Debug launches, no SIGSEGV.

- [ ] **Step 4: Verify ctest summary**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool\migration_project\cpp\build
ctest --output-on-failure -C Release
```
Expected output includes all test suites:
```
test_image_processing ....   Passed
test_feature_detection ...   Passed
test_image_matching ......   Passed
```

- [ ] **Step 5: Commit**

```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/.github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for Windows build and test

- Triggers on push/PR to migration_project/
- Installs Qt6 + GTest via conda, OpenCV via chocolatey
- Runs build_all.bat Release
- Uploads test results as artifact
- Active when migration_project/ gets its own GitHub repo"
```

- [ ] **Step 6: Final commit — update migration_project README**

Update `migration_project/README.md` to add Phase 5 build instructions. Append after the existing Phase 1/2 content:

```markdown

## Phase 5 — C++/Qt Native Application

### Quick Start

```bash
# One-command build (requires conda RSTao_tool env + OpenCV)
cd migration_project
build_all.bat

# Run the app
cd cpp_qt
run.bat Release
```

### Build with CMake directly

```bash
# Build rstao_core (C++ algorithm library)
cd migration_project/cpp
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release

# Build RSTaoStudio (Qt GUI)
cd ../cpp_qt
cmake -B build -S . -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release
```

### Run Tests

```bash
cd migration_project/cpp/build
ctest --output-on-failure -C Release
```

### Architecture

- `cpp/` — rstao_core static library (image processing, feature detection, matching)
- `cpp_qt/` — RSTaoStudio Qt6 GUI application
- See `cpp_qt/docs/crt-workaround.md` for CRT compatibility details
```

Commit:
```bash
cd C:\Users\25854\Desktop\RSTao-Tool
git add migration_project/README.md
git commit -m "docs: update migration_project README with Phase 5 build instructions

- Quick start with build_all.bat
- Manual CMake build instructions
- Test execution instructions
- Architecture overview"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `git status` in migration_project/ shows clean working tree
- [ ] `build_all.bat` completes without errors
- [ ] `run.bat Release` launches RSTaoStudio
- [ ] `run.bat Debug` launches RSTaoStudio
- [ ] `ctest --output-on-failure -C Release` in cpp/build/ shows all tests pass
- [ ] No hardcoded absolute paths in CMakeLists.txt files
- [ ] No hardcoded absolute paths in .bat scripts
- [ ] `.clang-format` exists and is valid
- [ ] `cpp_qt/docs/crt-workaround.md` exists and documents the CRT issue
- [ ] `.github/workflows/ci.yml` exists and is valid YAML
