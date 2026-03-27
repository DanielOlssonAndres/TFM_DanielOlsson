#ifndef BATTERY_H
#define BATTERY_H

#include <stdint.h>
#include "esp_err.h"

esp_err_t battery_init(void);
uint8_t battery_get_level(void);

#endif 