#include "bsp.h"
#include "sys_config.h"
#include "driver/gpio.h"
#include "driver/i2c.h" 
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void bsp_init(void) {
#if TARGET_M5STICKC_PLUS2
    /* CRÍTICO: Enclavamiento de energía interno del M5Stick */
    gpio_reset_pin(PIN_POWER_HOLD);
    gpio_set_direction(PIN_POWER_HOLD, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_POWER_HOLD, 1);
    
    /* Se omite de forma intencionada la inicialización del PIN_MODE_SWITCH 
     * y cualquier pin de reset externo en esta plataforma. */
#else
    /* LEDs específicos de hardware custom */
    gpio_reset_pin(PIN_LED_GREEN);
    gpio_set_direction(PIN_LED_GREEN, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_LED_GREEN, 0); 

    gpio_reset_pin(PIN_LED_RED);
    gpio_set_direction(PIN_LED_RED, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_LED_RED, 0); 

    /* Switch de modo y Reset (Solo hardware custom) */
    gpio_reset_pin(PIN_MODE_SWITCH);
    gpio_set_direction(PIN_MODE_SWITCH, GPIO_MODE_INPUT);
    gpio_set_pull_mode(PIN_MODE_SWITCH, GPIO_PULLUP_ONLY);
#endif

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
        ESP_LOGE("BSP", "Fallo al iniciar I2C");
    }
}

bool bsp_read_mode_switch(void) {
#if TARGET_M5STICKC_PLUS2
    /* Hardware comercial: Fuerza siempre Multi-Link (falso) independientemente de los GPIOs */
    return false;
#else
    /* Hardware custom: Lee el estado físico del botón */
    return (gpio_get_level(PIN_MODE_SWITCH) == 0);
#endif
}

void bsp_set_led_green(bool state) {
#if !TARGET_M5STICKC_PLUS2
    gpio_set_level(PIN_LED_GREEN, state ? 1 : 0);
#endif
}

void bsp_system_halt_error(const char *msg) {
    ESP_LOGE("HALT", "System Halt: %s", msg);
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}