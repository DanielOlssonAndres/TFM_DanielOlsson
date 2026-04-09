#ifndef SYS_CONFIG_H
#define SYS_CONFIG_H

#include "hal/adc_types.h"

/* --- CONFIGURACIÓN GENERAL --- */
#define DEVICE_NAME "D2526_P1" 
#define MAX_CONNECTIONS 4
#define SAMPLES_PER_PACKET 25 /* Muestras por paquete BLE/IA */

/* --- CONFIGURACIÓN DE TAREAS (OS) --- */
#define PRIO_NIMBLE_HOST   5
#define PRIO_ACCEL_TASK    4
#define PRIO_BLE_SEND      3
#define PRIO_BATT_TASK     2

#define STACK_SIZE_NIMBLE  4096
#define STACK_SIZE_ACCEL   4096
#define STACK_SIZE_SEND    4096
#define STACK_SIZE_BATT    2048

/* --- DEFINICIÓN DE PINES (GPIO) --- */
#define PIN_MODE_SWITCH    13
#define PIN_LED_GREEN      26
#define PIN_LED_RED        27
#define PIN_MPU_INT        25

/* --- CONFIGURACIÓN DE BATERÍA (Hardware) --- */
#define BATT_ADC_UNIT        ADC_UNIT_1
#define PIN_BATT_ADC         34 /* Canal 6 del ADC1 */
#define BATT_MAX_VOLTAGE_MV  4200
#define BATT_MIN_VOLTAGE_MV  3300
#define BATT_UPDATE_MS       10000 /* Lectura cada 10s */

/* --- CONFIGURACIÓN DE BUSES (I2C) --- */
#define I2C_MASTER_NUM       0
#define I2C_MASTER_SDA_IO    32
#define I2C_MASTER_SCL_IO    33
#define I2C_MASTER_FREQ_HZ   400000

/* --- CONFIGURACIÓN BLE --- */
#define BLE_ADV_ITVL_MIN_MS  500
#define BLE_ADV_ITVL_MAX_MS  510
#define BLE_CONN_ITVL_MIN    80   /* 100 ms (80 * 1.25) */
#define BLE_CONN_ITVL_MAX    160  /* 200 ms (160 * 1.25) */
#define BLE_CONN_TIMEOUT     200  /* 2 segundos (200 * 10ms) */

#endif // SYS_CONFIG_H