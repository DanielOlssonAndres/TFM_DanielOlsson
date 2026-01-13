#ifndef COMMON_H
#define COMMON_H

/* Includes */
/* STD APIs */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h> 

/* ESP APIs */
#include "esp_log.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include "driver/gpio.h" 

/* FreeRTOS APIs */
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

/* NimBLE stack APIs */
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "nimble/ble.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"

/* --- FIX: Se añade este include para ble_store_config_init() --- */
#include "host/ble_store.h" 

/* --- CONFIGURACIÓN DEL DISPOSITIVO --- */
#define DEVICE_NAME "Puls_1" 

#endif // COMMON_H