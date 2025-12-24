#ifndef ACCEL_H
#define ACCEL_H

#include <stdint.h> /*Para gestion de los tipos de datos*/
#include <stdbool.h>

#define ACCEL_SAMPLING_FREQ 100 /* 100 Hz = 1 muestra cada 10ms */
#define SAMPLES_PER_PACKET  35 /* Numero de muestras por paquete */

/* Estructura de una muestra (X, Y, Z) */
typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} accel_raw_t;

/* Estructura del paquete a enviar por Bluetooth*/
/* __attribute__((packed)) evita huecos en memoria para que Python lo lea bien */
typedef struct __attribute__((packed)) {
    uint32_t sequence_id; /* Contador para detectar paquetes perdidos */
    uint32_t timestamp_start; /* Tiempo (ms) de la PRIMERA muestra del array */
    accel_raw_t samples[SAMPLES_PER_PACKET]; 
} accel_packet_t;

/* Declaraciones de funciones */
void accel_init(void);
void accel_sample_and_store(void); /* Toma 1 muestra y la guarda en el buffer */
bool accel_is_batch_ready(void);   /* ¿Está el buffer lleno? */
accel_packet_t* accel_get_batch(void); /* Devuelve el paquete listo */
accel_raw_t accel_get_last_sample(void); /* Leer el ultimo dato */
void accel_reset_counters(void);

#endif 