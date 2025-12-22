#ifndef GAP_SVC_H
#define GAP_SVC_H

/* Includes */
#include "host/ble_gap.h"
#include "services/gap/ble_svc_gap.h"

/* Defines */
#define BLE_GAP_LE_ROLE_PERIPHERAL 0x00

/* Declaraciones de las funciones */
void adv_init(void);
int gap_init(void);

#endif // GAP_SVC_H
