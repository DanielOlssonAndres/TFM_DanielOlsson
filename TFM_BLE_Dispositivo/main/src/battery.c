#include "battery.h"
#include "common.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define BATT_ADC_UNIT    ADC_UNIT_1
#define BATT_ADC_CHANNEL ADC_CHANNEL_6 /* GPIO 34 */
#define BATT_SAMPLE_TIME_MS 10000      /* Lectura cada 10 segundos */

static adc_oneshot_unit_handle_t adc1_handle;
static adc_cali_handle_t cali_handle = NULL;
static bool do_calibration = false;
static uint8_t current_battery_level = 100;

/* Convierte el voltaje leído a porcentaje (Aproximación lineal simple para LiPo 3.3V - 4.2V) */
static uint8_t voltage_to_percentage(int voltage_mv) {
    /* El divisor de tensión divide a la mitad. Voltaje real = voltaje_mv * 2 */
    int real_voltage_mv = voltage_mv * 2;
    
    if (real_voltage_mv >= 4200) return 100;
    if (real_voltage_mv <= 3300) return 0;
    
    return (uint8_t)(((real_voltage_mv - 3300) * 100) / (4200 - 3300));
}

/* Tarea de lectura pasiva */
static void battery_task(void *param) {
    while (1) {
        int adc_raw = 0;
        int voltage = 0;
        int adc_reading_sum = 0;
        
        /* Multisampling para estabilizar la lectura */
        for (int i = 0; i < 10; i++) {
            ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, BATT_ADC_CHANNEL, &adc_raw));
            adc_reading_sum += adc_raw;
            vTaskDelay(pdMS_TO_TICKS(10));
        }
        adc_raw = adc_reading_sum / 10;

        /* Convertir raw a milivoltios aplicando calibración si está disponible */
        if (do_calibration) {
            ESP_ERROR_CHECK(adc_cali_raw_to_voltage(cali_handle, adc_raw, &voltage));
        } else {
            /* Si falla la calibración, se hace una estimación rudimentaria sin calibrar (poco preciso) */
            voltage = (adc_raw * 2450) / 4095; 
        }

        current_battery_level = voltage_to_percentage(voltage);

        vTaskDelay(pdMS_TO_TICKS(BATT_SAMPLE_TIME_MS));
    }
}

esp_err_t battery_init(void) {
    esp_err_t ret;

    /* 1. Configurar la unidad ADC */
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = BATT_ADC_UNIT,
        .clk_src = ADC_RTC_CLK_SRC_DEFAULT,
    };
    ret = adc_oneshot_new_unit(&init_config, &adc1_handle);
    if (ret != ESP_OK) return ret;

    /* 2. Configurar el canal ADC (Atenuación 11dB, 12 bits) */
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_11,
    };
    ret = adc_oneshot_config_channel(adc1_handle, BATT_ADC_CHANNEL, &config);
    if (ret != ESP_OK) return ret;

    /* 3. Configurar la calibración (Line Fitting para ESP32 clásico) */
    adc_cali_line_fitting_config_t cali_config = {
        .unit_id = BATT_ADC_UNIT,
        .atten = ADC_ATTEN_DB_11,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    
    ret = adc_cali_create_scheme_line_fitting(&cali_config, &cali_handle);
    if (ret == ESP_OK) {
        do_calibration = true;
    } else {
        ESP_LOGW("BATT", "Calibración no soportada o fallida. Usando valores raw.");
    }

    /* 4. Crear tarea de lectura pasiva (Prioridad 2) */
    xTaskCreate(battery_task, "Battery_Task", 2048, NULL, 2, NULL);

    return ESP_OK;
}

uint8_t battery_get_level(void) {
    return current_battery_level;
}