#include <stdio.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"

#include "sys_config.h"
#include "bsp.h"
#include "gap.h"
#include "gatt_svc.h"
#include "battery.h"
#include "mpu6050.h"       
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

/* --------------------- FUNCIONES NIMBLE ---------------------------*/

/* Callback que se produce cuando el hardware esta listo */
static void on_stack_sync(void) {
    ESP_LOGI("MAIN", "Anuncio iniciado.");
    adv_init(); 
}

/* Configuracion de NimBLE */
static void nimble_host_config_init(void) {
    /* Rellenamos la estructura ble_hs_cfg => Ajustes globales de comportamiento */

    /* Callback a llamar tras iniciar el hardware */
    ble_hs_cfg.sync_cb = on_stack_sync; 
    /* IO Capabilities: No tenemos pantalla ni teclado. Modo "Just Works" */
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;
    /* Sin Bonding */
    ble_hs_cfg.sm_bonding = 0;
    /* Habilitar Secure Connections */
    ble_hs_cfg.sm_sc = 1;
    /* Configuración MITM (Man in the Middle) desactivada para Just Works */
    ble_hs_cfg.sm_mitm = 0;
    
    ble_att_set_preferred_mtu(256); /* Aceptamos paquetes de hasta 256 bytes */
}

/* --------------------- INTERRUPCIONES ---------------------------*/

/* Rutina de Servicio de Interrupción (ISR) del acelerómetro */
static void IRAM_ATTR mpu_isr_handler(void* arg) {
    if (accel_task_handle == NULL) return; 

    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    vTaskNotifyGiveFromISR(accel_task_handle, &xHigherPriorityTaskWoken);
    
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR(xHigherPriorityTaskWoken); 
    }
}

static void setup_mpu_interrupt(void) {
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_POSEDGE, 
        .pin_bit_mask = (1ULL << PIN_MPU_INT),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = 0,
        .pull_down_en = 1 
    };
    gpio_config(&io_conf);
    
    esp_err_t err = gpio_install_isr_service(0); 
    /* Toleramos el error de que el servicio ya esté inicializado */
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        bsp_system_halt_error("ISR_SERVICE");
    }

    err = gpio_isr_handler_add(PIN_MPU_INT, mpu_isr_handler, NULL);
    if (err != ESP_OK) {
        bsp_system_halt_error("ISR_HANDLER");
    }
}

/* --------------------- TAREAS FREERTOS ---------------------------*/

/* Mantener vivo el sistema Bluetooth*/
static void nimble_host_task(void *param) {
    nimble_port_run(); /* Bucle infinito de funcionamiento de Bluetooth */
}

/* Leer sensor y generar los datos */
static void accelerometer_task(void *param) {
    accel_raw_t sample;
    
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        
        /* Leer hardware puro */
        if (mpu6050_read_accel(&sample) == ESP_OK) {
            /* Procesar lógicamente */
            accel_buffer_process_sample(my_accel_buffer, sample);
            
            /* Comprobar estado y notificar consumidor */
            if (accel_buffer_is_batch_ready(my_accel_buffer)) { 
                xTaskNotifyGive(ble_send_task_handle);
            }
        } else {
            ESP_LOGW("MAIN", "Error leyendo MPU6050");
        }
    }
}

static void battery_task(void *param) {
    while (1) {
        /* Bloquea la tarea durante 10 segundos (10000 ms) antes de volver a leer */
        vTaskDelay(pdMS_TO_TICKS(BATT_UPDATE_MS));        
        battery_update();
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

    int rc;
    esp_err_t ret; 
    bool is_single_link; 

    /* Inicializar hardware base */
    bsp_init();
    is_single_link = bsp_read_mode_switch();

    ESP_LOGI("MAIN", "MODO: %s", is_single_link ? "SINGLE-LINK" : "MULTI-LINK");

    /* instancia del gestor de datos */
    my_accel_buffer = accel_buffer_create();
    if (my_accel_buffer == NULL) {
        bsp_system_halt_error("ACCEL_BUFFER_MEM");
    }

    /* Inicializar Módulo Acelerómetro */
    ret = mpu6050_init();
    if (ret != ESP_OK) bsp_system_halt_error("MPU6050 (I2C)");

    /* Inicializar Batería */
    ret = battery_init();
    if (ret != ESP_OK) {
        bsp_system_halt_error("ADC_BATTERY");
    }

    /* Inicialización de NVS */
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ret = nvs_flash_erase();
        if (ret != ESP_OK) bsp_system_halt_error("NVS_ERASE");
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) bsp_system_halt_error("NVS_INIT");

    /* Inicializar pila NimBLE */
    ret = nimble_port_init();
    if (ret != ESP_OK) {
        bsp_system_halt_error("NIMBLE_PORT");
    }

    /* Inicializar servicio GAP */
    rc = gap_init(is_single_link);
    if (rc != 0) bsp_system_halt_error("GAP_SVC");

    rc = gatt_svc_init(battery_get_level, get_last_accel_sample_wrapper, reset_accel_counters_wrapper);
    if (rc != 0) bsp_system_halt_error("GATT_SVC");

    /* Inicializar configuración NimBLE */
    nimble_host_config_init();

    /* Crear tareas FreeRTOS */
    xTaskCreate(nimble_host_task, "NimBLE_Host", STACK_SIZE_NIMBLE, NULL, PRIO_NIMBLE_HOST, NULL); 
    xTaskCreate(ble_send_worker_task, "BLE_Send", STACK_SIZE_SEND, NULL, PRIO_BLE_SEND, &ble_send_task_handle); 
    xTaskCreate(accelerometer_task, "Accel_Task", STACK_SIZE_ACCEL, NULL, PRIO_ACCEL_TASK, &accel_task_handle);    
    xTaskCreate(battery_task, "Battery_Task", STACK_SIZE_BATT, NULL, PRIO_BATT_TASK, NULL);
    
    /* Iniciar la interrupción hardware del acelerómetro después de crear la tarea */
    setup_mpu_interrupt();
    /* Desbloqueo de hardware sin afectar a los búferes */
    mpu6050_clear_interrupt();

    ESP_LOGI("MAIN", "Sistema inicializado correctamente. Listo para conectar.");
    bsp_set_led_green(true); /* Encender LED Verde */

    return;
}
