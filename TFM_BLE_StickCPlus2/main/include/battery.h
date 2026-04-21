#ifndef BATTERY_H
#define BATTERY_H

#include "esp_err.h"
#include <stdint.h>

esp_err_t battery_init(void);
void battery_update(void); 
uint8_t battery_get_level(void); 

#endif // BATTERY_H