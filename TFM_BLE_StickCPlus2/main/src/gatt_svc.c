#include "gatt_svc.h"
#include "sys_config.h"
#include "freertos/semphr.h"
#include "esp_log.h"

/* Mutex para proteger las variables de estado de las conexiones */
static SemaphoreHandle_t conn_mutex = NULL;

static int64_t conn_time_offsets[MAX_CONNECTIONS] = {0}; /* Almacena el tiempo de conexión para cada cliente, usado para calcular timestamps relativos */
static uint16_t conn_handles[MAX_CONNECTIONS]; /* Almacena los identificadores de conexión de NimBLE */
static bool conn_slots[MAX_CONNECTIONS] = {0}; /* Mapa de bits (implementado como array de booleanos) en búsqueda de slots libres*/
static int active_subscribers_count = 0;

/* Punteros a funciones (Callbacks) inyectados desde la capa de aplicación */
/* Desacoplan la lógica del sensor de la lógica BLE */
static batt_read_cb_t get_battery_level_internal = NULL;
static accel_read_cb_t get_accel_sample_internal = NULL;
static on_first_subscribe_cb_t on_subscribe_internal = NULL;

/* Definición de UUIDs de 16 bits */
static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF); 
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01); 
static const ble_uuid16_t batt_svc_uuid = BLE_UUID16_INIT(0x180F);
static const ble_uuid16_t batt_chr_uuid = BLE_UUID16_INIT(0x2A19); 
static const ble_uuid16_t sync_chr_uuid = BLE_UUID16_INIT(0xFF02);

/* Handles de las características */
static uint16_t accel_chr_val_handle; 
static uint16_t batt_chr_val_handle;
static uint16_t sync_chr_val_handle;

/* Prototipos locales para las funciones de acceso GATT */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);
static int batt_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);
static int sync_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);

/* Tabla de definición del árbol GATT */
static const struct ble_gatt_svc_def gatt_svr_svcs[] = { 
    {
        /* Servicio de Acelerómetro */
        .type = BLE_GATT_SVC_TYPE_PRIMARY, 
        .uuid = &accel_svc_uuid.u, 
        .characteristics = (struct ble_gatt_chr_def[]) { 
            {
                .uuid = &accel_chr_uuid.u, 
                .access_cb = accel_chr_access, 
                /* READ_ENC: Requiere conexión encriptada para lectura explícita */
                /* NOTIFY: Permite al servidor enviar actualizaciones sin petición del cliente */
                .flags = BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &accel_chr_val_handle 
            },
            {
                .uuid = &sync_chr_uuid.u,
                .access_cb = sync_chr_access,
                .flags = BLE_GATT_CHR_F_WRITE,
                .val_handle = &sync_chr_val_handle
            },
            { 0 }
        },
    },

    {
        /* Servicio de Batería */
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &batt_svc_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &batt_chr_uuid.u,
                .access_cb = batt_chr_access,
                /* Lectura estándar sin requerir encriptación */
                .flags = BLE_GATT_CHR_F_READ,
                .val_handle = &batt_chr_val_handle
            },
            { 0 }
        },
    },
    
    { 0 } 
};

/* Registra una nueva conexión como suscriptora de notificaciones */
/* Protegido por mutex ya que interacciona con la tarea host de NimBLE */
static void add_subscriber(uint16_t conn_handle) {
    if (xSemaphoreTake(conn_mutex, portMAX_DELAY) == pdTRUE) {
        for (int i = 0; i < MAX_CONNECTIONS; i++) {
            if (!conn_slots[i]) { 
                conn_handles[i] = conn_handle;
                conn_slots[i] = true;
                active_subscribers_count++;
                break; 
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

/* Elimina una conexión del registro de suscriptores */
static void remove_subscriber(uint16_t conn_handle) {
    if (xSemaphoreTake(conn_mutex, portMAX_DELAY) == pdTRUE) {
        for (int i = 0; i < MAX_CONNECTIONS; i++) {
            if (conn_slots[i] && conn_handles[i] == conn_handle) {
                conn_slots[i] = false; 
                if (active_subscribers_count > 0) {
                    active_subscribers_count--; 
                }
                break; 
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

/* Callback de escritura. La Raspi envía su tiempo actual */
static int sync_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint64_t master_time_ms;
        if (os_mbuf_copydata(ctxt->om, 0, sizeof(uint64_t), &master_time_ms) != 0) return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;

        uint64_t local_now = esp_timer_get_time() / 1000;

        if (xSemaphoreTake(conn_mutex, portMAX_DELAY) == pdTRUE) {
            for (int i = 0; i < MAX_CONNECTIONS; i++) {
                if (conn_slots[i] && conn_handles[i] == conn_handle) {
                    // Offset = Tiempo_Raspi - Tiempo_ESP32
                    conn_time_offsets[i] = (int64_t)master_time_ms - (int64_t)local_now;
                    break;
                }
            }
            xSemaphoreGive(conn_mutex);
        }
        return 0;
    }
    return BLE_ATT_ERR_UNLIKELY;
}

/* Callback ejecutado por la tarea de NimBLE cuando un cliente GATT lee la característica */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    accel_raw_t single_data = {0,0,0};
    int rc;
    
    /* Verifica que la operación sea de lectura */
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == accel_chr_val_handle) { 
            /* Invoca el callback de la capa de aplicación para obtener el dato más reciente */
            if (get_accel_sample_internal) {
                get_accel_sample_internal(&single_data);
            }
            /* Adjunta el dato al buffer de memoria (mbuf) de la pila BLE */
            rc = os_mbuf_append(ctxt->om, &single_data, sizeof(single_data));
            /* Devuelve 0 si fue exitoso, o código de error de recursos insuficientes */
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES; 
        }
    }
    return BLE_ATT_ERR_UNLIKELY;
}

/* Callback para lectura del nivel de batería */
static int batt_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t batt_level = 0;
    int rc;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == batt_chr_val_handle) {
            if (get_battery_level_internal) {
                batt_level = get_battery_level_internal();
            }
            rc = os_mbuf_append(ctxt->om, &batt_level, sizeof(batt_level));
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
    }
    return BLE_ATT_ERR_UNLIKELY;
}

/* Función llamada por la aplicación para hacer un push de un lote de datos a todos los clientes */
void send_accel_batch(accel_packet_t *batch) {
    struct os_mbuf *om;
    if (xSemaphoreTake(conn_mutex, portMAX_DELAY) == pdTRUE) {
        for (int i=0; i<MAX_CONNECTIONS; i++) {
            if (conn_slots[i]) {
                accel_packet_t translated_packet = *batch;
                // Aplicamos el offset específico de esta conexión
                translated_packet.timestamp_start = (uint64_t)((int64_t)batch->timestamp_start + conn_time_offsets[i]);

                om = ble_hs_mbuf_from_flat(&translated_packet, sizeof(accel_packet_t));
                if (om) ble_gatts_notify_custom(conn_handles[i], accel_chr_val_handle, om);
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

/* Callback invocado por GAP en eventos de suscripción */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        /* cur_notify > 0 significa que el cliente ha activado las notificaciones */
        if (event->subscribe.cur_notify > 0) {
            if (active_subscribers_count == 0) {
                /* Dispara evento de primera suscripción */
                if (on_subscribe_internal != NULL) {
                    on_subscribe_internal();
                }
            }
            add_subscriber(event->subscribe.conn_handle);
        } else {
            /* El cliente ha desactivado las notificaciones */
            remove_subscriber(event->subscribe.conn_handle);
        }
    }
}

/* Inicialización del servicio GATT */
int gatt_svc_init(batt_read_cb_t batt_cb, accel_read_cb_t accel_cb, on_first_subscribe_cb_t sub_cb) {
    int rc;
    get_battery_level_internal = batt_cb;
    get_accel_sample_internal = accel_cb;
    on_subscribe_internal = sub_cb;

    conn_mutex = xSemaphoreCreateMutex();
    if (conn_mutex == NULL) { return BLE_HS_ENOMEM; }

    ble_svc_gatt_init(); 
    
    /* Pre-calcula los recursos necesarios para la tabla de servicios */
    rc = ble_gatts_count_cfg(gatt_svr_svcs); 
    if (rc != 0) return rc;
    
    /* Añade los servicios a la base de datos de NimBLE */
    rc = ble_gatts_add_svcs(gatt_svr_svcs); 
    if (rc != 0) return rc;
    
    return 0;
}