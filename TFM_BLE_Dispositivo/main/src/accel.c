#include "accel.h"
#include "common.h"
#include "driver/i2c.h"
#include "esp_timer.h" 

#define I2C_MASTER_SCL_IO           33
#define I2C_MASTER_SDA_IO           32
#define I2C_MASTER_NUM              0
#define I2C_MASTER_FREQ_HZ          400000
#define I2C_MASTER_TX_BUF_DISABLE   0
#define I2C_MASTER_RX_BUF_DISABLE   0

#define MPU6050_ADDR                0x68
#define MPU6050_PWR_MGMT_1          0x6B
#define MPU6050_ACCEL_CONFIG        0x1C
#define MPU6050_ACCEL_XOUT_H        0x3B
#define MPU6050_SMPLRT_DIV          0x19
#define MPU6050_CONFIG              0x1A
#define MPU6050_INT_PIN_CFG         0x37
#define MPU6050_INT_ENABLE          0x38

/* --- ARQUITECTURA DE DOBLE BÚFER --- */
static accel_packet_t buffers[2];
static uint8_t write_idx = 0;             /* Búfer activo para escritura (0 o 1) */
static volatile bool batch_ready = false; /* Notificación al consumidor (BLE) */

static int sample_count = 0;
static uint32_t global_packet_counter = 0;
static int64_t start_time_offset = 0;
static accel_raw_t last_valid_sample = {0, 0, 0}; /* Seguridad de integridad de datos */

/* Inicializar el driver I2C */
static esp_err_t i2c_master_init(void) {
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = I2C_MASTER_SDA_IO,
        .scl_io_num = I2C_MASTER_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_MASTER_FREQ_HZ,
    };
    esp_err_t err = i2c_param_config(I2C_MASTER_NUM, &conf);
    if (err != ESP_OK) return err;
    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, I2C_MASTER_RX_BUF_DISABLE, I2C_MASTER_TX_BUF_DISABLE, 0);
}

/* Escribir un byte */
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

/* Leer un byte */
static esp_err_t mpu6050_read_byte(uint8_t reg_addr, uint8_t *data) {
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, reg_addr, true);
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read_byte(cmd, data, I2C_MASTER_NACK);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);
    return ret;
}

esp_err_t accel_init(void) {
    esp_err_t err = i2c_master_init();
    if (err != ESP_OK) return err;

    /* Configuración del sensor */
    err = mpu6050_write_byte(MPU6050_PWR_MGMT_1, 0x00);
    if (err != ESP_OK) return err;
    /* Configurar escala a ±8g (Valor de registro: 0x10) */
    err = mpu6050_write_byte(MPU6050_ACCEL_CONFIG, 0x10);
    err = mpu6050_write_byte(MPU6050_CONFIG, 0x03);
    if (err != ESP_OK) return err;
    err = mpu6050_write_byte(MPU6050_SMPLRT_DIV, 19);
    if (err != ESP_OK) return err;
    err = mpu6050_write_byte(MPU6050_INT_PIN_CFG, 0x30);
    if (err != ESP_OK) return err;
    err = mpu6050_write_byte(MPU6050_INT_ENABLE, 0x01);
    if (err != ESP_OK) return err;

    /* Limpieza del Latch inicial */
    uint8_t dummy;
    mpu6050_read_byte(0x3A, &dummy);

    start_time_offset = esp_timer_get_time();
    return ESP_OK;
}

void accel_reset_counters(void) {
    global_packet_counter = 0;
    sample_count = 0;
    write_idx = 0;
    batch_ready = false;
    start_time_offset = esp_timer_get_time();    
}

void accel_sample_and_store(void) {
    uint8_t raw_data[6];

    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, MPU6050_ACCEL_XOUT_H, true);
    
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read(cmd, raw_data, 5, I2C_MASTER_ACK);
    i2c_master_read_byte(cmd, &raw_data[5], I2C_MASTER_NACK);
    i2c_master_stop(cmd);
    
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);

    /* Puntero al búfer activo actual */
    accel_packet_t *current_buffer = &buffers[write_idx];

    /* Asignar timestamp de inicio en la primera muestra del paquete */
    if (sample_count == 0) {
        int64_t relative_time = esp_timer_get_time() - start_time_offset;
        current_buffer->timestamp_start = (uint32_t)(relative_time / 1000); 
        current_buffer->sequence_id = global_packet_counter;
    }

    if (ret == ESP_OK) {
        current_buffer->samples[sample_count].x = (int16_t)((raw_data[0] << 8) | raw_data[1]);
        current_buffer->samples[sample_count].y = (int16_t)((raw_data[2] << 8) | raw_data[3]);
        current_buffer->samples[sample_count].z = (int16_t)((raw_data[4] << 8) | raw_data[5]);
        last_valid_sample = current_buffer->samples[sample_count];
    } else {
        /* En caso de error, mantener el último dato para no destruir las estadísticas en la RasPi */
        current_buffer->samples[sample_count] = last_valid_sample;
    }

    sample_count++;

    /* Si se llena el paquete, hacer el swap de búfer */
    if (sample_count >= SAMPLES_PER_PACKET) {
        sample_count = 0;
        global_packet_counter++;
        batch_ready = true;
        write_idx = !write_idx; /* Cambiar a 0 si era 1, y viceversa */
    }
}

bool accel_is_batch_ready(void) {
    return batch_ready;
}

accel_packet_t* accel_get_batch(void) {
    batch_ready = false; 
    /* El BLE lee del búfer OPUESTO al que está escribiendo el sensor actualmente */
    return &buffers[!write_idx];
}

accel_raw_t accel_get_last_sample(void) {
    return last_valid_sample;
}

void accel_clear_latch(void) {
    uint8_t dummy;
    mpu6050_read_byte(0x3A, &dummy); /* 0x3A = INT_STATUS. Leerlo baja el pin a 0V */
}