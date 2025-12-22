#ifndef ACCEL_H
#define ACCEL_H

#include <stdint.h>

/* Estructura para los datos X, Y, Z */
typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} accel_data_t;

/* Funciones */
void accel_init(void);
accel_data_t accel_get_data(void);

#endif 