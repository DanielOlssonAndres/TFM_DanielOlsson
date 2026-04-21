#include "gatt_svc.h"
#include "sys_config.h"
#include "freertos/semphr.h"

/* Mutex para proteger los arrays de conexiones concurrentes desde la tarea BLE y la tarea principal */
static SemaphoreHandle_t conn_mutex = NULL;

/* Arrays paralelos para mantener un registro de las conexiones BLE suscritas a notificaciones */
static uint16_t conn_handles[MAX_CONNECTIONS];
static bool conn_slots[MAX_CONNECTIONS] = {0};

/* Punteros a funciones (callbacks) */
static batt_read_cb_t get_battery_level_internal = NULL;

/* Definicion de UUIDs para el perfil GATT usando NimBLE */
/* Servicio del acelerometro */
static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF);
/* Caracteristica de datos del acelerometro */
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01);
/* Servicio de Bateria */
static const ble_uuid16_t batt_svc_uuid = BLE_UUID16_INIT(0x180F);
/* Caracteristica de Nivel de Bateria */
static const ble_uuid16_t batt_chr_uuid = BLE_UUID16_INIT(0x2A19);

/* Handles asignados por la pila BLE al inicializar las caracteristicas */
static uint16_t accel_chr_val_handle;
static uint16_t batt_chr_val_handle;

/* Callback de acceso para la caracteristica de datos del acelerometro */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    return BLE_ATT_ERR_UNLIKELY;
}

/* Callback de acceso para la caracteristica de la bateria */
static int batt_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t lvl;
    
    /* Llama al callback para obtener el porcentaje de bateria */
    lvl = get_battery_level_internal ? get_battery_level_internal() : 0;
    /* Copia el byte de nivel de bateria al buffer mbuf de respuesta */
    return os_mbuf_append(ctxt->om, &lvl, sizeof(lvl)) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

/* Tabla de definicion de servicios y caracteristicas GATT */
static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &accel_svc_uuid.u, .characteristics = (struct ble_gatt_chr_def[]){
        {.uuid = &accel_chr_uuid.u, .access_cb = accel_chr_access, .flags = BLE_GATT_CHR_F_NOTIFY, .val_handle = &accel_chr_val_handle},
        {0} 
    }},
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &batt_svc_uuid.u, .characteristics = (struct ble_gatt_chr_def[]){
        {.uuid = &batt_chr_uuid.u, .access_cb = batt_chr_access, .flags = BLE_GATT_CHR_F_READ, .val_handle = &batt_chr_val_handle}, 
        {0} 
    }}, 
    {0} 
};

/* Funcion para enviar un bloque de muestras del acelerometro a todos los clientes suscritos */
void send_accel_batch(accel_packet_t *batch) {
    int i;
    struct os_mbuf *om;

    /* Bloquea el mutex para evitar que cambie la lista de conexiones mientras iteramos */
    if (xSemaphoreTake(conn_mutex, portMAX_DELAY)) {
        for (i=0; i<MAX_CONNECTIONS; i++) {
            if (conn_slots[i]) {
                /* Crea un buffer mbuf a partir de los datos en crudo */
                om = ble_hs_mbuf_from_flat(batch, sizeof(accel_packet_t));
                /* Si hay memoria disponible, empuja la notificacion al cliente especifico */
                if (om) ble_gatts_notify_custom(conn_handles[i], accel_chr_val_handle, om);
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

/* Callback disparado por el stack BLE cuando un cliente altera sus suscripciones */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    int i;

    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        xSemaphoreTake(conn_mutex, portMAX_DELAY);
        /* cur_notify > 0 indica que el cliente acaba de habilitar las notificaciones */
        if (event->subscribe.cur_notify > 0) {
            /* Busca un slot libre y guarda el handle de la conexion */
            for(i=0; i<MAX_CONNECTIONS; i++) {
                if(!conn_slots[i]) { 
                    conn_handles[i] = event->subscribe.conn_handle; 
                    conn_slots[i] = true; 
                    break; 
                }
            }
        } else {
            /* cur_notify == 0 indica que el cliente ha deshabilitado las notificaciones */
            for(i=0; i<MAX_CONNECTIONS; i++) {
                if(conn_slots[i] && conn_handles[i] == event->subscribe.conn_handle) { 
                    conn_slots[i] = false; 
                    break; 
                }
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

int gatt_svc_init(batt_read_cb_t batt_cb) {
    get_battery_level_internal = batt_cb; 
    
    conn_mutex = xSemaphoreCreateMutex();
    
    ble_svc_gatt_init();
    /* Calcula internamente cuantas definiciones de atributos se necesitan */
    ble_gatts_count_cfg(gatt_svr_svcs);
    /* Registra la estructura de servicios en la pila BLE y devuelve el resultado */
    return ble_gatts_add_svcs(gatt_svr_svcs);
}