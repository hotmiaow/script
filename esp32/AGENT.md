# AGENT.md - Developer Guide & Project Context

## Project Summary & Tech Stack
This project is an **ESP32-S3 Google News Ticker** built for the **Waveshare ESP32-S3-Touch-LCD-3.49** development board (352x352 tall screen, rotated to $640 \times 172$ landscape layout).

### Tech Stack
* **Microcontroller**: ESP32-S3 (with 16MB Flash, OPI PSRAM enabled).
* **Framework**: Arduino Core for ESP32 (v3.0+ based on ESP-IDF v5).
* **Graphics Library**: LVGL v9 (Light and Versatile Graphics Library).
* **Display Driver**: AXS15231B QSPI LCD driver.
* **Touch Controller**: CST328 I2C touch screen.
* **Audio Codec**: ES8311 Codec + TCA9554 IO Expander (onboard mic input).
* **APIs Used**:
  * `http://ip-api.com/json/` (Geolocation by external IP).
  * `http://api.open-meteo.com/` (Plain HTTP Weather API).
  * `https://news.google.com/rss/` (HTTPS Google News Search RSS feeds).

---

## Coding Standards & Architectural Patterns
* **Dual Core Multitasking**:
  * **Core 1 (LVGL Runner)**: Drives UI ticks and rendering via `lvgl_port.c` FreeRTOS task. Thread-safety is enforced using `lvgl_port_lock()` and `lvgl_port_unlock()`.
  * **Core 0 (Network & Sensors)**: Background `fetch_news_task` fetches location, weather, and local news RSS feeds, parses the streaming XML directly to reduce memory, and updates LVGL text variables.
* **Non-allocating XML Stream Parser**:
  * `parse_rss_stream` reads the incoming secure HTTPS connection byte-by-byte, resolving elements inside CDATA without buffer reallocation or string fragmentation.
* **Power Management / Screen Auto-Dim**:
  * Every 5 minutes, the ES8311 codec records audio for 2 seconds.
  * If the amplitude falls below the noise floor threshold (`350.0`) for 10 minutes, the backlight is dimmed to `10/255` via the onboard PWM driver.
  * Tapping the screen at any point wakes the backlight immediately.

---

## File Structure Overview
* **[Google_News_Ticker/](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker)**: Main sketch directory.
  * [Google_News_Ticker.ino](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/Google_News_Ticker.ino): Global state, tasks, XML streaming parser, audio check timer, and CJK layout builders.
  * [user_config.h](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/user_config.h): Core resolution settings, display rotation, pin assignments, and timings.
  * [lvgl_port.h](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/lvgl_port.h) / [lvgl_port.c](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/lvgl_port.c): Handles display setup, touch handler callback, double buffering, and lock sync.
  * [i2c_bsp.h](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/i2c_bsp.h) / [i2c_bsp.c](file:///Users/keithlee/Library/CloudStorage/OneDrive-Personal/script/esp32/Google_News_Ticker/i2c_bsp.c): Drives I2C master configurations on Port 0 and Port 1.
  * **`src/`**: Driver folders.
    * `axs15231b/` (LCD driver), `lcd_bl_bsp/` (PWM backlight), `touch/` (touch IC).
    * `tca9554/` (IO expander), `codec_board/` & `esp_codec_dev/` (ES8311 codec).

---

## Current Task Status
- [x] Full-Width CJK Pipe Separators added to PingFang custom font
- [x] Degree Symbol `°` rendering fix
- [x] Temperature JSON search index fix (current block isolation)
- [x] Widescreen 3-Band Layout refactor (Time/Weather top, two horizontal cards bottom)
- [x] Geolocation-based City search integration
- [x] Regional language toggle (zh-HK in Asia, en-CA outside Asia)
- [x] Backlight dimming task via TCA9554 / ES8311 microphone sound checks (5m check / 10m timeout)
- [x] Fixed XML tag parsing index bug (checking for `>` before appending to buffer)
- [x] Unified 4px gap sizes for the three panels to fit perfectly on the 640x172 screen
- [x] Configured TCA9554 Expander Pin 6 (Power Latch) to keep battery power on when releasing power button or unplugging USB
- [x] Implemented news source blacklist filtering (ignoring "香港文匯報" / "文匯報" / "香港文汇报")
- [x] Developed Web Configuration Portal for dynamically configuring SSID, Password, Blacklist, Sleep hours, and Day/Night brightness levels
- [x] Implemented Smart Sleep Hours (backlight completely off during sleep window, wakes temporarily for 30s on screen tap)
- [x] Added dynamic day/night auto-brightness scaling based on NTP local clock hours
- [x] Integrated swiping page navigation (left/right gestures) to switch between News Ticker and 3-day Weather Forecast view
- [x] Implemented Sound-Activated Wake Up (clapping or shouting wakes the screen instantly)
- [x] Integrated Web-based OTA (Over-The-Air) firmware updates via the /update page
- [x] Added dynamic Wi-Fi network scanner in Web Portal to auto-populate SSID
- [x] Integrated Wi-Fi Signal (RSSI) and battery level percentage indicators in the status bar (using ADC GPIO 4)
- [x] Added configurable news page flip durations in the Web Portal
- [x] Implemented automatic headline de-duplication inside the RSS parser to filter out identical stories from different sources
- [x] Added 5 Custom RSS Feed URL configurations in Web Portal (distributed within the 50 items limit) with 10 suggested English news feeds and a Clear All button
- [x] Configured CPU boot frequency to 80 MHz (lowest stable frequency that preserves correct SPI LCD & I2C Touch peripheral bus operations)
- [x] Bypassed Wi-Fi connection and HTTP news fetches during Smart Sleep Hours to maximize battery saving (checking only once per hour instead of every 5 minutes)
- [x] Disabled touch screen polling and hardware driver initialization in lvgl_port.c to conserve CPU wake cycles and I2C bus traffic
- [x] Implemented 5 selectable LCD display color themes (Cyberpunk Green, Sunset Coral, Retro Amber, Forest Calcite, Royal Monarch) configured from the Web Portal and applied instantly without device reboot
- [x] Removed on-screen weather symbols (keeping only text) and disabled local screen Wi-Fi RSSI rotation (Wi-Fi strength is visible on the web dashboard)
- [x] Integrated a stacked, half-size 4-dot square rating system (■ and □) modeled after the iPhone secondary SIM signal indicator for battery level (B:) and refresh timer (R:) on the far right of the top bar with 5px row padding and larger CJK font rendering
- [x] Fixed theme persistence by loading NVS settings early during setup() before create_layout() runs
- [x] Reduced SSL/TLS socket buffer sizes to 4KB/1KB to resolve memory allocation failures during secure news handshakes
- [x] Implemented 16-sample ADC moving average filter for smooth battery voltage readings
- [x] Implemented low-battery auto-shutdown (< 3.2V) to protect lithium battery from over-discharge
- [x] Added HTTP/HTTPS auto-detection for RSS feeds (using plain WiFiClient for http:// to save 32KB TLS buffer per fetch)
- [x] Added 500ms delay between consecutive RSS source fetches to prevent SRAM fragmentation
- [x] Implemented exponential backoff retry on news fetch failures (30s → 60s → 120s)
- [x] Added Task Watchdog Timer (60s timeout) on NewsTask to auto-recover from stalled network sockets
- [x] Added stack high-water-mark memory monitoring log every 60s
- [x] Implemented relative headline age formatter ("2h ago", "Just now", "Yesterday") parsed from RSS pubDate
- [x] Implemented breaking news alert animation (flashing red top card on keywords like BREAKING/突發/緊急)
- [x] Implemented LCD burn-in pixel-shifting protection (shifting container translate by 1-2px every 30 mins)
- [x] Configured mDNS responder (`http://newsticker.local`) for easy Web Portal access without knowing device IP
- [x] Integrated DNS Captive Portal in AP mode (auto-redirecting connected phones to setup page)
- [x] Added Web Portal Configuration Export (`/api/export`) & Import (`/api/import`) JSON backup/restore
- [x] Added visual color indicators/icons to LCD theme dropdown options in the Web Portal


