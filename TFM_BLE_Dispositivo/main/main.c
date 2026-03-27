#include "common.h"
#include "gap.h"
#include "gatt_svc.h"
#include "accel.h"
#include "battery.h"

#define MODE_SWITCH_GPIO GPIO_NUM_13
#define LED_GREEN_GPIO GPIO_NUM_26
#define LED_RED_GPIO GPIO_NUM_27

bool is_single_link_mode = true;

/* --------------------- FUNCIONES ---------------------------*/

static void setup_leds(void) {
    gpio_reset_pin(LED_GREEN_GPIO);
    gpio_set_direction(LED_GREEN_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GREEN_GPIO, 0); /* Apagado por defecto */

    gpio_reset_pin(LED_RED_GPIO);
    gpio_set_direction(LED_RED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_RED_GPIO, 0); /* Apagado por defecto */
}

static void setup_switch(void) {
    /* Reset del pin para limpiar cualquier config previa */
    gpio_reset_pin(MODE_SWITCH_GPIO);
    /* Config del pin como entrada */
    gpio_set_direction(MODE_SWITCH_GPIO, GPIO_MODE_INPUT);
    /* Se activa la resistencia PULL-UP interna */
    gpio_set_pull_mode(MODE_SWITCH_GPIO, GPIO_PULLUP_ONLY);
}

/* Función que atrapa el sistema en caso de fallo crítico */
static void system_halt_error(const char* module) {
    gpio_set_level(LED_RED_GPIO, 1);   /* Enciende Rojo */
    gpio_set_level(LED_GREEN_GPIO, 0); /* Apaga Verde (por seguridad) */
    ESP_LOGE("MAIN", "FALLO CRÍTICO EN MÓDULO: %s. SISTEMA DETENIDO.", module);
    
    /* Bucle infinito para evitar el reinicio automático de ESP_ERROR_CHECK */
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static bool read_mode_switch(void) {
    int level;
    
    level = gpio_get_level(MODE_SWITCH_GPIO);
    ESP_LOGI("SWITCH", "Estado del Switch (GPIO %d): %d", MODE_SWITCH_GPIO, level);

    return (level == 1); /* 1 = Modo single-link, 0 = Modo multi-link */
}

/* Callback que se produce cuando el hardware esta listo */
static void on_stack_sync(void) {
    ESP_LOGE("MAIN", "Anuncio iniciado.");
    adv_init();  /* Inicializamos el anuncio */
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

/* --------------------- TAREAS FREERTOS ---------------------------*/

/* Mantener vivo el sistema Bluetooth*/
static void nimble_host_task(void *param) {
    /* Tarea gestionada por la librería NimBLE */
    nimble_port_run(); /* Bucle infinito de funcionamiento de Bluetooth */
}

/* Leer sensor y generar los datos */
static void accelerometer_task(void *param) {

    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / ACCEL_SAMPLING_FREQ); /* 20ms */
    TickType_t xLastWakeTime;
    
    xLastWakeTime = xTaskGetTickCount();

    while (1) {

        /* Tomamos una muestra y la metemos en el buffer */
        accel_sample_and_store();
        if (accel_is_batch_ready()) { /* Si el buffer se llena, lo enviamos */
            send_accel_batch();
        }

        /* Esperar hasta el siguiente ciclo */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/* --------------------- MAIN ---------------------------*/

void app_main(void) {

    int rc;
    esp_err_t ret; 

    /* Inicializar periféricos */
    setup_leds();
    setup_switch();

    is_single_link_mode = read_mode_switch();

    if (is_single_link_mode) {
        ESP_LOGI("MAIN", "MODO: SINGLE-LINK");
    } else {
        ESP_LOGI("MAIN", "MODO: MULTI-LINK");
    }

    /* Inicializar Acelerómetro */
    ret = accel_init();
    if (ret != ESP_OK) {
        system_halt_error("MPU6050 (I2C)");
    }

    /* Inicializar Batería */
    ret = battery_init();
    if (ret != ESP_OK) {
        system_halt_error("ADC_BATTERY");
    }

    /* Inicialización de NVS segura */
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ret = nvs_flash_erase();
        if (ret != ESP_OK) system_halt_error("NVS_ERASE");
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) system_halt_error("NVS_INIT");

    /* Inicializar pila NimBLE */
    ret = nimble_port_init();
    if (ret != ESP_OK) {
        system_halt_error("NIMBLE_PORT");
    }

    /* Inicializar servicio GAP */
    rc = gap_init();
    if (rc != 0) {
        system_halt_error("GAP_SVC");
    }

    /* Inicializar servidor GATT */
    rc = gatt_svc_init();
    if (rc != 0) {
        system_halt_error("GATT_SVC");
    }

    /* Inicializar configuración NimBLE */
    nimble_host_config_init();

    /* Crear tareas FreeRTOS */
    xTaskCreate(nimble_host_task, "NimBLE_Host", 4*1024, NULL, 5, NULL); 
    xTaskCreate(accelerometer_task, "Accel_Task", 4*1024, NULL, 4, NULL); 

    ESP_LOGI("MAIN", "Sistema inicializado correctamente. Listo para conectar.");
    gpio_set_level(LED_GREEN_GPIO, 1); /* Encender LED Verde */

    return;
}
