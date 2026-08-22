cmake_minimum_required(VERSION 3.16)
project(pumpsteer_mini_host_tests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(
    pumpsteer_mini_core_test
    core_test.cpp
    ../components/pumpsteer_core/controller.cpp
    ../components/pumpsteer_core/pi_controller.cpp
)

target_include_directories(
    pumpsteer_mini_core_test
    PRIVATE ../components/pumpsteer_core/include
)
