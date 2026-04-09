#include "battery.h"
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "esp_log.h"
#include "sys_config.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static adc_oneshot_unit_handle_t adc1_handle;
static adc_cali_handle_t cali_handle = NULL;
static bool do_calibration = false;
static uint8_t current_battery_level = 100;

/* Convierte el voltaje leído a porcentaje (Aproximación lineal simple para LiPo 3.3V - 4.2V) */
static uint8_t voltage_to_percentage(int voltage_mv) {
    int real_voltage_mv = voltage_mv * 2;
    
    if (real_voltage_mv >= BATT_MAX_VOLTAGE_MV) return 100;
    if (real_voltage_mv <= BATT_MIN_VOLTAGE_MV) return 0;
    
    return (uint8_t)(((real_voltage_mv - BATT_MIN_VOLTAGE_MV) * 100) / (BATT_MAX_VOLTAGE_MV - BATT_MIN_VOLTAGE_MV));
}

void battery_update(void) {
    int adc_raw = 0;
    int voltage = 0;
    int adc_reading_sum = 0;
    
    /* Multisampling para estabilizar la lectura */
    for (int i = 0; i < 10; i++) {
        esp_err_t err = adc_oneshot_read(adc1_handle, PIN_BATT_ADC, &adc_raw);
        if (err == ESP_OK) {
            adc_reading_sum += adc_raw;
        }
        vTaskDelay(pdMS_TO_TICKS(10)); 
    }
    adc_raw = adc_reading_sum / 10;

    /* Convertir raw a milivoltios aplicando calibración si está disponible */
    if (do_calibration) {
        esp_err_t err = adc_cali_raw_to_voltage(cali_handle, adc_raw, &voltage);
        if (err != ESP_OK) {
            ESP_LOGW("BATT", "Error en conversión calibrada");
        }
    } else {
        /* Estimación sin calibrar */
        voltage = (adc_raw * 2450) / 4095; 
    }

    current_battery_level = voltage_to_percentage(voltage);
}

esp_err_t battery_init(void) {
    esp_err_t ret;

    /* Configurar la unidad ADC */
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = BATT_ADC_UNIT,
        .clk_src = ADC_RTC_CLK_SRC_DEFAULT,
    };
    ret = adc_oneshot_new_unit(&init_config, &adc1_handle);
    if (ret != ESP_OK) return ret;

    /* Configurar el canal ADC (Atenuación 12dB en IDF v5, 12 bits) */
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12, 
    };
    ret = adc_oneshot_config_channel(adc1_handle, PIN_BATT_ADC, &config);
    if (ret != ESP_OK) return ret;

    /* Configurar la calibración (Line Fitting para ESP32 clásico) */
    adc_cali_line_fitting_config_t cali_config = {
        .unit_id = BATT_ADC_UNIT,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    
    ret = adc_cali_create_scheme_line_fitting(&cali_config, &cali_handle);
    if (ret == ESP_OK) {
        do_calibration = true;
    } else {
        ESP_LOGW("BATT", "Calibración no soportada o fallida. Usando valores raw.");
    }

    /* Realizar una lectura inicial */
    battery_update();

    return ESP_OK;
}

uint8_t battery_get_level(void) {
    return current_battery_level;
}