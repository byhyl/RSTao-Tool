cmake_minimum_required(VERSION 3.16)
if(POLICY CMP0144)
    cmake_policy(SET CMP0144 NEW)
endif()
project(rstao_core VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# UTF-8, force Release CRT (conda Qt6/OpenCV are /MD only).
if(MSVC)
    add_compile_options(/utf-8)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
    add_compile_definitions($<$<CONFIG:Debug>:_ITERATOR_DEBUG_LEVEL=0>)
endif()

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

add_library(rstao_core STATIC
    src/image_processing.cpp
    src/feature_detection.cpp
    src/image_matching.cpp
    src/image_io.cpp
)

target_include_directories(rstao_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(rstao_core PUBLIC ${RSTAO_OPENCV_LINK_LIBS})

option(BUILD_TESTS "Build unit tests" ON)
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
