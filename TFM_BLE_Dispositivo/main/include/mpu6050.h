#ifndef MPU6050_H
#define MPU6050_H

#include "esp_err.h"
#include "sensor_types.h"

esp_err_t mpu6050_init(void);
esp_err_t mpu6050_read_accel(accel_raw_t *sample);
void mpu6050_clear_interrupt(void);

#endif // MPU6050_H