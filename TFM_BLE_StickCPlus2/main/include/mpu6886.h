#ifndef MPU6886_H
#define MPU6886_H

#include "esp_err.h"
#include "sensor_type.h"

// Registros MPU6886
#define MPU6886_ADDR          0x68
#define MPU6886_WHO_AM_I      0x75 
#define MPU6886_PWR_MGMT_1    0x6B
#define MPU6886_ACCEL_CONFIG  0x1C
#define MPU6886_ACCEL_XOUT_H  0x3B
#define MPU6886_SMPLRT_DIV    0x19
#define MPU6886_CONFIG        0x1A

esp_err_t mpu6886_init(void);
esp_err_t mpu6886_read_accel(accel_raw_t *sample);
void mpu6886_clear_interrupt(void);

#endif