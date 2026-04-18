#include <stdio.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nimble/nimble_port.h"

#include "sys_config.h"
#include "bsp.h"
#include "gap.h"
#include "gatt_svc.h"
#include "accel_buffer.h"   

static TaskHandle_t accel_task_handle = NULL;
static TaskHandle_t ble_send_task_handle = NULL; 

static AccelBufferHandle my_accel_buffer = NULL;

/* --------------------- WRAPPERS PARA GATT -------------------*/

static void get_last_accel_sample_wrapper(accel_raw_t *sample_out) {
    if (sample_out != NULL) {
        *sample_out = accel_buffer_get_last_sample(my_accel_buffer);
    }
}

static void reset_accel_counters_wrapper(void) {
    accel_buffer_reset_counters(my_accel_buffer);
}

/* --------------------- INTERRUPCIONES ---------------------------*/

/* Rutina de Servicio de Interrupción (ISR) del IMU */
static void IRAM_ATTR imu_isr_handler(void* arg) {
    if (accel_task_handle == NULL) return; 

    /* Detección dinámica del contexto (Hardware ISR / Software Timer) */
    if (xPortInIsrContext()) {
        BaseType_t xHigherPriorityTaskWoken = pdFALSE;
        vTaskNotifyGiveFromISR(accel_task_handle, &xHigherPriorityTaskWoken);
        if (xHigherPriorityTaskWoken) {
            portYIELD_FROM_ISR(xHigherPriorityTaskWoken); 
        }
    } else {
        /* Contexto de tarea normal */
        xTaskNotifyGive(accel_task_handle);
    }
}

/* --------------------- TAREAS FREERTOS ---------------------------*/

/* Leer sensor y generar los datos */
static void accelerometer_task(void *param) {
    accel_raw_t sample;
    
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        
        /* Lectura del sensor */
        if (bsp_imu_read_accel(&sample) == ESP_OK) {
            accel_buffer_process_sample(my_accel_buffer, sample);
            
            /* Comprobar estado y notificar consumidor */
            if (accel_buffer_is_batch_ready(my_accel_buffer)) { 
                xTaskNotifyGive(ble_send_task_handle);
            }
        } else {
            ESP_LOGW("MAIN", "Error leyendo IMU");
        }
    }
}

static void battery_task(void *param) {
    while (1) {
        /* Bloquea la tarea durante 10 segundos (10000 ms) antes de volver a leer */
        vTaskDelay(pdMS_TO_TICKS(BATT_UPDATE_MS));        
        bsp_battery_update();
    }
}

static void ble_send_worker_task(void *param) {
    while(1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        
        accel_packet_t *batch = accel_buffer_get_batch(my_accel_buffer);
        if (batch != NULL) {
            send_accel_batch(batch);
        }
    }
}

/* --------------------- MAIN ---------------------------*/

void app_main(void) {

    esp_err_t ret;

    /* Inicializar hardware base */
    bsp_init();

    /* Instancia del gestor de datos */
    my_accel_buffer = accel_buffer_create();
    if (my_accel_buffer == NULL) {
        bsp_error_check(7);
    }

    /* Inicializar NVS */
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        if (nvs_flash_erase() != ESP_OK) { bsp_error_check(8); }
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) { bsp_error_check(8); }

    /* Inicializar pila NimBLE */
    if(nimble_port_init() != ESP_OK) { bsp_error_check(9); }

    /* Inicializar GAP */
    if(gap_init(bsp_read_mode_switch()) != 0) { bsp_error_check(10); }

    /* Inicializar GATT */
    if(gatt_svc_init(bsp_battery_get_level, get_last_accel_sample_wrapper, reset_accel_counters_wrapper) != 0) { bsp_error_check(11); }
    
    /* Configuración NimBLE */
    gap_host_config_init();

    /* Crear tareas FreeRTOS */
    gap_start_host_task(); /* Tarea que mantiene viva la pila BLE */
    xTaskCreate(ble_send_worker_task, "BLE_Send", STACK_SIZE_SEND, NULL, PRIO_BLE_SEND, &ble_send_task_handle); 
    xTaskCreate(accelerometer_task, "Accel_Task", STACK_SIZE_ACCEL, NULL, PRIO_ACCEL_TASK, &accel_task_handle);    
    xTaskCreate(battery_task, "Battery_Task", STACK_SIZE_BATT, NULL, PRIO_BATT_TASK, NULL);
    
    /* Iniciar la interrupción hardware del acelerómetro después de crear la tarea */
    if (bsp_imu_register_interrupt(imu_isr_handler, NULL) != ESP_OK) { bsp_error_check(13); }
    /* Desbloqueo de hardware sin afectar a los búferes */
    bsp_imu_clear_interrupt();

    ESP_LOGI("MAIN", "SISTEMA COMPLETO INICIALIZADO CON ÉXITO.");
    bsp_set_led_green(true); /* Encender LED Verde */

    return;
}
