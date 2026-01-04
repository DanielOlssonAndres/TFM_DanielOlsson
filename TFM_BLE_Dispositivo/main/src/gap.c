#include "gap.h"
#include "common.h"
#include "gatt_svc.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/ble.h"
#include "nimble/hci_common.h"
#include "host/ble_store.h"
#include "host/ble_gap.h"

/* Declaraciones de las funciones */
static int gap_event_handler(struct ble_gap_event *event, void *arg);

/* Variables globales */
static uint8_t own_addr_type; /* Tipo de dirección del dispositivo */
static uint8_t addr_val[6] = {0}; /* Dirección del dispositivo */

/* VARIABLES Y FUNCIONES PARA GESTIONAR LA WHITELIST */
#define MAX_BONDS 8
static ble_addr_t bonded_addrs[MAX_BONDS];
static int bonded_addrs_count = 0;

/* Callback auxiliar: se ejecuta por cada dispositivo guardado en memoria */
static int collect_bonded_cb(int obj_type, union ble_store_value *val, void *arg) {
    if (bonded_addrs_count < MAX_BONDS) {
        /* Copiamos la dirección del dispositivo guardado a nuestro array */
        bonded_addrs[bonded_addrs_count] = val->sec.peer_addr;
        bonded_addrs_count++;
    }
    return 0;
}

/* Función que carga la Whitelist manualmente */
static void load_whitelist_from_bonds(void) {
    bonded_addrs_count = 0;
    /* Iteramos sobre todos los secretos (claves) de peers guardados */
    ble_store_iterate(BLE_STORE_OBJ_TYPE_PEER_SEC, collect_bonded_cb, NULL);
    
    if (bonded_addrs_count > 0) {
        /* Enviamos la lista al controlador Bluetooth */
        int rc = ble_gap_wl_set(bonded_addrs, bonded_addrs_count);
        if (rc == 0) {
            ESP_LOGI("GAP", "Whitelist cargada con %d dispositivos.", bonded_addrs_count);
        } else {
            ESP_LOGE("GAP", "Error cargando Whitelist: %d", rc);
        }
    }
}

/*El dispositivo anuncia su existencia al mundo*/
static void start_advertising(void) { 

    int rc = 0; /*Código de retorno para funciones*/
    struct ble_hs_adv_fields adv_fields = {0}; /*Paquete de anuncio*/
    struct ble_gap_adv_params adv_params = {0}; /*Parametros de tiempos y modos*/
    int num_bonds = 0; /*Número de dispositivos emparejados*/

    /* INICIO CONFIGURACION DE "adv_fields" ----------------------------------------- */

    /* General Discoverable: Siempre visible */
    /* BR/EDR Unsupported: Indica que es solo BLE, no Bluetooth clasico */
    adv_fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    /* Ponemos nombre al dispositivo */
    adv_fields.name = (uint8_t *)ble_svc_gap_device_name(); /*Nombre definido en "common" mediante DEVICE_NAME*/
    adv_fields.name_len = strlen(ble_svc_gap_device_name()); /*Longitud del nombre*/
    adv_fields.name_is_complete = 1; /*Indica que el nombre es completo, no abreviatura*/

    /* Ponemos el icono de un "WRIST WORN" (estetico) */
    adv_fields.appearance = 0x03C0; 
    adv_fields.appearance_is_present = 1;

    /* Aplicamos la configuracion de los campos de anuncio */
    rc = ble_gap_adv_set_fields(&adv_fields);
    if (rc != 0) {
        ESP_LOGE("GAP", "ERROR en config. de adv_fields. ERROR code: %d", rc);
        return;
    }

    /* FIN CONFIGURACION DE "adv_fields" -------------------------------------------- */

    /* LÓGICA DE WHITELISTING */
    ble_store_util_count(BLE_STORE_OBJ_TYPE_PEER_SEC, &num_bonds);

    if (num_bonds > 0) {        
        /* Cargamos los dispositivos vinculados en la Whitelist del controlador BLE */
        load_whitelist_from_bonds();
        
        /* Configuramos el anuncio para usar la Whitelist */
        adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
        adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
        
        /* Filtramos para que SOLO los de la lista blanca puedan escanear o conectar */
        adv_params.filter_policy = BLE_HCI_ADV_FILT_BOTH;
        
    } else {
        
        /* Modo abierto a todo el mundo */
        adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
        adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
        /* Sin filtro */
        adv_params.filter_policy = BLE_HCI_ADV_FILT_NONE;
    }

    /* INICIO CONFIGURACION DE "adv_params" ----------------------------------------- */

    /* Se manda el anuncio cada 500-510 ms (para evitar colisiones) */
    adv_params.itvl_min = BLE_GAP_ADV_ITVL_MS(500);
    adv_params.itvl_max = BLE_GAP_ADV_ITVL_MS(510);

    /* Comenzar a anunciarse */
    rc = ble_gap_adv_start(
                        own_addr_type, /*Tipo de dirección del dispositivo*/
                        NULL, /*Dirección del destinatario (no usada en este caso)*/
                        BLE_HS_FOREVER, /*Duración del anuncio*/
                        &adv_params, /*Parametros de anuncio*/
                        gap_event_handler, /*Callback de conexión*/
                        NULL /*Argumento para el callback de conexión*/
                    );
    if (rc != 0) {
        ESP_LOGE("GAP", "ERROR en comienzo de anuncio. ERROR code: %d", rc);
        return;
    }

    /* FIN CONFIGURACION DE "adv_params" -------------------------------------------- */

    ESP_LOGI("GAP", "Advertising started");
}

/* Funcion de callback cuando se produce un evento GAP */
static int gap_event_handler(struct ble_gap_event *event, void *arg) {
    
    int rc = 0; /*Código de retorno para funciones*/
    struct ble_gap_conn_desc desc; /*Descriptor de la conexión*/
    struct ble_gap_upd_params params = {0}; /*Parametros de actualización de conexión*/

    /* Manejo de eventos */
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT: /* Evento de conexión */
            if (event->connect.status == 0) { /* Conexión exitosa */
                /* Pedir modo rápido (7.5ms - 15ms) */
                params.itvl_min = 6;  /* 7.5 ms */
                params.itvl_max = 12; /* 15 ms */
                params.latency = 0;
                params.supervision_timeout = 100;

                rc = ble_gap_update_params(event->connect.conn_handle, &params);
                if (rc != 0) ESP_LOGW("GAP", "ERROR pidiendo modo rapido. ERROR code: %d", rc);
            }
            else { /* Conexión fallida */
            start_advertising(); /* Reiniciar anuncio */
            }
            break;

        case BLE_GAP_EVENT_DISCONNECT: /* Evento de desconexión */
            ESP_LOGI("GAP", "Evento de desconexion");
            start_advertising(); /* Reiniciar anuncio */
            break;

        case BLE_GAP_EVENT_SUBSCRIBE: /* Evento de suscripción */
            ESP_LOGI("GAP", "Evento de suscripcion");
            /*Poner "sensor_notify_enabled = true" mediante callback*/
            gatt_svr_subscribe_cb(event);
            break;

            case BLE_GAP_EVENT_CONN_UPDATE: /* Evento de actualizacion de parametros de conexion */
            ESP_LOGI("GAP", "Evento de parametros de conexion actualizados");
            break;

        case BLE_GAP_EVENT_CONN_UPDATE_REQ: /* Evento de peticion de actualizacion de parametros */
            return 0; /* Aceptar siempre */

        case BLE_GAP_EVENT_REPEAT_PAIRING: /* Evento de re-emparejamiento */
            /* Si el móvil ya tenía claves antiguas, permitimos que intente emparejarse de nuevo */
            /* Para reconectar automáticamente tras borrar la flash del ESP32 */
            ESP_LOGI("GAP", "Evento de intento de re-emparejamiento");
            rc = ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc);
            if (rc != 0) {
                return BLE_GAP_REPEAT_PAIRING_IGNORE;
            }
            return BLE_GAP_REPEAT_PAIRING_RETRY;

        case BLE_GAP_EVENT_MTU: /* Evento de MTU actualizado */
            ESP_LOGI("GAP", "Evento de MTU actualizado a %d bytes", event->mtu.value);
            break;

        default:
            ESP_LOGI("GAP", "Evento no definido: %d", event->type);
            return 0;
            break;
    }

    return rc;
}


/* Funciones publicas */

/* Inicializa el anuncio */
void adv_init(void) {

    int rc = 0; /*Código de retorno para funciones*/

    /* Verificar que el dispositivo tenga una dirección BT disponible */
    rc = ble_hs_util_ensure_addr(0);

    /* Decidir que tipo de direccion usar (auto) */
    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE("GAP", "ERROR al decidir una direccion. ERROR code: %d", rc);
        return;
    }

    /* Imprimir la direccion */
    rc = ble_hs_id_copy_addr(own_addr_type, addr_val, NULL);
    ESP_LOG_BUFFER_HEX("GAP", addr_val, 6); /* Imprimir la dirección en hexadecimal */

    /* Comenzar el anuncio */
    start_advertising();
}

/* Inicializa el GAP */
int gap_init(void) {

    int rc = 0; /*Código de retorno para funciones*/

    /* Inicializar el servicio GAP */
    /*Crea el servicio "Generic Access" para cumplir con el estandar Bluetooth*/
    ble_svc_gap_init();

    /* Configurar el nombre del dispositivo */
    rc = ble_svc_gap_device_name_set(DEVICE_NAME);
    if (rc != 0) {
        ESP_LOGE("GAP", "ERROR al configurar el nombre del dispositivo, ERROR code: %d", rc);
    }
    return rc;
}
