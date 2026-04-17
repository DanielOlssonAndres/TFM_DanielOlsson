#ifndef SYS_CONFIG_H
#define SYS_CONFIG_H

#include "hal/adc_types.h"

/* --- SELECTOR DE PLATAFORMA --- */
/* (La macro TARGET_M5STICKC_PLUS2 viene inyectada desde CMakeLists.txt) */

#define DEVICE_NAME "D2526_P3"

#if TARGET_M5STICKC_PLUS2    
    /* Pines M5StickC Plus 2 */
    #define PIN_POWER_HOLD     4   /* Enclavamiento de energía */
    #define PIN_MODE_SWITCH    37  /* Botón A */
    #define PIN_LED_INDICATOR  19  /* LED Rojo interno / IR */
    
    #define I2C_MASTER_SDA_IO  21  /* Bus I2C interno */
    #define I2C_MASTER_SCL_IO  22
    
    #define PIN_BATT_ADC       ADC_CHANNEL_2 /* GPIO 38 */
    #define BATT_DIVIDER_MULT  2   /* Multiplicador del divisor de tensión interno */

#else    
    /* Pines Hardware Custom Original */
    #define PIN_MODE_SWITCH    13
    #define PIN_LED_GREEN      26
    #define PIN_LED_RED        27
    #define PIN_MPU_INT        25
    
    #define I2C_MASTER_SDA_IO  32
    #define I2C_MASTER_SCL_IO  33
    
    #define PIN_BATT_ADC       ADC_CHANNEL_6
    #define BATT_DIVIDER_MULT  2   
#endif

/* --- CONFIGURACIÓN DE BUFFER Y SENSORES --- */
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

/* --- CONFIGURACIÓN DE BATERÍA (Tiempos y Umbrales) --- */
#define BATT_ADC_UNIT        ADC_UNIT_1
#define BATT_MAX_VOLTAGE_MV  4200
#define BATT_MIN_VOLTAGE_MV  3300
#define BATT_UPDATE_MS       10000 /* Lectura cada 10s */

/* --- CONFIGURACIÓN DE BUSES (I2C) --- */
#define I2C_MASTER_NUM       0
#define I2C_MASTER_FREQ_HZ   400000

/* --- CONFIGURACIÓN BLE (GAP/GATT) --- */
#define MAX_CONNECTIONS      4

/* Tiempos de Anuncio (Advertising) */
#define BLE_ADV_ITVL_MIN_MS  500
#define BLE_ADV_ITVL_MAX_MS  510

/* Parámetros de Conexión */
#define BLE_CONN_ITVL_MIN    80   /* 100 ms (80 * 1.25) */
#define BLE_CONN_ITVL_MAX    160  /* 200 ms (160 * 1.25) */
#define BLE_CONN_TIMEOUT     200  /* 2 segundos (200 * 10ms) */

#endif // SYS_CONFIG_H