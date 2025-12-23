#include "gatt_svc.h"
#include "common.h"
#include "accel.h" 

/* Declaracion de la funcion de acceso (callback) */
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg);

/* UUID del servicio del acelerometro */
static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF);
/* UUID de la característica del acelerometro */
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01);

/* Handles para saber donde escribir/notificar */
static uint16_t accel_chr_val_handle; /*Identificador de la caracteristica de acelerometro*/
static uint16_t accel_chr_conn_handle = 0; /*Identificador del cliente (raspi)*/
static bool accel_chr_conn_handle_inited = false; /*Indica si "accel_chr_conn_handle" tiene un valor valido*/
static bool accel_notify_status = false; /*Indica si el cliente está suscrito*/

/* Tabla de servicios GATT */
static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    {
        /* Servicio de Acelerómetro */
        .type = BLE_GATT_SVC_TYPE_PRIMARY, /*Servicio primario*/
        .uuid = &accel_svc_uuid.u, /*UUID del servicio*/
        .characteristics = (struct ble_gatt_chr_def[]) { /*Sub-lista de caracteristicas*/
            {
                .uuid = &accel_chr_uuid.u, /*UUID del dato*/
                .access_cb = accel_chr_access, /*Callback de acceso a la característica*/
                /*(Permisos). READ: Se puede preguntar puntualmente por los valores. NOTIFY: Envio de datos proactivamente*/
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY, 
                .val_handle = &accel_chr_val_handle /*Identificador de la caracteristica de acelerometro*/
            },
            {
                0, /*Fin de la lista de características*/
            }
        },
    },
    {
        0, /*Fin de la lista de servicios*/
    },
};

/* Callback de acceso a la característica */
/*Argumentos: Quien pregunta, que caracteristica pide, donde se devuelve el dato*/
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg) {
    
    accel_data_t data;
    int rc;

    // Si el móvil intenta LEER (Read Request)
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == accel_chr_val_handle) { /* Se mira si se piden los datos del acelerometro */
            /* Obtenemos el dato mock */
            data = accel_get_data();
            /* Se mete el dato dentro de "ble_gatt_access_ctxt" */
            rc = os_mbuf_append(ctxt->om, &data, sizeof(data));
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES; /* Error si hay fallo en empaquetado */
        }
    }

    /* Si se intenta escribir, que no lo hemos habilitado, el if es falso y devolvemos error */
    return BLE_ATT_ERR_UNLIKELY;
}

/* Funcion para enviar datos activamente */
void send_accel_notification(void) {

    accel_data_t data;
    struct os_mbuf *om;
    int rc;

    /* Verificamos que el cliente esta suscrito y hay una conexion valida */
    if (accel_notify_status && accel_chr_conn_handle_inited) {
        /* Lectura del dato para hacer una copia */
        data = accel_get_data();

        /* Empaquetamos el dato en un 'mbuf' de NimBLE */
        /*ble_hs_mbuf_from_flat convierte los datos crudos en el formato adecuado para NimBLE*/
        om = ble_hs_mbuf_from_flat(&data, sizeof(data));

        /* Se envia la notificacion */
        rc = ble_gatts_notify_custom(accel_chr_conn_handle, accel_chr_val_handle, om);
        if (rc == 0) {
            ESP_LOGI("GATTsvc", "Notificacion enviada: X=%d Y=%d Z=%d", data.x, data.y, data.z);
        } else {
            ESP_LOGE("GATTsvc", "ERROR al notificar. ERROR code: %d", rc);
        }
    }
}

/* Callback de suscripcion (cuando se activa la suscripcion) */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    /* Verificamos la caracteristica a la que se ha suscrito */
    if (event->subscribe.attr_handle == accel_chr_val_handle) { /*Acelerometro*/
        accel_chr_conn_handle = event->subscribe.conn_handle; /*Destinatario*/
        accel_chr_conn_handle_inited = true; /*Indicador de conexion inicializada*/
        accel_notify_status = event->subscribe.cur_notify; /*Estado de la suscripcion*/
    }
}

/* Inicializacion del servicio */
int gatt_svc_init(void) {
    
    int rc;

    ble_svc_gatt_init(); /*Inicializa el servicio GATT (obligatorio por estandar)*/
    rc = ble_gatts_count_cfg(gatt_svr_svcs); /*Contamos los servicios (seguridad)*/
    if (rc != 0) return rc;
    rc = ble_gatts_add_svcs(gatt_svr_svcs); /*Agregamos los servicios definidos*/
    if (rc != 0) return rc;
    return 0;
}

