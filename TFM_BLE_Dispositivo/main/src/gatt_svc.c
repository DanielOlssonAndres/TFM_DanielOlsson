#include "gatt_svc.h"
#include "common.h"
#include "accel.h" 

#define MAX_CONN MAX_CONNECTIONS_OPEN_MODE

/* Array para guardar quién está conectado */
static uint16_t conn_handles[MAX_CONNECTIONS]; 
static bool conn_slots[MAX_CONNECTIONS] = {0}; /* false = libre, true = ocupado */
static int active_subscribers_count = 0;

static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF); /* UUID del servicio del acelerometro */
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01); /* UUID de la característica del acelerometro */
static uint16_t accel_chr_val_handle; /* Identificador de la caracteristica de acelerometro */

static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg);

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
            {
                0, /*Fin de la lista de características*/
            }
        },
    },
    {
        0, /*Fin de la lista de servicios*/
    },
};

/* Función para añadir suscripciones */
static void add_subscriber(uint16_t conn_handle) {
    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (!conn_slots[i]) { /* Buscamos hueco libre */
            conn_handles[i] = conn_handle;
            conn_slots[i] = true;
            active_subscribers_count++;
            return;
        }
    }
}

/* Función para quitar suscripciones */
static void remove_subscriber(uint16_t conn_handle) {
    for (int i = 0; i < MAX_CONNECTIONS; i++) {
        if (conn_slots[i] && conn_handles[i] == conn_handle) {
            conn_slots[i] = false; /* Liberamos el hueco */
            if (active_subscribers_count > 0) {
                active_subscribers_count--; 
            }
            return;
        }
    }
}

/* Callback de acceso único a la característica */
/*Argumentos: Quien pregunta, que caracteristica pide, donde se devuelve el dato*/
static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg) {
    
    accel_raw_t single_data;
    int rc;

    // Si se intenta LEER (Read Request)
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (attr_handle == accel_chr_val_handle) { /* Se mira si se piden los datos del acelerometro */
            /* Devolvemos solo la ultima muestra */
            single_data = accel_get_last_sample();
            /* Se mete el dato dentro de "ble_gatt_access_ctxt" */
            rc = os_mbuf_append(ctxt->om, &single_data, sizeof(single_data));
            return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES; /* Error si hay fallo en empaquetado */
        }
    }

    /* Si se intenta escribir, que no lo hemos habilitado, el if es falso y devolvemos error */
    return BLE_ATT_ERR_UNLIKELY;
}

/* ----------------- FUNCIONES PÚBLICAS --------------------- */

/* Función de envío de Bloques */
void send_accel_batch(void) {
    accel_packet_t *batch;
    struct os_mbuf *om;

    /* Si no hay nadie escuchando, vaciamos buffer y salimos */
    if (active_subscribers_count == 0) {
        accel_get_batch(); 
        return;
    }
    
    batch = accel_get_batch();

    /* Comprobar si hay alguien escuchando */
    for (int i=0; i<MAX_CONNECTIONS; i++) {
        if (conn_slots[i]) {
            /* Crear un mbuf NUEVO para cada envío */
            om = ble_hs_mbuf_from_flat(batch, sizeof(accel_packet_t));
            ble_gatts_notify_custom(conn_handles[i], accel_chr_val_handle, om);
            break;
        }
    }
}

/* Callback de suscripcion (cuando se activa la suscripcion) */
void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        if (event->subscribe.cur_notify > 0) {
            if (active_subscribers_count == 0) {
                accel_reset_counters();
            }
            add_subscriber(event->subscribe.conn_handle);
        } else {
            remove_subscriber(event->subscribe.conn_handle);
        }
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

