cmake_minimum_required(VERSION 3.16)
project(pumpsteer_mini_host_tests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()

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

add_test(NAME core COMMAND pumpsteer_mini_core_test)

add_executable(
    pumpsteer_mini_bthome_test
    bthome_test.cpp
    ../components/ble_sensors/bthome.cpp
)

target_include_directories(
    pumpsteer_mini_bthome_test
    PRIVATE ../components/ble_sensors/include
)

add_test(NAME bthome COMMAND pumpsteer_mini_bthome_test)

add_executable(
    pumpsteer_mini_sensor_registry_test
    sensor_registry_test.cpp
    ../components/ble_sensors/sensor_registry.cpp
)

target_include_directories(
    pumpsteer_mini_sensor_registry_test
    PRIVATE ../components/ble_sensors/include
)

add_test(NAME sensor_registry COMMAND pumpsteer_mini_sensor_registry_test)

add_executable(
    pumpsteer_mini_thermal_learning_test
    thermal_learning_test.cpp
    ../components/thermal_learning/thermal_learning.cpp
)

target_include_directories(
    pumpsteer_mini_thermal_learning_test
    PRIVATE ../components/thermal_learning/include
)

add_test(NAME thermal_learning COMMAND pumpsteer_mini_thermal_learning_test)
