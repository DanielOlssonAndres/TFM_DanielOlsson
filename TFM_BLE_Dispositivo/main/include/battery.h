#ifndef BATTERY_H
#define BATTERY_H

#include "esp_err.h"
#include <stdint.h>

esp_err_t battery_init(void);
void battery_update(void); /* Fuerza una nueva lectura del ADC */
uint8_t battery_get_level(void); /* Devuelve el último nivel calculado */

#endif // BATTERY_H