#include "bsp.h"
#include "sys_config.h"
#include "driver/gpio.h"
#include "driver/i2c.h"
#include "freertos/FreeRTOS.h"
#include "esp_timer.h" 
#include "esp_log.h" 

#include "mpu6886.h"
#include "battery.h"

/* ---------- Simulación de ISR para el StickC-Plus2 ---------- */
static esp_timer_handle_t imu_timer = NULL; 
static void (*imu_isr_proxy)(void*) = NULL;

static void imu_timer_callback(void* arg) { 
    if (imu_isr_proxy) { imu_isr_proxy(NULL); }
}

/* ----------------------------------------------------------- */

/* Configuración del LED verde */
int bsp_LED_green_init(void){ 
    return 0; // No disponible en StickC-Plus2
}

/* Configuración del LED rojo */
int bsp_LED_red_init(void){ 
    if(gpio_reset_pin(PIN_LED_RED) != ESP_OK) { return 2; }
    if(gpio_set_direction(PIN_LED_RED, GPIO_MODE_OUTPUT) != ESP_OK) { return 2; }
    if(gpio_set_level(PIN_LED_RED, 1) != ESP_OK) { return 2; } 
    return 0;
}

/* Configuración del switch de modo */
int bsp_switch_mode_init(void){
    return 0; // No disponible en StickC-Plus2
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

/* Inicialización del módulo IMU */
int bsp_imu_init(void) {
    if(mpu6886_init() != ESP_OK) { return 5; }
    return 0;
}

/* Configuración del sistema de lectura de batería */
int bsp_battery_init(void) {
    if(battery_init() != ESP_OK) { return 6; }
    return 0;
}

void bsp_init(void) {

    /* POWER HOLD: Obligatorio para StickC-Plus2 */
    gpio_reset_pin(PIN_POWER_HOLD);
    gpio_set_direction(PIN_POWER_HOLD, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_POWER_HOLD, 1); // Mantener alimentación alta

    /* Configuración del LED rojo */
    bsp_error_check(bsp_LED_red_init());

    /* Configuración del bus I2C */
    bsp_error_check(bsp_i2c_init());
    
    /* Inicialización del módulo IMU - IMPORTANTE después de inicializar el bus I2C */
    bsp_error_check(bsp_imu_init());

    /* Configuración del sistema de lectura de batería */
    bsp_error_check(bsp_battery_init());
}

bool bsp_read_mode_switch(void) {
    return false; // Siempre en multi-link mode
}

void bsp_set_led_green(bool state) {
    // No disponible en StickC-Plus2
    // Hacemos la lógica con el LED rojo
    gpio_set_level(PIN_LED_RED, state ? 0 : 1);
}

void bsp_battery_update(void) {
    battery_update();
}

uint8_t bsp_battery_get_level(void) {
    return battery_get_level();
}

esp_err_t bsp_imu_read_accel(accel_raw_t *sample) {
    return mpu6886_read_accel(sample);
}

void bsp_imu_clear_interrupt(void) {
    mpu6886_clear_interrupt();
}

esp_err_t bsp_imu_register_interrupt(void (*isr_handler)(void*), void* arg) {
    imu_isr_proxy = isr_handler;
    
    const esp_timer_create_args_t timer_args = {
        .callback = &imu_timer_callback,
        .name = "IMU_HW_TIMER"
    };
    
    esp_err_t err = esp_timer_create(&timer_args, &imu_timer);
    if (err != ESP_OK) return err;
    
    // 20000 microsegundos = 20 ms = 50Hz 
    return esp_timer_start_periodic(imu_timer, 20000); 
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
            gpio_set_level(PIN_LED_RED, 0);        }
        while(1) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    else{
        gpio_set_level(PIN_LED_RED, 1);   
    }
}