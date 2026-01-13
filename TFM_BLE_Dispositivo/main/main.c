#include "common.h"
#include "gap.h"
#include "gatt_svc.h"
#include "accel.h"

/* --------------------- FUNCIONES ---------------------------*/

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

    /* Habilitar Bonding: Guardar claves en la memoria flash (NVS) para recordar a la Raspi */
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

    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / ACCEL_SAMPLING_FREQ); /* 10ms */
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
    esp_err_t ret; /* Retrono para errores en ESP-IDF */

    accel_init(); /* Inicializar el acelerometro */

    /* Inicialización de NVS (Requerido por WiFi/Bluetooth drivers) */
    ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        /* Si la partición NVS estaba corrupta o llena, la borramos y reintentamos */
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* Inicializar pila NimBLE en RAM */
    ret = nimble_port_init();
    if (ret != ESP_OK) {
        ESP_LOGE("MAIN", "ERROR de pila NimBLE. ERROR code: %d ", ret);
        return;
    }

    /* Inicializar servicio GAP */
    rc = gap_init();
    if (rc != 0) {
        ESP_LOGE("MAIN", "ERROR de servicio GAP. ERROR code: %d", rc);
        return;
    }

    /* GATT server initialization */
    rc = gatt_svc_init();
    if (rc != 0) {
        ESP_LOGE("MAIN", "ERROR de servidor GATT. ERROR code: %d", rc);
        return;
    }

    /* Inicializar la configuracion de NimBLE */
    nimble_host_config_init();

    ESP_LOGE("MAIN", "Sistema inicializado correctamente.");

    /* Crear tareas FreeRTOS */
    /* ARGUMENTOS: Funcion a ejecutar, Nombre, Tamaño de pila, Parametros, Prioridad, Handle */
    xTaskCreate(nimble_host_task, "NimBLE_Host", 4*1024, NULL, 5, NULL); /* Tarea Bluetooth NimBLE */
    xTaskCreate(accelerometer_task, "Accel_Task", 4*1024, NULL, 4, NULL); /* Tarea Acelerometro */

    return;
}
