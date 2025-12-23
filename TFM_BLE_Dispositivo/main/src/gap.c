/* Includes */
#include "gap.h"
#include "common.h"
#include "gatt_svc.h"

/* Declaraciones de las funciones */
static int gap_event_handler(struct ble_gap_event *event, void *arg);

/* Variables globales */
static uint8_t own_addr_type; /* Tipo de dirección del dispositivo */
static uint8_t addr_val[6] = {0}; /* Dirección del dispositivo */

/* Definiciones de las funciones */

/*El dispositivo anuncia su existencia al mundo*/
static void start_advertising(void) { 

    int rc = 0; /*Código de retorno para funciones*/
    const char *name; /*Nombre del dispositivo*/
    struct ble_hs_adv_fields adv_fields = {0}; /*Paquete de anuncio*/
    struct ble_gap_adv_params adv_params = {0}; /*Parametros de tiempos y modos*/

    /* INICIO CONFIGURACION DE "adv_fields" ----------------------------------------- */

    /* General Discoverable: Siempre visible */
    /* BR/EDR Unsupported: Indica que es solo BLE, no Bluetooth clasico */
    adv_fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    /* Ponemos nombre al dispositivo */
    name = ble_svc_gap_device_name(); /*Nombre definido en "common" mediante DEVICE_NAME*/
    adv_fields.name = (uint8_t *)name; /*Puntero al nombre*/
    adv_fields.name_len = strlen(name); /*Longitud del nombre*/
    adv_fields.name_is_complete = 1; /*Indica que el nombre es completo, no abreviatura*/

    /* Ponemos el icono de un "WRIST WORN" (estetico) */
    adv_fields.appearance = 0x03C0; 
    adv_fields.appearance_is_present = 1;

    /* Anunciamos explicitamente que el dispositivo es un periférico (buena practica)*/
    adv_fields.le_role = BLE_GAP_LE_ROLE_PERIPHERAL;
    adv_fields.le_role_is_present = 1;

    /* Aplicamos la configuracion de los campos de anuncio */
    rc = ble_gap_adv_set_fields(&adv_fields);
    if (rc != 0) {
        ESP_LOGE("GAP", "ERROR en config. de adv_fields. ERROR code: %d", rc);
        return;
    }

    /* FIN CONFIGURACION DE "adv_fields" -------------------------------------------- */

    /* INICIO CONFIGURACION DE "adv_params" ----------------------------------------- */

    /* Undirected: Acepta conexiones (suscripciones) de cualquier dispositivo */
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;

    /* General discoverable: Siempre es visible */
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;

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

    /* Manejo de eventos */
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT: /* Evento de conexión */
            if (event->connect.status == 0) { /* Conexión exitosa */
                rc = ble_gap_conn_find(event->connect.conn_handle, &desc);
                if (rc != 0) {
                    ESP_LOGE("GAP","ERROR de conexion. ERROR code: %d", rc);
                }
                ESP_LOGI("GAP", "Evento de conexion");
            }
            else { /* Conexión fallida */
            start_advertising(); /* Reiniciar anuncio */
            }
            break;

        case BLE_GAP_EVENT_DISCONNECT: /* Evento de desconexión */
            ESP_LOGI("GAP", "Evento de desconexion");
            start_advertising(); /* Reiniciar anuncio */
            break;

        case BLE_GAP_EVENT_ADV_COMPLETE: /* Evento de anuncio completado */
            /* No se usa en este caso pero se pone por buena practica*/
            ESP_LOGI("GAP", "Evento de anuncio completado");
            start_advertising();
            break;

        case BLE_GAP_EVENT_SUBSCRIBE: /* Evento de suscripción */
            ESP_LOGI("GAP", "Evento de suscripcion");
            /*Poner "sensor_notify_enabled = true" mediante callback*/
            gatt_svr_subscribe_cb(event);
            break;

            case BLE_GAP_EVENT_CONN_UPDATE: /* Evento de actualizacion de parametros de conexion */
            ESP_LOGI("GAP", "Evento de parametros de conexion actualizados (Event 3)");
            break;

        case BLE_GAP_EVENT_CONN_UPDATE_REQ: /* Evento de peticion de actualizacion de parametros */
            ESP_LOGI("GAP", "Evento de peticion de actualizacion de parametros recibida (Event 4)");
            return 0; 

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

        case BLE_GAP_EVENT_PHY_UPDATE_COMPLETE: /* Evento 38 */
            /* Se ha negociado la velocidad física (1M o 2M) */
            ESP_LOGI("GAP", "Evento de velocidad fisica actualizada");
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
