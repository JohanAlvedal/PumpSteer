idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    REQUIRES pumpsteer_core ble_sensors esp_timer nvs_flash
)
