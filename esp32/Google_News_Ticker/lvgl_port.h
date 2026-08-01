#ifndef LVGL_PORT_H
#define LVGL_PORT_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Initialize the LVGL display and touch drivers
void lvgl_port_init(void);

// Thread safety locks for accessing LVGL APIs
bool lvgl_port_lock(int timeout_ms);
void lvgl_port_unlock(void);

#ifdef __cplusplus
}
#endif

#endif
