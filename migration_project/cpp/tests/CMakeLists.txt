cmake_minimum_required(VERSION 3.16)

option(BUILD_TESTS "Build unit tests" ON)

if(NOT BUILD_TESTS)
    return()
endif()

find_package(GTest QUIET)
if(NOT GTest_FOUND)
    message(STATUS "GTest not found; tests disabled.")
    message(STATUS "  Install with: conda install gtest -c conda-forge")
    return()
endif()

include(GoogleTest)

add_executable(test_image_processing test_image_processing.cpp)
target_link_libraries(test_image_processing PRIVATE rstao_core GTest::gtest_main ${RSTAO_OPENCV_LINK_LIBS})
gtest_discover_tests(test_image_processing)

add_executable(test_feature_detection test_feature_detection.cpp)
target_link_libraries(test_feature_detection PRIVATE rstao_core GTest::gtest_main ${RSTAO_OPENCV_LINK_LIBS})
gtest_discover_tests(test_feature_detection)

add_executable(test_image_matching test_image_matching.cpp)
target_link_libraries(test_image_matching PRIVATE rstao_core GTest::gtest_main ${RSTAO_OPENCV_LINK_LIBS})
gtest_discover_tests(test_image_matching)
