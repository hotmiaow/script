#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include "time.h"

#include "user_config.h"
#include "lvgl_port.h"
#include "i2c_bsp.h"
#include "src/lcd_bl_bsp/lcd_bl_pwm_bsp.h"
#include "lvgl.h"

// Audio & Codec Includes
#include "src/tca9554/esp_io_expander_tca9554.h"
#include "src/codec_board/codec_board.h"
#include "src/codec_board/codec_init.h"

// ==========================================
// USER CONFIGURATION: Configure Wi-Fi Here
// ==========================================
#include "secrets.h"

// ==========================================

// Global State
#define MAX_HEADLINE_LEN 160
#define MAX_SOURCE_LEN   48
#define MAX_PUBDATE_LEN  24

struct NewsItem {
  char headline[MAX_HEADLINE_LEN];
  char source[MAX_SOURCE_LEN];
  char pubDate[MAX_PUBDATE_LEN];
};

#define MAX_NEWS_ITEMS 20
#define MAX_CACHED_NEWS 10
NewsItem news_list[MAX_NEWS_ITEMS];

int news_count = 0;
bool is_updating = false;
volatile bool fetch_requested = true;
int seconds_to_refresh = 300; // 5 minutes refresh interval
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
unsigned long last_sound_check_time = 0;

// LVGL UI Handles
LV_FONT_DECLARE(lv_font_source_han_sans_sc_16_cjk);
static lv_style_t main_style;
static lv_style_t title_style;
static lv_style_t sub_style;

lv_obj_t *main_screen = NULL;
lv_obj_t *top_panel = NULL;
lv_obj_t *date_label = NULL;
lv_obj_t *time_label = NULL;
lv_obj_t *weather_loc_label = NULL;
lv_obj_t *weather_desc_label = NULL;
lv_obj_t *status_label = NULL;

lv_obj_t *carousel_container = NULL;
lv_obj_t *top_card = NULL;
lv_obj_t *bottom_card = NULL;
lv_obj_t *top_headline_lbl = NULL;
lv_obj_t *bottom_headline_lbl = NULL;

lv_obj_t *top_meta_lbl = NULL;
lv_obj_t *bottom_meta_lbl = NULL;

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

void reset_dim_timer(void) {
  silence_minutes = 0;
  if (is_dimmed) {
    is_dimmed = false;
    // Called from LVGL's own event context (screen/panel tap), so no
    // extra lvgl_port_lock needed here - already inside the LVGL task.
    set_brightness_smooth(10, 255, 250);
    Serial.println("[Power] Screen woke up: ramping to max brightness.");
  }
}

static void screen_click_event_handler(lv_event_t * e) {
  lv_event_code_t code = lv_event_get_code(e);
  if(code == LV_EVENT_PRESSED || code == LV_EVENT_CLICKED) {
    reset_dim_timer();
  }
}

void tca9554_init(void)
{
  i2c_master_bus_handle_t tca9554_i2c_bus_ = NULL;
  ESP_ERROR_CHECK(i2c_master_get_bus_handle(0,&tca9554_i2c_bus_));
  esp_io_expander_new_i2c_tca9554(tca9554_i2c_bus_, ESP_IO_EXPANDER_I2C_TCA9554_ADDRESS_000, &io_expander);
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
  // Initialize Serial Monitor
  Serial.begin(115200);
  delay(100);
  Serial.println("Initializing ESP32-S3 Google News Ticker...");

  // Load any cached news from a previous session BEFORE anything else,
  // so we have something to show the instant the UI is created —
  // no waiting on Wi-Fi/RSS fetch for the first paint.
  load_cached_news();

  // Initialize Onboard Dual I2C buses (Touch & Sensors)
  i2c_master_Init();

  // Initialize TCA9554 and Audio Codec (Power pin 7)
  tca9554_init();
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
  xTaskCreatePinnedToCore(fetch_news_task, "NewsTask", 10240, NULL, 1, NULL, 0);
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

  // 5. Status Label (Countdown)
  status_label = lv_label_create(top_panel);
  lv_obj_add_style(status_label, &sub_style, 0);
  lv_label_set_text(status_label, "Initializing...");

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
}

// ----------------------------------------------------
// UI News Cards Rendering (Traditional Chinese)
// ----------------------------------------------------
void update_ui_news(void) {
  current_page = 0;
  update_ui_news_labels();
}


void update_ui_news_labels(void) {
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

}

// ----------------------------------------------------
// Time Update Logic
// ----------------------------------------------------
void update_status_time(void) {
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    char timeStr[6];
    sprintf(timeStr, "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
    
    char dateStr[32];
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
String build_news_meta(const NewsItem &item) {
  bool has_source = item.source[0] != '\0';
  bool has_date = item.pubDate[0] != '\0';
  if (!has_source && !has_date) return "";
  if (!has_source) return String(item.pubDate);
  if (!has_date) return String(item.source);
  return String(item.source) + " · " + String(item.pubDate);
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
int parse_rss_stream(WiFiClientSecure *stream) {
  int count = 0;

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

          if (count < MAX_NEWS_ITEMS && item_title_len > 0) {
            item_title_buf[item_title_len] = '\0';
            item_pubdate_buf[item_pubdate_len] = '\0';

            char* trimmed_title = trim_inplace(item_title_buf);
            char* trimmed_pubdate = trim_inplace(item_pubdate_buf);

            // Split "Headline - Source Name"
            char* split = strrstr_custom(trimmed_title, " - ");
            if (split) {
              int headline_len = split - trimmed_title;
              if (headline_len >= MAX_HEADLINE_LEN) headline_len = MAX_HEADLINE_LEN - 1;
              strncpy(news_list[count].headline, trimmed_title, headline_len);
              news_list[count].headline[headline_len] = '\0';

              strncpy(news_list[count].source, split + 3, MAX_SOURCE_LEN - 1);
              news_list[count].source[MAX_SOURCE_LEN - 1] = '\0';
            } else {
              strncpy(news_list[count].headline, trimmed_title, MAX_HEADLINE_LEN - 1);
              news_list[count].headline[MAX_HEADLINE_LEN - 1] = '\0';
              strncpy(news_list[count].source, "谷歌新聞", MAX_SOURCE_LEN - 1);
              news_list[count].source[MAX_SOURCE_LEN - 1] = '\0';
            }

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
          if (count >= MAX_NEWS_ITEMS) break;
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

void fetch_news_task(void *pvParameters) {
  // Connect to Wi-Fi
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  
  if (lvgl_port_lock(-1)) {
    lv_label_set_text(status_label, "Connecting Wi-Fi...");
    lvgl_port_unlock();
  }

  // Disable Wi-Fi sleep to prevent random disconnects, lags, and excessive latency
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int retry_count = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retry_count++;
    if (retry_count > 30) { // Timeout after 15 seconds
      Serial.println("\nWi-Fi connection failed.");
      if (lvgl_port_lock(-1)) {
        lv_label_set_text(status_label, "Connection failed");
        lvgl_port_unlock();
      }
      break;
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi Connected successfully!");
    if (lvgl_port_lock(-1)) {
      lv_label_set_text(status_label, "Wi-Fi Connected");
      lvgl_port_unlock();
    }
    wifi_was_connected = true; // baseline state for the health-tracking logic

    // Configure NTP Local Chinese Time (Beijing/Hong Kong time: GMT+8)
    configTzTime("CST-8", "pool.ntp.org", "ntp.aliyun.com");
  }

  unsigned long last_fetch_time = 0;
  unsigned long last_scroll_time = 0;
  
  for(;;) {
    // 1. Periodically update NTP clock every second
    if (WiFi.status() == WL_CONNECTED) {
      update_status_time();
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
    if (news_count > 0 && !is_updating && (now - last_scroll_time > 10000)) {
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

    // 3. Update refresh countdown label - only touch LVGL when the text
    // actually changed, avoiding redundant redraws (e.g. every tick while
    // "is_updating" stays true for the whole fetch cycle).
    {
      static char last_status_str[32] = "";
      char new_status_str[32];

      if (is_updating) {
        strncpy(new_status_str, is_asia ? "正在更新..." : "Updating...", sizeof(new_status_str) - 1);
        new_status_str[sizeof(new_status_str) - 1] = '\0';
      } else if (is_asia) {
        snprintf(new_status_str, sizeof(new_status_str), "%d秒後更新", seconds_to_refresh);
      } else {
        snprintf(new_status_str, sizeof(new_status_str), "Refresh in %ds", seconds_to_refresh);
      }

      if (strcmp(new_status_str, last_status_str) != 0) {
        strncpy(last_status_str, new_status_str, sizeof(last_status_str) - 1);
        last_status_str[sizeof(last_status_str) - 1] = '\0';
        if (lvgl_port_lock(100)) {
          lv_label_set_text(status_label, new_status_str);
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
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
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
          lv_label_set_text(status_label, "正在更新...");
          lvgl_port_unlock();
        }

        WiFiClientSecure secure_client;
        secure_client.setInsecure(); // Disable SSL verification for simple parsing
        
        WiFiClient client; // Non-SSL client for HTTP API calls

        double lat = 22.3193; // Default Hong Kong coordinates
        double lon = 114.1694;

        // A. Geolocation: Get location coordinates from external IP
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

          // Parse Country (used to resolve the correct metro area for news search)
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

        // B. Weather: Query Open-Meteo API using parsed coordinates
        Serial.println("Querying Weather API...");
        String weather_url = "http://api.open-meteo.com/v1/forecast?latitude=" + String(lat, 4) + 
                             "&longitude=" + String(lon, 4) + "&current=temperature_2m,weather_code";
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

        // Fetch Local News search feed based on the resolved metro-area city
        // (districts/suburbs are mapped to their parent city for better results)
// Fetch Local News search feed using the region-matched city and
        // its correct Google News hl/gl/ceid edition params.
        String query_city = news_query_city;
        query_city.replace(" ", "%20");
        String feed_url = "https://news.google.com/rss/search?q=" + query_city +
                           "&hl=" + news_hl + "&gl=" + news_gl + "&ceid=" + news_ceid +
                           "&nocache=" + String(millis());

        Serial.println("Fetching local news from: " + feed_url);
        http.begin(secure_client, feed_url);
        http.setTimeout(8000); // slightly longer - this response is a full RSS feed body
        int httpCodeNews = http.GET();
        if (httpCodeNews == HTTP_CODE_OK) {
          WiFiClientSecure *stream = (WiFiClientSecure*)http.getStreamPtr();
          int items_parsed = parse_rss_stream(stream);
          
          if (items_parsed > 0) {
            news_count = items_parsed;
            Serial.printf("Successfully parsed %d news items.\n", news_count);
            if (lvgl_port_lock(-1)) {
              update_ui_news();
              lvgl_port_unlock();
            }
            save_news_cache(); // Persist latest headlines to NVS for next boot
          } else {
            Serial.println("No news items parsed.");
            if (lvgl_port_lock(-1)) {
              lv_label_set_text(status_label, is_asia ? "解析失敗" : "Parse failed");
              lvgl_port_unlock();
            }
          }
        } else {
          Serial.printf("HTTP news request failed, code: %d\n", httpCodeNews);
          if (lvgl_port_lock(-1)) {
            lv_label_set_text(status_label, is_asia ? "網絡錯誤" : "Network error");
            lvgl_port_unlock();
          }
        }
        http.end();
        is_updating = false;
        seconds_to_refresh = 300; // Reset countdown
      } else {
        Serial.println("Cannot fetch data: Wi-Fi is offline.");
        if (lvgl_port_lock(-1)) {
          lv_label_set_text(status_label, is_asia ? "網路離線" : "Offline");
          lvgl_port_unlock();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}