#include "battery.h"
#include "sys_config.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "BATTERY";
static adc_oneshot_unit_handle_t adc_handle;
static adc_cali_handle_t cali_handle = NULL;
static bool do_calibration = false;
static uint8_t current_battery_percentage = 0;

static bool adc_calibration_init(void) {
    adc_cali_line_fitting_config_t cali_config = {
        .unit_id = BATT_ADC_UNIT,
        .atten = ADC_ATTEN_DB_12, 
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    esp_err_t ret = adc_cali_create_scheme_line_fitting(&cali_config, &cali_handle);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "Calibración lineal ADC configurada");
        return true;
    }
    ESP_LOGW(TAG, "Falló la calibración ADC, usando aproximación bruta");
    return false;
}

esp_err_t battery_init(void) {
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = BATT_ADC_UNIT,
        /* Evita conflictos con la radio BLE */
        .clk_src = ADC_DIGI_CLK_SRC_DEFAULT, 
    };
    esp_err_t ret = adc_oneshot_new_unit(&init_config, &adc_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fallo init ADC: %s", esp_err_to_name(ret));
        return ret;
    }

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12, 
    };
    ret = adc_oneshot_config_channel(adc_handle, PIN_BATT_ADC, &config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fallo config canal ADC: %s", esp_err_to_name(ret));
        return ret;
    }

    do_calibration = adc_calibration_init();
    
    return ESP_OK;
}

static uint8_t voltage_to_percentage(int voltage_mv) {
    if (voltage_mv >= BATT_MAX_VOLTAGE_MV) return 100;
    if (voltage_mv <= BATT_MIN_VOLTAGE_MV) return 0;
    return (uint8_t)(((voltage_mv - BATT_MIN_VOLTAGE_MV) * 100) / (BATT_MAX_VOLTAGE_MV - BATT_MIN_VOLTAGE_MV));
}

void battery_update(void) {
    int adc_raw = 0;
    int voltage = 0;
    
    esp_err_t err = adc_oneshot_read(adc_handle, PIN_BATT_ADC, &adc_raw);
    if (err == ESP_OK) {
        /* Imprime el valor raw para depuración por si el hardware está fallando */
        ESP_LOGD(TAG, "ADC Raw: %d", adc_raw); 

        if (do_calibration) {
            adc_cali_raw_to_voltage(cali_handle, adc_raw, &voltage);
            voltage = voltage * BATT_DIVIDER_MULT;
        } else {
            /* Fórmula manual: (Raw / max_raw) * v_ref * mult */
            /* En ESP32 a 12dB, el full scale no es 3.3V exactos, suele ser ~3.1V efectivos */
            voltage = ((adc_raw * 3100) / 4095) * BATT_DIVIDER_MULT; 
        }
        
        ESP_LOGD(TAG, "Voltaje Batería Estimado: %d mV", voltage);
        current_battery_percentage = voltage_to_percentage(voltage);
    } else {
        ESP_LOGE(TAG, "Error lectura ADC: %s", esp_err_to_name(err));
    }
}

uint8_t battery_get_level(void) {
    return current_battery_percentage;
}