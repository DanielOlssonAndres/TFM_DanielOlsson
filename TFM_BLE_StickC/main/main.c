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
#include "accel_buffer.h"   
#include "imu_sensor.h"

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

/* --------------------- INTERRUPCIONES (Condicional) -------------------*/
#if !TARGET_M5STICKC_PLUS2
static void IRAM_ATTR mpu_isr_handler(void* arg) {
    if (accel_task_handle == NULL) return; 
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    vTaskNotifyGiveFromISR(accel_task_handle, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR(xHigherPriorityTaskWoken); 
}

static void setup_mpu_interrupt(void) {
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_POSEDGE,
        .pin_bit_mask = (1ULL << PIN_MPU_INT),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = 0,
        .pull_down_en = 0
    };
    gpio_config(&io_conf);
    gpio_install_isr_service(0);
    gpio_isr_handler_add(PIN_MPU_INT, mpu_isr_handler, NULL);
}
#endif

/* --------------------- TAREAS FREERTOS ---------------------------*/

/* Tarea principal del host NimBLE */
static void nimble_host_task(void *param) {
    nimble_port_run();
    nimble_port_freertos_deinit();
}

/* Tarea que procesa el envío de batches BLE cuando el buffer está listo */
static void ble_send_worker_task(void *param) {
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        accel_packet_t* batch = accel_buffer_get_batch(my_accel_buffer);
        if (batch) {
            send_accel_batch(batch);
        }
    }
}

/* Tarea de lectura del acelerómetro */
static void accelerometer_task(void *param) {
    accel_raw_t sample;
    
#if TARGET_M5STICKC_PLUS2
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(20); /* 50Hz Polling */
#endif

    while (1) {
#if TARGET_M5STICKC_PLUS2
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
#else
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
#endif
        
        if (imu_read_accel(&sample) == ESP_OK) {
            accel_buffer_process_sample(my_accel_buffer, sample);
            if (accel_buffer_is_batch_ready(my_accel_buffer)) { 
                if (ble_send_task_handle != NULL) {
                    xTaskNotifyGive(ble_send_task_handle);
                }
            }
        }
#if !TARGET_M5STICKC_PLUS2
        imu_clear_interrupt();
#endif
    }
}

/* Tarea de lectura de batería */
static void battery_task(void *param) {
    bool led_state = false;
    while (1) {
        battery_update();
        
        /* Parpadeo del LED (ignorado en M5Stick gracias a la abstracción de BSP) */
        led_state = !led_state;
        bsp_set_led_green(led_state);

        vTaskDelay(pdMS_TO_TICKS(BATT_UPDATE_MS)); 
    }
}

/* --------------------- CONFIGURACIÓN NIMBLE ----------------------*/
static void ble_app_on_reset(int reason) {
    ESP_LOGE("MAIN", "NimBLE host reset; reason=%d", reason);
}

static void ble_app_on_sync(void) {
    ESP_LOGI("MAIN", "NimBLE host synced. Iniciando Advertising...");
    /* Arranca el anuncio BLE una vez que la pila está lista */
    adv_init(); 
}

static void nimble_host_config_init(void) {
    /* Configurar callbacks del host BLE */
    ble_hs_cfg.reset_cb = ble_app_on_reset;
    ble_hs_cfg.sync_cb = ble_app_on_sync;
    
    /* Configuración de seguridad BLE estándar (Just Works) */
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 0;
    ble_hs_cfg.sm_sc = 1;
}
/* ----------------------------------------------------------------- */

/* ------------------------- FUNCIÓN PRINCIPAL ------------------------------- */

void app_main(void) {
    /* Inicializar Flash (Obligatorio para NimBLE) */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* Inicializar hardware (Botones, I2C, Power Hold) */
    bsp_init();
    
    /* Inicializar ADC de Batería */
    battery_init();

    /* Crear el buffer de aceleración */
    my_accel_buffer = accel_buffer_create();
    if (!my_accel_buffer) bsp_system_halt_error("BUFFER_MEM_FAIL");

    /* Inicializar Módulo Acelerómetro (HAL) */
    ret = imu_init();
    if (ret != ESP_OK) bsp_system_halt_error("IMU_INIT_FAIL");

    /* Inicializar pila NimBLE */
    ret = nimble_port_init();
    if (ret != ESP_OK) {
        bsp_system_halt_error("NIMBLE_PORT");
    }

    /* Inicializar servicio GAP */
    bool is_single_link = bsp_read_mode_switch();
    int rc = gap_init(is_single_link);
    if (rc != 0) bsp_system_halt_error("GAP_SVC");

    /* Inicializar servicio GATT */
    rc = gatt_svc_init(battery_get_level, get_last_accel_sample_wrapper, reset_accel_counters_wrapper);
    if (rc != 0) bsp_system_halt_error("GATT_SVC");

    /* Inicializar configuración NimBLE */
    nimble_host_config_init();

    /* Crear tareas FreeRTOS */
    xTaskCreate(nimble_host_task, "NimBLE_Host", STACK_SIZE_NIMBLE, NULL, PRIO_NIMBLE_HOST, NULL); 
    xTaskCreate(ble_send_worker_task, "BLE_Send", STACK_SIZE_SEND, NULL, PRIO_BLE_SEND, &ble_send_task_handle); 
    xTaskCreatePinnedToCore(accelerometer_task, "accel_task", STACK_SIZE_ACCEL, NULL, PRIO_ACCEL_TASK, &accel_task_handle, 1);
    xTaskCreate(battery_task, "batt_task", STACK_SIZE_BATT, NULL, PRIO_BATT_TASK, NULL);

#if !TARGET_M5STICKC_PLUS2
    /* Interrupciones solo en el hardware que las soporta físicamente */
    setup_mpu_interrupt();
    imu_clear_interrupt();
#endif

    ESP_LOGI("MAIN", "Sistema inicializado. Platforma: %s", DEVICE_NAME);
}