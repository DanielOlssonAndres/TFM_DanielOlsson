#ifndef SENSOR_TYPES_H
#define SENSOR_TYPES_H

#include <stdint.h>
#include "sys_config.h"

typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} accel_raw_t;

typedef struct __attribute__((packed)) {
    uint32_t sequence_id;
    uint32_t timestamp_start;
    accel_raw_t samples[SAMPLES_PER_PACKET]; 
} accel_packet_t;

#endif // SENSOR_TYPES_H