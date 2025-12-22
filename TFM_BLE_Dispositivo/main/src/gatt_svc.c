#include "gatt_svc.h"
#include "common.h"
#include "accel.h" 

/* Declaración de la función de acceso (callback) */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg);

/* Variables Privadas */

/* * UUIDs Personalizados para tu TFM 
 * (Es buena práctica no usar UUIDs reservados si no sigues el estándar estricto)
 * Servicio: 0x00FF
 * Característica: 0xFF01
 */
static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF);
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01);

/* Handles (Manejadores) para saber dónde escribir/notificar */
static uint16_t accel_chr_val_handle;
static uint16_t accel_chr_conn_handle = 0;
static bool accel_chr_conn_handle_inited = false;
static bool accel_notify_status = false; 

/* Tabla de Servicios GATT */
static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    {
        /* Servicio de Acelerómetro */
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &accel_svc_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                /* Característica de Datos (Lectura y Notificación) */
                .uuid = &accel_chr_uuid.u,
                .access_cb = accel_chr_access,
                /* Usamos NOTIFY en vez de INDICATE porque es más rápido para sensores */
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY, 
                .val_handle = &accel_chr_val_handle
            },
            {
                0, /* Fin de características */
            }
        },
    },
    {
        0, /* Fin de servicios */
    },
};

/* Función que se ejecuta cuando el móvil lee o se suscribe */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg) {
    
    // Si el móvil intenta LEER (Read Request)
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == accel_chr_val_handle) {
            // 1. Obtenemos el dato mock
            accel_data_t data = accel_get_data();
            
            // 2. Lo empaquetamos en el buffer de salida
            int rc = os_mbuf_append(ctxt->om, &data, sizeof(data));
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
    }

    return BLE_ATT_ERR_UNLIKELY;
}

/* Función Pública: Enviar datos al móvil activamente */
void send_accel_notification(void) {
    if (accel_notify_status && accel_chr_conn_handle_inited) {
        // 1. Leemos el dato mock
        accel_data_t data = accel_get_data();

        // 2. Empaquetamos el dato en un 'mbuf' de NimBLE
        // ble_hs_mbuf_from_flat convierte tus datos crudos en el formato que NimBLE quiere.
        struct os_mbuf *om = ble_hs_mbuf_from_flat(&data, sizeof(data));

        // 3. Enviamos la notificación
        // Ahora sí le pasamos el 'om' (3 argumentos, no 4)
        int rc = ble_gatts_notify_custom(accel_chr_conn_handle, 
                                         accel_chr_val_handle, 
                                         om);
        
        if (rc == 0) {
            ESP_LOGI(TAG, "Notificación enviada: X=%d Y=%d Z=%d", data.x, data.y, data.z);
        } else {
            ESP_LOGE(TAG, "Error al notificar: %d", rc);
        }
    }
}

/* Callback de suscripción (cuando activas la campanita en el móvil) */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        accel_chr_conn_handle = event->subscribe.conn_handle;
        accel_chr_conn_handle_inited = true;
        accel_notify_status = event->subscribe.cur_notify; // Guardamos si activó notificaciones
        
        ESP_LOGI(TAG, "Suscripción actualizada. Notificar: %d", accel_notify_status);
    }
}

/* Inicialización del Servicio (Igual que antes) */
int gatt_svc_init(void) {
    int rc;
    ble_svc_gatt_init();
    rc = ble_gatts_count_cfg(gatt_svr_svcs);
    if (rc != 0) return rc;
    rc = ble_gatts_add_svcs(gatt_svr_svcs);
    if (rc != 0) return rc;
    return 0;
}

/* * Callback para registrar eventos GATT 
 * (Necesario para que el main.c no de error al compilar)
 */
void gatt_svr_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg) {
    char buf[BLE_UUID_STR_LEN];

    switch (ctxt->op) {
    case BLE_GATT_REGISTER_OP_SVC:
        ESP_LOGD(TAG, "Servicio registrado %s handle=%d",
                 ble_uuid_to_str(ctxt->svc.svc_def->uuid, buf),
                 ctxt->svc.handle);
        break;

    case BLE_GATT_REGISTER_OP_CHR:
        ESP_LOGD(TAG, "Caracteristica registrada %s handle=%d",
                 ble_uuid_to_str(ctxt->chr.chr_def->uuid, buf),
                 ctxt->chr.val_handle);
        break;

    default:
        break;
    }
}