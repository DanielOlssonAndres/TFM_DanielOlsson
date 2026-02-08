file(GLOB_RECURSE srcs "main.c" "src/*.c")

idf_component_register(SRCS "${srcs}"
                       INCLUDE_DIRS "./include"
                       PRIV_REQUIRES bt nvs_flash driver esp_timer esp_driver_gpio)