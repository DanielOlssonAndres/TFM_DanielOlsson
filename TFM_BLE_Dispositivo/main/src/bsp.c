#include "bsp.h"
#include "sys_config.h"
#include "driver/gpio.h"
#include "driver/i2c.h" 
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "battery.h"
#include "mpu6050.h"

/* Configuración del LED verde */
int bsp_LED_green_init(void){ 
    if(gpio_reset_pin(PIN_LED_GREEN) != ESP_OK) { return 1; }
    if(gpio_set_direction(PIN_LED_GREEN, GPIO_MODE_OUTPUT) != ESP_OK) { return 1; }
    if(gpio_set_level(PIN_LED_GREEN, 0) != ESP_OK) { return 1; }
    return 0;
}

/* Configuración del LED rojo */
int bsp_LED_red_init(void){ 
    if(gpio_reset_pin(PIN_LED_RED) != ESP_OK) { return 2; }
    if(gpio_set_direction(PIN_LED_RED, GPIO_MODE_OUTPUT) != ESP_OK) { return 2; }
    if(gpio_set_level(PIN_LED_RED, 0) != ESP_OK) { return 2; }
    return 0;
}

/* Configuración del switch de modo */
int bsp_switch_mode_init(void){
    if(gpio_reset_pin(PIN_MODE_SWITCH) != ESP_OK) { return 3; }
    if(gpio_set_direction(PIN_MODE_SWITCH, GPIO_MODE_INPUT) != ESP_OK) { return 3; }
    if(gpio_set_pull_mode(PIN_MODE_SWITCH, GPIO_PULLUP_ONLY) != ESP_OK) { return 3; }
    return 0;
}

/* Configuración del bus I2C */
int bsp_i2c_init(void) {
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = I2C_MASTER_SDA_IO,
        .scl_io_num = I2C_MASTER_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_MASTER_FREQ_HZ,
    };
    if(i2c_param_config(I2C_MASTER_NUM, &conf) != ESP_OK) { return 4; }
    if(i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0) != ESP_OK) { return 4; }
    return 0;
}

/* Inicialización del módulo MPU6050 */
int bsp_imu_init(void) {
    if(mpu6050_init() != ESP_OK) { return 5; }
    return 0;
}

/* Configuración del sistema de lectura de batería */
int bsp_battery_init(void) {
    if(battery_init() != ESP_OK) { return 6; }
    return 0;
}

void bsp_init(void) {

    /* Configuración del LED verde */
    bsp_error_check(bsp_LED_green_init());

    /* Configuración del LED rojo */
    bsp_error_check(bsp_LED_red_init());

    /* Configuración del switch de modo */
    bsp_error_check(bsp_switch_mode_init());

    /* Configuración del bus I2C */
    bsp_error_check(bsp_i2c_init());
    
    /* Inicialización del módulo IMU - IMPORTANTE después de inicializar el bus I2C */
    bsp_error_check(bsp_imu_init());

    /* Configuración del sistema de lectura de batería */
    bsp_error_check(bsp_battery_init());
}

bool bsp_read_mode_switch(void) {
    int level = gpio_get_level(PIN_MODE_SWITCH);
    return (level == 1); 
}

void bsp_set_led_green(bool state) {
    gpio_set_level(PIN_LED_GREEN, state ? 1 : 0);
}

void bsp_battery_update(void) {
    battery_update();
}

uint8_t bsp_battery_get_level(void) {
    return battery_get_level();
}

esp_err_t bsp_imu_read_accel(accel_raw_t *sample) {
    return mpu6050_read_accel(sample);
}

void bsp_imu_clear_interrupt(void) {
    mpu6050_clear_interrupt();
}

esp_err_t bsp_imu_register_interrupt(void (*isr_handler)(void*), void* arg) {
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_POSEDGE, 
        .pin_bit_mask = (1ULL << PIN_IMU_INT),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = 0,
        .pull_down_en = 1 
    };
    gpio_config(&io_conf);
    
    esp_err_t err = gpio_install_isr_service(0); 
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }

    return gpio_isr_handler_add(PIN_IMU_INT, isr_handler, arg);
}

void bsp_error_check(int error_code) { 
    switch(error_code){
        case 1:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL LED VERDE");
            break;
        case 2:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL LED ROJO");
            break;
        case 3:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL SWITCH DE MODO");
            break;
        case 4:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL BUS I2C");
            break;
        case 5:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL MÓDULO IMU");
            break;
        case 6:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL SISTEMA DE LECTURA DE BATERÍA");
            break;
        case 7:
            ESP_LOGE("BSP", "ERROR: FALLO AL INSTANCIAR EL GESTOR DE DATOS");
            break;
        case 8:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DE NVS");
            break;
        case 9:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DE NIMBLE");
            break;
        case 10:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL SERVICIO GAP");
            break;
        case 11:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INICIALIZACIÓN DEL SERVICIO GATT");
            break;
        case 12:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA INSTALACIÓN DEL SERVICIO DE INTERRUPCIONES GPIO");
            break;
        case 13:
            ESP_LOGE("BSP", "ERROR: FALLO EN LA ASIGNACIÓN DEL MANEJADOR DE INTERRUPCIONES GPIO");
            break;  
        default:
            ESP_LOGI("BSP", "INICIALIZACIÓN BSP COMPLETADA CON ÉXITO");
            break;
    }

    /* Se queda pillado en un bucle infinito en caso de error*/
    if(error_code != 0) {
        if(error_code != 1 && error_code != 2) {
            gpio_set_level(PIN_LED_RED, 1);   
            gpio_set_level(PIN_LED_GREEN, 0);
        }
        while(1) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    else{
        gpio_set_level(PIN_LED_RED, 0);   
        gpio_set_level(PIN_LED_GREEN, 0);
    }
}