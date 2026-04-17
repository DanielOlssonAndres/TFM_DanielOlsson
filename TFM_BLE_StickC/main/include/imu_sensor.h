#ifndef IMU_SENSOR_H
#define IMU_SENSOR_H

#include "esp_err.h"
#include "sensor_types.h"

esp_err_t imu_init(void);
esp_err_t imu_read_accel(accel_raw_t *sample);
void imu_clear_interrupt(void);

#endif // IMU_SENSOR_H