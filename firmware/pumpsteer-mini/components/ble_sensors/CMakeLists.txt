idf_component_register(
    SRCS
        "bthome.cpp"
        "sensor_registry.cpp"
        "ble_scanner.cpp"
    INCLUDE_DIRS "include"
    REQUIRES bt esp_timer
)
