#include "accel.h"
#include "common.h"

void accel_init(void) {
    
    ESP_LOGI("ACCEL", "Acelerometro inicializado"); /*Mensaje por terminal de tipo INFO*/
}

accel_data_t accel_get_data(void) {
    accel_data_t data;
    
    data.x = 1;
    data.y = 1;
    data.z = 1;

    return data;
}