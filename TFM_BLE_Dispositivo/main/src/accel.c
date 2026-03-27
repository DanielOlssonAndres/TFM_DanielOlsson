#include "accel.h"
#include "common.h"
#include "driver/i2c.h"
#include "esp_timer.h" // Para el reloj de alta precisión
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#define I2C_MASTER_SCL_IO           33    /* GPIO para Clock (SCL) */
#define I2C_MASTER_SDA_IO           32    /* GPIO para Data (SDA) */
#define I2C_MASTER_NUM              0     /* Puerto I2C 0 */
#define I2C_MASTER_FREQ_HZ          400000 /* 400kHz (Fast Mode) */
#define I2C_MASTER_TX_BUF_DISABLE   0     /* I2C master no necesita buffer */
#define I2C_MASTER_RX_BUF_DISABLE   0

/* Registros MPU6050 */
#define MPU6050_ADDR                0x68  /* Dirección I2C (AD0 a GND) */
#define MPU6050_PWR_MGMT_1          0x6B  /* Registro de energía */
#define MPU6050_ACCEL_CONFIG        0x1C  /* Configuración del acelerómetro */
#define MPU6050_ACCEL_XOUT_H        0x3B  /* Primer registro de datos */

/* Mutex */
static SemaphoreHandle_t accel_mutex = NULL;

static accel_packet_t acc_buffer; /* El paquete que estamos llenando */
static accel_raw_t last_sample; /* Ultima muestra */
static int sample_count = 0; /* Cuantas muestras llevamos en este paquete */
static uint32_t global_packet_counter = 0; /* ID de secuencia */
static int64_t start_time_offset = 0; /* Offset de tiempo al iniciar */

/* Inicializar el driver I2C del ESP32 */
static esp_err_t i2c_master_init(void) {
    esp_err_t err;
    
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = I2C_MASTER_SDA_IO,
        .scl_io_num = I2C_MASTER_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_MASTER_FREQ_HZ,
    };

    err = i2c_param_config(I2C_MASTER_NUM, &conf);
    if (err != ESP_OK) return err;

    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, I2C_MASTER_RX_BUF_DISABLE, I2C_MASTER_TX_BUF_DISABLE, 0);
}

/* Escribir un byte en un registro del MPU6050 */
static esp_err_t mpu6050_write_byte(uint8_t reg_addr, uint8_t data) {
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, reg_addr, true);
    i2c_master_write_byte(cmd, data, true);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);
    return ret;
}

esp_err_t accel_init(void) {
    accel_mutex = xSemaphoreCreateMutex();
    if (accel_mutex == NULL) return ESP_FAIL;

    esp_err_t err = i2c_master_init();
    if (err != ESP_OK) return err;

    err = mpu6050_write_byte(MPU6050_PWR_MGMT_1, 0x00);
    if (err != ESP_OK) return err;

    /* Configurar escala (±4g) */
    err = mpu6050_write_byte(MPU6050_ACCEL_CONFIG, 0x08);
    if (err != ESP_OK) return err;

    start_time_offset = esp_timer_get_time();
    return ESP_OK;
}

void accel_reset_counters(void) {
    if (xSemaphoreTake(accel_mutex, portMAX_DELAY) == pdTRUE) {
        global_packet_counter = 0;
        sample_count = 0;
        start_time_offset = esp_timer_get_time();    
        xSemaphoreGive(accel_mutex);
    }
}

void accel_sample_and_store(void) {
    
    int64_t current_time;
    int64_t relative_time;
    uint8_t raw_data[6]; /* Buffer para X, Y, Z */

    /* Lectura I2C en ráfaga */
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, MPU6050_ACCEL_XOUT_H, true);
    
    /* Leer 6 bytes seguidos */
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read(cmd, raw_data, 5, I2C_MASTER_ACK);      /* Leer primeros 5 con ACK */
    i2c_master_read_byte(cmd, &raw_data[5], I2C_MASTER_NACK); /* Leer último con NACK */
    i2c_master_stop(cmd);
    
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);

    if (xSemaphoreTake(accel_mutex, portMAX_DELAY) == pdTRUE) {
        if (sample_count == 0) {
            current_time = esp_timer_get_time();
            relative_time = current_time - start_time_offset;
            acc_buffer.timestamp_start = (uint32_t)(relative_time / 1000); 
            acc_buffer.sequence_id = global_packet_counter;
        }

        if (ret == ESP_OK) {
            acc_buffer.samples[sample_count].x = (int16_t)((raw_data[0] << 8) | raw_data[1]);
            acc_buffer.samples[sample_count].y = (int16_t)((raw_data[2] << 8) | raw_data[3]);
            acc_buffer.samples[sample_count].z = (int16_t)((raw_data[4] << 8) | raw_data[5]);
        } else {
            acc_buffer.samples[sample_count].x = 0;
            acc_buffer.samples[sample_count].y = 0;
            acc_buffer.samples[sample_count].z = 0;
        }

        last_sample = acc_buffer.samples[sample_count];
        sample_count++;
        xSemaphoreGive(accel_mutex);
    }
}

bool accel_is_batch_ready(void) {
    bool ready = false;
    if (xSemaphoreTake(accel_mutex, portMAX_DELAY) == pdTRUE) {
        ready = (sample_count >= SAMPLES_PER_PACKET);
        xSemaphoreGive(accel_mutex);
    }
    return ready;
}

accel_packet_t* accel_get_batch(void) {
    if (xSemaphoreTake(accel_mutex, portMAX_DELAY) == pdTRUE) {
        sample_count = 0;
        global_packet_counter++;
        xSemaphoreGive(accel_mutex);
    }
    return &acc_buffer;
}

accel_raw_t accel_get_last_sample(void) {
    return last_sample;
}