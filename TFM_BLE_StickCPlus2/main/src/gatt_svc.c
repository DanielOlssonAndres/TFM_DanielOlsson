#include "gatt_svc.h"
#include "sys_config.h"
#include "freertos/semphr.h"
#include "esp_timer.h"

static SemaphoreHandle_t conn_mutex = NULL;
static uint16_t conn_handles[MAX_CONNECTIONS];
static bool conn_slots[MAX_CONNECTIONS] = {0};
static int active_subscribers_count = 0;

static batt_read_cb_t get_battery_level_internal = NULL;
static accel_read_cb_t get_accel_sample_internal = NULL;
static on_first_subscribe_cb_t on_subscribe_internal = NULL;

static const ble_uuid16_t accel_svc_uuid = BLE_UUID16_INIT(0x00FF);
static const ble_uuid16_t accel_chr_uuid = BLE_UUID16_INIT(0xFF01);
static const ble_uuid16_t sync_chr_uuid = BLE_UUID16_INIT(0xFF02);
static const ble_uuid16_t batt_svc_uuid = BLE_UUID16_INIT(0x180F);
static const ble_uuid16_t batt_chr_uuid = BLE_UUID16_INIT(0x2A19);

static uint16_t accel_chr_val_handle;
static uint16_t sync_chr_val_handle;
static uint16_t batt_chr_val_handle;

static int sync_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        // Ignoramos el valor recibido, solo usamos el evento para resetear buffers
        if (on_subscribe_internal) on_subscribe_internal();
        return 0;
    }
    return BLE_ATT_ERR_UNLIKELY;
}

static int accel_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    accel_raw_t data;
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (get_accel_sample_internal) get_accel_sample_internal(&data);
        return os_mbuf_append(ctxt->om, &data, sizeof(data)) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }
    return BLE_ATT_ERR_UNLIKELY;
}

static int batt_chr_access(uint16_t conn_handle, uint16_t attr_handle, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    uint8_t lvl = get_battery_level_internal ? get_battery_level_internal() : 0;
    return os_mbuf_append(ctxt->om, &lvl, sizeof(lvl)) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &accel_svc_uuid.u, .characteristics = (struct ble_gatt_chr_def[]){
        {.uuid = &accel_chr_uuid.u, .access_cb = accel_chr_access, .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY, .val_handle = &accel_chr_val_handle},
        {.uuid = &sync_chr_uuid.u, .access_cb = sync_chr_access, .flags = BLE_GATT_CHR_F_WRITE, .val_handle = &sync_chr_val_handle}, {0}}},
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &batt_svc_uuid.u, .characteristics = (struct ble_gatt_chr_def[]){
        {.uuid = &batt_chr_uuid.u, .access_cb = batt_chr_access, .flags = BLE_GATT_CHR_F_READ, .val_handle = &batt_chr_val_handle}, {0}}}, {0}
};

void send_accel_batch(accel_packet_t *batch) {
    if (xSemaphoreTake(conn_mutex, portMAX_DELAY)) {
        for (int i=0; i<MAX_CONNECTIONS; i++) {
            if (conn_slots[i]) {
                struct os_mbuf *om = ble_hs_mbuf_from_flat(batch, sizeof(accel_packet_t));
                if (om) ble_gatts_notify_custom(conn_handles[i], accel_chr_val_handle, om);
            }
        }
        xSemaphoreGive(conn_mutex);
    }
}

void gatt_svr_subscribe_cb(struct ble_gap_event *event) {
    if (event->subscribe.attr_handle == accel_chr_val_handle) {
        xSemaphoreTake(conn_mutex, portMAX_DELAY);
        if (event->subscribe.cur_notify > 0) {
            for(int i=0; i<MAX_CONNECTIONS; i++) if(!conn_slots[i]) { conn_handles[i] = event->subscribe.conn_handle; conn_slots[i] = true; break; }
        } else {
            for(int i=0; i<MAX_CONNECTIONS; i++) if(conn_slots[i] && conn_handles[i] == event->subscribe.conn_handle) { conn_slots[i] = false; break; }
        }
        xSemaphoreGive(conn_mutex);
    }
}

int gatt_svc_init(batt_read_cb_t batt_cb, accel_read_cb_t accel_cb, on_first_subscribe_cb_t sub_cb) {
    get_battery_level_internal = batt_cb; get_accel_sample_internal = accel_cb; on_subscribe_internal = sub_cb;
    conn_mutex = xSemaphoreCreateMutex();
    ble_svc_gatt_init();
    ble_gatts_count_cfg(gatt_svr_svcs);
    return ble_gatts_add_svcs(gatt_svr_svcs);
}