#include "gatt_svc.h"
#include "sys_config.h"
#include "freertos/semphr.h"
#include "esp_log.h"

/* Mutex */
static SemaphoreHandle_t conn_mutex = NULL;

/* Array para guardar quién está conectado */
static uint16_t conn_handles[MAX_CONNECTIONS]; 
static bool conn_slots[MAX_CONNECTIONS] = {0}; /* false = libre, true = ocupado */
static int active_subscribers_count = 0;

/* Variables para almacenar los callbacks inyectados */
static batt_read_cb_t get_battery_level_internal = NULL;
static accel_read_cb_t get_accel_sample_internal = NULL;
static on_first_subscribe_cb_t on_subscribe_internal = NULL;

/* UUIDs para los servicios y características */
static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF); /* UUID del servicio del acelerometro */
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01); /* UUID de la característica del acelerometro */
static uint16_t accel_chr_val_handle; /* Identificador de la caracteristica de acelerometro */
static const ble_uuid16_t batt_svc_uuid = BLE_UUID16_INIT(0x180F);
static const ble_uuid16_t batt_chr_uuid = BLE_UUID16_INIT(0x2A19);
static uint16_t batt_chr_val_handle;

static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);
static int batt_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);

static const struct ble_gatt_svc_def gatt_svr_svcs[] = { /* Tabla de servicios GATT */
    {
        /* Servicio de Acelerómetro */
        .type = BLE_GATT_SVC_TYPE_PRIMARY, /*Servicio primario*/
        .uuid = &accel_svc_uuid.u, /*UUID del servicio*/
        .characteristics = (struct ble_gatt_chr_def[]) { /*Sub-lista de caracteristicas*/
            {
                .uuid = &accel_chr_uuid.u, /*UUID del dato*/
                .access_cb = accel_chr_access, /*Callback de acceso a la característica*/
                /*(Permisos). ENCRIPTADO. NOTIFY: Envio de datos proactivamente*/
                .flags = BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &accel_chr_val_handle /*Identificador de la caracteristica de acelerometro*/
            },
            { 0 } /*Fin de la lista de características*/
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
                /* Lectura encriptada (just works) */
                .flags = BLE_GATT_CHR_F_READ,
                .val_handle = &batt_chr_val_handle
            },
            { 0 }
        },
    },
    
    { 0 } /* Fin de la lista de servicios */
};

/* Función para añadir suscripciones */
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

/* Función para quitar suscripciones */
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

/* Callback de acceso único a la característica */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    accel_raw_t single_data = {0,0,0};
    int rc;
    
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == accel_chr_val_handle) { 
            // Inyección por referencia
            if (get_accel_sample_internal) {
                get_accel_sample_internal(&single_data);
            }
            rc = os_mbuf_append(ctxt->om, &single_data, sizeof(single_data));
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES; 
        }
    }
    return BLE_ATT_ERR_UNLIKELY;
}

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

/* Función de envío de Bloques */
void send_accel_batch(accel_packet_t *batch) {
    struct os_mbuf *om;

    if (xSemaphoreTake(conn_mutex, portMAX_DELAY) == pdTRUE) {
        if (active_subscribers_count == 0 || batch == NULL) {
            xSemaphoreGive(conn_mutex);
            return;
        }
        
        for (int i=0; i<MAX_CONNECTIONS; i++) {
            if (conn_slots[i]) {
                om = ble_hs_mbuf_from_flat(batch, sizeof(accel_packet_t));
                if (om != NULL) {
                    ble_gatts_notify_custom(conn_handles[i], accel_chr_val_handle, om);
                } else {
                    ESP_LOGW("GATT", "Pool mbufs agotado.");
                }       
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

/* Callback de suscripcion (cuando se activa la suscripcion) */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        if (event->subscribe.cur_notify > 0) {
            if (active_subscribers_count == 0) {
                /* Llamamos al callback inyectado en lugar de usar la dependencia directa */
                if (on_subscribe_internal != NULL) {
                    on_subscribe_internal();
                }
            }
            add_subscriber(event->subscribe.conn_handle);
        } else {
            remove_subscriber(event->subscribe.conn_handle);
        }
    }
}

/* Inicializacion del servicio */
int gatt_svc_init(batt_read_cb_t batt_cb, accel_read_cb_t accel_cb, on_first_subscribe_cb_t sub_cb) {
    int rc;
    get_battery_level_internal = batt_cb;
    get_accel_sample_internal = accel_cb;
    on_subscribe_internal = sub_cb;

    conn_mutex = xSemaphoreCreateMutex();
    if (conn_mutex == NULL) { return BLE_HS_ENOMEM; }

    ble_svc_gatt_init(); 
    rc = ble_gatts_count_cfg(gatt_svr_svcs); 
    if (rc != 0) return rc;
    rc = ble_gatts_add_svcs(gatt_svr_svcs); 
    if (rc != 0) return rc;
    return 0;
}

