# RSTao Migration Project

This directory contains staged migration work for the new Qt workbench and the
native C++/Qt application. It stays separate from the current CustomTkinter app
so the stable application can continue to run from `main.py`.

## Phase 1: Python Qt (PySide6)

Current scope:

- PySide6 / Qt 6 preview workbench
- Dock-based desktop shell
- Project create/open/save using the existing project format
- Resource import using the existing resource model
- Chinese/English bilingual UI, default Chinese
- Light/Dark theme, default Light
- All commands via menus only; no toolbar or page shortcut buttons
- Empty central area when no project is open

Run with the `RSTao_tool` conda environment only:

```bash
conda activate RSTao_tool
python migration_project/main_qt.py
```

## Phase 2: C++/Qt Workbench

The native C++/Qt 6 application mirrors the Phase 1 workbench structure. See
[`cpp_qt/README.md`](cpp_qt/README.md) for the detailed build and launch guide.

Feature mapping:

| Python Qt (Phase 1) | C++ Qt (Phase 2) |
|---------------------|------------------|
| `ui_qt/app.py` | `src/main.cpp` |
| `ui_qt/main_window.py` | `src/MainWindow.h/.cpp` |
| `ui_qt/i18n.py` | `src/I18n.h/.cpp` |
| `ui_qt/theme/__init__.py` | `src/ThemeManager.h/.cpp` |
| `core/project_manager.py` | `src/ProjectModel.h/.cpp` |
| `ui_qt/docks/*.py` | `src/docks/*.h/.cpp` |
| `ui_qt/workspaces/*.py` | `src/workspaces/*.h/.cpp` |
| `ui_qt/theme/*.qss` | `resources/theme/*.qss` |

## Phase 5: Engineering Foundation

The C++ code is split into:

- `cpp/`: `rstao_core`, a static algorithm library
- `cpp_qt/`: `RSTaoStudio`, the Qt Widgets application

Requirements:

- Conda environment: `RSTao_tool`
- CMake 3.16+
- MSVC with C++17 support
- Qt 6.5+ in `RSTao_tool`
- OpenCV with `OpenCVConfig.cmake`
- GTest is optional; tests are disabled when GTest is not found

Recommended environment variables:

- `OPENCV_ROOT`: OpenCV install root
- `OpenCV_DIR`: directory containing `OpenCVConfig.cmake`
- `RSTAO_CMAKE_GENERATOR`: optional CMake generator override, default
  `Visual Studio 17 2022`
- `RSTAO_CMAKE_ARCH`: optional architecture override, default `x64`

Quick build:

```bat
conda activate RSTao_tool
cd migration_project
build_all.bat Release
```

Run the native app:

```bat
cd migration_project\cpp_qt
run.bat Release
```

Build with CMake directly:

```bat
conda activate RSTao_tool

cd migration_project\cpp
cmake -B build -S . -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release

cd ..\cpp_qt
cmake -B build -S . -G "Visual Studio 17 2022" -A x64 -DCMAKE_PREFIX_PATH="%CONDA_PREFIX%\Library"
cmake --build build --config Release
```

Run C++ tests:

```bat
cd migration_project\cpp\build
ctest --output-on-failure -C Release
```

See [`cpp_qt/docs/crt-workaround.md`](cpp_qt/docs/crt-workaround.md) for the
CRT compatibility decision used by Debug and Release builds.
