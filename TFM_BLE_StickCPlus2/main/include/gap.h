#ifndef GAP_SVC_H
#define GAP_SVC_H

#include <stdbool.h>

int gap_init(bool single_link_mode); 
void gap_host_config_init(void);
void gap_start_host_task(void);

#endif // GAP_SVC_H