#ifndef COMMON_H
#define COMMON_H

/* Includes */
/* STD APIs */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h> /*Para gestion de los tipos de datos*/

/* ESP APIs */
#include "esp_log.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

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

/* Defines para la aplicacion*/
#define TAG "NimBLE_GATT_Server" /*Etiqueta por defecto para los mensajes por el terminal*/
#define DEVICE_NAME "Puls_1" /*Nombre del dispositivo BLE que se mostrara al escanear*/

#endif // COMMON_H
