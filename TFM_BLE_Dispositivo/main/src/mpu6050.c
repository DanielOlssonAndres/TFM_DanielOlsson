#include "mpu6050.h"
#include "driver/i2c.h"
#include "sys_config.h"

#define MPU6050_ADDR                0x68
#define MPU6050_PWR_MGMT_1          0x6B
#define MPU6050_ACCEL_CONFIG        0x1C
#define MPU6050_ACCEL_XOUT_H        0x3B
#define MPU6050_SMPLRT_DIV          0x19
#define MPU6050_CONFIG              0x1A
#define MPU6050_INT_PIN_CFG         0x37
#define MPU6050_INT_ENABLE          0x38

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

esp_err_t mpu6050_init(void) {
    /* El driver I2C ya lo inicializó el BSP */
    if (mpu6050_write_byte(MPU6050_PWR_MGMT_1, 0x00) != ESP_OK) return ESP_FAIL;
    mpu6050_write_byte(MPU6050_ACCEL_CONFIG, 0x10);
    mpu6050_write_byte(MPU6050_CONFIG, 0x03);
    mpu6050_write_byte(MPU6050_SMPLRT_DIV, 19);
    mpu6050_write_byte(MPU6050_INT_PIN_CFG, 0x30);
    mpu6050_write_byte(MPU6050_INT_ENABLE, 0x01);

    uint8_t dummy;
    mpu6050_read_byte(0x3A, &dummy); // Clear latch
    return ESP_OK;
}

esp_err_t mpu6050_read_accel(accel_raw_t *sample) {
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

    if (ret == ESP_OK && sample != NULL) {
        sample->x = (int16_t)((raw_data[0] << 8) | raw_data[1]);
        sample->y = (int16_t)((raw_data[2] << 8) | raw_data[3]);
        sample->z = (int16_t)((raw_data[4] << 8) | raw_data[5]);
    }
    return ret;
}

void mpu6050_clear_interrupt(void) {
    uint8_t dummy;
    mpu6050_read_byte(0x3A, &dummy); 
}