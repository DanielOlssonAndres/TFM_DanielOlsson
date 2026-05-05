#ifndef MPU6050_H
#define MPU6050_H

#include "esp_err.h"
#include "sys_config.h"
#include "sensor_type.h"

/* Registros MPU6050 */
#define MPU6050_ADDR        0x68 // Dirección I2C por defecto del MPU6050 (cuando AD0 = 0)
#define MPU6050_PWR_MGMT_1  0x6B // Registro para gestión de energía (reset, sleep, selección de reloj)
#define MPU6050_ACCEL_CONFIG 0x1C // Configuración del rango de escala completa del acelerómetro (±2g, ±4g, ±8g, ±16g)
#define MPU6050_ACCEL_XOUT_H 0x3B // Primer registro de datos del acelerómetro (eje X, byte alto). Los siguientes 5 registros contienen el resto (X_L, Y_H, Y_L, Z_H, Z_L)
#define MPU6050_SMPLRT_DIV  0x19 // Divisor de la tasa de muestreo (Sample Rate = Gyro_Rate / (1 + SMPLRT_DIV))
#define MPU6050_CONFIG      0x1A // Configuración del Filtro Pasa Baja Digital (DLPF) y sincronización
#define MPU6050_INT_PIN_CFG 0x37 // Configuración del comportamiento del pin físico de interrupción (nivel activo, push-pull/open-drain, latch)
#define MPU6050_INT_ENABLE  0x38 // Registro para habilitar fuentes de interrupción 

esp_err_t mpu6050_init(void);
esp_err_t mpu6050_read_accel(accel_raw_t *sample);
void mpu6050_clear_interrupt(void);

#endif // MPU6050_H