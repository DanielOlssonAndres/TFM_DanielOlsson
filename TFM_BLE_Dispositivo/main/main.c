#include "common.h"
#include "gap.h"
#include "gatt_svc.h"
#include "accel.h"
#include "user_input.h"
#include "host/ble_store.h"
#include "host/util/util.h"

/* Para guardar info de Bluetooth como claves a largo plazo*/
/*Definida en libreria de NimBLE*/
void ble_store_config_init(void);

/* Tarea para vigilar el botón */
static void button_task(void *param) {
    while (1) {
        if (is_factory_reset_pressed()) {
            ESP_LOGW("MAIN", "¡BOTÓN RESET PULSADO! Borrando claves...");
            
            /* Borrar todas las claves de seguridad (NVS) */
            ble_store_util_delete_all(BLE_STORE_OBJ_TYPE_PEER_SEC, NULL);
            
            /* Si estamos conectados, desconectar forzosamente */
            /* Esto hará que la Raspi se entere de que la conexión cayó */            
            ble_gap_adv_stop();
            
            /* Al reiniciar el anuncio, la función start_advertising() 
               verá que num_bonds es 0 y abrirá la Whitelist */
            adv_init();
            
            ESP_LOGI("MAIN", "Sistema reseteado. Esperando nueva conexión...");
            
            /* Esperamos a que el usuario suelte el botón para no borrar en bucle */
            vTaskDelay(pdMS_TO_TICKS(2000)); 
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/* Callback que se produce cuando el hardware esta listo */
static void on_stack_sync(void) {
    adv_init();  /* Comienza el anuncio*/
}

/* Configuracion de NimBLE */
static void nimble_host_config_init(void) {
    /* Set host callbacks */
    ble_hs_cfg.sync_cb = on_stack_sync; /* Funcion que se ejecuta despues de arrancar NimBLE*/
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr; /* Gestion de memoria FLASH */

    /* IO Capabilities: No tenemos pantalla ni teclado. Modo "Just Works" */
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;

    /* Habilitar Bonding: Guardar claves en la memoria flash (NVS) para recordar a la Raspi */
    ble_hs_cfg.sm_bonding = 1;

    /* Habilitar Secure Connections */
    ble_hs_cfg.sm_sc = 1;

    /* Configuración MITM (Man in the Middle) desactivada para Just Works */
    ble_hs_cfg.sm_mitm = 0;

    ble_att_set_preferred_mtu(256); /* Aceptamos paquetes de hasta 256 bytes */

    ble_store_config_init(); /* Leer configuraciones antiguas si las hay */
}

/* Tarea FreeRTOS */
/* Mantener vivo el sistema Bluetooth*/
static void nimble_host_task(void *param) {

    nimble_port_run(); /* Bucle infinito de funcionamiento de Bluetooth */
    vTaskDelete(NULL); /* No deberia llegar aqui nunca (Buena practica) */
}

/* Tarea FreeRTOS */
/* Leer sensor y generar los datos */
static void accelerometer_task(void *param) {

    /* Tiempo */
    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / ACCEL_SAMPLING_FREQ); /* 10ms */
    TickType_t xLastWakeTime = xTaskGetTickCount();
    
    while (1) {

        /* Tomamos una muestra y la metemos en el buffer */
        accel_sample_and_store();
        if (accel_is_batch_ready()) { /* Si el buffer se llena, lo enviamos */
            send_accel_batch();
        }

        /* Esperar hasta el siguiente ciclo */
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }

    vTaskDelete(NULL); /* No deberia llegar aqui nunca (Buena practica) */
}

/* --------------------- MAIN ---------------------------*/

void app_main(void) {

    int rc;
    esp_err_t ret; /* Retrono para errores en ESP-IDF */

    accel_init(); /* Inicializar el acelerometro */
    button_init(); /* Inicializar GPIO del botón */

    ret = nvs_flash_init(); /* Inicializar memoria NVS para Bluetooth */
    /* Mecanismo de autoreparacion de memoria corrupta o llena */
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE("MAIN", "ERROR de memoria NVS flash. ERROR code: %d ", ret);
        return;
    }

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
        ESP_LOGE("MAIN", "failed to initialize GATT server, error code: %d", rc);
        return;
    }

    /* Inicializar la configuracion de NimBLE */
    nimble_host_config_init();

    /* Crear tareas FreeRTOS */
    /* ARGUMENTOS: Funcion a ejecutar, Nombre, Tamaño de pila, Parametros, Prioridad, Handle */
    xTaskCreate(nimble_host_task, "NimBLE_Host", 4*1024, NULL, 5, NULL); /* Tarea Bluetooth NimBLE */
    xTaskCreate(accelerometer_task, "Accel_Task", 4*1024, NULL, 4, NULL); /* Tarea Acelerometro */
    xTaskCreate(button_task, "Button_Task", 2048, NULL, 3, NULL); /* Tarea Botón */

    return;
}
