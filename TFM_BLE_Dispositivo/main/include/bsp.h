#ifndef BSP_H
#define BSP_H

#include <stdbool.h>

void bsp_init(void);
bool bsp_read_mode_switch(void);
void bsp_set_led_green(bool state);
void bsp_system_halt_error(const char* module);

#endif // BSP_H