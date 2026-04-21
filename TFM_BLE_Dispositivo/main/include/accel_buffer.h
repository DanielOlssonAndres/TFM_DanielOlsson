#ifndef ACCEL_BUFFER_H
#define ACCEL_BUFFER_H

#include <stdbool.h>
#include "sys_config.h"
#include "sensor_type.h"

/* Multiple-Instance Module */
typedef struct AccelBufferStruct* AccelBufferHandle;

/* Funciones de la interfaz */
AccelBufferHandle accel_buffer_create(void);
void accel_buffer_destroy(AccelBufferHandle handle);
void accel_buffer_process_sample(AccelBufferHandle handle, accel_raw_t sample);
bool accel_buffer_is_batch_ready(AccelBufferHandle handle);
accel_packet_t* accel_buffer_get_batch(AccelBufferHandle handle);
accel_raw_t accel_buffer_get_last_sample(AccelBufferHandle handle);
void accel_buffer_reset_counters(AccelBufferHandle handle);

#endif // ACCEL_BUFFER_H