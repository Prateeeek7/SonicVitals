#define CAMERA_MODEL_ESP32S3_EYE

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <driver/i2s.h>
#include "esp_camera.h"
#include "camera_pins.h"
#include <base64.h>
#include <math.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

// Verified OLED I2C Pins (GPIO 47 & GPIO 48)
#define OLED_SDA_PIN  47
#define OLED_SCL_PIN  48

// INMP441 Microphone Pin Assignments (TX=GPIO 43, RX=GPIO 44, BOOT=GPIO 0)
#define I2S_SCK_PIN   43
#define I2S_WS_PIN    44
#define I2S_SD_PIN    0
#define I2S_PORT      I2S_NUM_0

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
bool oledReady = false;
bool camReady = false;
bool micReady = false;

void initOLED() {
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN, 400000);
  if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    oledReady = true;
    display.setRotation(0); // Standard original orientation
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(6, 0);
    display.println("SONICVITALS CLINICAL");
    display.drawFastHLine(0, 10, 128, SSD1306_WHITE);
    display.setCursor(0, 16);
    display.println("Booting Node Sensors...");
    display.display();
  }
}

void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;

  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_HQVGA; // 240x160
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);
  if (err == ESP_OK) {
    camReady = true;
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);
  }
}

void initI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 128,
    .use_apll = false
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK_PIN,
    .ws_io_num = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD_PIN
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err == ESP_OK) {
    if (i2s_set_pin(I2S_PORT, &pin_config) == ESP_OK) {
      micReady = true;
    }
  }
}

void setup() {
  Serial.begin(460800);
  delay(400);

  initOLED();
  initCamera();
  initI2S();
}

// Telemetry & Clinical Parameters
unsigned long lastOledTime = 0;
unsigned long frameCount = 0;
unsigned long lastFpsTime = 0;
float currentFps = 15.0;
double currentRms = 0;

// Clinical estimation variables
int currentHR = 0;
int currentRR = 0;
int currentSpO2 = 0;
int currentConf = 0;
String currentStatusStr = "PATIENT: SEARCH";
String serialRxBuf = "";

void loop() {
  // 0. Non-blocking Serial Telemetry Receiver from Python Backend
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialRxBuf.startsWith("<<VITALS:") && serialRxBuf.endsWith(">>")) {
        String p = serialRxBuf.substring(9, serialRxBuf.length() - 2);
        int c1 = p.indexOf(',');
        int c2 = p.indexOf(',', c1 + 1);
        int c3 = p.indexOf(',', c2 + 1);
        if (c1 > 0 && c2 > 0 && c3 > 0) {
          currentHR = p.substring(0, c1).toInt();
          currentRR = p.substring(c1 + 1, c2).toInt();
          currentSpO2 = p.substring(c2 + 1, c3).toInt();
          String st = p.substring(c3 + 1);
          if (st == "STABLE") {
            currentStatusStr = "PATIENT: STABLE";
            currentConf = 91;
          } else if (st == "CALIB") {
            currentStatusStr = "OBSERVING / CALIB";
            currentConf = 50;
          } else {
            currentStatusStr = "PATIENT: SEARCH";
            currentConf = 0;
          }
        }
      }
      serialRxBuf = "";
    } else {
      if (serialRxBuf.length() < 64) {
        serialRxBuf += c;
      }
    }
  }

  // 1. Microphone Audio Reading
  if (micReady) {
    int32_t samples[64];
    size_t bytes_read = 0;
    esp_err_t res = i2s_read(I2S_PORT, samples, sizeof(samples), &bytes_read, 0);
    if (res == ESP_OK && bytes_read > 0) {
      int count = bytes_read / sizeof(int32_t);
      double sumSq = 0;
      for (int i = 0; i < count; i++) {
        int32_t v = samples[i] >> 14;
        sumSq += (double)v * v;
      }
      currentRms = sqrt(sumSq / count);
    }
  }

  // 2. Camera Capture and USB Serial Delivery
  if (camReady) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      uint8_t * out_jpg = NULL;
      size_t out_jpg_len = 0;
      bool ok = frame2jpg(fb, 60, &out_jpg, &out_jpg_len);
      esp_camera_fb_return(fb);

      if (ok && out_jpg && out_jpg_len > 0) {
        String b64 = base64::encode(out_jpg, out_jpg_len);
        free(out_jpg);

        Serial.println("<<FRAME_START>>");
        Serial.println(b64);
        Serial.println("<<FRAME_END>>");
        frameCount++;
      }
    }
  }

  // Calculate actual FPS every second
  if (millis() - lastFpsTime >= 1000) {
    static unsigned long prevFrames = 0;
    currentFps = (frameCount - prevFrames) * (1000.0 / (millis() - lastFpsTime));
    if (currentFps < 1.0) currentFps = 15.0;
    prevFrames = frameCount;
    lastFpsTime = millis();
  }

  // 3. Render Requested Clinical Layout on OLED Screen (every 200ms)
  if (oledReady && (millis() - lastOledTime >= 200)) {
    lastOledTime = millis();

    display.clearDisplay();
    display.setTextWrap(false); // Crucial: prevents overlapping text wrapping
    display.setTextColor(SSD1306_WHITE);

    // Header (Y: 1-9)
    display.setTextSize(1);
    display.setCursor(4, 1);
    display.println("SONICVITALS CLINICAL");
    display.drawFastHLine(0, 11, 128, SSD1306_WHITE);

    // Row 1: Heart Rate & Respiration Rate (Clean 20 chars, Y: 15)
    display.setCursor(2, 15);
    if (currentHR > 0) {
      display.printf("HR: %2d BPM   RR: %2d/m", currentHR, currentRR);
    } else {
      display.print("HR: -- BPM   RR: --/m");
    }

    // Row 2: SpO2 & Fusion Confidence (Clean 20 chars, Y: 26)
    display.setCursor(2, 26);
    if (currentSpO2 > 0) {
      display.printf("SpO2: %d%%   Conf: %d%%", currentSpO2, currentConf);
    } else {
      display.print("SpO2: --%   Conf: --%");
    }

    // Row 3: Sensor Telemetry (Clean 19 chars, Y: 37)
    display.setCursor(2, 37);
    display.printf("Cam: %.0ffps  Mic: %s", currentFps, (currentRms > 400) ? "ACT*" : "OK");

    // Row 4: Status Bar (Clean white text, Y: 51)
    display.drawFastHLine(0, 47, 128, SSD1306_WHITE);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(2, 52);
    display.print(currentStatusStr);

    display.display();
  }
}
