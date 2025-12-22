#ifndef ACCEL_H
#define ACCEL_H

#include <stdint.h> /*Para gestion de los tipos de datos*/

/* Estructura para los datos X, Y, Z */
typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} accel_data_t;

/* Declaraciones de funciones */
void accel_init(void);
accel_data_t accel_get_data(void);

#endif 