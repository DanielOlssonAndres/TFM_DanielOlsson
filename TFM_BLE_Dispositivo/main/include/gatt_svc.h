#ifndef GATT_SVR_H
#define GATT_SVR_H

#include "host/ble_gatt.h"
#include "services/gatt/ble_svc_gatt.h"
#include "host/ble_gap.h"

/* Declaraciones de las funciones */
void send_accel_notification(void);
void gatt_svr_subscribe_cb(struct ble_gap_event *event);
int gatt_svc_init(void);
void send_accel_batch(void);

#endif // GATT_SVR_H