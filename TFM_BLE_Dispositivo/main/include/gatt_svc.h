#ifndef GATT_SVR_H
#define GATT_SVR_H

#include <stdint.h>
#include "host/ble_gatt.h"
#include "services/gatt/ble_svc_gatt.h"
#include "host/ble_gap.h"
#include "sensor_type.h" 

typedef uint8_t (*batt_read_cb_t)(void);
typedef void (*accel_read_cb_t)(accel_raw_t *sample_out);
typedef void (*on_first_subscribe_cb_t)(void);

int gatt_svc_init(batt_read_cb_t batt_cb, accel_read_cb_t accel_cb, on_first_subscribe_cb_t sub_cb);
void send_accel_batch(accel_packet_t *batch);
void gatt_svr_subscribe_cb(struct ble_gap_event *event);

#endif // GATT_SVR_H