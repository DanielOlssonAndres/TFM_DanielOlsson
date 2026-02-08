#include "accel.h"
#include "common.h"
#include "driver/i2c.h"
#include "esp_timer.h" // Para el reloj de alta precisión

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

void accel_init(void) {

    ESP_ERROR_CHECK(i2c_master_init());
    ESP_ERROR_CHECK(mpu6050_write_byte(MPU6050_PWR_MGMT_1, 0x00));

    /* Configurar escala (±4g) */
    /* 0x00=2g, 0x08=4g, 0x10=8g, 0x18=16g */
    ESP_ERROR_CHECK(mpu6050_write_byte(MPU6050_ACCEL_CONFIG, 0x08));
    start_time_offset = esp_timer_get_time();
}

void accel_reset_counters(void) {

    global_packet_counter = 0;
    sample_count = 0;
    
    /* Se marca el "Ahora" como el nuevo punto cero */
    start_time_offset = esp_timer_get_time();    
}

void accel_sample_and_store(void) {
    
    int64_t current_time;
    int64_t relative_time;
    uint8_t raw_data[6]; /* Buffer para X, Y, Z */

    /* Gestión de cabecera del paquete si es la primera muestra */
    if (sample_count == 0) {
        current_time = esp_timer_get_time();
        relative_time = current_time - start_time_offset;
        acc_buffer.timestamp_start = (uint32_t)(relative_time / 1000); 
        acc_buffer.sequence_id = global_packet_counter;
    }

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

    if (ret == ESP_OK) {
        /* Unir bytes High y Low en entero de 16 bits con signo */
        acc_buffer.samples[sample_count].x = (int16_t)((raw_data[0] << 8) | raw_data[1]);
        acc_buffer.samples[sample_count].y = (int16_t)((raw_data[2] << 8) | raw_data[3]);
        acc_buffer.samples[sample_count].z = (int16_t)((raw_data[4] << 8) | raw_data[5]);
    } else {
        /* En caso de error, ponemos 0 para evitar datos basura */
        acc_buffer.samples[sample_count].x = 0;
        acc_buffer.samples[sample_count].y = 0;
        acc_buffer.samples[sample_count].z = 0;
    }

    /* Guardamos copia de la última muestra para lecturas individuales */
    last_sample = acc_buffer.samples[sample_count];

    sample_count++;
}

bool accel_is_batch_ready(void) {
    return sample_count >= SAMPLES_PER_PACKET;
}

accel_packet_t* accel_get_batch(void) {
    sample_count = 0;
    global_packet_counter++;
    return &acc_buffer;
}

accel_raw_t accel_get_last_sample(void) {
    return last_sample;
}