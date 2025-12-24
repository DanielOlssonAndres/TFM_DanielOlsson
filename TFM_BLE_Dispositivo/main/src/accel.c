#include "accel.h"
#include "common.h"
#include "esp_timer.h" // Para el reloj de alta precisión

#include <stdlib.h>    // Para rand() (Mock data)

static accel_packet_t acc_buffer; /* El paquete que estamos llenando */
static accel_raw_t last_sample; /* Ultima muestra */
static int sample_count = 0; /* Cuantas muestras llevamos en este paquete */
static uint32_t global_packet_counter = 0; /* ID de secuencia */
static int64_t start_time_offset = 0; /* Offset de tiempo al iniciar */

void accel_init(void) {

    /* Inicializar offset con el tiempo actual por defecto */
    start_time_offset = esp_timer_get_time();

    /*...*/

}

void accel_reset_counters(void) {

    global_packet_counter = 0;
    sample_count = 0;
    
    /* Se marca el "Ahora" como el nuevo punto cero */
    start_time_offset = esp_timer_get_time();
    
    ESP_LOGI("ACCEL", "Contadores y reloj reiniciados a 0");
}

void accel_sample_and_store(void) {
    
    int64_t current_time;
    int64_t relative_time;

    int16_t x_val;
    int16_t y_val;
    int16_t z_val;

    /* Si es la primera muestra del paquete, marcamos el tiempo y el ID */
    if (sample_count == 0) {
        /* Hora actual - Hora de conexión = Tiempo desde conexion */
        current_time = esp_timer_get_time();
        relative_time = current_time - start_time_offset;

        acc_buffer.timestamp_start = (uint32_t)(relative_time / 1000); 
        acc_buffer.sequence_id = global_packet_counter;
    }

    /* Leemos el sensor */
    /*...*/
    x_val = (rand() % 2000) - 1000;
    y_val = (rand() % 2000) - 1000;
    z_val = (rand() % 2000) - 1000;

    /* Guardamos en el array */
    acc_buffer.samples[sample_count].x = x_val;
    acc_buffer.samples[sample_count].y = y_val;
    acc_buffer.samples[sample_count].z = z_val;

    /* Guardamos copia */
    last_sample = acc_buffer.samples[sample_count];

    sample_count++;
}

bool accel_is_batch_ready(void) {
    return sample_count >= SAMPLES_PER_PACKET;
}

accel_packet_t* accel_get_batch(void) {
    /* Reseteamos para el siguiente ciclo */
    sample_count = 0;
    global_packet_counter++;
    
    /* Devolvemos la direccion del buffer lleno */
    return &acc_buffer;
}

accel_raw_t accel_get_last_sample(void) {
    return last_sample;
}