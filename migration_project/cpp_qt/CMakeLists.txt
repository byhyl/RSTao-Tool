cmake_minimum_required(VERSION 3.16)
if(POLICY CMP0144)
    cmake_policy(SET CMP0144 NEW)
endif()
project(RSTaoStudio VERSION 0.3.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

# UTF-8, force Release CRT (conda Qt6/OpenCV are /MD only).
if(MSVC)
    add_compile_options(/utf-8)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
    add_compile_definitions($<$<CONFIG:Debug>:_ITERATOR_DEBUG_LEVEL=0>)
endif()

# Qt6: prefer CONDA_PREFIX, fallback to CMAKE_PREFIX_PATH.
if(DEFINED ENV{CONDA_PREFIX})
    list(APPEND CMAKE_PREFIX_PATH "$ENV{CONDA_PREFIX}/Library")
endif()
find_package(Qt6 REQUIRED COMPONENTS Core Widgets)
message(STATUS "Qt6 found at: ${Qt6_DIR}")

# OpenCV: prefer explicit variables, then conda and common install roots.
if(NOT DEFINED OpenCV_DIR AND DEFINED ENV{OpenCV_DIR})
    set(OpenCV_DIR "$ENV{OpenCV_DIR}")
endif()

set(RSTAO_OPENCV_SEARCH_ROOTS)
if(DEFINED OPENCV_ROOT)
    list(APPEND RSTAO_OPENCV_SEARCH_ROOTS "${OPENCV_ROOT}")
endif()
if(DEFINED ENV{OPENCV_ROOT})
    list(APPEND RSTAO_OPENCV_SEARCH_ROOTS "$ENV{OPENCV_ROOT}")
endif()
if(DEFINED ENV{CONDA_PREFIX})
    list(APPEND RSTAO_OPENCV_SEARCH_ROOTS "$ENV{CONDA_PREFIX}/Library")
endif()
list(APPEND RSTAO_OPENCV_SEARCH_ROOTS
    "C:/opencv/build/x64/vc16"
    "C:/opencv/build"
    "C:/opencv"
)

if(NOT DEFINED OpenCV_DIR)
    foreach(candidate IN LISTS RSTAO_OPENCV_SEARCH_ROOTS)
        foreach(suffix "" "lib" "lib/cmake/opencv4" "x64/vc16/lib")
            if(suffix STREQUAL "")
                set(config_dir "${candidate}")
            else()
                set(config_dir "${candidate}/${suffix}")
            endif()
            if(EXISTS "${config_dir}/OpenCVConfig.cmake")
                set(OpenCV_DIR "${config_dir}" CACHE PATH "OpenCV config directory" FORCE)
                set(OPENCV_ROOT "${candidate}" CACHE PATH "OpenCV install root" FORCE)
                break()
            endif()
        endforeach()
        if(DEFINED OpenCV_DIR)
            break()
        endif()
    endforeach()
endif()

if(NOT DEFINED OpenCV_DIR OR NOT EXISTS "${OpenCV_DIR}/OpenCVConfig.cmake")
    message(FATAL_ERROR
        "OpenCV not found. Set OPENCV_ROOT to an OpenCV install root or "
        "OpenCV_DIR to the directory containing OpenCVConfig.cmake.")
endif()

find_package(OpenCV REQUIRED CONFIG PATHS "${OpenCV_DIR}" NO_DEFAULT_PATH)
message(STATUS "OpenCV config: ${OpenCV_DIR}")

# CRT workaround: prefer the Release opencv_world library in all configs.
set(RSTAO_OPENCV_LIBRARY_HINTS "${OpenCV_DIR}")
if(DEFINED OPENCV_ROOT)
    list(APPEND RSTAO_OPENCV_LIBRARY_HINTS
        "${OPENCV_ROOT}"
        "${OPENCV_ROOT}/lib"
        "${OPENCV_ROOT}/x64/vc16/lib"
    )
endif()
if(DEFINED ENV{CONDA_PREFIX})
    list(APPEND RSTAO_OPENCV_LIBRARY_HINTS "$ENV{CONDA_PREFIX}/Library/lib")
endif()

find_library(RSTAO_OPENCV_WORLD_LIB
    NAMES opencv_world4120 opencv_world
    PATHS ${RSTAO_OPENCV_LIBRARY_HINTS}
    NO_DEFAULT_PATH
)
if(RSTAO_OPENCV_WORLD_LIB)
    set(RSTAO_OPENCV_LINK_LIBS "${RSTAO_OPENCV_WORLD_LIB}")
    message(STATUS "OpenCV link library: ${RSTAO_OPENCV_WORLD_LIB}")
else()
    set(RSTAO_OPENCV_LINK_LIBS ${OpenCV_LIBS})
    message(STATUS "OpenCV link libraries: ${OpenCV_LIBS}")
endif()

add_library(rstao_core STATIC IMPORTED)
set(RSTAO_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../cpp/build")

# Debug maps to the Release rstao_core library to keep the CRT consistent.
set_target_properties(rstao_core PROPERTIES
    IMPORTED_LOCATION_DEBUG "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELWITHDEBINFO "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_MINSIZEREL "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION_RELEASE "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    IMPORTED_LOCATION "${RSTAO_LIB_DIR}/Release/rstao_core.lib"
    INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/../cpp/include;${OpenCV_INCLUDE_DIRS}"
)

set(SOURCES
    src/main.cpp
    src/MainWindow.cpp
    src/I18n.cpp
    src/ThemeManager.cpp
    src/ProjectModel.cpp
    src/docks/ProjectDock.cpp
    src/docks/LayerDock.cpp
    src/docks/PropertiesDock.cpp
    src/docks/TaskDock.cpp
    src/docks/LogDock.cpp
    src/workspaces/WelcomeWorkspace.cpp
    src/workspaces/ProjectWorkspace.cpp
    src/widgets/RasterViewerWidget.cpp
    src/widgets/ComparisonView.cpp
    src/widgets/OperatorChainWidget.cpp
    src/tabs/ImageProcessingTab.cpp
    src/tabs/OperatorRegistry.cpp
    src/core/HistoryStack.cpp
    src/core/PresetManager.cpp
)

set(HEADERS
    src/MainWindow.h
    src/I18n.h
    src/ThemeManager.h
    src/ProjectModel.h
    src/docks/ProjectDock.h
    src/docks/LayerDock.h
    src/docks/PropertiesDock.h
    src/docks/TaskDock.h
    src/docks/LogDock.h
    src/workspaces/WelcomeWorkspace.h
    src/workspaces/ProjectWorkspace.h
    src/widgets/RasterViewerWidget.h
    src/widgets/ComparisonView.h
    src/widgets/OperatorChainWidget.h
    src/tabs/ImageProcessingTab.h
    src/tabs/OperatorRegistry.h
    src/core/HistoryStack.h
    src/core/PresetManager.h
)

set(RESOURCES
    resources/resources.qrc
)

add_executable(${PROJECT_NAME} ${SOURCES} ${HEADERS} ${RESOURCES})

target_include_directories(${PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)

target_link_libraries(${PROJECT_NAME} PRIVATE
    Qt6::Core
    Qt6::Widgets
    rstao_core
    ${RSTAO_OPENCV_LINK_LIBS}
)

if(WIN32)
    set_target_properties(${PROJECT_NAME} PROPERTIES WIN32_EXECUTABLE TRUE)
endif()
