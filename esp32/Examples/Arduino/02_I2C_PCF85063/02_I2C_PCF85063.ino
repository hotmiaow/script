#include "rtc_bsp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static void gpio_init(void)
{
  gpio_config_t gpio_conf = {};
  gpio_conf.intr_type = GPIO_INTR_DISABLE;
  gpio_conf.mode = GPIO_MODE_OUTPUT;
  gpio_conf.pin_bit_mask = 0x1ULL << GPIO_NUM_8;
  gpio_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_conf.pull_up_en = GPIO_PULLUP_ENABLE;

  ESP_ERROR_CHECK_WITHOUT_ABORT(gpio_config(&gpio_conf));

  gpio_set_level(GPIO_NUM_8,true);
}

void setup()
{
  gpio_init();
  Serial.begin(115200);
  rtc_init(); //rtc init
  i2c_rtc_setTime(2025,9,9,14,51,30);//Set the RTC time to June 26, 2025, 14:51:30.
  xTaskCreatePinnedToCore(i2c_rtc_loop_task, "i2c_rtc_loop_task", 3 * 1024, NULL , 2, NULL,0); //rtc read data
}

void loop() 
{
  
}
