#ifndef USER_CONFIG_H
#define USER_CONFIG_H

#define BOARD_VERSION_2   // Comment out for V1

// SPI host configuration
#define LCD_HOST SPI3_HOST

// I2C SCL/SDA Pin Assignment for Touch Screen (Bus 1)
#define Touch_SCL_NUM (GPIO_NUM_18)
#define Touch_SDA_NUM (GPIO_NUM_17)

// I2C SCL/SDA Pin Assignment for Onboard Peripherals (Bus 0 - RTC, IMU, etc.)
#define ESP_SCL_NUM (GPIO_NUM_48)
#define ESP_SDA_NUM (GPIO_NUM_47)

// LCD Driver Pin Configuration (QSPI Interface)
#define EXAMPLE_PIN_NUM_LCD_CS     (GPIO_NUM_9) 
#define EXAMPLE_PIN_NUM_LCD_PCLK   (GPIO_NUM_10)
#define EXAMPLE_PIN_NUM_LCD_DATA0  (GPIO_NUM_11)
#define EXAMPLE_PIN_NUM_LCD_DATA1  (GPIO_NUM_12)
#define EXAMPLE_PIN_NUM_LCD_DATA2  (GPIO_NUM_13)
#define EXAMPLE_PIN_NUM_LCD_DATA3  (GPIO_NUM_14)
#define EXAMPLE_PIN_NUM_LCD_RST    (GPIO_NUM_21)
// LCD Backlight PWM pin (V2 board = GPIO 8, V1 board = GPIO 42)
#define EXAMPLE_PIN_NUM_BK_LIGHT   (GPIO_NUM_8) 

// Onboard I2C Device Addresses
#define I2C_TOUCH_ADDR             0x3b
#define EXAMPLE_RTC_ADDR           0x51
#define EXAMPLE_IMU_ADDR           0x6b

// Touch Config (Pins not connected directly or handled over I2C)
#define EXAMPLE_PIN_NUM_TOUCH_RST  (-1)
#define EXAMPLE_PIN_NUM_TOUCH_INT  (-1)

// LVGL Porting Timers & Tasks
#define LVGL_TICK_PERIOD_MS        5
#define LVGL_TASK_MAX_DELAY_MS     500
#define LVGL_TASK_MIN_DELAY_MS     5
#define LVGL_TASK_STACK_SIZE       (8 * 1024)
#define LVGL_TASK_PRIORITY         2

// Backlight Test configuration (0 = static max brightness, 1 = testing brightness levels)
#define Backlight_Testing          0

// Screen Rotation Modes
#define USER_DISP_ROT_90           1
#define USER_DISP_ROT_NONO         0

// Set to 1 (USER_DISP_ROT_90) to enable landscape mode (640x172 resolution)
#define Rotated                    USER_DISP_ROT_90

// Native LCD resolution (tall bar display)
#define EXAMPLE_LCD_H_RES          172   
#define EXAMPLE_LCD_V_RES          640

#define LCD_NOROT_HRES             172
#define LCD_NOROT_VRES             640

// Buffers sized for RGB565 color format (2 bytes per pixel)
// 16 lines instead of 64 lines frees 16.5KB of internal DMA SRAM for HTTPS TLS handshakes
#define LVGL_DMA_BUFF_LEN          (LCD_NOROT_HRES * 16 * 2)
#define LVGL_SPIRAM_BUFF_LEN       (EXAMPLE_LCD_H_RES * EXAMPLE_LCD_V_RES * 2)

#endif
