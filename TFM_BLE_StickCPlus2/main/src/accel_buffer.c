#include "accel_buffer.h"
#include "esp_timer.h"
#include <stdlib.h>

/* Constructor del manejador del buffer */
AccelBufferHandle accel_buffer_create(void) {
    /* Utiliza calloc para asegurar que toda la estructura se inicializa a 0 */ 
    AccelBufferHandle handle = (AccelBufferHandle)calloc(1, sizeof(struct AccelBufferStruct));
    if (handle) {
        /* Guarda el tiempo absoluto de inicio (en microsegundos) para calcular timestamps relativos */
        handle->start_time_offset = esp_timer_get_time();
    }
    return handle;
}

/* Destructor. Libera la memoria dinámica asignada */
void accel_buffer_destroy(AccelBufferHandle handle) {
    if (handle) free(handle);
}

/* Reinicia el estado del buffer sin reasignar memoria */
void accel_buffer_reset_counters(AccelBufferHandle handle) {
    if (!handle) return;
    handle->global_packet_counter = 0; /* ID secuencial global */
    handle->sample_count = 0;          /* Índice de la muestra actual dentro del buffer */
    handle->write_idx = 0;             /* Índice del buffer activo para escritura (0 o 1) */
    handle->batch_ready = false;       /* Flag de disponibilidad */
    handle->start_time_offset = esp_timer_get_time();    
}

void accel_buffer_process_sample(AccelBufferHandle handle, accel_raw_t sample) {
    if (!handle) return;

    /* Selecciona el buffer de escritura actual (0 o 1) basándose en write_idx */
    accel_packet_t *current_buffer = &handle->buffers[handle->write_idx];

    /* Si es la primera muestra del paquete, genera los metadatos del paquete */
    if (handle->sample_count == 0) {
        /* Guarda estrictamente el tiempo local del ESP32 en milisegundos */
        current_buffer->timestamp_start = (uint64_t)(esp_timer_get_time() / 1000); 
        current_buffer->sequence_id = handle->global_packet_counter;
    }

    /* Almacena la muestra en el array del buffer */
    current_buffer->samples[handle->sample_count] = sample;
    /* Actualiza el registro de la última muestra leída */
    handle->last_valid_sample = sample;
    handle->sample_count++;

    /* Verifica si el buffer actual ha alcanzado su capacidad máxima */
    if (handle->sample_count >= SAMPLES_PER_PACKET) {
        handle->sample_count = 0;              /* Reinicia el contador para el siguiente buffer */
        handle->global_packet_counter++;       /* Incrementa el ID del paquete global */
        handle->batch_ready = true;            /* Señaliza al consumidor que hay un paquete listo */
        
        /* INTERCAMBIO DE BUFFER (PING-PONG): */
        /* Si write_idx era 0 pasa a 1, si era 1 (u otro distinto de 0) pasa a 0. */
        /* A partir de este momento, los nuevos datos van al otro buffer */
        handle->write_idx = !handle->write_idx; 
    }
}

/* Polling para verificar si hay un paquete listo para consumir */
bool accel_buffer_is_batch_ready(AccelBufferHandle handle) {
    return handle ? handle->batch_ready : false;
}

/* Devuelve el puntero al buffer que está lleno y listo para ser procesado */
accel_packet_t* accel_buffer_get_batch(AccelBufferHandle handle) {
    if (!handle) return NULL;
    
    /* Resetea el flag inmediatamente después de reclamar el lote */
    handle->batch_ready = false; 
    
    /* Retorna el buffer contrario al que se está escribiendo actualmente */
    return &handle->buffers[!handle->write_idx];
}

accel_raw_t accel_buffer_get_last_sample(AccelBufferHandle handle) {
    accel_raw_t empty = {0,0,0};
    return handle ? handle->last_valid_sample : empty;
}