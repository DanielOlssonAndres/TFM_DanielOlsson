#include "mpu6886.h"
#include "driver/i2c.h"
#include "sys_config.h"

static esp_err_t mpu6886_write_byte(uint8_t reg, uint8_t data) {
    i2c_cmd_handle_t cmd;
    esp_err_t ret;

    cmd = i2c_cmd_link_create();

    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6886_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, reg, true);
    i2c_master_write_byte(cmd, data, true);
    i2c_master_stop(cmd);
    ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);
    return ret;
}

esp_err_t mpu6886_init(void) {
    /* Secuencia de encendido y configuración del MPU6886 */
    if (mpu6886_write_byte(MPU6886_PWR_MGMT_1, 0x00) != ESP_OK) return ESP_FAIL;
    
    vTaskDelay(pdMS_TO_TICKS(10)); /* Dar tiempo a que estabilice tras salir del sleep */
    
    mpu6886_write_byte(MPU6886_PWR_MGMT_1, 0x01);   /* Seleccionar reloj óptimo (Auto) */
    mpu6886_write_byte(MPU6886_ACCEL_CONFIG, 0x10); /* Rango del acelerómetro: +-8G */
    mpu6886_write_byte(MPU6886_CONFIG, 0x01);       /* Filtro paso bajo */
    mpu6886_write_byte(MPU6886_SMPLRT_DIV, 0x05);   /* Divisor de frecuencia de muestreo */
    
    return ESP_OK;
}

/* Lectura de los ejes del acelerómetro */
esp_err_t mpu6886_read_accel(accel_raw_t *sample) {
    uint8_t raw[6];
    i2c_cmd_handle_t cmd;
    esp_err_t ret;
    
    cmd = i2c_cmd_link_create();
    
    /* Configurar el puntero de registro de lectura en ACCEL_XOUT_H (0x3B) */
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6886_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, MPU6886_ACCEL_XOUT_H, true);
    
    /* Reiniciar transmisión en modo lectura */
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6886_ADDR << 1) | I2C_MASTER_READ, true);
    
    /* Leer 5 bytes enviando ACK a cada uno para continuar la transmisión */
    i2c_master_read(cmd, raw, 5, I2C_MASTER_ACK);
    /* Leer el 6º byte enviando NACK para finalizar la transmisión en el bus I2C */
    i2c_master_read_byte(cmd, &raw[5], I2C_MASTER_NACK);
    
    i2c_master_stop(cmd);
    
    /* Ejecutar el comando */
    ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);

    /* Procesar los datos si la lectura fue exitosa */
    if (ret == ESP_OK && sample != NULL) {
        sample->x = (int16_t)((raw[0] << 8) | raw[1]);
        sample->y = (int16_t)((raw[2] << 8) | raw[3]);
        sample->z = (int16_t)((raw[4] << 8) | raw[5]);
    }
    return ret;
}

void mpu6886_clear_interrupt(void) {
    // No disponible en StickC-Plus2
}