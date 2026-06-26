# RSTao Studio: C++/Qt Migration

This is the native C++/Qt 6 workbench for RSTao. It mirrors the Python Qt
workbench structure while moving the algorithm layer into `migration_project/cpp`.

## Requirements

- Conda environment: `RSTao_tool`
- Qt 6.5+ installed in the conda environment
- CMake 3.16+
- MSVC with C++17 support
- OpenCV with `OpenCVConfig.cmake`

Use environment variables instead of machine-specific paths:

- `CONDA_PREFIX` is set by `conda activate RSTao_tool`
- `OPENCV_ROOT` can point to the OpenCV install root
- `OpenCV_DIR` can point directly to the folder containing `OpenCVConfig.cmake`

## Quick Start

```bat
conda activate RSTao_tool
cd migration_project
build_all.bat Release

cd cpp_qt
run.bat Release
```

`build_all.bat` builds `rstao_core` first, then builds `RSTaoStudio`.

## Manual Build

```bat
conda activate RSTao_tool

cd migration_project\cpp
cmake -B build -S . -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release

cd ..\cpp_qt
cmake -B build -S . -G "Visual Studio 17 2022" -A x64 -DCMAKE_PREFIX_PATH="%CONDA_PREFIX%\Library"
cmake --build build --config Release
```

If your machine uses another generator, either pass it directly to CMake or set:

```bat
set RSTAO_CMAKE_GENERATOR=Visual Studio 17 2022
set RSTAO_CMAKE_ARCH=x64
```

## Troubleshooting

If CMake cannot find Qt, activate `RSTao_tool` first and confirm that
`%CONDA_PREFIX%\Library` exists.

If CMake cannot find OpenCV, set one of:

```bat
set OPENCV_ROOT=C:\path\to\opencv
set OpenCV_DIR=C:\path\to\opencv\build\x64\vc16\lib
```

If `moc.exe`, `rcc.exe`, or `uic.exe` cannot start, make sure
`%CONDA_PREFIX%\Library\bin` is on `PATH`. `build_all.bat` and `run.bat` do this
after activating `RSTao_tool`.

## Structure

```text
cpp_qt/
  CMakeLists.txt
  CMakePresets.json
  README.md
  resources/
    resources.qrc
    theme/
      light.qss
      dark.qss
  src/
    main.cpp
    MainWindow.h / .cpp
    I18n.h / .cpp
    ThemeManager.h / .cpp
    ProjectModel.h / .cpp
    docks/
    workspaces/
    widgets/
    tabs/
```

## Current Features

| Feature | Status |
|---------|--------|
| Main window with dock layout | Done |
| Menus: File, View, Tools, Language, Help | Done |
| Chinese/English bilingual UI | Done |
| Light/Dark theme switching | Done |
| Project create/open/save (`.rstao` JSON) | Done |
| Resource import | Done |
| Project dock tree | Done |
| Layer dock | Placeholder |
| Properties dock | Done |
| Task dock | Placeholder |
| Log dock | Done |
| Welcome workspace | Done |
| Project workspace | Done |
| No toolbar / no page shortcut buttons | Done |
| All commands via menus only | Done |

## Mapping from Python Qt

| Python | C++ |
|--------|-----|
| `ui_qt/app.py` | `src/main.cpp` |
| `ui_qt/main_window.py` | `src/MainWindow.h/.cpp` |
| `ui_qt/i18n.py` | `src/I18n.h/.cpp` |
| `ui_qt/theme/__init__.py` | `src/ThemeManager.h/.cpp` |
| `core/project_manager.py` | `src/ProjectModel.h/.cpp` |
| `ui_qt/docks/project_dock.py` | `src/docks/ProjectDock.h/.cpp` |
| `ui_qt/docks/layer_dock.py` | `src/docks/LayerDock.h/.cpp` |
| `ui_qt/docks/properties_dock.py` | `src/docks/PropertiesDock.h/.cpp` |
| `ui_qt/docks/task_dock.py` | `src/docks/TaskDock.h/.cpp` |
| `ui_qt/docks/log_dock.py` | `src/docks/LogDock.h/.cpp` |
| `ui_qt/workspaces/welcome_workspace.py` | `src/workspaces/WelcomeWorkspace.h/.cpp` |
| `ui_qt/workspaces/project_workspace.py` | `src/workspaces/ProjectWorkspace.h/.cpp` |
| `ui_qt/theme/light.qss` | `resources/theme/light.qss` |
| `ui_qt/theme/dark.qss` | `resources/theme/dark.qss` |
