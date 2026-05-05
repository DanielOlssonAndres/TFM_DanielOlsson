#include "mpu6050.h"
#include "driver/i2c.h"
#include "sys_config.h"

static esp_err_t mpu6050_write_byte(uint8_t reg_addr, uint8_t data) {
    i2c_cmd_handle_t cmd;
    esp_err_t ret;
    
    /* Crear un enlace de comandos I2C (cola de operaciones) */
    cmd = i2c_cmd_link_create();
    
    i2c_master_start(cmd);
    
    /* Enviar dirección I2C del esclavo (0x68 desplazado 1 bit a la izq) + bit de ESCRITURA (0) */
    /* El 'true' indica que esperamos un ACK del esclavo. */
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    
    /* Enviar la dirección del registro interno al que queremos acceder */
    i2c_master_write_byte(cmd, reg_addr, true);
    
    /* Enviar el byte de datos que se escribirá en ese registro */
    i2c_master_write_byte(cmd, data, true);
    
    /* Condición de STOP */
    i2c_master_stop(cmd);
    
    /* Ejecutar todos los comandos encolados de forma bloqueante (timeout de 1000 ms) */
    ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    
    /* 8. Liberar la memoria del enlace de comandos */
    i2c_cmd_link_delete(cmd);
    
    return ret;
}

static esp_err_t mpu6050_read_byte(uint8_t reg_addr, uint8_t *data) {
    esp_err_t ret;
    i2c_cmd_handle_t cmd; 
    
    cmd = i2c_cmd_link_create();

    /* Condición de START para apuntar al registro que queremos leer */
    i2c_master_start(cmd);
    
    /* Enviar dirección del esclavo + bit de ESCRITURA */
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    
    /* Escribir la dirección del registro objetivo */
    i2c_master_write_byte(cmd, reg_addr, true);
    
    i2c_master_start(cmd);
    
    /* Enviar dirección del esclavo + bit de LECTURA (1) */
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_READ, true);
    
    /* Leer 1 byte de datos. Como es el único/último byte, respondemos con NACK. */
    i2c_master_read_byte(cmd, data, I2C_MASTER_NACK);
    
    /* Condición de STOP y ejecución */
    i2c_master_stop(cmd);
    ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);
    
    return ret;
}

esp_err_t mpu6050_init(void) {
    uint8_t dummy;

    /* Despertar el sensor: Escribir 0x00 en PWR_MGMT_1 saca al dispositivo del modo Sleep */
    if (mpu6050_write_byte(MPU6050_PWR_MGMT_1, 0x00) != ESP_OK) return ESP_FAIL;
    
    /* Rango del acelerómetro a ±8g. */
    mpu6050_write_byte(MPU6050_ACCEL_CONFIG, 0x10);
    
    /* Configuración del DLPF (Digital Low Pass Filter) */
    /* Establece el ancho de banda del filtro del acelerómetro a ~44Hz. */
    mpu6050_write_byte(MPU6050_CONFIG, 0x03);
    
    /* Divisor de tasa de muestreo: 19 */
    /* Tasa de muestreo = 1kHz / (1 + 19) = 50Hz */
    mpu6050_write_byte(MPU6050_SMPLRT_DIV, 19);
    
    /* Configuración del pin de Interrupción (INT) */
    /* Bit 5 = 1 (Nivel activo LOW). Bit 4 = 1 (Open-Drain). */
    mpu6050_write_byte(MPU6050_INT_PIN_CFG, 0x30);
    
    /* Habilita la interrupción de 'Data Ready' */
    mpu6050_write_byte(MPU6050_INT_ENABLE, 0x01);

    /* Limpiar interrupción residual */
    mpu6050_read_byte(0x3A, &dummy); 

    return ESP_OK;
}

esp_err_t mpu6050_read_accel(accel_raw_t *sample) {
    uint8_t raw_data[6]; // Buffer para los 6 bytes (2 bytes por cada eje: X, Y, Z)
    
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    
    /* Apuntar al primer registro de datos del acelerómetro (Eje X, byte alto) */
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, MPU6050_ACCEL_XOUT_H, true);
    
    /* Cambiar a modo lectura para hacer una lectura en ráfaga */
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MPU6050_ADDR << 1) | I2C_MASTER_READ, true);
    
    /* Leer los primeros 5 bytes enviando un ACK para decirle al esclavo que siga enviando */
    i2c_master_read(cmd, raw_data, 5, I2C_MASTER_ACK);
    
    /* Leer el 6º y último byte enviando un NACK para indicar el fin de la lectura */
    i2c_master_read_byte(cmd, &raw_data[5], I2C_MASTER_NACK);
    
    /* Finalizar transacción */
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd, 1000 / portTICK_PERIOD_MS);
    i2c_cmd_link_delete(cmd);

    /* Si la lectura por I2C fue bien y el puntero es válido, recomponer los datos */
    if (ret == ESP_OK && sample != NULL) {
        /* Los datos del MPU6050 son de 16 bits en complemento a 2, divididos en dos registros de 8 bits */
        /* Se desplaza el High Byte (<< 8) y se hace un OR con el Low Byte */
        sample->x = (int16_t)((raw_data[0] << 8) | raw_data[1]);
        sample->y = (int16_t)((raw_data[2] << 8) | raw_data[3]);
        sample->z = (int16_t)((raw_data[4] << 8) | raw_data[5]);
    }
    return ret;
}

void mpu6050_clear_interrupt(void) {
    uint8_t dummy;
    /* Registro 0x3A es INT_STATUS. Leer este registro limpia el pin de interrupción */
    mpu6050_read_byte(0x3A, &dummy); 
}