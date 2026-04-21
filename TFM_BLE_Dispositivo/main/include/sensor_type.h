#ifndef SENSOR_TYPE_H
#define SENSOR_TYPE_H

#include <stdint.h>
#include "sys_config.h"

typedef struct {
    int16_t x;
    int16_t y;
    int16_t z;
} accel_raw_t;

typedef struct __attribute__((packed)) {
    uint32_t sequence_id;
    accel_raw_t samples[SAMPLES_PER_PACKET]; 
} accel_packet_t;

struct AccelBufferStruct {
    accel_packet_t buffers[2];
    uint8_t write_idx;
    bool batch_ready;
    int sample_count;
    uint32_t global_packet_counter;
};

#endif