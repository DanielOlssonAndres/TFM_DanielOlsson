#include "gap.h"
#include "common.h"
#include "gatt_svc.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/ble.h"
#include "nimble/hci_common.h"
#include "host/ble_gap.h"

/* Variables globales */
static uint8_t own_addr_type; /* Tipo de dirección del dispositivo */
static bool session_locked = false; /* Flag para saber si ya estamos conectados a un dispositivo */  
static uint16_t active_conn_handle = BLE_HS_CONN_HANDLE_NONE; /* Identificador de la conexión actual */
static ble_addr_t locked_peer_addr; /* Dirección MAC del dispositivo conectado */


/* --------------------------------- CÓDIGO PRIVADO --------------------------------------- */

static void start_advertising(void);

/* Funcion de callback cuando se produce un evento GAP */
static int gap_event_handler(struct ble_gap_event *event, void *arg) {
    
    int rc = 0;
    struct ble_gap_conn_desc desc; /*Detalles de la conexión*/
    struct ble_gap_upd_params params = {0}; /*Parametros de actualización de conexión*/

    /* Manejo de eventos */
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT: /* Evento de conexión */
            if (event->connect.status == 0) { /* Conexión exitosa */
                /* Se guarda el identificador de la conexión*/
                active_conn_handle = event->connect.conn_handle; 
                /* Buscamos los detalles de quien se ha conectado usando el Handle */
                rc = ble_gap_conn_find(event->connect.conn_handle, &desc);
                if (rc == 0) {
                    if (!session_locked) { /* Si es la primera conexión, guardamos la dirección */
                    session_locked = true;
                    locked_peer_addr = desc.peer_ota_addr; 
                    }
                }
                
                /* Pedir modo rápido para mayor velocidad de recepción de datos */
                params.itvl_min = 6;  /* 7.5 ms */
                params.itvl_max = 12; /* 15 ms */
                params.latency = 0;
                params.supervision_timeout = 100;
                rc = ble_gap_update_params(event->connect.conn_handle, &params);
            }
            else { /* Conexión fallida */
                start_advertising(); /* Reiniciar anuncio */
            }
            break;

        case BLE_GAP_EVENT_DISCONNECT: /* Evento de desconexión */
            /* Eliminamos los datos de la conexión anterior */
            active_conn_handle = BLE_HS_CONN_HANDLE_NONE;
            start_advertising(); 
            break;

        case BLE_GAP_EVENT_SUBSCRIBE: /* Evento de suscripción */
            gatt_svr_subscribe_cb(event);
            break;

        case BLE_GAP_EVENT_CONN_UPDATE_REQ: /* Evento de peticion de actualizacion de parametros */
            return 0; /* Aceptar siempre */

        case BLE_GAP_EVENT_REPEAT_PAIRING: /* Raro que pase, pero por seguridad */
            if (ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc) != 0) {
                return BLE_GAP_REPEAT_PAIRING_IGNORE;
            }
            return BLE_GAP_REPEAT_PAIRING_RETRY;

        default:
            return 0;
            break;
    }

    return rc;
}

/*El dispositivo anuncia su existencia al mundo*/
static void start_advertising(void) { 

    struct ble_hs_adv_fields adv_fields = {0}; 
    struct ble_gap_adv_params adv_params = {0}; 

    /* ---- CONFIGURACIÓN DE CAMPOS DE ANUNCIO (Payload) ---- */

    /* Nombre del dispositivo */
    adv_fields.name = (uint8_t *)ble_svc_gap_device_name(); 
    adv_fields.name_len = strlen(ble_svc_gap_device_name()); 
    adv_fields.name_is_complete = 1; 

    /* Icono (Wrist Worn) */
    adv_fields.appearance = 0x03C0; 
    adv_fields.appearance_is_present = 1;

    if (session_locked) { /* En caso de ya estar conectados a un dispositivo */
        adv_fields.flags = BLE_HS_ADV_F_BREDR_UNSUP; /* No somos descubribles y usamos BLE */
    } else { /* En caso de estar libres */
        adv_fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP; /* Descubrible con BLE */
    }

    /* Aplicamos los campos */
    ble_gap_adv_set_fields(&adv_fields);
   

    /* ---- CONFIGURACIÓN DE PARÁMETROS Y WHITELIST ---- */

    if (session_locked) { /* En caso de ya estar conectados a un dispositivo */ 
        /* Solo permitimos entrar a la Raspi que se conectó antes */
        /* Cargamos la dirección guardada en RAM en la Whitelist del hardware */
        ble_gap_wl_set(&locked_peer_addr, 1);
        
        adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
        adv_params.disc_mode = BLE_GAP_DISC_MODE_NON; /* Invisible (Non-discoverable) */
        
        /* Política de filtro: Escaneos y Conexiones solo de la Whitelist */
        adv_params.filter_policy = BLE_HCI_ADV_FILT_BOTH; 
        
    } else { /* En caso de estar libres */        
        adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
        adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN; /* Visible (General) */
        adv_params.filter_policy = BLE_HCI_ADV_FILT_NONE; /* Sin filtros */
    }

    /* Cada cuánto se realiza el anuncio */
    adv_params.itvl_min = BLE_GAP_ADV_ITVL_MS(500);
    adv_params.itvl_max = BLE_GAP_ADV_ITVL_MS(510);

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

/* ------------------------- FUNCIONES PÚBLICAS ------------------------------- */

/* Inicializa el anuncio */
void adv_init(void) {

    /* Verificar que el dispositivo tenga una dirección BT disponible */
    ble_hs_util_ensure_addr(0);

    /* Decidir que tipo de direccion usar (auto) */
    ble_hs_id_infer_auto(0, &own_addr_type);

    /* Comenzar el anuncio */
    start_advertising();
}

/* Inicializa el GAP */
int gap_init(void) {

    int rc = 0; 

    /* Inicializar el servicio GAP */
    ble_svc_gap_init();

    /* Configurar el nombre del dispositivo */
    rc = ble_svc_gap_device_name_set(DEVICE_NAME);

    return rc;
}


