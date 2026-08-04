#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFiAP.h>
#include <Update.h>
#include <ESPmDNS.h>
#include <DNSServer.h>
#include "time.h"
#include "esp_task_wdt.h"

#include "user_config.h"
#include "lvgl_port.h"
#include "i2c_bsp.h"
#include "src/lcd_bl_bsp/lcd_bl_pwm_bsp.h"
#include "lvgl.h"

#include "esp_heap_caps.h"

// Audio & Codec Includes
#include "src/tca9554/esp_io_expander_tca9554.h"
#include "src/codec_board/codec_board.h"
#include "src/codec_board/codec_init.h"

#include "esp_sleep.h"
#include "driver/gpio.h"
#include "esp_pm.h"
#include <Wire.h>

// ==========================================
// USER CONFIGURATION: Configure Wi-Fi Here
// ==========================================
#include "secrets.h"

// ==========================================

// Global State
#define MAX_HEADLINE_LEN 250
#define MAX_SOURCE_LEN   48
#define MAX_PUBDATE_LEN  24

struct NewsItem {
  char headline[MAX_HEADLINE_LEN];
  char source[MAX_SOURCE_LEN];
  char pubDate[MAX_PUBDATE_LEN];
};

#define MAX_NEWS_ITEMS 200
#define MAX_CACHED_NEWS 50
NewsItem* news_list = nullptr;   // was: NewsItem news_list[MAX_NEWS_ITEMS];

int news_count = 0;
bool is_updating = false;

WebServer server(80);
bool ap_mode_started = false;

// Dynamic Settings & Blacklist
String wifi_ssid = "";
String wifi_pass = "";
String blacklist_str = "香港文匯報,文匯報,香港文汇报";
bool sleep_enabled = false;
int sleep_start = 23;
int sleep_end = 7;
bool auto_bright = false;
int day_bright = 255;
int night_bright = 50;
int scroll_interval_seconds = 10;
String custom_rss_urls[5] = {"", "", "", "", ""};
String custom_city = "";

#define MAX_BLACKLIST_COUNT 16
char blacklist_items[MAX_BLACKLIST_COUNT][MAX_SOURCE_LEN];
int blacklist_count = 0;

// Forecast variables
double forecast_max[3] = {0.0, 0.0, 0.0};
double forecast_min[3] = {0.0, 0.0, 0.0};
int forecast_code[3] = {0, 0, 0};
bool forecast_fetched = false;
int active_page = 0; // 0 = News, 1 = Forecast
unsigned long last_sleep_bypass_time = 0;

void switch_page(int page);

void update_blacklist_array() {
  blacklist_count = 0;
  String temp = blacklist_str;
  temp.trim();
  if (temp.length() == 0) return;

  int last_idx = 0;
  int comma_idx = temp.indexOf(',');
  while (blacklist_count < MAX_BLACKLIST_COUNT) {
    String val;
    if (comma_idx == -1) {
      val = temp.substring(last_idx);
      val.trim();
      if (val.length() > 0) {
        strncpy(blacklist_items[blacklist_count], val.c_str(), MAX_SOURCE_LEN - 1);
        blacklist_items[blacklist_count][MAX_SOURCE_LEN - 1] = '\0';
        blacklist_count++;
      }
      break;
    } else {
      val = temp.substring(last_idx, comma_idx);
      val.trim();
      if (val.length() > 0) {
        strncpy(blacklist_items[blacklist_count], val.c_str(), MAX_SOURCE_LEN - 1);
        blacklist_items[blacklist_count][MAX_SOURCE_LEN - 1] = '\0';
        blacklist_count++;
      }
      last_idx = comma_idx + 1;
      comma_idx = temp.indexOf(',', last_idx);
    }
  }
}

bool allocate_news_buffer(void) {
  // Try PSRAM first (external 8MB SPIRAM)
  if (psramFound()) {
    size_t psram_total = ESP.getPsramSize();
    size_t psram_free  = ESP.getFreePsram();
    Serial.printf("[PSRAM] Detected %d KB total, %d KB free\n", 
                  psram_total / 1024, psram_free / 1024);

    news_list = (NewsItem*)ps_malloc(MAX_NEWS_ITEMS * sizeof(NewsItem));
    if (news_list) {
      Serial.printf("[PSRAM] news_list allocated at %p (%d bytes)\n",
                    news_list, MAX_NEWS_ITEMS * (int)sizeof(NewsItem));
    }
  }

  // Fallback to internal RAM if PSRAM missing or failed
  if (!news_list) {
    Serial.println("[PSRAM] WARNING: Falling back to internal RAM for news_list");
    news_list = (NewsItem*)malloc(MAX_NEWS_ITEMS * sizeof(NewsItem));
  }

  if (!news_list) {
    Serial.println("[FATAL] Could not allocate news_list. Halting.");
    return false;
  }

  // ps_malloc does NOT zero memory (unlike static BSS arrays).
  // Zero it now so empty strings behave safely.
  memset(news_list, 0, MAX_NEWS_ITEMS * sizeof(NewsItem));
  return true;
}

// Battery ADC smoothing: 16-sample ring buffer for stable readings
#define BAT_SAMPLE_COUNT 16
static float bat_samples[BAT_SAMPLE_COUNT];
static int bat_sample_idx = 0;
static bool bat_samples_filled = false;

float get_battery_voltage() {
  int raw = analogRead(4);
  float voltage = (raw * 3.3 / 4095.0) * 3.0;
  bat_samples[bat_sample_idx] = voltage;
  bat_sample_idx = (bat_sample_idx + 1) % BAT_SAMPLE_COUNT;
  if (bat_sample_idx == 0) bat_samples_filled = true;
  int count = bat_samples_filled ? BAT_SAMPLE_COUNT : bat_sample_idx;
  if (count == 0) return voltage;
  float sum = 0;
  for (int i = 0; i < count; i++) sum += bat_samples[i];
  return sum / count;
}

int get_battery_percentage() {
  float v = get_battery_voltage();
  if (v >= 4.20) return 100;
  if (v >= 4.10) return 90 + (v - 4.10) * 100;
  if (v >= 4.00) return 80 + (v - 4.00) * 100;
  if (v >= 3.90) return 60 + (v - 3.90) * 200;
  if (v >= 3.80) return 40 + (v - 3.80) * 200;
  if (v >= 3.70) return 20 + (v - 3.70) * 200;
  if (v >= 3.60) return 10 + (v - 3.60) * 100;
  if (v >= 3.50) return 5  + (v - 3.50) * 50;
  if (v >= 3.30) return (v - 3.30) * 25;
  return 0;
}

// Burn-in protection: pixel shift offset applied every 30 minutes
static int burnin_offset_x = 0;
static int burnin_offset_y = 0;
static unsigned long last_burnin_shift_time = 0;

// DNS server for captive portal in AP mode
DNSServer dnsServer;
static bool dns_server_active = false;

// Retry backoff state
static int fetch_fail_count = 0;

bool is_source_blacklisted(const char* source) {
  if (source == NULL) return false;
  for (int i = 0; i < blacklist_count; i++) {
    if (strstr(source, blacklist_items[i]) != NULL) {
      return true;
    }
  }
  return false;
}

bool is_duplicate_headline(const char* headline, int current_count) {
  if (headline == NULL || strlen(headline) == 0) return false;
  for (int i = 0; i < current_count; i++) {
    if (strcmp(news_list[i].headline, headline) == 0) {
      return true;
    }
  }
  return false;
}
volatile bool fetch_requested = true;
int seconds_to_refresh = 3600; // 60 minutes refresh interval
int current_page = 0;

static void brightness_anim_cb(void * var, int32_t v);
void set_brightness_smooth(int from, int to, int duration_ms);
static uint8_t brightness_anim_target; // dummy var address for lv_anim identity


Preferences newsPrefs;

// Weather Data
String local_city = "Locating...";
double local_temp = 0.0;
String local_weather_desc = "Fetching";
bool weather_fetched = false;
bool is_asia = false;

// News search city - resolved from detected country to a representative
// metro area (e.g. any HK district -> "Hong Kong", any Canadian city -> "Toronto")

// News search region - resolved from detected country. Each region carries
// its own metro-area city name AND matching Google News language/edition
// params, so the feed URL and UI language always stay consistent for
// whatever country the device is currently in.
String news_query_city = "Hong Kong";
String news_hl   = "zh-HK";     // Google News interface language
String news_gl   = "HK";        // Google News edition/country
String news_ceid = "HK:zh-Hant"; // Google News content edition ID

unsigned long wifi_disconnected_since = 0;
bool wifi_was_connected = true;

// Audio Dev Codec handles & Dimming State
esp_codec_dev_handle_t playback = NULL;
esp_codec_dev_handle_t record = NULL;
esp_io_expander_handle_t io_expander = NULL;
volatile int silence_minutes = 0;
volatile bool is_dimmed = false;
volatile int last_applied_brightness = -1;
unsigned long last_sound_check_time = 0;

// LVGL UI Handles
LV_FONT_DECLARE(lv_font_source_han_sans_sc_16_cjk);
LV_FONT_DECLARE(lv_font_indicator_14);
static lv_style_t main_style;
static lv_style_t title_style;
static lv_style_t sub_style;
static lv_style_t indicator_style;

lv_obj_t *main_screen = NULL;
lv_obj_t *top_panel = NULL;
lv_obj_t *date_label = NULL;
lv_obj_t *time_label = NULL;
lv_obj_t *weather_loc_label = NULL;
lv_obj_t *weather_desc_label = NULL;
lv_obj_t *battery_label = NULL;
lv_obj_t *refresh_label = NULL;

lv_obj_t *carousel_container = NULL;
lv_obj_t *top_card = NULL;
lv_obj_t *bottom_card = NULL;
lv_obj_t *top_headline_lbl = NULL;
lv_obj_t *bottom_headline_lbl = NULL;

lv_obj_t *top_meta_lbl = NULL;
lv_obj_t *bottom_meta_lbl = NULL;

void save_settings(void);

// Low-battery auto-shutdown: prevents lithium over-discharge
void check_low_battery_shutdown() {
  float v = get_battery_voltage();
  if (v > 0.5 && v < 3.2) { // v > 0.5 excludes USB-only (no battery)
    Serial.println("[Power] CRITICAL: Battery below 3.2V! Saving state and shutting down.");
    save_settings();
    if (lvgl_port_lock(200)) {
      lv_label_set_text(top_headline_lbl, is_asia ? "電量過低，即將關機..." : "Battery Critical - Shutting Down...");
      lv_label_set_text(bottom_headline_lbl, "");
      lvgl_port_unlock();
    }
    delay(2000);
    setUpduty(0);
    esp_deep_sleep_start(); // No wakeup source = stay off until power button
  }
}

// Functions declarations
void init_ui_styles(void);
void create_layout(void);
void update_ui_news(void);
void update_ui_news_labels(void);
void update_status_time(void);
void fetch_news_task(void *pvParameters);
void trigger_news_update(void);
String truncate_utf8(String str, int max_chars);
String get_weather_desc(int code);
void reset_dim_timer(void);
bool check_for_sound(void);
void load_cached_news(void);
void save_news_cache(void);
void resolve_region(String country);
static void flash_top_panel(void);
String build_news_meta(const NewsItem &item);
void handle_root(void);
void handle_save(void);
void handle_ota_get(void);
void handle_ota_post(void);
void handle_ota_upload(void);
void show_ap_mode_ui(void);
void handle_api_status(void);
void handle_api_set_theme(void);
void handle_api_export(void);
void handle_api_import(void);
void sync_system_time_from_rtc(void);
void sync_rtc_from_system_time(void);
void rtc_set_time(int year, int month, int day, int hour, int minute, int second);
bool rtc_get_time(int &year, int &month, int &day, int &hour, int &minute, int &second);
bool resolve_custom_city_coords(String city, float &lat, float &lon, String &resolved_name, String &country);
void save_settings(void);
void check_low_battery_shutdown(void);

// Add these definitions before setup()
// Power management pins for ESP32-S3-Touch-LCD-3.49
#define PIN_POWER_ON    21  // Common power enable pin
#define PIN_BAT_ADC     14  // Battery voltage monitoring (if available)

// Add this function before setup()
void init_power_management() {
    Serial.println("Configuring power management...");
    
    // Some Waveshare boards have these pins for power control
    // Try setting GPIO 46 high if it exists (common power hold pin)
    pinMode(46, OUTPUT);
    digitalWrite(46, HIGH);
    
    // Also try GPIO 21 (sometimes used for power enable)
    pinMode(21, OUTPUT);
    digitalWrite(21, HIGH);
    
    // Prevent deep sleep
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
    
    Serial.println("Power management configured.");
}

// RTC and Time Sync Helpers
void rtc_set_time(int year, int month, int day, int hour, int minute, int second) {
  uint8_t buf[7];
  buf[0] = ((second / 10) << 4) | (second % 10);
  buf[1] = ((minute / 10) << 4) | (minute % 10);
  buf[2] = ((hour / 10) << 4) | (hour % 10);
  buf[3] = ((day / 10) << 4) | (day % 10);
  buf[4] = 0; // Weekday
  buf[5] = ((month / 10) << 4) | (month % 10);
  buf[6] = (((year % 100) / 10) << 4) | ((year % 100) % 10);

  i2c_write_buff(rtc_dev_handle, 0x04, buf, 7);
  Serial.printf("[RTC] Set RTC: %04d-%02d-%02d %02d:%02d:%02d\n", year, month, day, hour, minute, second);
}

bool rtc_get_time(int &year, int &month, int &day, int &hour, int &minute, int &second) {
  uint8_t buf[7];
  if (i2c_read_buff(rtc_dev_handle, 0x04, buf, 7) == 0) {
    second = ((buf[0] & 0x7F) >> 4) * 10 + (buf[0] & 0x0F);
    minute = ((buf[1] & 0x7F) >> 4) * 10 + (buf[1] & 0x0F);
    hour = ((buf[2] & 0x3F) >> 4) * 10 + (buf[2] & 0x0F);
    day = ((buf[3] & 0x3F) >> 4) * 10 + (buf[3] & 0x0F);
    month = ((buf[5] & 0x1F) >> 4) * 10 + (buf[5] & 0x0F);
    year = 2000 + ((buf[6] & 0xFF) >> 4) * 10 + (buf[6] & 0x0F);
    return (year >= 2025 && year <= 2099 && month >= 1 && month <= 12 && day >= 1 && day <= 31 && hour <= 23 && minute <= 59 && second <= 59);
  }
  return false;
}

void sync_system_time_from_rtc() {
  int y, m, d, hh, mm, ss;
  if (rtc_get_time(y, m, d, hh, mm, ss)) {
    struct tm tInfo;
    tInfo.tm_year = y - 1900;
    tInfo.tm_mon = m - 1;
    tInfo.tm_mday = d;
    tInfo.tm_hour = hh;
    tInfo.tm_min = mm;
    tInfo.tm_sec = ss;
    tInfo.tm_isdst = -1;
    
    time_t t = mktime(&tInfo);
    struct timeval tv = { .tv_sec = t, .tv_usec = 0 };
    settimeofday(&tv, NULL);
    Serial.printf("[RTC] Synced system time from RTC: %04d-%02d-%02d %02d:%02d:%02d\n", y, m, d, hh, mm, ss);
  } else {
    Serial.println("[RTC] Failed to read valid time from RTC.");
  }
}

void sync_rtc_from_system_time() {
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    rtc_set_time(timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday, timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    Serial.println("[RTC] Synced RTC from NTP system time.");
  }
}

// Geocoding Custom City Resolution
bool resolve_custom_city_coords(String city, float &lat, float &lon, String &resolved_name, String &country) {
  HTTPClient http;
  WiFiClient client;
  city.replace(" ", "%20");
  String url = "http://geocoding-api.open-meteo.com/v1/search?name=" + city + "&count=1&format=json";
  
  Serial.print("[Geo-API] Resolving city coordinates: ");
  Serial.println(url);
  
  http.begin(client, url);
  http.setTimeout(6000);
  int code = http.GET();
  if (code == HTTP_CODE_OK) {
    String payload = http.getString();
    http.end();
    
    int lat_idx = payload.indexOf("\"latitude\":");
    int lon_idx = payload.indexOf("\"longitude\":");
    int name_idx = payload.indexOf("\"name\":\"");
    int country_idx = payload.indexOf("\"country\":\"");
    
    if (lat_idx != -1 && lon_idx != -1) {
      int lat_end = payload.indexOf(",", lat_idx);
      lat = payload.substring(lat_idx + 11, lat_end).toFloat();
      
      int lon_end = payload.indexOf(",", lon_idx);
      if (lon_end == -1) lon_end = payload.indexOf("}", lon_idx);
      lon = payload.substring(lon_idx + 12, lon_end).toFloat();
      
      if (name_idx != -1) {
        int name_end = payload.indexOf("\"", name_idx + 8);
        resolved_name = payload.substring(name_idx + 8, name_end);
      }
      if (country_idx != -1) {
        int country_end = payload.indexOf("\"", country_idx + 11);
        country = payload.substring(country_idx + 11, country_end);
      }
      return true;
    }
  } else {
    http.end();
  }
  return false;
}


// Add to loop() or create a task for battery monitoring
void check_battery_status() {
    // Read battery voltage (if ADC pin is available)
    analogReadResolution(12);
    int bat_raw = analogRead(PIN_BAT_ADC);
    float bat_voltage = (bat_raw / 4095.0) * 3.3 * 2; // Assuming voltage divider
    
    static unsigned long last_bat_check = 0;
    if (millis() - last_bat_check > 60000) { // Check every minute
        last_bat_check = millis();
        Serial.printf("Battery: %.2fV (Raw: %d)\n", bat_voltage, bat_raw);
        
        // Update UI if battery is low
        if (bat_voltage < 3.3 && lvgl_port_lock(100)) {
            lv_label_set_text(refresh_label, "Low Bat!");
            lvgl_port_unlock();
        }
    }
}

// Trims leading/trailing whitespace in-place; returns pointer to trimmed start.
static char* trim_inplace(char* s) {
  while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n') s++;
  if (*s == '\0') return s;
  char* end = s + strlen(s) - 1;
  while (end > s && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) {
    *end = '\0';
    end--;
  }
  return s;
}

// Decodes common HTML entities in-place inside a null-terminated buffer.
// Handles named (&quot; &amp; &lt; &gt; &apos; &nbsp;) and numeric
// (&#39; &#x27; &#x2019; etc.) entities. Unknown entities are left as-is
// to avoid corrupting existing UTF-8 CJK text.
static void decode_html_entities_inplace(char* str) {
  char* r = str;   // read head
  char* w = str;   // write head

  while (*r) {
    if (*r == '&') {
      // Look ahead for ';' within a sane window (max 10 chars)
      char* semi = r + 1;
      int scan = 0;
      while (*semi && *semi != ';' && scan < 10) {
        semi++;
        scan++;
      }

      if (*semi == ';' && scan > 0) {
        char decoded = '\0';
        int len = semi - r - 1; // length between & and ;

        // ----- Named entities -----
        if (len == 4 && strncmp(r + 1, "quot", 4) == 0)       decoded = '"';
        else if (len == 4 && strncmp(r + 1, "apos", 4) == 0)  decoded = '\'';
        else if (len == 3 && strncmp(r + 1, "amp", 3) == 0)   decoded = '&';
        else if (len == 2 && strncmp(r + 1, "lt", 2) == 0)    decoded = '<';
        else if (len == 2 && strncmp(r + 1, "gt", 2) == 0)    decoded = '>';
        else if (len == 4 && strncmp(r + 1, "nbsp", 4) == 0)  decoded = ' ';

        // ----- Numeric entities (&#123; or &#x7B;) -----
        else if (r[1] == '#') {
          unsigned int code = 0;
          if (len > 2 && (r[2] == 'x' || r[2] == 'X')) {
            // Hex: &#xNNNN;
            for (int i = 3; i <= len; i++) {
              char c = r[i];
              if (c >= '0' && c <= '9')       code = code * 16 + (c - '0');
              else if (c >= 'a' && c <= 'f')  code = code * 16 + (c - 'a' + 10);
              else if (c >= 'A' && c <= 'F')  code = code * 16 + (c - 'A' + 10);
              else break;
            }
          } else {
            // Decimal: &#NNNN;
            for (int i = 2; i <= len; i++) {
              char c = r[i];
              if (c >= '0' && c <= '9') code = code * 10 + (c - '0');
              else break;
            }
          }

          // Whitelist: only map safe punctuation / ASCII.
          // CJK codepoints are intentionally skipped (left raw) so we
          // never break multi-byte UTF-8 sequences.
          if      (code == 34)   decoded = '"';     // &#34;
          else if (code == 39)   decoded = '\'';    // &#39;
          else if (code == 38)   decoded = '&';     // &#38;
          else if (code == 60)   decoded = '<';     // &#60;
          else if (code == 62)   decoded = '>';     // &#62;
          else if (code == 160)  decoded = ' ';     // non-breaking space
          else if (code == 8217) decoded = '\'';    // ’ right single quote
          else if (code == 8220) decoded = '"';     // “ left double quote
          else if (code == 8221) decoded = '"';     // ” right double quote
          else if (code == 8230) {                  // … horizontal ellipsis
            *w++ = '.'; *w++ = '.'; *w++ = '.';
            r = semi + 1;
            continue;
          }
          else if (code >= 32 && code <= 126) decoded = (char)code;
        }

        if (decoded) {
          *w++ = decoded;
          r = semi + 1;   // skip past the ';'
          continue;
        }
      }
    }
    *w++ = *r++;
  }
  *w = '\0';
}


// Finds the LAST occurrence of needle in haystack (like strstr but reversed).
static char* strrstr_custom(const char* haystack, const char* needle) {
  if (!*needle) return NULL;
  char* result = NULL;
  char* p = (char*)haystack;
  while ((p = strstr(p, needle)) != NULL) {
    result = p;
    p++;
  }
  return result;
}

// Animation Callbacks
static void set_opacity_anim_cb(void * var, int32_t v) {
  lv_obj_set_style_opa((lv_obj_t *)var, v, 0);
}

// LVGL animation exec callback - drives the PWM duty cycle smoothly
static void brightness_anim_cb(void * var, int32_t v) {
  (void)var;
  setUpduty((uint8_t)v);
}

// Ramps backlight duty from `from` to `to` over duration_ms using an LVGL
// animation (non-blocking - runs on LVGL's own timer, doesn't stall the
// calling task). Must be called while holding lvgl_port_lock() if calling
// from outside LVGL's own event context.
void set_brightness_smooth(int from, int to, int duration_ms) {
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, &brightness_anim_target);
  lv_anim_set_values(&a, from, to);
  lv_anim_set_duration(&a, duration_ms);
  lv_anim_set_exec_cb(&a, brightness_anim_cb);
  lv_anim_start(&a);
}

static void fade_out_completed_cb(lv_anim_t * anim) {
  // Increment page index
  int total_pages = (news_count + 1) / 2;
  if (total_pages > 0) {
    current_page = (current_page + 1) % total_pages;
  } else {
    current_page = 0;
  }
  
  // Update labels text content
  update_ui_news_labels();

  // Fade back in
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, carousel_container);
  lv_anim_set_values(&a, LV_OPA_TRANSP, LV_OPA_COVER);
  lv_anim_set_duration(&a, 400);
  lv_anim_set_exec_cb(&a, set_opacity_anim_cb);
  lv_anim_start(&a);
}

// Left Panel Click Event Handler (Manual Refresh)
static void refresh_btn_event_handler(lv_event_t * e) {
  lv_event_code_t code = lv_event_get_code(e);
  if(code == LV_EVENT_CLICKED) {
    trigger_news_update();
    reset_dim_timer(); // Tapping top panel also resets dim timer
    flash_top_panel();  // Immediate visual confirmation of the tap
  }
}

bool is_sleep_time_active() {
  if (!sleep_enabled) return false;
  struct tm timeinfo;
  int current_hour = -1;
  if (getLocalTime(&timeinfo)) {
    current_hour = timeinfo.tm_hour;
  } else {
    return false;
  }
  
  if (sleep_start > sleep_end) {
    return (current_hour >= sleep_start || current_hour < sleep_end);
  } else {
    return (current_hour >= sleep_start && current_hour < sleep_end);
  }
}

void reset_dim_timer(void) {
  silence_minutes = 0;
  last_sleep_bypass_time = millis();
  
  struct tm timeinfo;
  int current_hour = 12;
  if (getLocalTime(&timeinfo)) {
    current_hour = timeinfo.tm_hour;
  }
  
  int target_bright = 255;
  if (auto_bright) {
    if (current_hour >= 7 && current_hour < 19) {
      target_bright = day_bright;
    } else {
      target_bright = night_bright;
    }
  } else {
    target_bright = day_bright;
  }

  if (is_dimmed || is_sleep_time_active()) {
    is_dimmed = false;
    last_applied_brightness = target_bright;
    set_brightness_smooth(10, target_bright, 250);
    Serial.printf("[Power] Screen woke up: ramping to %d.\n", target_bright);
  }
}

static void screen_click_event_handler(lv_event_t * e) {
  lv_event_code_t code = lv_event_get_code(e);
  if(code == LV_EVENT_PRESSED || code == LV_EVENT_CLICKED) {
    reset_dim_timer();
  }
  else if (code == LV_EVENT_GESTURE) {
    lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_active());
    if (dir == LV_DIR_LEFT) {
      Serial.println("[UI] Gesture Left detected: Swapping to Weather page");
      switch_page(1);
    } else if (dir == LV_DIR_RIGHT) {
      Serial.println("[UI] Gesture Right detected: Swapping to News page");
      switch_page(0);
    }
  }
}

void tca9554_init(void)
{
  i2c_master_bus_handle_t tca9554_i2c_bus_ = NULL;
  if (i2c_master_get_bus_handle(0,&tca9554_i2c_bus_) != ESP_OK) {
      Serial.println("TCA9554 bus not ready");
      return;
  }
  esp_io_expander_new_i2c_tca9554(tca9554_i2c_bus_, ESP_IO_EXPANDER_I2C_TCA9554_ADDRESS_000, &io_expander);
  
  // Power latch pin 6: Holds the power latch to keep the board on when running on battery (18650)
  esp_io_expander_set_dir(io_expander, IO_EXPANDER_PIN_NUM_6, IO_EXPANDER_OUTPUT);
  esp_io_expander_set_level(io_expander, IO_EXPANDER_PIN_NUM_6, 1);

  // Audio power pin 7: Enables codec/audio power
  esp_io_expander_set_dir(io_expander, IO_EXPANDER_PIN_NUM_7, IO_EXPANDER_OUTPUT);
  esp_io_expander_set_level(io_expander, IO_EXPANDER_PIN_NUM_7, 1);
}

void audio_init(void)
{
  set_codec_board_type("S3_LCD_3_49");
  codec_init_cfg_t codec_cfg = 
  {
    .in_mode = CODEC_I2S_MODE_TDM,
    .out_mode = CODEC_I2S_MODE_TDM,
    .in_use_tdm = false,
    .reuse_dev = false,
  };
  ESP_ERROR_CHECK(init_codec(&codec_cfg));
  playback = get_playback_handle();
  record = get_record_handle();
}

void setup()
{
  setCpuFrequencyMhz(80);
  // Initialize Serial Monitor
  Serial.begin(115200);
  delay(100);
  Serial.println("Initializing ESP32-S3 Google News Ticker...");
  
  init_power_management();

  if (!allocate_news_buffer()) return;   // Fatal if no RAM at all

  // Load any cached news from a previous session BEFORE anything else,
  // so we have something to show the instant the UI is created —
  // no waiting on Wi-Fi/RSS fetch for the first paint.
  i2c_master_Init();

  tca9554_init();

  // Clear PCF85063 control register stop bit to ensure clock ticks
  {
    uint8_t ctrl = 0x00;
    i2c_write_buff(rtc_dev_handle, 0x00, &ctrl, 1);
  }
  sync_system_time_from_rtc();

  load_settings();
  load_cached_news();

  // Initialize Onboard Dual I2C buses (Touch & Sensors)

  // Initialize TCA9554 and Audio Codec (Power pin 7)
  audio_init();

  // Initialize LVGL Port (AXS15231B LCD & CST328 Touch Panel)
  lvgl_port_init();
  

  // Lock the panel to landscape (640x172). The AXS15231B is natively
  // 172x640 portrait, so rotate to get the wide horizontal strip this
  // UI is built for. Fixed at boot, not runtime-changing.
  // If the UI shows rotated 90 degrees from what you expect on real
  // hardware, change this to LV_DISPLAY_ROTATION_90.
  lv_display_t *disp = lv_display_get_default();
  if (disp) {
    lv_display_set_rotation(disp, LV_DISPLAY_ROTATION_270);
  }

  // Initialize Backlight PWM and set to max brightness (255)
  lcd_bl_pwm_bsp_init(LCD_PWM_MODE_255);
  setUpduty(LCD_PWM_MODE_255);

  // Initialize UI Styles and Base Layout
  lvgl_port_lock(-1);
  init_ui_styles();
  create_layout();

  // Immediately populate the carousel with cached headlines (if any)
  // instead of leaving it on the default "Fetching..." placeholder.
  update_ui_news();

  // Add click listener on screen active to reset dim timer on touch
  lv_obj_add_event_cb(lv_screen_active(), screen_click_event_handler, LV_EVENT_ALL, NULL);
  lvgl_port_unlock();

  // Start background Wi-Fi and News Fetching Task on Core 0
  xTaskCreatePinnedToCore(fetch_news_task, "NewsTask", 6144, NULL, 1, NULL, 0);
}

bool check_for_sound(void) {
  Serial.println("[Audio] Starting sound check...");
  
  esp_codec_dev_sample_info_t fs = {};
  fs.sample_rate = 16000;
  fs.channel = 1;
  fs.bits_per_sample = 16;
  
  esp_err_t err = esp_codec_dev_open(record, &fs);
  if (err != ESP_OK) {
    Serial.printf("[Audio] Failed to open record device, err: %d\n", err);
    return false;
  }

  esp_codec_dev_set_in_gain(record, 45.0);

  int16_t read_buf[256];
  unsigned long start_time = millis();
  float max_amplitude = 0.0;

  while (millis() - start_time < 2000) {
    int read_len = esp_codec_dev_read(record, read_buf, sizeof(read_buf));
    if (read_len > 0) {
      int samples = read_len / sizeof(int16_t);
      long sum = 0;
      for (int i = 0; i < samples; i++) {
        sum += abs(read_buf[i]);
      }
      float avg = (float)sum / samples;
      if (avg > max_amplitude) {
        max_amplitude = avg;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }

  esp_codec_dev_close(record);
  Serial.printf("[Audio] Sound check complete. Max amplitude: %.2f\n", max_amplitude);

  // If a very loud sound is detected (e.g. clap, shout > 1200.0) and the screen is dimmed/sleeping, wake it up!
  if (max_amplitude > 1200.0 && (is_dimmed || is_sleep_time_active())) {
    Serial.println("[Audio] Loud sound detected! Waking screen up.");
    reset_dim_timer();
  }

  return (max_amplitude > 350.0);
}

void loop()
{
  // The main loop is kept clean since LVGL runs in its own FreeRTOS task inside lvgl_port.c
  delay(1000);
}

// ----------------------------------------------------
// UI Styles & Layout Configurations (LVGL9)
// ----------------------------------------------------
int current_theme = 0;

void apply_theme_styles() {
  lv_color_t bg_screen_color, bg_screen_grad;
  lv_color_t bg_panel_color, border_panel_color;
  lv_color_t bg_card_color, bg_card_grad, border_card_color;
  lv_color_t title_text_color, main_text_color, sub_text_color;
  
  switch(current_theme) {
    case 1: // Sunset Coral (Warm Peach & Slate)
      bg_screen_color = lv_color_make(26, 26, 46);
      bg_screen_grad = lv_color_make(36, 36, 62);
      bg_panel_color = lv_color_make(47, 47, 84);
      border_panel_color = lv_color_make(61, 61, 109);
      bg_card_color = lv_color_make(36, 36, 62);
      bg_card_grad = lv_color_make(26, 26, 46);
      border_card_color = lv_color_make(61, 61, 109);
      title_text_color = lv_color_make(255, 126, 103); // Soft Coral
      main_text_color = lv_color_make(226, 226, 240); // Ice White
      sub_text_color = lv_color_make(139, 139, 168);  // Slate Gray
      break;
      
    case 2: // Retro Terminal (Amber Orange)
      bg_screen_color = lv_color_make(18, 18, 18);
      bg_screen_grad = lv_color_make(28, 28, 28);
      bg_panel_color = lv_color_make(32, 32, 32);
      border_panel_color = lv_color_make(60, 60, 60);
      bg_card_color = lv_color_make(26, 26, 26);
      bg_card_grad = lv_color_make(18, 18, 18);
      border_card_color = lv_color_make(70, 70, 70);
      title_text_color = lv_color_make(255, 159, 0); // Neon Amber
      main_text_color = lv_color_make(255, 191, 70); // Light Amber
      sub_text_color = lv_color_make(180, 140, 90);
      break;
      
    case 3: // Forest Calcite (Mint Green)
      bg_screen_color = lv_color_make(12, 26, 26);
      bg_screen_grad = lv_color_make(18, 38, 38);
      bg_panel_color = lv_color_make(24, 50, 50);
      border_panel_color = lv_color_make(38, 80, 80);
      bg_card_color = lv_color_make(18, 38, 38);
      bg_card_grad = lv_color_make(12, 26, 26);
      border_card_color = lv_color_make(38, 80, 80);
      title_text_color = lv_color_make(102, 205, 170); // Mint Green
      main_text_color = lv_color_make(204, 227, 222);  // Pale Sage
      sub_text_color = lv_color_make(140, 180, 175);
      break;
      
    case 4: // Royal Monarch (Orchid Gold)
      bg_screen_color = lv_color_make(16, 5, 30);
      bg_screen_grad = lv_color_make(26, 10, 48);
      bg_panel_color = lv_color_make(38, 15, 68);
      border_panel_color = lv_color_make(70, 28, 120);
      bg_card_color = lv_color_make(26, 10, 48);
      bg_card_grad = lv_color_make(16, 5, 30);
      border_card_color = lv_color_make(88, 36, 160);
      title_text_color = lv_color_make(255, 215, 0); // Rich Gold
      main_text_color = lv_color_make(248, 240, 255); // Pearlescent White
      sub_text_color = lv_color_make(180, 140, 210);  // Lavender
      break;

    case 0:
    default: // Cyberpunk Neon Green (Default)
      bg_screen_color = lv_color_make(15, 17, 22);
      bg_screen_grad = lv_color_make(25, 30, 40);
      bg_panel_color = lv_color_make(24, 28, 37);
      border_panel_color = lv_color_make(45, 52, 68);
      bg_card_color = lv_color_make(33, 38, 48);
      bg_card_grad = lv_color_make(24, 28, 35);
      border_card_color = lv_color_make(55, 63, 80);
      title_text_color = lv_color_make(0, 255, 102); // Cyberpunk Neon Green
      main_text_color = lv_color_white();
      sub_text_color = lv_color_make(180, 180, 180);
      break;
  }

  if (main_screen) {
    lv_obj_set_style_bg_color(main_screen, bg_screen_color, 0);
    lv_obj_set_style_bg_grad_color(main_screen, bg_screen_grad, 0);
  }
  if (top_panel) {
    lv_obj_set_style_bg_color(top_panel, bg_panel_color, 0);
    lv_obj_set_style_border_color(top_panel, border_panel_color, 0);
  }
  if (top_card) {
    lv_obj_set_style_bg_color(top_card, bg_card_color, 0);
    lv_obj_set_style_bg_grad_color(top_card, bg_card_grad, 0);
    lv_obj_set_style_border_color(top_card, border_card_color, 0);
  }
  if (bottom_card) {
    lv_obj_set_style_bg_color(bottom_card, bg_card_color, 0);
    lv_obj_set_style_bg_grad_color(bottom_card, bg_card_grad, 0);
    lv_obj_set_style_border_color(bottom_card, border_card_color, 0);
  }

  // Update styles properties dynamically
  lv_style_set_text_color(&main_style, main_text_color);
  lv_style_set_text_color(&title_style, title_text_color);
  lv_style_set_text_color(&sub_style, sub_text_color);
  lv_style_set_text_color(&indicator_style, sub_text_color);

  // Notify objects to refresh style cache
  if (top_headline_lbl) lv_obj_refresh_style(top_headline_lbl, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (top_meta_lbl) lv_obj_refresh_style(top_meta_lbl, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (bottom_headline_lbl) lv_obj_refresh_style(bottom_headline_lbl, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (bottom_meta_lbl) lv_obj_refresh_style(bottom_meta_lbl, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (date_label) lv_obj_refresh_style(date_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (time_label) lv_obj_refresh_style(time_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (weather_loc_label) lv_obj_refresh_style(weather_loc_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (weather_desc_label) lv_obj_refresh_style(weather_desc_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (battery_label) lv_obj_refresh_style(battery_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
  if (refresh_label) lv_obj_refresh_style(refresh_label, LV_PART_ANY, LV_STYLE_PROP_ANY);
}

void init_ui_styles(void) {
  // Base text style using PingFang size 20 font (linked as lv_font_source_han_sans_sc_16_cjk)
  lv_style_init(&main_style);
  lv_style_set_text_font(&main_style, &lv_font_source_han_sans_sc_16_cjk);
  lv_style_set_text_color(&main_style, lv_color_white());

  // Title style
  lv_style_init(&title_style);
  lv_style_set_text_font(&title_style, &lv_font_source_han_sans_sc_16_cjk);
  lv_style_set_text_color(&title_style, lv_color_make(50, 205, 50)); // Lime Green

  // Subtitle/Muted style
  lv_style_init(&sub_style);
  lv_style_set_text_font(&sub_style, &lv_font_source_han_sans_sc_16_cjk);
  lv_style_set_text_color(&sub_style, lv_color_make(180, 180, 180)); // Muted Gray

  // Indicator style (custom 14px size)
  lv_style_init(&indicator_style);
  lv_style_set_text_font(&indicator_style, &lv_font_indicator_14);
  lv_style_set_text_color(&indicator_style, lv_color_make(150, 150, 150));
}

void create_layout(void) {
  main_screen = lv_screen_active();

  // Set main screen background to deep dark slate gradient
  lv_obj_set_style_bg_color(main_screen, lv_color_make(15, 17, 22), 0);
  lv_obj_set_style_bg_grad_color(main_screen, lv_color_make(25, 30, 40), 0);
  lv_obj_set_style_bg_grad_dir(main_screen, LV_GRAD_DIR_VER, 0);
  lv_obj_set_style_pad_all(main_screen, 0, 0);
  lv_obj_remove_flag(main_screen, LV_OBJ_FLAG_SCROLLABLE);

  // Root screen is a vertical flex column: top_panel (content-sized height)
  // + carousel_container (grows to fill whatever is left). Sizing is done
  // with LV_PCT / flex-grow rather than literal pixels, so it always fits
  // the actual current display resolution.
  lv_obj_set_flex_flow(main_screen, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(main_screen, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
  // Explicit gap between top_panel and carousel_container so they never
  // touch/overlap regardless of how tall the top bar's text ends up.
  lv_obj_set_style_pad_row(main_screen, 3, 0);

  // Top Control Panel Container (full width banner, clickable to refresh)
  top_panel = lv_obj_create(main_screen);
  lv_obj_set_width(top_panel, LV_PCT(100));
  lv_obj_set_height(top_panel, LV_SIZE_CONTENT);
  lv_obj_set_style_min_height(top_panel, 40, 0);
  lv_obj_set_style_bg_color(top_panel, lv_color_make(24, 28, 37), 0);
  lv_obj_set_style_border_color(top_panel, lv_color_make(45, 52, 68), 0);
  lv_obj_set_style_border_width(top_panel, 1, 0);
  lv_obj_set_style_border_side(top_panel, LV_BORDER_SIDE_BOTTOM, 0); // Bottom border only
  lv_obj_set_style_radius(top_panel, 0, 0); // Flat edges
  lv_obj_set_style_pad_hor(top_panel, 12, 0);
  lv_obj_set_style_pad_ver(top_panel, 6, 0);
  lv_obj_remove_flag(top_panel, LV_OBJ_FLAG_SCROLLABLE);

  // Make the top panel container clickable to trigger manual updates
  lv_obj_add_flag(top_panel, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(top_panel, refresh_btn_event_handler, LV_EVENT_ALL, NULL);

  // Use horizontal flex row layout to distribute time, date, location, weather, and status
  lv_obj_set_flex_flow(top_panel, LV_FLEX_FLOW_ROW);
  lv_obj_set_flex_align(top_panel, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

  // 1. Time Label
  time_label = lv_label_create(top_panel);
  lv_obj_add_style(time_label, &main_style, 0);
  lv_label_set_text(time_label, "--:--");

  // 2. Date Label
  date_label = lv_label_create(top_panel);
  lv_obj_add_style(date_label, &sub_style, 0);
  lv_label_set_text(date_label, "--月--日 週-");

  // 3. Weather Location Label
  weather_loc_label = lv_label_create(top_panel);
  lv_obj_add_style(weather_loc_label, &title_style, 0); // Lime Green accent
  lv_label_set_text(weather_loc_label, local_city.c_str());

  // 4. Weather Temp & Description Label
  weather_desc_label = lv_label_create(top_panel);
  lv_obj_add_style(weather_desc_label, &main_style, 0);
  lv_label_set_text(weather_desc_label, "Fetching");

  // 5. Stacked Status Panel (Far right)
  lv_obj_t *status_panel = lv_obj_create(top_panel);
  lv_obj_remove_style_all(status_panel);
  lv_obj_set_size(status_panel, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(status_panel, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(status_panel, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
  lv_obj_set_style_pad_all(status_panel, 0, 0);
  lv_obj_set_style_pad_row(status_panel, 3, 0); // 3px gap between battery and refresh

  battery_label = lv_label_create(status_panel);
  lv_obj_add_style(battery_label, &indicator_style, 0);
  lv_label_set_text(battery_label, "B: □□□□");

  refresh_label = lv_label_create(status_panel);
  lv_obj_add_style(refresh_label, &indicator_style, 0);
  lv_label_set_text(refresh_label, "R: □□□□");

  // News Container - fills all remaining vertical space below top_panel
  carousel_container = lv_obj_create(main_screen);
  lv_obj_set_width(carousel_container, LV_PCT(100));
  lv_obj_set_flex_grow(carousel_container, 1);
  lv_obj_set_style_bg_opa(carousel_container, LV_OPA_TRANSP, 0); // Transparent background
  lv_obj_set_style_border_opa(carousel_container, LV_OPA_TRANSP, 0);
  lv_obj_set_style_pad_all(carousel_container, 6, 0);
  lv_obj_set_style_pad_row(carousel_container, 4, 0); // Gap between cards
  lv_obj_remove_flag(carousel_container, LV_OBJ_FLAG_SCROLLABLE);

  // Vertical flex column layout; each card gets an equal grown share
  lv_obj_set_flex_flow(carousel_container, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(carousel_container, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

  // 1. Top Card (For top news)
  top_card = lv_obj_create(carousel_container);
  lv_obj_set_width(top_card, LV_PCT(100));
  lv_obj_set_flex_grow(top_card, 1);
  lv_obj_set_style_bg_color(top_card, lv_color_make(33, 38, 48), 0);
  lv_obj_set_style_bg_grad_color(top_card, lv_color_make(24, 28, 35), 0);
  lv_obj_set_style_bg_grad_dir(top_card, LV_GRAD_DIR_VER, 0);
  lv_obj_set_style_radius(top_card, 8, 0);
  lv_obj_set_style_border_color(top_card, lv_color_make(55, 63, 80), 0);
  lv_obj_set_style_border_width(top_card, 1, 0);
  lv_obj_set_style_pad_all(top_card, 0, 0);
  lv_obj_set_style_pad_hor(top_card, 16, 0);
  lv_obj_remove_flag(top_card, LV_OBJ_FLAG_SCROLLABLE);

// Stack headline + meta subtitle vertically instead of one label
  // filling the whole card.
// Stack headline + meta subtitle vertically instead of one label
  // filling the whole card.
  lv_obj_set_flex_flow(top_card, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(top_card, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

  // Headline gets a FIXED height of exactly 2 text lines, computed from
  // the actual font's line height, rather than flex_grow - guarantees
  // 2-line wrapping every time regardless of card size/meta label presence.
  const lv_font_t *headline_font = &lv_font_source_han_sans_sc_16_cjk;
  int headline_two_line_h = headline_font->line_height * 2 + 2; // +2px safety margin

  top_headline_lbl = lv_label_create(top_card);
  lv_obj_add_style(top_headline_lbl, &main_style, 0);
  lv_obj_set_width(top_headline_lbl, LV_PCT(100));
  lv_obj_set_height(top_headline_lbl, headline_two_line_h);
  lv_label_set_long_mode(top_headline_lbl, LV_LABEL_LONG_DOT); // wraps, ellipsis on 2nd line if still too long

  top_meta_lbl = lv_label_create(top_card);
  lv_obj_add_style(top_meta_lbl, &sub_style, 0);
  lv_obj_set_width(top_meta_lbl, LV_PCT(100));
  lv_obj_set_flex_grow(top_meta_lbl, 1); // meta label absorbs any leftover space instead
  lv_label_set_long_mode(top_meta_lbl, LV_LABEL_LONG_DOT);
  lv_label_set_text(top_meta_lbl, "");


  // 2. Bottom Card (For cycling other news)
  bottom_card = lv_obj_create(carousel_container);
  lv_obj_set_width(bottom_card, LV_PCT(100));
  lv_obj_set_flex_grow(bottom_card, 1);
  lv_obj_set_style_bg_color(bottom_card, lv_color_make(33, 38, 48), 0);
  lv_obj_set_style_bg_grad_color(bottom_card, lv_color_make(24, 28, 35), 0);
  lv_obj_set_style_bg_grad_dir(bottom_card, LV_GRAD_DIR_VER, 0);
  lv_obj_set_style_radius(bottom_card, 8, 0);
  lv_obj_set_style_border_color(bottom_card, lv_color_make(55, 63, 80), 0);
  lv_obj_set_style_border_width(bottom_card, 1, 0);
  lv_obj_set_style_pad_all(bottom_card, 0, 0);
  lv_obj_set_style_pad_hor(bottom_card, 16, 0);
  lv_obj_remove_flag(bottom_card, LV_OBJ_FLAG_SCROLLABLE);

  lv_obj_set_flex_flow(bottom_card, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_flex_align(bottom_card, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

  bottom_headline_lbl = lv_label_create(bottom_card);
  lv_obj_add_style(bottom_headline_lbl, &main_style, 0);
  lv_obj_set_width(bottom_headline_lbl, LV_PCT(100));
  lv_obj_set_height(bottom_headline_lbl, headline_two_line_h);
  lv_label_set_long_mode(bottom_headline_lbl, LV_LABEL_LONG_DOT);

  bottom_meta_lbl = lv_label_create(bottom_card);
  lv_obj_add_style(bottom_meta_lbl, &sub_style, 0);
  lv_obj_set_width(bottom_meta_lbl, LV_PCT(100));
  lv_obj_set_flex_grow(bottom_meta_lbl, 1);
  lv_label_set_long_mode(bottom_meta_lbl, LV_LABEL_LONG_DOT);
  lv_label_set_text(bottom_meta_lbl, "");

  // Apply active theme colors
  apply_theme_styles();
}

// ----------------------------------------------------
// UI News Cards Rendering (Traditional Chinese)
// ----------------------------------------------------
void update_ui_news(void) {
  current_page = 0;
  update_ui_news_labels();
}


void update_ui_news_labels(void) {
  if (active_page == 1) {
    char tom_str[128];
    char day_after_str[128];
    
    if (is_asia) {
      sprintf(tom_str, "明日預報: %.1f°C ~ %.1f°C | %s", forecast_min[1], forecast_max[1], get_weather_desc(forecast_code[1]).c_str());
      sprintf(day_after_str, "後日預報: %.1f°C ~ %.1f°C | %s", forecast_min[2], forecast_max[2], get_weather_desc(forecast_code[2]).c_str());
      
      lv_label_set_text(top_headline_lbl, tom_str);
      lv_label_set_text(top_meta_lbl, "天氣預報");
      
      lv_label_set_text(bottom_headline_lbl, day_after_str);
      lv_label_set_text(bottom_meta_lbl, "天氣預報");
    } else {
      sprintf(tom_str, "Tomorrow: %.1f°C - %.1f°C | %s", forecast_min[1], forecast_max[1], get_weather_desc(forecast_code[1]).c_str());
      sprintf(day_after_str, "Day After: %.1f°C - %.1f°C | %s", forecast_min[2], forecast_max[2], get_weather_desc(forecast_code[2]).c_str());
      
      lv_label_set_text(top_headline_lbl, tom_str);
      lv_label_set_text(top_meta_lbl, "Weather Forecast");
      
      lv_label_set_text(bottom_headline_lbl, day_after_str);
      lv_label_set_text(bottom_meta_lbl, "Weather Forecast");
    }
    return;
  }

  if (news_count == 0) {
    if (is_asia) {
      lv_label_set_text(top_headline_lbl, is_updating ? "正在擷取最新新聞..." : "無可用新聞。");
    } else {
      lv_label_set_text(top_headline_lbl, is_updating ? "Fetching latest news..." : "No news available.");
    }
    lv_label_set_text(top_meta_lbl, "");
    lv_label_set_text(bottom_headline_lbl, "");
    lv_label_set_text(bottom_meta_lbl, "");
    return;
  }

  // Display 2 different news items on the top and bottom cards
  int top_idx = (current_page * 2) % news_count;
  int bottom_idx = (current_page * 2 + 1) % news_count;

  // Set Top Card
  if (top_idx < news_count) {
    lv_label_set_text(top_headline_lbl, news_list[top_idx].headline);
    lv_label_set_text(top_meta_lbl, build_news_meta(news_list[top_idx]).c_str());
  } else {
    lv_label_set_text(top_headline_lbl, "");
    lv_label_set_text(top_meta_lbl, "");
  }

  // Set Bottom Card
  if (bottom_idx < news_count && bottom_idx != top_idx) {
    lv_label_set_text(bottom_headline_lbl, news_list[bottom_idx].headline);
    lv_label_set_text(bottom_meta_lbl, build_news_meta(news_list[bottom_idx]).c_str());
  } else {
    lv_label_set_text(bottom_headline_lbl, "");
    lv_label_set_text(bottom_meta_lbl, "");
  }

  // Check for breaking news keywords to flash red alert animation
  if (top_idx < news_count) {
    const char* h = news_list[top_idx].headline;
    if (strstr(h, "BREAKING") || strstr(h, "突發") || strstr(h, "緊急") || strstr(h, "Alert") || strstr(h, "FLASH")) {
      flash_breaking_news();
    }
  }
}

// ----------------------------------------------------
// Time Update Logic
// ----------------------------------------------------
void update_status_time(void) {
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    char timeStr[6];
    sprintf(timeStr, "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
    
    char dateStr[80];
    if (is_asia) {
      // Traditional Chinese date: e.g. "8月1日 週六"
      const char* wd_names[] = {"週日", "週一", "週二", "週三", "週四", "週五", "週六"};
      sprintf(dateStr, "%d月%d日 %s", timeinfo.tm_mon + 1, timeinfo.tm_mday, wd_names[timeinfo.tm_wday]);
    } else {
      // English date: e.g. "Aug 1 Sat"
      const char* months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
      const char* wd_names[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
      sprintf(dateStr, "%s %d %s", months[timeinfo.tm_mon], timeinfo.tm_mday, wd_names[timeinfo.tm_wday]);
    }



    // Safely update LVGL labels
    if (lvgl_port_lock(100)) {
      lv_label_set_text(time_label, timeStr);
      lv_label_set_text(date_label, dateStr);
      lvgl_port_unlock();
    }
  }
}

// Helper to truncate UTF-8 string to a maximum of characters
String truncate_utf8(String str, int max_chars) {
  int char_count = 0;
  int byte_idx = 0;
  while (byte_idx < str.length() && char_count < max_chars) {
    unsigned char c = str[byte_idx];
    if (c < 0x80) {
      byte_idx += 1;
    } else if ((c & 0xE0) == 0xC0) {
      byte_idx += 2;
    } else if ((c & 0xF0) == 0xE0) {
      byte_idx += 3;
    } else if ((c & 0xF8) == 0xF0) {
      byte_idx += 4;
    } else {
      byte_idx += 1;
    }
    char_count++;
  }
  return str.substring(0, byte_idx);
}

// Builds the "Source · Date" subtitle shown under each headline.
// Note: pubDate is already cleaned to "31 Jul 12:34" format at parse time
// (no year in the RSS feed), so this shows absolute time rather than a
// true relative "2h ago" - computing that reliably would need the article's
// full date compared against NTP time, which the feed doesn't give us
// precisely enough to do safely.
// Parse RSS pubDate (e.g. "Sat, 02 Aug 2026 10:30:00 GMT") into epoch seconds.
// Returns 0 on parse failure.
static time_t parse_rss_date(const char* dateStr) {
  if (!dateStr || dateStr[0] == '\0') return 0;
  struct tm tm_parsed = {};
  // RFC 822 format: "Day, DD Mon YYYY HH:MM:SS TZ"
  const char* months[] = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"};
  // Skip day name (find first space after comma)
  const char* p = strchr(dateStr, ',');
  if (!p) p = dateStr; else p++;
  while (*p == ' ') p++;
  int day_val = 0, year_val = 0, hour_val = 0, min_val = 0, sec_val = 0;
  char mon_str[4] = "";
  if (sscanf(p, "%d %3s %d %d:%d:%d", &day_val, mon_str, &year_val, &hour_val, &min_val, &sec_val) >= 5) {
    tm_parsed.tm_mday = day_val;
    tm_parsed.tm_year = year_val - 1900;
    tm_parsed.tm_hour = hour_val;
    tm_parsed.tm_min = min_val;
    tm_parsed.tm_sec = sec_val;
    for (int i = 0; i < 12; i++) {
      if (strcasecmp(mon_str, months[i]) == 0) { tm_parsed.tm_mon = i; break; }
    }
    return mktime(&tm_parsed);
  }
  return 0;
}

// Format a human-readable relative age string from pubDate
static String format_relative_age(const char* pubDate) {
  time_t pub_epoch = parse_rss_date(pubDate);
  if (pub_epoch == 0) return String(pubDate); // fallback to raw string
  
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return String(pubDate);
  time_t now_epoch = mktime(&timeinfo);
  
  long diff = (long)(now_epoch - pub_epoch);
  if (diff < 0) diff = 0;
  
  if (diff < 60) return "Just now";
  if (diff < 3600) return String(diff / 60) + "m ago";
  if (diff < 86400) return String(diff / 3600) + "h ago";
  if (diff < 172800) return "Yesterday";
  return String(diff / 86400) + "d ago";
}

String build_news_meta(const NewsItem &item) {
  bool has_source = item.source[0] != '\0';
  bool has_date = item.pubDate[0] != '\0';
  if (!has_source && !has_date) return "";
  String age = has_date ? format_relative_age(item.pubDate) : "";
  if (!has_source) return age;
  if (!has_date) return String(item.source);
  return String(item.source) + " · " + age;
}

// Weather code mapping
String get_weather_desc(int code) {
  if (is_asia) {
    switch(code) {
      case 0: return "晴朗";
      case 1: case 2: case 3: return "多雲";
      case 45: case 48: return "有霧";
      case 51: case 53: case 55: return "細雨";
      case 61: case 63: case 65: return "下雨";
      case 71: case 73: case 75: return "降雪";
      case 80: case 81: case 82: return "陣雨";
      case 95: case 96: case 99: return "雷雨";
      default: return "陰天";
    }
  } else {
    switch(code) {
      case 0: return "Clear";
      case 1: case 2: case 3: return "Cloudy";
      case 45: case 48: return "Foggy";
      case 51: case 53: case 55: return "Drizzle";
      case 61: case 63: case 65: return "Rainy";
      case 71: case 73: case 75: return "Snowy";
      case 80: case 81: case 82: return "Showers";
      case 95: case 96: case 99: return "Stormy";
      default: return "Overcast";
    }
  }
}

// ----------------------------------------------------
// News Cache (NVS) - shows last known headlines instantly at boot,
// before Wi-Fi connects or the first RSS fetch completes.
// ----------------------------------------------------
void load_cached_news(void) {
  newsPrefs.begin("newscache", true); // read-only
  int cached_count = newsPrefs.getInt("cnt", 0);
  if (cached_count > MAX_CACHED_NEWS) cached_count = MAX_CACHED_NEWS;
  if (cached_count > MAX_NEWS_ITEMS) cached_count = MAX_NEWS_ITEMS;

  for (int i = 0; i < cached_count; i++) {
    char key[8];
    sprintf(key, "h%d", i);
    String headline = newsPrefs.getString(key, "");
    strncpy(news_list[i].headline, headline.c_str(), MAX_HEADLINE_LEN - 1);
    news_list[i].headline[MAX_HEADLINE_LEN - 1] = '\0';
    news_list[i].source[0] = '\0';
    news_list[i].pubDate[0] = '\0';
  }
  news_count = cached_count;
  newsPrefs.end();

  Serial.printf("[Cache] Loaded %d cached headline(s) from NVS.\n", news_count);
}

void save_news_cache(void) {
  newsPrefs.begin("newscache", false); // read-write
  int to_save = news_count;
  if (to_save > MAX_CACHED_NEWS) to_save = MAX_CACHED_NEWS;

  for (int i = 0; i < to_save; i++) {
    char key[8];
    sprintf(key, "h%d", i);
    newsPrefs.putString(key, news_list[i].headline); // Preferences API requires String here - fine, infrequent
  }
  newsPrefs.putInt("cnt", to_save);
  newsPrefs.end();

  Serial.printf("[Cache] Saved %d headline(s) to NVS.\n", to_save);
}

// ----------------------------------------------------
// Resolve the detected country into a representative metro-area name
// for Google News search. Districts/suburbs/cities within that country
// all roll up to one search term - e.g. Yuen Long, Tin Shui Wai, or
// Central all become "Hong Kong"; Markham, Mississauga, or downtown
// Toronto all become "Toronto". Extend this table for other countries
// the device may travel to.
// ----------------------------------------------------

// ----------------------------------------------------
// Region lookup table: maps a detected country to the metro-area name
// used for the news search query, the matching Google News hl/gl/ceid
// params for that edition, and whether the UI should render in
// Traditional Chinese (is_asia) or English.
// Add a row here for any other country the device may travel to.
// ----------------------------------------------------
struct RegionInfo {
  const char* country_match; // substring matched against ip-api "country"
  const char* city;          // news search city
  const char* hl;            // Google News hl param
  const char* gl;            // Google News gl param
  const char* ceid;          // Google News ceid param
  bool use_cjk_ui;           // true = Traditional Chinese labels, false = English
};

static const RegionInfo region_table[] = {
  { "Hong Kong",       "Hong Kong", "zh-HK", "HK", "HK:zh-Hant", true  },
  { "Taiwan",          "Taipei",    "zh-TW", "TW", "TW:zh-Hant", true  },
  { "Canada",          "Toronto",   "en-CA", "CA", "CA:en",      false },
  { "United States",   "New York",  "en-US", "US", "US:en",      false },
  { "Singapore",       "Singapore", "en-SG", "SG", "SG:en",      false },
  { "United Kingdom",  "London",    "en-GB", "GB", "GB:en",      false },
  { "Australia",       "Sydney",    "en-AU", "AU", "AU:en",      false },
  { "Japan",           "Tokyo",     "en-US", "US", "US:en",      false }, // no JP font loaded, use English feed
};

// Resolve the detected country into a full region config (city + feed
// params + UI language) and apply it to the global news_* / is_asia state.
void resolve_region(String country) {
  for (size_t i = 0; i < sizeof(region_table) / sizeof(region_table[0]); i++) {
    if (country.indexOf(region_table[i].country_match) != -1) {
      news_query_city = region_table[i].city;
      news_hl   = region_table[i].hl;
      news_gl   = region_table[i].gl;
      news_ceid = region_table[i].ceid;
      is_asia   = region_table[i].use_cjk_ui;
      return;
    }
  }

  // No match - fall back to Hong Kong feed params but keep the detected
  // country name as the search city so results are still locally relevant.
  news_query_city = country.length() > 0 ? country : "World";
  news_hl = "en-US";
  news_gl = "US";
  news_ceid = "US:en";
  is_asia = false;
}

// ----------------------------------------------------
// Google News RSS Streaming XML Parser (Traditional Chinese - HK Edition)
// ----------------------------------------------------
// ----------------------------------------------------
// Google News RSS Streaming XML Parser (Traditional Chinese - HK Edition)
// Uses fixed char buffers (no String churn per-character) and explicitly
// handles <![CDATA[ ... ]]> wrapped titles, which Google News uses.
// ----------------------------------------------------
int parse_rss_stream(Client *stream, int limit, int start_count) {
  int count = start_count;

  char tag_buf[24];
  int tag_len = 0;

  bool in_tag = false;
  bool in_item = false;
  bool in_title = false;
  bool in_pubdate = false;
  bool in_cdata = false;

  char cdata_end_win[3] = {0, 0, 0}; // rolling window to detect "]]>"

  char item_title_buf[MAX_HEADLINE_LEN * 2]; // raw title before split, headroom for long titles
  int item_title_len = 0;
  char item_pubdate_buf[MAX_PUBDATE_LEN + 16];
  int item_pubdate_len = 0;

  static const char CDATA_MARK[] = "![CDATA[";
  const int CDATA_MARK_LEN = 8;

  unsigned long timeout = millis();

  while (stream->connected() || stream->available()) {
    if (millis() - timeout > 15000) { // 15 seconds connection timeout
      Serial.println("[RSS Parser] Read timeout.");
      break;
    }

    if (!stream->available()) {
      delay(2);
      continue;
    }

    char c = stream->read();
    timeout = millis(); // Refresh timeout timer

    // --- Inside CDATA content ---
    if (in_cdata) {
      cdata_end_win[0] = cdata_end_win[1];
      cdata_end_win[1] = cdata_end_win[2];
      cdata_end_win[2] = c;

      if (cdata_end_win[0] == ']' && cdata_end_win[1] == ']' && cdata_end_win[2] == '>') {
        // CDATA just closed. The preceding "]]" were appended as content
        // before we knew the sequence was ending - trim them back off.
        if (in_title && item_title_len >= 2) item_title_len -= 2;
        if (in_pubdate && item_pubdate_len >= 2) item_pubdate_len -= 2;
        in_cdata = false;
        continue;
      }

      if (in_title && item_title_len < (int)sizeof(item_title_buf) - 1) {
        item_title_buf[item_title_len++] = c;
      } else if (in_pubdate && item_pubdate_len < (int)sizeof(item_pubdate_buf) - 1) {
        item_pubdate_buf[item_pubdate_len++] = c;
      }
      continue;
    }

    // --- Start of a tag ---
    if (c == '<') {
      in_tag = true;
      tag_len = 0;
      continue;
    }

    // --- Inside a tag name ---
    if (in_tag) {
      if (c == '>') {
        in_tag = false;

        if (strcmp(tag_buf, "item") == 0) {
          in_item = true;
          item_title_len = 0;   item_title_buf[0] = '\0';
          item_pubdate_len = 0; item_pubdate_buf[0] = '\0';
        } else if (strcmp(tag_buf, "/item") == 0) {
          in_item = false;

          if (count < start_count + limit && count < MAX_NEWS_ITEMS && item_title_len > 0) {
            item_title_buf[item_title_len] = '\0';
            item_pubdate_buf[item_pubdate_len] = '\0';
            decode_html_entities_inplace(item_title_buf);
            char* trimmed_title = trim_inplace(item_title_buf);
            char* trimmed_pubdate = trim_inplace(item_pubdate_buf);

            // Split "Headline - Source Name"
            char* split = strrstr_custom(trimmed_title, " - ");
            char source_name[MAX_SOURCE_LEN] = "";
            if (split) {
              strncpy(source_name, split + 3, MAX_SOURCE_LEN - 1);
              source_name[MAX_SOURCE_LEN - 1] = '\0';
            } else {
              strncpy(source_name, "谷歌新聞", MAX_SOURCE_LEN - 1);
              source_name[MAX_SOURCE_LEN - 1] = '\0';
            }

            char* trimmed_source = trim_inplace(source_name);

            if (is_source_blacklisted(trimmed_source)) {
              Serial.printf("[News] Ignored blacklisted source: %s\n", trimmed_source);
            } else {
              char temp_headline[MAX_HEADLINE_LEN] = "";
              if (split) {
                int headline_len = split - trimmed_title;
                if (headline_len >= MAX_HEADLINE_LEN) headline_len = MAX_HEADLINE_LEN - 1;
                strncpy(temp_headline, trimmed_title, headline_len);
                temp_headline[headline_len] = '\0';
              } else {
                strncpy(temp_headline, trimmed_title, MAX_HEADLINE_LEN - 1);
                temp_headline[MAX_HEADLINE_LEN - 1] = '\0';
              }
              
              char* final_headline = trim_inplace(temp_headline);

              if (is_duplicate_headline(final_headline, count)) {
                Serial.printf("[News] Ignored duplicate headline: %s\n", final_headline);
              } else {
                strcpy(news_list[count].headline, final_headline);
                strncpy(news_list[count].source, trimmed_source, MAX_SOURCE_LEN - 1);
                news_list[count].source[MAX_SOURCE_LEN - 1] = '\0';

              // Clean up UTC timestamp: "Fri, 31 Jul 2026 12:34:56 GMT" -> "31 Jul 12:34"
              size_t pd_len = strlen(trimmed_pubdate);
              if (pd_len > 22) {
                char day_month[8]; // "31 Jul"
                char hh_mm[8];     // "12:34"
                strncpy(day_month, trimmed_pubdate + 5, 6); day_month[6] = '\0';
                strncpy(hh_mm, trimmed_pubdate + 17, 5); hh_mm[5] = '\0';
                snprintf(news_list[count].pubDate, MAX_PUBDATE_LEN, "%s %s", day_month, hh_mm);
              } else {
                strncpy(news_list[count].pubDate, trimmed_pubdate, MAX_PUBDATE_LEN - 1);
                news_list[count].pubDate[MAX_PUBDATE_LEN - 1] = '\0';
              }

              Serial.printf("[News] Got: %s [%s]\n", news_list[count].headline, news_list[count].source);
              count++;
            }
          }
        }
        if (count >= start_count + limit || count >= MAX_NEWS_ITEMS) break;
        } else if (strcmp(tag_buf, "title") == 0) {
          in_title = true; in_pubdate = false;
        } else if (strcmp(tag_buf, "/title") == 0) {
          in_title = false;
        } else if (strcmp(tag_buf, "pubDate") == 0) {
          in_pubdate = true; in_title = false;
        } else if (strcmp(tag_buf, "/pubDate") == 0) {
          in_pubdate = false;
        }
        tag_len = 0;
        continue;
      }

      // If not '>', append to tag_buf
      if (tag_len < (int)sizeof(tag_buf) - 1) {
        tag_buf[tag_len++] = c;
        tag_buf[tag_len] = '\0';
      }

      // Recognize "<![CDATA[" as soon as fully matched
      if (tag_len == CDATA_MARK_LEN && strncmp(tag_buf, CDATA_MARK, CDATA_MARK_LEN) == 0) {
        in_cdata = true;
        in_tag = false;
        tag_len = 0;
        cdata_end_win[0] = cdata_end_win[1] = cdata_end_win[2] = 0;
        continue;
      }
      continue;
    }

    // --- Plain content char (not in a tag, not in CDATA) ---
    if (in_item) {
      if (in_title && item_title_len < (int)sizeof(item_title_buf) - 1) {
        item_title_buf[item_title_len++] = c;
      } else if (in_pubdate && item_pubdate_len < (int)sizeof(item_pubdate_buf) - 1) {
        item_pubdate_buf[item_pubdate_len++] = c;
      }
    }
  }
  return count;
}

// ----------------------------------------------------
// Background Wi-Fi & News/Weather Update Task
// ----------------------------------------------------
void trigger_news_update(void) {
  if (!is_updating) {
    fetch_requested = true;
    seconds_to_refresh = 300;
  }
}

// Flashes the top panel with a brief lime-green highlight that fades back
// to its normal color, giving immediate visual confirmation of a tap.
static void panel_flash_anim_cb(void * var, int32_t v) {
  lv_obj_t * obj = (lv_obj_t *)var;
  lv_color_t base   = lv_color_make(24, 28, 37);
  lv_color_t accent = lv_color_make(50, 205, 50);
  // v: 0 = full accent, 255 = full base (i.e. animates accent -> base)
  lv_color_t mixed = lv_color_mix(base, accent, (lv_opa_t)v);
  lv_obj_set_style_bg_color(obj, mixed, 0);
}

static void flash_top_panel(void) {
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, top_panel);
  lv_anim_set_values(&a, 0, 255);
  lv_anim_set_duration(&a, 350);
  lv_anim_set_exec_cb(&a, panel_flash_anim_cb);
  lv_anim_start(&a);
}

// Flash top card red for 2 seconds on breaking news
static void breaking_news_anim_cb(void * var, int32_t v) {
  lv_obj_t * obj = (lv_obj_t *)var;
  lv_color_t base = lv_color_make(33, 38, 48);
  lv_color_t red_accent = lv_color_make(220, 30, 30);
  lv_color_t mixed = lv_color_mix(base, red_accent, (lv_opa_t)v);
  lv_obj_set_style_bg_color(obj, mixed, 0);
}

static void flash_breaking_news(void) {
  if (!top_card) return;
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, top_card);
  lv_anim_set_values(&a, 0, 255);
  lv_anim_set_duration(&a, 2000);
  lv_anim_set_exec_cb(&a, breaking_news_anim_cb);
  lv_anim_start(&a);
}

// Unified RSS stream fetcher with redirect following and TLS memory management
// AFTER
static int fetch_and_parse_rss_url(WiFiClientSecure& secure_client, const String& url, int limit, int start_idx) {
  if (url.length() == 0) return start_idx;
  int parsed_count = start_idx;

  // Short pause just lets lwIP release the previous TCP socket. TLS
  // RX/TX buffers are NOT reallocated here anymore since secure_client
  // is passed in by reference and reused across all source fetches -
  // that reuse is what actually fixes the SSL memory-allocation failures.
  vTaskDelay(pdMS_TO_TICKS(300));

  Serial.println("[RSS] Fetching: " + url);

  HTTPClient http_news;
  http_news.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http_news.begin(secure_client, url);
  http_news.setTimeout(8000);

  int code = http_news.GET();
  if (code == HTTP_CODE_OK) {
    Client *stream = http_news.getStreamPtr();
    parsed_count = parse_rss_stream(stream, limit, start_idx);
  } else {
    char err_buf[128] = "";
    secure_client.lastError(err_buf, sizeof(err_buf));
    Serial.printf("[RSS] Fetch failed for %s, HTTP code: %d, TLS error: %s, Free heap: %d\n", url.c_str(), code, err_buf, ESP.getFreeHeap());
  }

  http_news.end();
  // stop() closes the TCP/TLS session but keeps the already-allocated
  // buffers around on the object for the next fetch to reuse.
  secure_client.stop();
  return parsed_count;
}

void fetch_news_task(void *pvParameters) {
  // Load settings from NVS
  load_settings();

  if (lvgl_port_lock(-1)) {
    lv_label_set_text(refresh_label, "WiFi...");
    lvgl_port_unlock();
  }

  // Enable Wi-Fi Modem Sleep to save power
  WiFi.setSleep(true);
  WiFi.setAutoReconnect(true);

  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(wifi_ssid);
  WiFi.begin(wifi_ssid.c_str(), wifi_pass.c_str());
  int retry_count = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry_count++;
    if (retry_count > 30) { // Timeout after 15 seconds
      Serial.println("\nWi-Fi connection failed.");
      break;
    }
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nStarting Access Point 'ESP32_News_Ticker' for setup...");
    ap_mode_started = true;
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32_News_Ticker");
    
    Serial.print("AP IP Address: ");
    Serial.println(WiFi.softAPIP());
    
    // Captive Portal: redirect all DNS queries to our AP IP
    dnsServer.start(53, "*", WiFi.softAPIP());
    dns_server_active = true;
    
    // Show AP instructions on the screen
    show_ap_mode_ui();
    
    // Start Web Server
    server.on("/", handle_root);
    server.on("/save", HTTP_POST, handle_save);
    server.on("/update", HTTP_GET, handle_ota_get);
    server.on("/update", HTTP_POST, handle_ota_post, handle_ota_upload);
    server.on("/api/status", handle_api_status);
    server.on("/api/set_theme", handle_api_set_theme);
    server.on("/api/export", handle_api_export);
    server.on("/api/import", HTTP_POST, handle_api_import);
    // Captive portal: redirect any unknown path to root
    server.onNotFound([]() {
      server.sendHeader("Location", "http://" + WiFi.softAPIP().toString() + "/", true);
      server.send(302, "text/plain", "");
    });
    server.begin();
    WiFi.scanNetworks(true);
    
    // Loop in AP mode indefinitely until user configures Wi-Fi
    for (;;) {
      dnsServer.processNextRequest(); // Captive portal DNS
      server.handleClient();
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }

  Serial.println("\nWi-Fi Connected successfully!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  if (lvgl_port_lock(-1)) {
    char ip_str[32];
    sprintf(ip_str, "IP: %s", WiFi.localIP().toString().c_str());
    lv_label_set_text(refresh_label, ip_str);
    lvgl_port_unlock();
  }
  wifi_was_connected = true; // baseline state for the health-tracking logic

  // Configure NTP Local Chinese Time (Beijing/Hong Kong time: GMT+8)
  configTzTime("CST-8", "pool.ntp.org", "ntp.aliyun.com");

  // Wait up to 5 seconds for NTP clock synchronization
  {
    int retry = 0;
    struct tm timeinfo;
    while (!getLocalTime(&timeinfo) && retry < 10) {
      vTaskDelay(pdMS_TO_TICKS(500));
      retry++;
    }
    if (getLocalTime(&timeinfo)) {
      sync_rtc_from_system_time();
    }
  }

  // Start Web Server in Station Mode
  server.on("/", handle_root);
  server.on("/save", HTTP_POST, handle_save);
  server.on("/update", HTTP_GET, handle_ota_get);
  server.on("/update", HTTP_POST, handle_ota_post, handle_ota_upload);
  server.on("/api/status", handle_api_status);
  server.on("/api/set_theme", handle_api_set_theme);
  server.on("/api/export", handle_api_export);
  server.on("/api/import", HTTP_POST, handle_api_import);
  server.begin();
  WiFi.scanNetworks(true);

  // Register mDNS hostname so the portal is reachable at newsticker.local
  if (MDNS.begin("newsticker")) {
    MDNS.addService("http", "tcp", 80);
    Serial.println("[mDNS] Registered: http://newsticker.local");
  } else {
    Serial.println("[mDNS] Failed to start mDNS");
  }

  // Reconfigure or initialize watchdog timer (60s timeout) for this task
  esp_task_wdt_config_t twdt_config = {
    .timeout_ms = 60000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };
  if (esp_task_wdt_reconfigure(&twdt_config) != ESP_OK) {
    esp_task_wdt_init(&twdt_config);
  }
  esp_task_wdt_add(NULL); // Add current task to watchdog

  unsigned long last_fetch_time = 0;
  unsigned long last_scroll_time = 0;
  


  for(;;) {
    esp_task_wdt_reset(); // Feed the watchdog every loop iteration
    server.handleClient(); // Serve config page requests

    // Low-battery auto-shutdown check (every loop = every 1 second)
    check_low_battery_shutdown();

    // Burn-in protection: shift content by 1-2px every 30 minutes
    if (millis() - last_burnin_shift_time >= 1800000) { // 30 minutes
      last_burnin_shift_time = millis();
      burnin_offset_x = (burnin_offset_x + 1) % 3; // cycles 0, 1, 2
      burnin_offset_y = (burnin_offset_y + 1) % 3;
      if (lvgl_port_lock(100)) {
        if (carousel_container) lv_obj_set_style_translate_x(carousel_container, burnin_offset_x - 1, 0);
        if (carousel_container) lv_obj_set_style_translate_y(carousel_container, burnin_offset_y - 1, 0);
        if (top_panel) lv_obj_set_style_translate_x(top_panel, burnin_offset_x - 1, 0);
        lvgl_port_unlock();
      }
      Serial.printf("[Burnin] Pixel shift: x=%d, y=%d\n", burnin_offset_x - 1, burnin_offset_y - 1);
    }

    // Stack high-water-mark monitoring (every 60 seconds)
    {
      static unsigned long last_stack_log = 0;
      if (millis() - last_stack_log > 60000) {
        last_stack_log = millis();
        UBaseType_t hwm = uxTaskGetStackHighWaterMark(NULL);
        Serial.printf("[Stack] NewsTask high-water-mark: %u bytes remaining\n", hwm * 4);
      }
    //   Serial.printf("[Memory] Internal DRAM: %d KB free | PSRAM: %d KB free\n",
    //           ESP.getFreeHeap() / 1024,
    //           ESP.getFreePsram() / 1024);

    }

    // 1. Periodically update NTP clock every second
    if (WiFi.status() == WL_CONNECTED) {
      update_status_time();
    }

    struct tm timeinfo;
    int current_hour = 12;
    if (getLocalTime(&timeinfo)) {
      current_hour = timeinfo.tm_hour;
    }

    // Evaluate target brightness based on time/auto-brightness configuration
    int base_brightness = 255;
    if (auto_bright) {
      if (current_hour >= 7 && current_hour < 19) {
        base_brightness = day_bright;
      } else {
        base_brightness = night_bright;
      }
    } else {
      base_brightness = day_bright;
    }

    // Apply sleep scheduling
    bool sleep_active = is_sleep_time_active();
    int current_target = base_brightness;
    if (sleep_active) {
      if (millis() - last_sleep_bypass_time < 30000) {
        current_target = is_dimmed ? 10 : base_brightness;
      } else {
        current_target = 0;
      }
    } else {
      current_target = is_dimmed ? 10 : base_brightness;
    }
    
    // Low Power Mode: Cap maximum brightness at 100 when battery is below 20%
    int bat_pct = get_battery_percentage();
    if (bat_pct < 20 && current_target > 100) {
      current_target = 100;
    }

    if (current_target != last_applied_brightness) {
      last_applied_brightness = current_target;
      setUpduty(current_target);
      Serial.printf("[Power] Applied brightness level: %d\n", current_target);
    }

    // 5. Periodic Sound Level check (every 5 minutes)
    unsigned long now = millis();
    // We check if 5 minutes (300000ms) has passed since the last sound check
    if (now - last_sound_check_time >= 300000) {
      last_sound_check_time = now;
      bool sound_detected = check_for_sound();
      if (sound_detected) {
        reset_dim_timer();
      } else {
        silence_minutes += 5;
        Serial.printf("[Power] Silence duration: %d minutes.\n", silence_minutes);
        if (silence_minutes >= 10) {
          if (!is_dimmed) {
            is_dimmed = true;
            // This runs on a background task, not the LVGL task, so the
            // animation start must be lock-protected.
            if (lvgl_port_lock(100)) {
              set_brightness_smooth(255, 10, 400);
              lvgl_port_unlock();
            }
            Serial.println("[Power] No sound detected for 10 minutes. Screen dimming.");
          }
        }
      }
    }

    // 2. Automated Page-Flipping Scroll: Trigger fade transition every 10 seconds (10000ms)
    if (active_page == 0 && news_count > 0 && !is_updating && (now - last_scroll_time > (scroll_interval_seconds * 1000))) {
      last_scroll_time = now;
      if (lvgl_port_lock(100)) {
        // Trigger fade out transition on the news container
        lv_anim_t a;
        lv_anim_init(&a);
        lv_anim_set_var(&a, carousel_container);
        lv_anim_set_values(&a, LV_OPA_COVER, LV_OPA_TRANSP);
        lv_anim_set_duration(&a, 400);
        lv_anim_set_exec_cb(&a, set_opacity_anim_cb);
        lv_anim_set_completed_cb(&a, fade_out_completed_cb);
        lv_anim_start(&a);
        lvgl_port_unlock();
      }
    }

    // 3. Update battery and refresh indicators on top bar (4-dot squares with B: and R:)
    {
      static char last_bat_str[32] = "";
      static char last_ref_str[32] = "";
      
      char new_bat_str[32] = "";
      char new_ref_str[32] = "";

      int bat = get_battery_percentage();
      int bat_dots = 1;
      if (bat >= 75) bat_dots = 4;
      else if (bat >= 50) bat_dots = 3;
      else if (bat >= 25) bat_dots = 2;

      int ref_dots = 1;
      strcpy(new_ref_str, "R:");
      if (is_updating) {
        strcat(new_ref_str, "....");
      } else {
        if (seconds_to_refresh > 225) ref_dots = 4;
        else if (seconds_to_refresh > 150) ref_dots = 3;
        else if (seconds_to_refresh > 75) ref_dots = 2;
        
        for (int i = 0; i < 4; i++) {
          strcat(new_ref_str, (i < ref_dots) ? "■" : "□");
        }
      }

      strcpy(new_bat_str, "B:");
      for (int i = 0; i < 4; i++) {
        strcat(new_bat_str, (i < bat_dots) ? "■" : "□");
      }

      if (strcmp(new_bat_str, last_bat_str) != 0) {
        strcpy(last_bat_str, new_bat_str);
        if (lvgl_port_lock(100)) {
          lv_label_set_text(battery_label, new_bat_str);
          lvgl_port_unlock();
        }
      }

      if (strcmp(new_ref_str, last_ref_str) != 0) {
        strcpy(last_ref_str, new_ref_str);
        if (lvgl_port_lock(100)) {
          lv_label_set_text(refresh_label, new_ref_str);
          lvgl_port_unlock();
        }
      }
    }

    // 4. Timer decrement and fetch requests
    if (!is_updating) {
      if (seconds_to_refresh > 0) {
        seconds_to_refresh--;
      } else {
        fetch_requested = true;
        seconds_to_refresh = 300;
      }
    }

    if (fetch_requested) {
      fetch_requested = false;
      
      // If smart sleep is active (and not within 2 mins of boot), put CPU to Light Sleep to save maximum battery!
      if (is_sleep_time_active() && millis() > 120000) {
        Serial.println("[Power] Smart Sleep active. Turning off backlight and entering Light Sleep for 1 hour...");
        
        // Turn off backlight directly
        setUpduty(0);
        last_applied_brightness = 0;
        
        // Disable Wi-Fi radio to save extra power during sleep
        WiFi.disconnect(true);
        
        // Configure wake timer for 1 hour (3600 seconds)
        esp_sleep_enable_timer_wakeup(3600ULL * 1000000ULL);
        esp_light_sleep_start();
        
        Serial.println("[Power] Woke up from Smart Sleep! Re-enabling Wi-Fi...");
        WiFi.begin(wifi_ssid.c_str(), wifi_pass.c_str());
        
        seconds_to_refresh = 10; // Trigger news fetch quickly upon waking
        is_updating = false;
        continue;
      }
      
      last_fetch_time = now;

      // Smart Wi-Fi check: Wait for auto-reconnect if temporarily disconnected
// Wi-Fi health check: only force a full reconnect if the connection
      // has been down for a sustained period (not just a momentary status
      // flicker), and let WiFi.setAutoReconnect(true) handle brief drops
      // on its own without us calling WiFi.begin() redundantly.
      if (WiFi.status() != WL_CONNECTED) {
        if (wifi_was_connected) {
          // Just went down - start the clock, don't panic yet.
          wifi_disconnected_since = now;
          wifi_was_connected = false;
          Serial.println("[WiFi] Status dropped - waiting to see if it self-recovers...");
        }

        // Give the ESP32's own auto-reconnect up to 8 seconds to bring it
        // back before we intervene at all.
        unsigned long down_duration = now - wifi_disconnected_since;
        if (down_duration > 8000) {
          int wait_retries = 0;
          while (WiFi.status() != WL_CONNECTED && wait_retries < 10) {
            vTaskDelay(pdMS_TO_TICKS(500));
            wait_retries++;
          }
          if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WiFi] Still down after 8s+5s of waiting. Forcing reconnect...");
            WiFi.disconnect();
            vTaskDelay(pdMS_TO_TICKS(200));
            WiFi.begin(wifi_ssid.c_str(), wifi_pass.c_str());
            vTaskDelay(pdMS_TO_TICKS(3000));
          }
        }
      } else {
        if (!wifi_was_connected) {
          Serial.println("[WiFi] Reconnected on its own - no manual intervention needed.");
        }
        wifi_was_connected = true;
      }

      if (WiFi.status() == WL_CONNECTED) {
        is_updating = true;
        Serial.println("Refreshing news and weather...");
        if (lvgl_port_lock(-1)) {
          lv_label_set_text(refresh_label, ".....");
          lvgl_port_unlock();
        }


        double lat = 22.3193; // Default Hong Kong coordinates
        double lon = 114.1694;
        bool geo_resolved = false;

        if (custom_city.length() > 0) {
          float clat = 0, clon = 0;
          String resolved_name = "", rcountry = "";
          if (resolve_custom_city_coords(custom_city, clat, clon, resolved_name, rcountry)) {
            lat = clat;
            lon = clon;
            local_city = resolved_name;
            resolve_region(rcountry);
            geo_resolved = true;
            Serial.printf("[Geo-Custom] City resolved: %s, Lat: %.4f, Lon: %.4f, Country: %s\n", local_city.c_str(), lat, lon, rcountry.c_str());
          }
        }

        if (!geo_resolved) {
          // A. Geolocation: Get location coordinates from external IP
          WiFiClient client;
          HTTPClient http;
          Serial.println("Querying IP Geolocation API...");
          http.begin(client, "http://ip-api.com/json/");
          http.setTimeout(6000); // fail fast instead of hanging on a slow/stalled response
          int httpCode = http.GET();
          if (httpCode == HTTP_CODE_OK) {
            String payload = http.getString();
            Serial.println("[Geo] Response: " + payload);

            // Parse City Name
            int city_idx = payload.indexOf("\"city\":\"");
            if (city_idx != -1) {
              int start = city_idx + 8;
              int end = payload.indexOf("\"", start);
              local_city = payload.substring(start, end);
            }

            // Parse Lat
            int lat_idx = payload.indexOf("\"lat\":");
            if (lat_idx != -1) {
              int start = lat_idx + 6;
              int end = payload.indexOf(",", start);
              lat = payload.substring(start, end).toDouble();
            }

            // Parse Lon
            int lon_idx = payload.indexOf("\"lon\":");
            if (lon_idx != -1) {
              int start = lon_idx + 6;
              int end = payload.indexOf(",", start);
              lon = payload.substring(start, end).toDouble();
            }

            // Parse Timezone for Asia check
            int tz_idx = payload.indexOf("\"timezone\":\"");
            if (tz_idx != -1) {
              int start = tz_idx + 12;
              int end = payload.indexOf("\"", start);
              String local_timezone = payload.substring(start, end);
              is_asia = local_timezone.startsWith("Asia");
              Serial.printf("[Geo] Timezone: %s, Is Asia: %s\n", local_timezone.c_str(), is_asia ? "Yes" : "No");
            }

            // Parse Country (used to resolve the correct region: news city,
            // Google News feed params, and UI language)
            String local_country = "";
            int country_idx = payload.indexOf("\"country\":\"");
            if (country_idx != -1) {
              int start = country_idx + 11;
              int end = payload.indexOf("\"", start);
              local_country = payload.substring(start, end);
            }

            resolve_region(local_country);
            Serial.printf("[Geo] Region resolved from country '%s' -> city=%s hl=%s gl=%s ceid=%s asia_ui=%s\n",
                           local_country.c_str(), news_query_city.c_str(), news_hl.c_str(),
                           news_gl.c_str(), news_ceid.c_str(), is_asia ? "yes" : "no");

            Serial.printf("[Geo] City: %s, Lat: %.4f, Lon: %.4f\n", local_city.c_str(), lat, lon);
          } else {
            Serial.printf("[Geo] Failed, HTTP code: %d\n", httpCode);
            local_city = "Toronto"; // Fallback city name
            resolve_region("Canada"); // Sets news_query_city/hl/gl/ceid/is_asia consistently
          }
          http.end();
        }

        // B. Weather: Query Open-Meteo API using parsed coordinates
        Serial.println("Querying Weather API...");
        String weather_url = "http://api.open-meteo.com/v1/forecast?latitude=" + String(lat, 4) + 
                             "&longitude=" + String(lon, 4) + "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,weather_code";
        WiFiClient client;
        HTTPClient http;
        http.begin(client, weather_url);
        http.setTimeout(6000);
        int weatherCode = http.GET();
        if (weatherCode == HTTP_CODE_OK) {
          String payload = http.getString();
          Serial.println("[Weather] Response: " + payload);

          int current_idx = payload.indexOf("\"current\":{");
          if (current_idx != -1) {
            // Parse Temperature inside current block
            int temp_idx = payload.indexOf("\"temperature_2m\":", current_idx);
            if (temp_idx != -1) {
              int start = temp_idx + 17;
              int end = payload.indexOf(",", start);
              int end2 = payload.indexOf("}", start);
              if (end2 != -1 && end2 < end) end = end2;
              local_temp = payload.substring(start, end).toDouble();
            }

            // Parse Weather Code inside current block
            int wcode = 0;
            int wcode_idx = payload.indexOf("\"weather_code\":", current_idx);
            if (wcode_idx != -1) {
              int start = wcode_idx + 15;
              int end = payload.indexOf(",", start);
              int end2 = payload.indexOf("}", start);
              if (end2 != -1 && end2 < end) end = end2;
              wcode = payload.substring(start, end).toInt();
            }

            local_weather_desc = get_weather_desc(wcode);
            Serial.printf("[Weather] Temp: %.1f, Code: %d (%s)\n", local_temp, wcode, local_weather_desc.c_str());
            weather_fetched = true;
          }

          // Parse daily forecast arrays for Tomorrow and Day After
          int daily_idx = payload.indexOf("\"daily\":{");
          if (daily_idx != -1) {
            // 1. Max temperatures
            int max_idx = payload.indexOf("\"temperature_2m_max\":[", daily_idx);
            if (max_idx != -1) {
              int start = max_idx + 22;
              for (int i = 0; i < 3; i++) {
                int end = payload.indexOf(i == 2 ? "]" : ",", start);
                if (end != -1) {
                  forecast_max[i] = payload.substring(start, end).toDouble();
                  start = end + 1;
                }
              }
            }

            // 2. Min temperatures
            int min_idx = payload.indexOf("\"temperature_2m_min\":[", daily_idx);
            if (min_idx != -1) {
              int start = min_idx + 22;
              for (int i = 0; i < 3; i++) {
                int end = payload.indexOf(i == 2 ? "]" : ",", start);
                if (end != -1) {
                  forecast_min[i] = payload.substring(start, end).toDouble();
                  start = end + 1;
                }
              }
            }

            // 3. Weather codes
            int code_idx = payload.indexOf("\"weather_code\":[", daily_idx);
            if (code_idx != -1) {
              int start = code_idx + 16;
              for (int i = 0; i < 3; i++) {
                int end = payload.indexOf(i == 2 ? "]" : ",", start);
                if (end != -1) {
                  forecast_code[i] = payload.substring(start, end).toInt();
                  start = end + 1;
                }
              }
            }
            forecast_fetched = true;
          }
        } else {
          Serial.printf("[Weather] Failed, HTTP code: %d\n", weatherCode);
          local_weather_desc = is_asia ? "獲取失敗" : "Failed";
        }
        http.end();

        // Update Weather UI Elements
        if (lvgl_port_lock(-1)) {
          lv_label_set_text(weather_loc_label, local_city.c_str());
          char weather_str[48];
          if (weather_fetched) {
            sprintf(weather_str, "%.1f°C %s", local_temp, local_weather_desc.c_str());
          } else {
            sprintf(weather_str, is_asia ? "氣溫未知" : "Temp Unknown");
          }
          lv_label_set_text(weather_desc_label, weather_str);
          lvgl_port_unlock();
        }

 // AFTER
        // Fetch Local News search feed using HTTP/HTTPS auto-detection
        String feed_url = "";
        int current_count = 0;
        int active_sources = 0;
        for (int i = 0; i < 5; i++) {
          if (custom_rss_urls[i].length() > 0) {
            active_sources++;
          }
        }

        // ONE WiFiClientSecure reused for every feed fetch below (default
        // feed or up to 5 custom sources). A fresh WiFiClientSecure has to
        // malloc TLS RX/TX buffers + mbedTLS context every time it's
        // constructed - doing that 5x back-to-back was what exhausted/
        // fragmented the heap and caused "SSL - Memory allocation failed".
        // Reusing one instance means that allocation happens once per
        // refresh cycle, not once per source.
        WiFiClientSecure secure_client;
        secure_client.setInsecure();
        secure_client.setHandshakeTimeout(10);
        //secure_client.setBufferSizes(2048, 1024);

        if (active_sources == 0) {
          String query_city = news_query_city;
          query_city.replace(" ", "%20");
          String feed_url = "https://news.google.com/rss/search?q=" + query_city +
                             "&hl=" + news_hl + "&gl=" + news_gl + "&ceid=" + news_ceid +
                             "&nocache=" + String(millis());

          Serial.println("Fetching local news from default feed: " + feed_url);
          current_count = fetch_and_parse_rss_url(secure_client, feed_url, 50, 0);
        } else {
          int sources_processed = 0;
          for (int i = 0; i < 5; i++) {
            if (custom_rss_urls[i].length() > 0) {
              int limit = 50 / active_sources;
              if (active_sources == 2) limit = 25;
              else if (active_sources == 3) {
                limit = (sources_processed == 2) ? 18 : 16;
              } else if (active_sources == 4) {
                limit = (sources_processed == 3) ? 14 : 12;
              } else if (active_sources == 5) {
                limit = 10;
              }
              
              if (sources_processed > 0) {
                // Short gap just to let lwIP tear down the previous TCP
                // socket cleanly - secure_client itself is reused so no
                // TLS buffer realloc happens here anymore.
                vTaskDelay(pdMS_TO_TICKS(300));
              }
              
              Serial.printf("Fetching source %d: %s (limit: %d, start_idx: %d)\n", i + 1, custom_rss_urls[i].c_str(), limit, current_count);
              current_count = fetch_and_parse_rss_url(secure_client, custom_rss_urls[i], limit, current_count);
              sources_processed++;
            }
          }
        }

        if (current_count > 0) {
          news_count = current_count;
          fetch_fail_count = 0; // Reset fail counter on success
          Serial.printf("Successfully parsed %d news items total.\n", news_count);
          if (lvgl_port_lock(-1)) {
            update_ui_news();
            lvgl_port_unlock();
          }
          save_news_cache(); // Persist latest headlines to NVS for next boot
          seconds_to_refresh = 300; // Reset countdown to 5 min
        } else {
          fetch_fail_count++;
          int backoff = (fetch_fail_count == 1) ? 30 : ((fetch_fail_count == 2) ? 60 : 120);
          Serial.printf("No news items parsed. Exponential backoff retry in %d seconds (attempt %d).\n", backoff, fetch_fail_count);
          if (lvgl_port_lock(-1)) {
            lv_label_set_text(refresh_label, is_asia ? "失敗" : "Failed");
            lvgl_port_unlock();
          }
          seconds_to_refresh = backoff;
        }
        http.end();
        is_updating = false;
      } else {
        Serial.println("Cannot fetch data: Wi-Fi is offline.");
        if (lvgl_port_lock(-1)) {
          lv_label_set_text(refresh_label, is_asia ? "離線" : "Offline");
          lvgl_port_unlock();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

// ----------------------------------------------------
// NVS / Settings Management
// ----------------------------------------------------
void load_settings() {
  newsPrefs.begin("news", false);
  wifi_ssid = newsPrefs.getString("ssid", WIFI_SSID);
  wifi_pass = newsPrefs.getString("pass", WIFI_PASSWORD);
  blacklist_str = newsPrefs.getString("blacklist", "香港文匯報,文匯報,香港文汇报");
  sleep_enabled = newsPrefs.getBool("sleep_on", false);
  sleep_start = newsPrefs.getInt("sleep_start", 23);
  sleep_end = newsPrefs.getInt("sleep_end", 7);
  auto_bright = newsPrefs.getBool("auto_bright", false);
  day_bright = newsPrefs.getInt("day_bright", 255);
  night_bright = newsPrefs.getInt("night_bright", 50);
  scroll_interval_seconds = newsPrefs.getInt("scroll_int", 10);
  custom_rss_urls[0] = newsPrefs.getString("rss_url1", "");
  custom_rss_urls[1] = newsPrefs.getString("rss_url2", "");
  custom_rss_urls[2] = newsPrefs.getString("rss_url3", "");
  custom_rss_urls[3] = newsPrefs.getString("rss_url4", "");
  custom_rss_urls[4] = newsPrefs.getString("rss_url5", "");
  custom_city = newsPrefs.getString("custom_city", "");
  current_theme = newsPrefs.getInt("theme", 0);
  newsPrefs.end();

  update_blacklist_array();
}

void save_settings() {
  newsPrefs.begin("news", false);
  newsPrefs.putString("ssid", wifi_ssid);
  newsPrefs.putString("pass", wifi_pass);
  newsPrefs.putString("blacklist", blacklist_str);
  newsPrefs.putBool("sleep_on", sleep_enabled);
  newsPrefs.putInt("sleep_start", sleep_start);
  newsPrefs.putInt("sleep_end", sleep_end);
  newsPrefs.putBool("auto_bright", auto_bright);
  newsPrefs.putInt("day_bright", day_bright);
  newsPrefs.putInt("night_bright", night_bright);
  newsPrefs.putInt("scroll_int", scroll_interval_seconds);
  newsPrefs.putString("rss_url1", custom_rss_urls[0]);
  newsPrefs.putString("rss_url2", custom_rss_urls[1]);
  newsPrefs.putString("rss_url3", custom_rss_urls[2]);
  newsPrefs.putString("rss_url4", custom_rss_urls[3]);
  newsPrefs.putString("rss_url5", custom_rss_urls[4]);
  newsPrefs.putString("custom_city", custom_city);
  newsPrefs.putInt("theme", current_theme);
  newsPrefs.end();

  update_blacklist_array();
}

// ----------------------------------------------------
// Page Navigation (News Ticker vs Weather Forecast)
// ----------------------------------------------------
void switch_page(int page) {
  active_page = page;
  if (lvgl_port_lock(100)) {
    update_ui_news_labels();
    lvgl_port_unlock();
  }
}

// ----------------------------------------------------
// Web Portal Handlers & Content (PROGMEM)
// ----------------------------------------------------
const char config_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>News Ticker Setup</title>
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: linear-gradient(135deg, #0f1116 0%, #191e28 100%);
  color: #f0f0f0;
  margin: 0;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  min-height: 100vh;
  box-sizing: border-box;
}
.card {
  background: rgba(33, 38, 48, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(55, 63, 80, 0.8);
  border-radius: 16px;
  padding: 24px;
  width: 100%;
  max-width: 440px;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}
h2 {
  margin-top: 0;
  font-weight: 600;
  color: #00ff66;
  text-align: center;
  border-bottom: 1px solid rgba(55, 63, 80, 0.5);
  padding-bottom: 12px;
}
.form-group {
  margin-bottom: 20px;
}
label {
  display: block;
  font-size: 14px;
  margin-bottom: 8px;
  color: #b0b0b0;
}
input[type="text"], input[type="password"], select {
  width: 100%;
  padding: 12px;
  background: rgba(20, 24, 30, 0.8);
  border: 1px solid rgba(55, 63, 80, 0.8);
  border-radius: 8px;
  color: #ffffff;
  box-sizing: border-box;
  font-size: 16px;
}
input[type="text"]:focus, input[type="password"]:focus, select:focus {
  border-color: #00ff66;
  outline: none;
}
.row {
  display: flex;
  gap: 12px;
}
.row .form-group {
  flex: 1;
}
.toggle-group {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(20, 24, 30, 0.4);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(55, 63, 80, 0.4);
}
.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider-toggle {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #332630;
  transition: .3s;
  border-radius: 24px;
}
.slider-toggle:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .3s;
  border-radius: 50%;
}
input:checked + .slider-toggle {
  background-color: #00ff66;
}
input:checked + .slider-toggle:before {
  transform: translateX(24px);
}
.slider-val {
  display: flex;
  align-items: center;
  gap: 12px;
}
.slider-val input[type="range"] {
  flex: 1;
  accent-color: #00ff66;
}
.btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #00ff66 0%, #00cc55 100%);
  border: none;
  border-radius: 8px;
  color: #050505;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: 0.2s;
  margin-top: 10px;
}
.btn:hover {
  opacity: 0.9;
  box-shadow: 0 0 12px rgba(0, 255, 102, 0.4);
}
.footer {
  text-align: center;
  font-size: 12px;
  color: #606060;
  margin-top: 20px;
}
.sug-btn {
  background: rgba(0, 255, 102, 0.08);
  color: #00ff66;
  border: 1px solid rgba(0, 255, 102, 0.3);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: 0.2s;
}
.sug-btn:hover {
  background: rgba(0, 255, 102, 0.2);
  border-color: #00ff66;
  box-shadow: 0 0 8px rgba(0, 255, 102, 0.3);
}
</style>
<script>
function addSuggestion(url) {
  for (let i = 1; i <= 5; i++) {
    let inp = document.getElementById('rss_url_' + i);
    if (inp && inp.value === '') {
      inp.value = url;
      return;
    }
  }
  // If all are full, overwrite the first one
  let first = document.getElementById('rss_url_1');
  if (first) first.value = url;
}
function updateDashboard() {
  fetch('/api/status')
    .then(r => r.json())
    .then(d => {
      document.getElementById('dash_bat').innerText = d.battery_pct;
      document.getElementById('dash_wifi').innerText = d.wifi_rssi;
      document.getElementById('dash_cnt').innerText = d.news_count;
      document.getElementById('dash_status').innerText = d.is_updating ? 'Updating...' : 'Active';
      
      let list = document.getElementById('dash_headlines');
      list.innerHTML = '';
      if (d.headlines.length === 0) {
        list.innerHTML = '<li>No news loaded yet</li>';
      } else {
        d.headlines.forEach(h => {
          let li = document.createElement('li');
          li.innerText = h;
          list.appendChild(li);
        });
      }
    })
    .catch(e => console.error(e));
}
window.onload = function() {
  updateDashboard();
  setInterval(updateDashboard, 5000);
};
</script>
</head>
<body>
<div class="card" style="margin-bottom:20px;">
  <h2>Live Status Dashboard</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:15px;text-align:left;">
    <div><strong>Battery:</strong> <span id="dash_bat">--</span>%</div>
    <div><strong>Wi-Fi Signal:</strong> <span id="dash_wifi">--</span> dBm</div>
    <div><strong>News Count:</strong> <span id="dash_cnt">--</span> items</div>
    <div><strong>Status:</strong> <span id="dash_status">--</span></div>
  </div>
  <div style="text-align:left;">
    <strong>Latest Headlines:</strong>
    <ul id="dash_headlines" style="max-height:120px;overflow-y:auto;background:rgba(20,24,30,0.6);padding:10px 10px 10px 25px;border-radius:8px;border:1px solid rgba(55,63,80,0.6);margin:8px 0 0 0;font-size:13px;color:#a0a0a0;line-height:1.4;">
      <li>Loading...</li>
    </ul>
  </div>
</div>

<div class="card">
  <h2>News Ticker Setup</h2>
  <form action="/save" method="POST">
    <div class="form-group">
      <label>Scanned Wi-Fi Networks</label>
      <select id="wifi_select" onchange="if(this.value){document.getElementById('ssid_input').value = this.value;}">
        <option value="">-- Select network or type below --</option>
        {{WIFI_OPTIONS}}
      </select>
    </div>
    <div class="form-group">
      <label>Wi-Fi SSID</label>
      <input type="text" id="ssid_input" name="ssid" value="{{SSID}}" placeholder="Enter Wi-Fi SSID" required>
    </div>
    <div class="form-group">
      <label>Wi-Fi Password</label>
      <input type="password" name="pass" value="{{PASS}}" placeholder="Enter Wi-Fi Password">
    </div>
    <div class="form-group">
      <label>Custom Weather Location (City Name)</label>
      <input type="text" name="custom_city" value="{{CUSTOM_CITY}}" placeholder="e.g. Tokyo, London (Leave blank to use GPS)">
    </div>
    <div class="form-group">
      <label>Blacklisted Sources (Comma-separated)</label>
      <input type="text" name="blacklist" value="{{BLACKLIST}}" placeholder="e.g. 香港文匯報,文匯報">
    </div>
    <div class="form-group">
      <label>Custom RSS Feeds (Up to 5, leave blank to use default Google News)</label>
      <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:8px;">
        <input type="text" id="rss_url_1" name="rss_url1" value="{{RSS_URL1}}" placeholder="RSS Source 1 URL" style="margin:0;">
        <input type="text" id="rss_url_2" name="rss_url2" value="{{RSS_URL2}}" placeholder="RSS Source 2 URL" style="margin:0;">
        <input type="text" id="rss_url_3" name="rss_url3" value="{{RSS_URL3}}" placeholder="RSS Source 3 URL" style="margin:0;">
        <input type="text" id="rss_url_4" name="rss_url4" value="{{RSS_URL4}}" placeholder="RSS Source 4 URL" style="margin:0;">
        <input type="text" id="rss_url_5" name="rss_url5" value="{{RSS_URL5}}" placeholder="RSS Source 5 URL" style="margin:0;">
      </div>
      <button type="button" class="btn" onclick="for(let i=1;i<=5;i++)document.getElementById('rss_url_'+i).value='';" style="width:auto;margin:0 0 15px 0;padding:10px 15px;background:linear-gradient(135deg,#ff3366 0%,#cc1144 100%);color:#ffffff;border-radius:8px;font-weight:bold;cursor:pointer;">Restore Defaults (Clear All)</button>
    </div>
    
    <div class="form-group">
      <label>Suggested English News Sources (Click to add to empty slots)</label>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:6px;max-height:120px;overflow-y:auto;background:rgba(20, 24, 30, 0.6);padding:8px;border-radius:8px;border:1px solid rgba(55, 63, 80, 0.6);">
        <button type="button" class="sug-btn" onclick="addSuggestion('https://news.google.com/rss')">Google News</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('http://feeds.bbci.co.uk/news/world/rss.xml')">BBC News World</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('http://rss.cnn.com/rss/edition_world.rss')">CNN World</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('https://rss.nytimes.com/services/xml/rss/nyt/World.xml')">NYT World</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('https://ir.thomsonreuters.com/rss/news-releases.xml?items=15')">Reuters</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('https://news.google.com/rss/search?q=source:%22Associated%20Press%22')">AP News</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('https://techcrunch.com/feed/')">TechCrunch</button>
        <button type="button" class="sug-btn" onclick="addSuggestion('https://www.wired.com/feed/rss')">Wired Science</button>
      </div>
    </div>
    
    <div class="form-group toggle-group">
      <label style="margin-bottom:0;">Smart Sleep Hours</label>
      <label class="switch">
        <input type="checkbox" name="sleep_on" value="1" {{SLEEP_CHECKED}}>
        <span class="slider-toggle"></span>
      </label>
    </div>
    
    <div class="row">
      <div class="form-group">
        <label>Sleep Start Hour</label>
        <select name="sleep_start">
          {{START_OPTIONS}}
        </select>
      </div>
      <div class="form-group">
        <label>Sleep End Hour</label>
        <select name="sleep_end">
          {{END_OPTIONS}}
        </select>
      </div>
    </div>

    <div class="form-group toggle-group">
      <label style="margin-bottom:0;">Auto Brightness (Day/Night)</label>
      <label class="switch">
        <input type="checkbox" name="auto_bright" value="1" {{BRIGHT_CHECKED}}>
        <span class="slider-toggle"></span>
      </label>
    </div>

    <div class="form-group">
      <label>Day Brightness</label>
      <div class="slider-val">
        <input type="range" name="day_bright" min="10" max="255" value="{{DAY_BRIGHT}}" oninput="this.nextElementSibling.innerText = this.value">
        <span style="width: 30px; text-align: right;">{{DAY_BRIGHT}}</span>
      </div>
    </div>

    <div class="form-group">
      <label>Night Brightness</label>
      <div class="slider-val">
        <input type="range" name="night_bright" min="10" max="255" value="{{NIGHT_BRIGHT}}" oninput="this.nextElementSibling.innerText = this.value">
        <span style="width: 30px; text-align: right;">{{NIGHT_BRIGHT}}</span>
      </div>
    </div>
    
    <div class="form-group">
      <label>News Scroll Interval (seconds)</label>
      <input type="number" name="scroll_int" min="3" max="60" value="{{SCROLL_INT}}" required style="width:100%;padding:12px;background:rgba(20, 24, 30, 0.8);border:1px solid rgba(55, 63, 80, 0.8);border-radius:8px;color:#ffffff;box-sizing:border-box;font-size:16px;">
    </div>
    
    <div class="form-group">
      <label>LCD Color Theme (Applies instantly)</label>
      <select name="theme" onchange="fetch('/api/set_theme?val=' + this.value)">
        {{THEME_OPTIONS}}
      </select>
    </div>
    
    <button type="submit" class="btn">Save & Reboot</button>
  </form>
  <div style="display:flex;gap:10px;margin-top:15px;">
    <a href="/api/export" download class="sug-btn" style="flex:1;text-decoration:none;display:inline-block;padding:10px;text-align:center;">Export Config</a>
    <button type="button" class="sug-btn" style="flex:1;padding:10px;" onclick="document.getElementById('import_file').click()">Import Config</button>
    <input type="file" id="import_file" style="display:none" accept=".json" onchange="let f=this.files[0];if(f){let r=new FileReader();r.onload=e=>fetch('/api/import',{method:'POST',body:e.target.result}).then(()=>alert('Config imported successfully! Rebooting...')).then(()=>location.reload());r.readAsText(f);}">
  </div>
  <div style="text-align:center;margin-top:15px;">
    <a href="/update" style="color:#00ff66;text-decoration:none;font-size:14px;">Go to Firmware Update (OTA)</a>
  </div>
  <div class="footer">ESP32-S3 News Ticker Portal</div>
</div>
</body>
</html>
)rawliteral";

void handle_api_status() {
  String json = "{";
  json += "\"battery_pct\":" + String(get_battery_percentage()) + ",";
  
  int rssi = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;
  json += "\"wifi_rssi\":" + String(rssi) + ",";
  json += "\"news_count\":" + String(news_count) + ",";
  json += "\"is_updating\":" + String(is_updating ? "true" : "false") + ",";
  
json += "\"headlines\":[";
int api_limit = (news_count > 20) ? 20 : news_count;
  for (int i = 0; i < api_limit; i++) {
    String headline = String(news_list[i].headline);
    headline.replace("\\", "\\\\");
    headline.replace("\"", "\\\"");
    headline.replace("\n", "\\n");
    headline.replace("\r", "\\r");
    json += "\"" + headline + "\"";
    if (i < news_count - 1) json += ",";
  }
  json += "]";
  json += "}";
  
  server.send(200, "application/json; charset=utf-8", json);
}

void handle_api_set_theme() {
  if (server.hasArg("val")) {
    int new_theme = server.arg("val").toInt();
    if (new_theme >= 0 && new_theme < 5) {
      if (new_theme != current_theme) {
        current_theme = new_theme;
        if (lvgl_port_lock(-1)) {
          apply_theme_styles();
          lvgl_port_unlock();
        }
        save_settings();
      }
      server.send(200, "text/plain", "OK");
      return;
    }
  }
  server.send(400, "text/plain", "Bad Request");
}

void handle_api_export() {
  String json = "{";
  json += "\"ssid\":\"" + wifi_ssid + "\",";
  json += "\"pass\":\"" + wifi_pass + "\",";
  json += "\"blacklist\":\"" + blacklist_str + "\",";
  json += "\"sleep_on\":" + String(sleep_enabled ? "true" : "false") + ",";
  json += "\"sleep_start\":" + String(sleep_start) + ",";
  json += "\"sleep_end\":" + String(sleep_end) + ",";
  json += "\"auto_bright\":" + String(auto_bright ? "true" : "false") + ",";
  json += "\"day_bright\":" + String(day_bright) + ",";
  json += "\"night_bright\":" + String(night_bright) + ",";
  json += "\"scroll_int\":" + String(scroll_interval_seconds) + ",";
  json += "\"custom_city\":\"" + custom_city + "\",";
  json += "\"theme\":" + String(current_theme) + ",";
  json += "\"rss_urls\":[";
  for (int i = 0; i < 5; i++) {
    json += "\"" + custom_rss_urls[i] + "\"";
    if (i < 4) json += ",";
  }
  json += "]}";
  server.sendHeader("Content-Disposition", "attachment; filename=newsticker_config.json");
  server.send(200, "application/json; charset=utf-8", json);
}

void handle_api_import() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    int idx;
    if ((idx = body.indexOf("\"ssid\":\"")) != -1) {
      int end = body.indexOf("\"", idx + 8);
      if (end != -1) wifi_ssid = body.substring(idx + 8, end);
    }
    if ((idx = body.indexOf("\"pass\":\"")) != -1) {
      int end = body.indexOf("\"", idx + 8);
      if (end != -1) wifi_pass = body.substring(idx + 8, end);
    }
    if ((idx = body.indexOf("\"blacklist\":\"")) != -1) {
      int end = body.indexOf("\"", idx + 13);
      if (end != -1) blacklist_str = body.substring(idx + 13, end);
    }
    if ((idx = body.indexOf("\"custom_city\":\"")) != -1) {
      int end = body.indexOf("\"", idx + 15);
      if (end != -1) custom_city = body.substring(idx + 15, end);
    }
    if ((idx = body.indexOf("\"theme\":")) != -1) {
      current_theme = body.substring(idx + 8).toInt();
    }
    if ((idx = body.indexOf("\"scroll_int\":")) != -1) {
      scroll_interval_seconds = body.substring(idx + 13).toInt();
    }
    save_settings();
    server.send(200, "text/plain", "OK");
    return;
  }
  server.send(400, "text/plain", "Missing body");
}

void handle_root() {
  // Read scan results from background async scan (non-blocking)
  int n = WiFi.scanComplete();
  String wifi_opts = "";
  if (n > 0) {
    for (int i = 0; i < n; ++i) {
      String ssid = WiFi.SSID(i);
      int rssi = WiFi.RSSI(i);
      String enc = (WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? "Open" : "Secured";
      wifi_opts += "<option value=\"" + ssid + "\">" + ssid + " (" + String(rssi) + "dBm, " + enc + ")</option>\n";
    }
    WiFi.scanDelete(); // Free memory
  } else if (n == -1) { // WIFI_SCAN_RUNNING
    wifi_opts += "<option value=\"\">-- Scanning in progress... Refresh page in a few seconds --</option>\n";
  } else {
    wifi_opts += "<option value=\"\">-- No cached networks (refresh page to start scan) --</option>\n";
  }

  // Trigger a new async scan for the next load if it's not currently running
  if (n != -1) {
    WiFi.scanNetworks(true);
  }

  String html = String(config_html);   // Copies ~12KB from PROGMEM to RAM
  html.replace("{{WIFI_OPTIONS}}", wifi_opts);
  html.replace("{{SSID}}", wifi_ssid);
  html.replace("{{PASS}}", wifi_pass);
  html.replace("{{BLACKLIST}}", blacklist_str);
  html.replace("{{SLEEP_CHECKED}}", sleep_enabled ? "checked" : "");
  html.replace("{{BRIGHT_CHECKED}}", auto_bright ? "checked" : "");
  
  String start_opts = "";
  for (int h = 0; h < 24; h++) {
    String hr = String(h);
    String sel = (h == sleep_start) ? "selected" : "";
    start_opts += "<option value=\"" + hr + "\" " + sel + ">" + hr + ":00</option>\n";
  }
  html.replace("{{START_OPTIONS}}", start_opts);

  String end_opts = "";
  for (int h = 0; h < 24; h++) {
    String hr = String(h);
    String sel = (h == sleep_end) ? "selected" : "";
    end_opts += "<option value=\"" + hr + "\" " + sel + ">" + hr + ":00</option>\n";
  }
  html.replace("{{END_OPTIONS}}", end_opts);

  html.replace("{{DAY_BRIGHT}}", String(day_bright));
  html.replace("{{NIGHT_BRIGHT}}", String(night_bright));
  html.replace("{{SCROLL_INT}}", String(scroll_interval_seconds));
  html.replace("{{RSS_URL1}}", custom_rss_urls[0]);
  html.replace("{{RSS_URL2}}", custom_rss_urls[1]);
  html.replace("{{RSS_URL3}}", custom_rss_urls[2]);
  html.replace("{{RSS_URL4}}", custom_rss_urls[3]);
  html.replace("{{RSS_URL5}}", custom_rss_urls[4]);
  html.replace("{{CUSTOM_CITY}}", custom_city);

  String theme_opts = "";
  const char* theme_names[] = {
    "🟢 Cyberpunk Neon Green (Default)",
    "🌅 Sunset Coral (Warm Peach)",
    "🟧 Retro Terminal (Amber Orange)",
    "🍃 Forest Calcite (Mint Green)",
    "👑 Royal Monarch (Orchid Gold)"
  };
  for (int i = 0; i < 5; i++) {
    String sel = (i == current_theme) ? "selected" : "";
    theme_opts += "<option value=\"" + String(i) + "\" " + sel + ">" + String(theme_names[i]) + "</option>\n";
  }
  html.replace("{{THEME_OPTIONS}}", theme_opts);

  server.send(200, "text/html; charset=utf-8", html);
}

void handle_save() {
  if (server.hasArg("ssid")) {
    wifi_ssid = server.arg("ssid");
  }
  if (server.hasArg("pass")) {
    wifi_pass = server.arg("pass");
  }
  if (server.hasArg("blacklist")) {
    blacklist_str = server.arg("blacklist");
  }
  
  sleep_enabled = server.hasArg("sleep_on");
  if (server.hasArg("sleep_start")) {
    sleep_start = server.arg("sleep_start").toInt();
  }
  if (server.hasArg("sleep_end")) {
    sleep_end = server.arg("sleep_end").toInt();
  }
  
  auto_bright = server.hasArg("auto_bright");
  if (server.hasArg("day_bright")) {
    day_bright = server.arg("day_bright").toInt();
  }
  if (server.hasArg("night_bright")) {
    night_bright = server.arg("night_bright").toInt();
  }
  if (server.hasArg("scroll_int")) {
    scroll_interval_seconds = server.arg("scroll_int").toInt();
  }
  if (server.hasArg("rss_url1")) {
    custom_rss_urls[0] = server.arg("rss_url1");
  }
  if (server.hasArg("rss_url2")) {
    custom_rss_urls[1] = server.arg("rss_url2");
  }
  if (server.hasArg("rss_url3")) {
    custom_rss_urls[2] = server.arg("rss_url3");
  }
  if (server.hasArg("rss_url4")) {
    custom_rss_urls[3] = server.arg("rss_url4");
  }
  if (server.hasArg("rss_url5")) {
    custom_rss_urls[4] = server.arg("rss_url5");
  }
  if (server.hasArg("custom_city")) {
    custom_city = server.arg("custom_city");
  }
  if (server.hasArg("theme")) {
    int new_theme = server.arg("theme").toInt();
    if (new_theme != current_theme) {
      current_theme = new_theme;
      if (lvgl_port_lock(-1)) {
        apply_theme_styles();
        lvgl_port_unlock();
      }
    }
  }

  save_settings();

  String success_html = "<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
                        "<style>body{background:#0f1116;color:#00ff66;font-family:sans-serif;text-align:center;padding:50px;}"
                        "h2{margin-top:100px;}</style></head><body>"
                        "<h2>Settings Saved successfully!</h2>"
                        "<p>Rebooting device to apply new configurations...</p>"
                        "</body></html>";
  server.send(200, "text/html; charset=utf-8", success_html);
  
  delay(1000);
  ESP.restart();
}

void show_ap_mode_ui() {
  if (lvgl_port_lock(-1)) {
    lv_label_set_text(refresh_label, "Setup Mode");
    lv_label_set_text(top_headline_lbl, "Wi-Fi disconnected. Connect to Hotspot:\nSSID: ESP32_News_Ticker");
    lv_label_set_text(bottom_headline_lbl, "Open browser and configure device at:\nhttp://192.168.4.1/");
    lvgl_port_unlock();
  }
}

// ----------------------------------------------------
// Web OTA Firmware Updater Handlers & Page
// ----------------------------------------------------
const char ota_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Firmware Update</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:linear-gradient(135deg,#0f1116 0%,#191e28 100%);color:#f0f0f0;text-align:center;padding:50px;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;}
.card{background:rgba(33,38,48,0.7);backdrop-filter:blur(10px);border:1px solid rgba(55,63,80,0.8);border-radius:16px;padding:30px;width:100%;max-width:380px;box-shadow:0 8px 32px 0 rgba(0,0,0,0.3);}
h2{margin-top:0;font-weight:600;color:#00ff66;}
.btn{background:linear-gradient(135deg,#00ff66 0%,#00cc55 100%);color:#050505;border:none;padding:14px;border-radius:8px;font-size:16px;cursor:pointer;font-weight:bold;width:100%;margin-top:20px;transition:0.2s;}
.btn:hover{opacity:0.9;box-shadow:0 0 12px rgba(0,255,102,0.4);}
progress{width:100%;accent-color:#00ff66;margin-top:20px;height:12px;border-radius:6px;background:rgba(20,24,30,0.8);}
</style>
</head>
<body>
<div class="card">
  <h2>Firmware OTA Update</h2>
  <form method="POST" action="/update" enctype="multipart/form-data" id="upload_form">
    <input type="file" name="update" accept=".bin" required style="width:100%;background:rgba(20,24,30,0.8);padding:10px;border-radius:6px;box-sizing:border-box;border:1px solid rgba(55,63,80,0.8);color:#ffffff;">
    <button type="submit" class="btn">Update Firmware</button>
  </form>
  <div id="prg_box" style="display:none;">
    <progress id="prg" value="0" max="100"></progress>
    <div id="prg_pct" style="margin-top:10px;font-size:18px;font-weight:bold;color:#00ff66;">0%</div>
  </div>
</div>
<script>
document.getElementById('upload_form').onsubmit = function(e) {
  e.preventDefault();
  var form = new FormData(this);
  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/update', true);
  
  document.getElementById('upload_form').style.display = 'none';
  document.getElementById('prg_box').style.display = 'block';
  
  xhr.upload.onprogress = function(e) {
    if (e.lengthComputable) {
      var p = Math.round((e.loaded / e.total) * 100);
      document.getElementById('prg').value = p;
      document.getElementById('prg_pct').innerText = p + '%';
    }
  };
  
  xhr.onload = function() {
    if (xhr.status == 200) {
      document.body.innerHTML = '<h2>Update Successful!</h2><p>Rebooting device...</p>';
      setTimeout(function() { window.location.href = '/'; }, 5000);
    } else {
      document.body.innerHTML = '<h2 style="color:red;">Update Failed!</h2><p>' + xhr.responseText + '</p><a href="/update" style="color:#00ff66;">Try again</a>';
    }
  };
  xhr.send(form);
};
</script>
</body>
</html>
)rawliteral";

void handle_ota_get() {
  server.send(200, "text/html; charset=utf-8", ota_html);
}

void handle_ota_post() {
  server.sendHeader("Connection", "close");
  server.send(200, "text/plain", (Update.hasError()) ? "FAIL" : "OK");
  delay(1000);
  ESP.restart();
}

void handle_ota_upload() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("Update: %s\n", upload.filename.c_str());
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) { // Start with max available size
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) { // true to set the size to the current progress
      Serial.printf("Update Success: %u\nRebooting...\n", upload.totalSize);
    } else {
      Update.printError(Serial);
    }
  }
}