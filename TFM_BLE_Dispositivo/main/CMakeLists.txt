file(GLOB_RECURSE srcs "main.c" "src/*.c")

idf_component_register(SRCS "main.c"
                            "src/accel.c"
                            "src/gap.c"
                            "src/gatt_svc.c"
                            "src/battery.c"
                       INCLUDE_DIRS "./include"
                       PRIV_REQUIRES bt nvs_flash driver esp_timer esp_driver_gpio esp_adc)