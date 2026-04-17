# main/CMakeLists.txt

# 1. Selecciona la plataforma objetivo: "M5STICKC_PLUS2" o "CUSTOM_BOARD"
set(HARDWARE_TARGET "CUSTOM_BOARD") 

# 2. Asigna dinámicamente el archivo fuente del driver
if(HARDWARE_TARGET STREQUAL "M5STICKC_PLUS2")
    set(IMU_DRIVER "src/mpu6886.c")
else()
    set(IMU_DRIVER "src/mpu6050.c")
endif()

# 3. Registro del componente (se evalúa de forma segura en la primera pasada)
idf_component_register(SRCS "main.c"
                            "src/gap.c"
                            "src/gatt_svc.c"
                            "src/bsp.c"
                            "src/battery.c"
                            "src/accel_buffer.c"
                            ${IMU_DRIVER} 
                       INCLUDE_DIRS "./include"
                       PRIV_REQUIRES bt nvs_flash driver esp_timer esp_driver_gpio esp_adc)

# 4. Inyección de la directiva del preprocesador (se evalúa en la segunda pasada de compilación)
if(HARDWARE_TARGET STREQUAL "M5STICKC_PLUS2")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE TARGET_M5STICKC_PLUS2=1)
else()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE TARGET_M5STICKC_PLUS2=0)
endif()