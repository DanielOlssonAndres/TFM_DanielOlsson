#include "accel_buffer.h"
#include "esp_timer.h"
#include <stdlib.h>

/* Definición de la estructura de estado */
struct AccelBufferStruct {
    accel_packet_t buffers[2];
    uint8_t write_idx;
    bool batch_ready;
    int sample_count;
    uint32_t global_packet_counter;
    int64_t start_time_offset;
    accel_raw_t last_valid_sample;
};

AccelBufferHandle accel_buffer_create(void) {
    AccelBufferHandle handle = (AccelBufferHandle)calloc(1, sizeof(struct AccelBufferStruct));
    if (handle) {
        handle->start_time_offset = esp_timer_get_time();
    }
    return handle;
}

void accel_buffer_destroy(AccelBufferHandle handle) {
    if (handle) free(handle);
}

void accel_buffer_reset_counters(AccelBufferHandle handle) {
    if (!handle) return;
    handle->global_packet_counter = 0;
    handle->sample_count = 0;
    handle->write_idx = 0;
    handle->batch_ready = false;
    handle->start_time_offset = esp_timer_get_time();    
}

void accel_buffer_process_sample(AccelBufferHandle handle, accel_raw_t sample) {
    if (!handle) return;

    accel_packet_t *current_buffer = &handle->buffers[handle->write_idx];

    if (handle->sample_count == 0) {
        int64_t relative_time = esp_timer_get_time() - handle->start_time_offset;
        current_buffer->timestamp_start = (uint32_t)(relative_time / 1000); 
        current_buffer->sequence_id = handle->global_packet_counter;
    }

    current_buffer->samples[handle->sample_count] = sample;
    handle->last_valid_sample = sample;
    handle->sample_count++;

    if (handle->sample_count >= SAMPLES_PER_PACKET) {
        handle->sample_count = 0;
        handle->global_packet_counter++;
        handle->batch_ready = true;
        handle->write_idx = !handle->write_idx; 
    }
}

bool accel_buffer_is_batch_ready(AccelBufferHandle handle) {
    return handle ? handle->batch_ready : false;
}

accel_packet_t* accel_buffer_get_batch(AccelBufferHandle handle) {
    if (!handle) return NULL;
    handle->batch_ready = false; 
    return &handle->buffers[!handle->write_idx];
}

accel_raw_t accel_buffer_get_last_sample(AccelBufferHandle handle) {
    accel_raw_t empty = {0,0,0};
    return handle ? handle->last_valid_sample : empty;
}