#include "bsp.h"
#include "sys_config.h"
#include "driver/gpio.h"
#include "driver/i2c.h" 
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void bsp_init(void) {
    /* Configuración de LEDs */
    gpio_reset_pin(PIN_LED_GREEN);
    gpio_set_direction(PIN_LED_GREEN, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_LED_GREEN, 0); 

    gpio_reset_pin(PIN_LED_RED);
    gpio_set_direction(PIN_LED_RED, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_LED_RED, 0); 

    /* Configuración de Switch */
    gpio_reset_pin(PIN_MODE_SWITCH);
    gpio_set_direction(PIN_MODE_SWITCH, GPIO_MODE_INPUT);
    gpio_set_pull_mode(PIN_MODE_SWITCH, GPIO_PULLUP_ONLY);

    /* Configuración del bus I2C compartida */
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = I2C_MASTER_SDA_IO,
        .scl_io_num = I2C_MASTER_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_MASTER_FREQ_HZ,
    };
    i2c_param_config(I2C_MASTER_NUM, &conf);
    esp_err_t err = i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0);
    if (err != ESP_OK) {
        bsp_system_halt_error("I2C_BUS");
    }
}

bool bsp_read_mode_switch(void) {
    int level = gpio_get_level(PIN_MODE_SWITCH);
    ESP_LOGI("BSP", "Estado del Switch (GPIO %d): %d", PIN_MODE_SWITCH, level);
    return (level == 1); 
}

void bsp_set_led_green(bool state) {
    gpio_set_level(PIN_LED_GREEN, state ? 1 : 0);
}

void bsp_system_halt_error(const char* module) {
    gpio_set_level(PIN_LED_RED, 1);   
    gpio_set_level(PIN_LED_GREEN, 0); 
    ESP_LOGE("BSP", "FALLO CRÍTICO EN MÓDULO: %s. SISTEMA DETENIDO.", module);
    
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}