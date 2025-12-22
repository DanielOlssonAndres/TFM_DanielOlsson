#include "accel.h"
#include "esp_log.h"

static const char *TAG = "ACCEL";

void accel_init(void) {
    // Aquí iría la configuración I2C real en el futuro
    ESP_LOGI(TAG, "Acelerometro inicializado (MOCK)");
}

accel_data_t accel_get_data(void) {
    accel_data_t data;
    
    data.x = 1;
    data.y = 1;
    data.z = 1;

    return data;
}