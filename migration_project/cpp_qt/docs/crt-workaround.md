# CRT Compatibility Workaround

## Problem

The conda-installed Qt6 packages are built with the Release CRT (`/MD`). They do
not provide Debug CRT (`/MDd`) Qt DLLs.

Some OpenCV distributions provide both CRT variants:

- `opencv_world4120.lib`: Release CRT (`/MD`)
- `opencv_world4120d.lib`: Debug CRT (`/MDd`)

Mixing `/MDd` application or library objects with conda Qt6's `/MD` DLLs can
produce link errors such as `LNK2038` or startup crashes.

## Current Decision

Both `cpp/CMakeLists.txt` and `cpp_qt/CMakeLists.txt` force all configurations
to use the Release CRT:

```cmake
if(MSVC)
    add_compile_options(/utf-8)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
    add_compile_definitions($<$<CONFIG:Debug>:_ITERATOR_DEBUG_LEVEL=0>)
endif()
```

`cpp_qt/CMakeLists.txt` also maps Debug and other non-Release configurations to
the Release `rstao_core.lib`:

```cmake
set_target_properties(rstao_core PROPERTIES
    IMPORTED_LOCATION_DEBUG "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELWITHDEBINFO "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_MINSIZEREL "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELEASE "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
)
```

The CMake files prefer a Release `opencv_world` library when it is available.
When no `opencv_world` library is found, they fall back to `${OpenCV_LIBS}` from
`find_package(OpenCV)`.

## Result

Debug and Release builds use the same CRT family. This keeps the conda Qt6
runtime, OpenCV, `rstao_core`, and `RSTaoStudio` consistent.

## Future True Debug Builds

To use full Debug CRT behavior (`/MDd`), Qt6, OpenCV, `rstao_core`, and
`RSTaoStudio` must all be built with compatible Debug CRT settings. Until that
toolchain is maintained, keep this workaround in place.
