#include "gap.h"
#include "sys_config.h" 
#include "gatt_svc.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/ble.h"
#include "nimble/hci_common.h"
#include "host/ble_gap.h"
#include "esp_log.h"
#include "services/gap/ble_svc_gap.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nimble/nimble_port.h"

/* Variables globales */
static uint8_t own_addr_type; /* Tipo de dirección del dispositivo */
static int active_connections = 0;
static bool is_single_link_mode = true;

/* --------------------------------- CÓDIGO PRIVADO --------------------------------------- */

static void start_advertising(void);

/* Funcion de callback cuando se produce un evento GAP */
static int gap_event_handler(struct ble_gap_event *event, void *arg) {
    
    int rc;
    struct ble_gap_conn_desc desc;
    struct ble_gap_upd_params params = {0}; 
    int limite;

    switch (event->type) {
        
        case BLE_GAP_EVENT_CONNECT:
            if (event->connect.status == 0) {
                active_connections++; 
                
                /* Switch = 1 (Single). Switch = 0 (Multi) */
                limite = is_single_link_mode ? 1 : MAX_CONNECTIONS;

                /* Si aún caben más, seguimos anunciando */
                if (active_connections < limite) {
                    start_advertising(); 
                }
                /* Si llegamos al límite, no hacemos nada y el anuncio se detiene solo */

                /* Petición de modo equilibrado (despierta cada ~100ms) */
                params.itvl_min = BLE_CONN_ITVL_MIN;
                params.itvl_max = BLE_CONN_ITVL_MAX;
                params.latency = 0;
                params.supervision_timeout = BLE_CONN_TIMEOUT;
                
                rc = ble_gap_update_params(event->connect.conn_handle, &params);
                if (rc != 0) {
                     ESP_LOGE("GAP", "Fallo al actualizar params: %d", rc);
                }

            } else {
                /* Conexión fallida: reintentar anuncio */
                start_advertising(); 
            }
            break;

        case BLE_GAP_EVENT_DISCONNECT:
            /* Gestión de desconexión */
            active_connections--;
            if (active_connections < 0) active_connections = 0;
            /* Siempre volvemos a anunciar al salir alguien para rellenar el hueco */
            start_advertising(); 
            break;

        case BLE_GAP_EVENT_SUBSCRIBE:
            /* Delegamos al servicio GATT la gestión de la suscripción */
            gatt_svr_subscribe_cb(event);
            break;

        case BLE_GAP_EVENT_CONN_UPDATE_REQ:
            /* Aceptar siempre peticiones de actualización de la Raspi */
            return 0; 

        case BLE_GAP_EVENT_REPEAT_PAIRING:
            /* Gestión estándar de re-emparejamiento */
            rc = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
            if (rc != 0) {
                return BLE_GAP_REPEAT_PAIRING_IGNORE;
            }
            return BLE_GAP_REPEAT_PAIRING_RETRY;

        default:
            break;
    }

    return 0;
}

/*El dispositivo anuncia su existencia al mundo*/
static void start_advertising(void) { 

    /* Prevenir sobresaturación: Si ya se está anunciando, cancelar ejecución */
    if (ble_gap_adv_active()) {
        return;
    }

    struct ble_hs_adv_fields adv_fields = {0}; 
    struct ble_gap_adv_params adv_params = {0}; 

    /* ---- CONFIGURACIÓN DE CAMPOS DE ANUNCIO (Payload) ---- */

    /* Nombre del dispositivo */
    adv_fields.name = (uint8_t *)ble_svc_gap_device_name(); 
    adv_fields.name_len = strlen(ble_svc_gap_device_name()); 
    adv_fields.name_is_complete = 1; 
    adv_fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    /* Icono (Wrist Worn) */
    adv_fields.appearance = 0x03C0; 
    adv_fields.appearance_is_present = 1;

    /* Aplicamos los campos */
    ble_gap_adv_set_fields(&adv_fields);
   

    /* ---- CONFIGURACIÓN DE PARÁMETROS Y WHITELIST ---- */

    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    /* Cada cuánto se realiza el anuncio */
    adv_params.itvl_min = BLE_GAP_ADV_ITVL_MS(BLE_ADV_ITVL_MIN_MS);
    adv_params.itvl_max = BLE_GAP_ADV_ITVL_MS(BLE_ADV_ITVL_MAX_MS);

    adv_params.filter_policy = BLE_HCI_ADV_FILT_NONE;

    /* Arrancar anuncio */
    ble_gap_adv_start(
                        own_addr_type, /* Tipo de dirección MAC */
                        NULL, /* Destinatario específico */
                        BLE_HS_FOREVER, /* Duración del anuncio */
                        &adv_params, /* Parámetros de anuncio */
                        gap_event_handler, /* Callback: Qué pasa cuando sucede un evento de este anuncio (GAP) */
                        NULL /* Argumentos del callback*/
                    );
}

/* Inicializa el anuncio */
static void adv_init(void) {

    /* Verificar que el dispositivo tenga una dirección BT disponible */
    ble_hs_util_ensure_addr(0);

    /* Decidir que tipo de direccion usar (auto) */
    ble_hs_id_infer_auto(0, &own_addr_type);

    /* Comenzar el anuncio */
    start_advertising();
}

/* Callback que se produce cuando el hardware está listo */
static void on_stack_sync(void) {
    ESP_LOGI("GAP", "Pila sincronizada. Anuncio iniciado.");
    adv_init(); 
}

/* Tarea de FreeRTOS para mantener vivo el Bluetooth */
static void nimble_host_task(void *param) {
    nimble_port_run(); 
}

/* ------------------------- FUNCIONES PÚBLICAS ------------------------------- */

/* Configuración de NimBLE */
void gap_host_config_init(void) {
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

/* Lanza la tarea de la pila BLE */
void gap_start_host_task(void) {
    xTaskCreate(nimble_host_task, "NimBLE_Host", STACK_SIZE_NIMBLE, NULL, PRIO_NIMBLE_HOST, NULL); 
}

/* Inicializa el GAP */
int gap_init(bool single_link_mode) {

    int rc = 0; 

    is_single_link_mode = single_link_mode;

    /* Inicializar el servicio GAP */
    ble_svc_gap_init();

    /* Configurar el nombre del dispositivo */
    rc = ble_svc_gap_device_name_set(DEVICE_NAME);

    return rc;
}


