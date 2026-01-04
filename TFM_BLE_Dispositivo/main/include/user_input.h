#ifndef USER_INPUT_H
#define USER_INPUT_H

#include <stdbool.h>

#define BUTTON_GPIO 0 

void button_init(void);
bool is_factory_reset_pressed(void);

#endif