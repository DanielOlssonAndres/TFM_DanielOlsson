#ifndef BSP_H
#define BSP_H

#include <stdbool.h>
#include "sensor_type.h"
#include "esp_err.h"


int bsp_LED_green_init(void);
int bsp_LED_red_init(void);
int bsp_switch_mode_init(void);
int bsp_i2c_init(void);
int bsp_imu_init(void);
int bsp_battery_init(void);
void bsp_init(void);

bool bsp_read_mode_switch(void);
void bsp_set_led_green(bool state);

void bsp_battery_update(void);
uint8_t bsp_battery_get_level(void);

esp_err_t bsp_imu_read_accel(accel_raw_t *sample);
void bsp_imu_clear_interrupt(void);
esp_err_t bsp_imu_register_interrupt(void (*isr_handler)(void*), void* arg);

void bsp_error_check(int error_code);

#endif // BSP_H