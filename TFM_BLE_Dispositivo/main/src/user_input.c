#include "user_input.h"
#include "driver/gpio.h"
#include "esp_timer.h" /* Necesario para contar el tiempo (microsegundos) */

/* Variable estática para asegurar que el reset solo ocurre UNA vez */
static bool simulacion_ejecutada = false;

void button_init(void) {
    gpio_reset_pin(BUTTON_GPIO);
    gpio_set_direction(BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(BUTTON_GPIO, GPIO_PULLUP_ONLY);
}

bool is_factory_reset_pressed(void) {


    int64_t tiempo_actual = esp_timer_get_time();

    /* Si han pasado más de 20 segundos Y aún no hemos reseteado */
    if (tiempo_actual > 20000000 && !simulacion_ejecutada) {
        
        if(tiempo_actual > 25000000){
            simulacion_ejecutada = true; /* Marcar como hecho para no resetear infinitamente */
        }
        return true; 
    }

    return false;
}