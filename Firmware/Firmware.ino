// SonicVitals edge node firmware (protocol v2)
//
// Captures OV2640 frames and INMP441 audio, timestamps both with esp_timer
// (microseconds since boot, one clock for both streams), and streams them to
// the host. The host returns vital signs, which are shown on the SSD1306 OLED.
//
// Host link
//   SV_TRANSPORT_USB (default env "esp32s3"): native USB-CDC on GPIO19/20.
//     Required when the microphone is fitted, because the INMP441 uses
//     GPIO43/44, which are the UART0 TX/RX pins.
//   SV_TRANSPORT_WIFI (env "esp32s3_wifi"): TCP server on port 3333 over Wi-Fi.
//     For boards with a single USB connector (USB-UART bridge on UART0): the
//     cable only powers/flashes the board, so the mic keeps GPIO43/44/0.
//     Station mode if wifi_secrets.h defines an SSID, otherwise a WPA2 access point.
//   SV_TRANSPORT_UART (env "esp32s3_uart"): UART0 through the board's
//     USB-UART bridge. The microphone is disabled in this mode.
//
// Wire protocol (one record per line, ASCII):
//   <<HELLO:SonicVitals,2,<transport>,<mic_enabled>,i2c=<addrs>,fs=<audio rate Hz>>>
//   <<FRAME_START:<seq>,<t_us>,<jpeg_bytes>>>   then one Base64 line, then <<FRAME_END>>
//   <<AUDIO:<seq>,<t_us>,<n>,<base64 little-endian int16 PCM>>>
//        t_us = esp_timer time at which the block's FIRST sample was captured;
//        audio is low-pass filtered and decimated to fs (HELLO) before streaming
//   <<STAT:<fps_x10>,<frames>,<audio_blocks>,<audio_drops>,<mic_ready>,<cam_ready>,<jpeg_avg_bytes>,
//          <oled_ready>,<oled_ack>,<cam_auto_locked>,<frame_drops>>>
//   <<RGB:<seq>,<t_us>,<n>,<sumR>,<sumG>,<sumB>,<n_clipped>,<n_dark>>>  raw-pixel skin sums; saturated
//        and near-black pixels are excluded from the sums and counted separately
//   <<CAMEXP:<exposure>,<applied_count>>>   after every exposure change (GC2145 P0:0x03/0x04, row units)
// Host -> node:
//   <<VITALS:HR,RR,SpO2,CONF,STATUS>>   (CONF optional for backward compatibility; 0 = unknown)
//   <<ROI:x,y,w,h;...>> / <<ROI:none>>  skin boxes to sum (up to 4)
//   <<CAM:EXP,<n>>>                     manual exposure (auto exposure off); set by the host from skin brightness

#define CAMERA_MODEL_ESP32S3_EYE

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <driver/i2s.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include "esp_camera.h"
#include "camera_pins.h"
#include <math.h>
#include <esp_system.h>
#include <esp_heap_caps.h>

#if !defined(SV_TRANSPORT_USB) && !defined(SV_TRANSPORT_UART) && !defined(SV_TRANSPORT_WIFI)
#define SV_TRANSPORT_USB
#endif

#ifdef SV_TRANSPORT_WIFI
  #include <WiFi.h>
  #include <ESPmDNS.h>
  #if __has_include("wifi_secrets.h")
    #include "wifi_secrets.h"           // local, not committed: see wifi_secrets.example.h
  #endif
  #ifndef SV_WIFI_SSID
  #define SV_WIFI_SSID ""               // empty -> start an access point instead
  #endif
  #ifndef SV_WIFI_PASSWORD
  #define SV_WIFI_PASSWORD ""
  #endif
  #ifndef SV_AP_SSID
  #define SV_AP_SSID "SonicVitals-Node"
  #endif
  #ifndef SV_AP_PASSWORD
  #define SV_AP_PASSWORD "sonicvitals-lab"   // WPA2 needs >= 8 characters; change in wifi_secrets.h
  #endif
  #define SV_TCP_PORT 3333
#endif

#ifdef SV_TRANSPORT_UART
  #define SV_ENABLE_MIC 0          // GPIO43/44 are needed by UART0
  #ifndef SV_UART_BAUD
  #define SV_UART_BAUD 921600
  #endif
#else
  #ifndef SV_ENABLE_MIC
  #define SV_ENABLE_MIC 1
  #endif
#endif

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

// OLED I2C pins
#define OLED_SDA_PIN  47
#define OLED_SCL_PIN  48

// INMP441 pins (board header TX=GPIO43, RX=GPIO44, BOOT=GPIO0)
#define I2S_SCK_PIN   43
#define I2S_WS_PIN    44
#define I2S_SD_PIN    0
#define I2S_PORT      I2S_NUM_0

// Audio configuration
#define AUDIO_RATE_HZ      16000   // I2S capture rate
#define AUDIO_BLOCK        256     // samples per I2S read (16 ms at 16 kHz)
#define AUDIO_SHIFT        14      // 32-bit I2S slot -> int16 (saturating)
// Decimation before streaming. Heart sounds are analysed below 400 Hz (at 1 kHz on
// the host), so 4 kHz keeps a wide margin while cutting audio traffic by 4x; this
// matters on links with limited throughput (Wi-Fi via a phone hotspot, UART).
#ifndef AUDIO_DECIM
  #ifdef SV_TRANSPORT_USB
  #define AUDIO_DECIM 1
  #else
  #define AUDIO_DECIM 4
  #endif
#endif
#define AUDIO_OUT_RATE_HZ  (AUDIO_RATE_HZ / AUDIO_DECIM)
#define AUDIO_OUT_BLOCK    256     // samples per streamed block (64 ms at 4 kHz)
#define AUDIO_QUEUE_DEPTH  (2000 * AUDIO_OUT_RATE_HZ / AUDIO_OUT_BLOCK / 1000)   // ~2 s
#define FIR_TAPS           63      // anti-aliasing low-pass before decimation

// Camera settings
#define JPEG_QUALITY       12      // hardware JPEG quality (0-63, lower = better), OV2640-class sensors
#define SW_JPEG_QUALITY    65      // software JPEG quality (0-100). The pulse comes from raw-pixel ROI sums, so
                                   // the video only feeds face detection and the display; q85 overloaded hotspot links
#ifndef SV_TARGET_FPS
  #ifdef SV_TRANSPORT_WIFI
  #define SV_TARGET_FPS    5       // q85 frames are ~1.5x larger; phone hotspots carried 50-70 kB/s
  #else
  #define SV_TARGET_FPS    10
  #endif
#endif   // video rate sent to the host; frames queue in PSRAM if the link stalls
#ifndef SV_CAPTURE_FPS
#define SV_CAPTURE_FPS     10      // capture rate; skin-colour (ROI) sums are sent for every captured frame
#endif
#define JPEG_EVERY         ((SV_CAPTURE_FPS + SV_TARGET_FPS - 1) / SV_TARGET_FPS)   // JPEG-encode every Nth capture
#define RGB_QUEUE_DEPTH    128     // 12.8 s of ROI sums at 10 fps
#define FRAME_SLOTS        24      // PSRAM ring (2.4 s at 10 fps)
#define FRAME_SLOT_BYTES   16384   // max JPEG size per slot
// Camera task stack. Measured peak use is ~2.3 kB (frame2jpg + ROI sums); 16 kB leaves a wide margin.
// <<INFO>> reports the remaining margin (stack_cam) and the last reset reason.
#define CAMERA_TASK_STACK  16384
#define AUTO_LOCK_AFTER_MS 3000    // lock AEC/AGC/AWB after this settling time
#ifndef SV_AEC_TARGET
#define SV_AEC_TARGET      0x38    // GC2145 auto-exposure target luminance (factory 0x40; lower = darker, avoids clipped skin)
#endif

struct AudioBlock {
  uint32_t seq;
  int64_t  t_us;                   // capture time of the first sample
  int16_t  pcm[AUDIO_OUT_BLOCK];
};

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
bool oledReady = false;
bool oledPresent = false;      // SSD1306 acknowledged on I2C at the last check
bool camReady = false;
bool micReady = false;
bool camAutoLocked = false;
volatile int32_t pendingExposure = -1;   // set by the host command, applied by the camera task between frames
volatile int32_t camExposure = -1;       // current GC2145 exposure (rows), read back after every write
volatile uint32_t exposureApplied = 0;   // number of exposure writes; reported with <<CAMEXP>>
uint32_t exposureReported = 0;
int camInitErr = 0;
TaskHandle_t cameraTaskHandle = nullptr;
TaskHandle_t audioTaskHandle = nullptr;
uint32_t staleFrameDrops = 0;   // older queued frames skipped so the host always gets the newest one
String camLockInfo = "";       // register read-back of the GC2145 lock, reported once as <<INFO:...>>
uint16_t camPid = 0;          // sensor product ID (0x26 = OV2640, 0x2145 = GC2145, ...)
bool camHwJpeg = false;       // true if the sensor encodes JPEG itself
int frameSlots = 0;           // ring size actually allocated (PSRAM if present, else internal RAM)

QueueHandle_t audioQueue = nullptr;
volatile uint32_t audioBlocksCaptured = 0;
volatile uint32_t audioDrops = 0;
volatile float audioRms = 0.0f;

// Telemetry state
uint32_t frameSeq = 0;
uint32_t framesSent = 0;
uint32_t jpegBytesAccum = 0;
uint32_t jpegFramesAccum = 0;
float currentFps = 0.0f;

// Values returned by the host
int currentHR = 0;
int currentRR = 0;
int currentSpO2 = 0;
int currentConf = 0;
String currentStatusStr = "PATIENT: SEARCH";
String serialRxBuf = "";

// Skin regions (sensor pixel coordinates) chosen by the host's face detector. The camera
// task averages raw RGB565 pixels inside them before JPEG compression (<<RGB:...>>).
struct RoiBox { int16_t x, y, w, h; };
portMUX_TYPE roiMux = portMUX_INITIALIZER_UNLOCKED;
RoiBox roiBoxes[4];
int roiCount = 0;
uint32_t roiStampMs = 0;
#define ROI_TTL_MS 3000            // boxes older than this are ignored (host stopped updating)

struct RgbMsg {
  uint32_t seq;
  int64_t  t_us;
  uint32_t n, sr, sg, sb, nclip, ndark;
};
QueueHandle_t rgbQueue = nullptr;
volatile uint32_t rgbDrops = 0;
volatile int micChannel = -1;      // 0 = left, 1 = right, -1 = not decided yet

// ---------------------------------------------------------------- Host stream
// All protocol traffic goes through host(): Serial for USB/UART builds, the TCP
// client for Wi-Fi builds, or a sink that discards output when no host is attached.
class NullStream : public Stream {
 public:
  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override {}
  size_t write(uint8_t) override { return 1; }
  size_t write(const uint8_t *, size_t n) override { return n; }
};
NullStream nullStream;

#ifdef SV_TRANSPORT_WIFI
WiFiServer tcpServer(SV_TCP_PORT);
WiFiClient tcpClient;
String wifiLabel = "WiFi: starting";
bool hostAttached() { return tcpClient && tcpClient.connected(); }
Stream &host() { return hostAttached() ? (Stream &)tcpClient : (Stream &)nullStream; }
#else
bool hostAttached() { return true; }
Stream &host() { return Serial; }
#endif

// ---------------------------------------------------------------- OLED
String i2cScanResult = "";

// Lists every address that ACKs on the OLED bus (reported in HELLO for wiring diagnosis).
void scanI2C() {
  i2cScanResult = "";
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      if (i2cScanResult.length()) i2cScanResult += "/";
      i2cScanResult += String(a, HEX);
    }
  }
  if (!i2cScanResult.length()) i2cScanResult = "none";
}

int oledAck();

void initOLED() {
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN, 400000);
  scanI2C();
  oledPresent = oledAck() == 1;
  if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    oledReady = true;
    display.setRotation(0);
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(6, 0);
    display.println("SONICVITALS NODE");
    display.drawFastHLine(0, 10, 128, SSD1306_WHITE);
    display.setCursor(0, 16);
    display.println("Booting sensors...");
    display.display();
  }
}

// ---------------------------------------------------------------- Camera
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

  // The OV2640 encodes JPEG in hardware; software encoding of RGB565 limited the
  // first firmware to ~7.5 frames/s and stalled capture while frames were sent.
  config.pixel_format = PIXFORMAT_JPEG;
  config.jpeg_quality = JPEG_QUALITY;
  config.frame_size = FRAMESIZE_HQVGA;      // 240x160
  config.fb_count = 2;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err == ESP_ERR_NOT_SUPPORTED) {
    // Sensor without a JPEG encoder (e.g. GC2145): capture RGB565 and encode in the
    // camera task (frame2jpg), still at a fixed rate.
    esp_camera_deinit();
    config.pixel_format = PIXFORMAT_RGB565;
    err = esp_camera_init(&config);
  }
  if (err != ESP_OK && config.fb_location == CAMERA_FB_IN_PSRAM) {   // retry in internal RAM
    esp_camera_deinit();
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.fb_count = 1;
    err = esp_camera_init(&config);
  }
  camInitErr = (int)err;
  if (err == ESP_OK) {
    sensor_t *sid = esp_camera_sensor_get();
    camPid = sid ? sid->id.PID : 0;
    camHwJpeg = config.pixel_format == PIXFORMAT_JPEG;
    camReady = true;
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);
    if (camPid == 0x2145) gc2145SetAecTarget(s);
  }
}

// The esp32-camera GC2145 driver implements the generic exposure/gain/white-balance
// controls as no-ops, so the GC2145 is controlled through its own registers
// (page select 0xFE; P1:0x13 AEC target; P0:0xB6 bit0 AEC enable; P0:0x82 bit1 AWB enable).
int gcRead(sensor_t *s, uint8_t page, uint8_t reg) {
  s->set_reg(s, 0xFE, 0xFF, page);
  return s->get_reg(s, reg, 0xFF);
}
void gcWrite(sensor_t *s, uint8_t page, uint8_t reg, uint8_t mask, uint8_t val) {
  s->set_reg(s, 0xFE, 0xFF, page);
  s->set_reg(s, reg, mask, val);
}
void gc2145SetAecTarget(sensor_t *s) {
  int before = gcRead(s, 1, 0x13);
  gcWrite(s, 1, 0x13, 0xFF, SV_AEC_TARGET);
  int after = gcRead(s, 1, 0x13);
  s->set_reg(s, 0xFE, 0xFF, 0);
  camLockInfo = "aec_target=" + String(before, HEX) + "->" + String(after, HEX);
}
void gc2145Lock(sensor_t *s) {
  int b6 = gcRead(s, 0, 0xB6), r82 = gcRead(s, 0, 0x82);
  gcWrite(s, 0, 0xB6, 0x01, 0x00);       // AEC off: exposure and gain stay where they settled
  gcWrite(s, 0, 0x82, 0x02, 0x00);       // AWB off: colour gains stay where they settled
  int b6a = gcRead(s, 0, 0xB6), r82a = gcRead(s, 0, 0x82);
  camExposure = ((gcRead(s, 0, 0x03) & 0x1F) << 8) | gcRead(s, 0, 0x04);
  s->set_reg(s, 0xFE, 0xFF, 0);
  exposureApplied++;                     // report the settled exposure to the host once
  camLockInfo += ",b6=" + String(b6, HEX) + "->" + String(b6a, HEX) + ",82=" + String(r82, HEX) + "->" + String(r82a, HEX);
}

// Manual exposure (GC2145 P0:0x03 bits 4:0 = exposure[12:8], P0:0x04 = exposure[7:0]), auto exposure
// off. Called only from the camera task, so SCCB access never overlaps another task.
void gc2145SetExposure(sensor_t *s, int32_t e) {
  e = constrain(e, 1, 0x1FFF);
  gcWrite(s, 0, 0xB6, 0x01, 0x00);
  gcWrite(s, 0, 0x03, 0xFF, (e >> 8) & 0x1F);
  gcWrite(s, 0, 0x04, 0xFF, e & 0xFF);
  s->set_reg(s, 0xFE, 0xFF, 0);
  // The sensor latches exposure at the next frame, so an immediate read-back returns the old value.
  camExposure = e;
  exposureApplied++;
}

// Freeze automatic exposure, gain and white balance once they have settled, so
// that pixel values change only with the scene (needed for rPPG and colorimetry).
void lockCameraAutoControls() {
  sensor_t *s = esp_camera_sensor_get();
  if (!s) return;
  s->set_exposure_ctrl(s, 0);
  s->set_aec2(s, 0);
  s->set_gain_ctrl(s, 0);
  s->set_whitebal(s, 0);
  s->set_awb_gain(s, 0);
  if (camPid == 0x2145) gc2145Lock(s);
  camAutoLocked = true;
}

// ---------------------------------------------------------------- Audio
void initI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = AUDIO_RATE_HZ,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,   // both slots; the active one is chosen at run time
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,                     // 8 x 256 samples = 128 ms of DMA buffering
    .dma_buf_len = AUDIO_BLOCK,
    .use_apll = false
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK_PIN,
    .ws_io_num = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD_PIN
  };

  if (i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL) == ESP_OK &&
      i2s_set_pin(I2S_PORT, &pin_config) == ESP_OK) {
    micReady = true;
  }
}

// Runs on core 0. Drains I2S DMA into fixed-size PCM blocks and hands them to
// the streamer through a queue; never touches the serial port.
// Windowed-sinc (Hamming) low-pass, cutoff 0.4 * output Nyquist, unity DC gain.
static float firCoeffs[FIR_TAPS];
void designDecimationFilter() {
  const float fc = 0.4f / AUDIO_DECIM;          // cycles/sample at the input rate
  const int M = FIR_TAPS - 1;
  float sum = 0.0f;
  for (int n = 0; n < FIR_TAPS; n++) {
    float k = n - M / 2.0f;
    float sinc = (k == 0.0f) ? 2.0f * fc : sinf(2.0f * PI * fc * k) / (PI * k);
    float w = 0.54f - 0.46f * cosf(2.0f * PI * n / M);
    firCoeffs[n] = sinc * w;
    sum += firCoeffs[n];
  }
  for (int n = 0; n < FIR_TAPS; n++) firCoeffs[n] /= sum;
}

// Runs on core 0. Drains I2S DMA, low-pass filters and decimates, and hands
// fixed-size PCM blocks to the streamer through a queue; never touches the host link.
void audioTask(void *arg) {
  static int32_t raw[2 * AUDIO_BLOCK];          // interleaved stereo frames
  double varEma[2] = {0.0, 0.0};
  int blocksSeen = 0;
  static float hist[FIR_TAPS];                  // circular history of input samples
  int histPos = 0;
  int phase = 0;                                // input samples since the last output
  int outCount = 0;
  int64_t blockStartUs = 0;
  AudioBlock block;
  uint32_t seq = 0;
  const float inPeriodUs = 1e6f / AUDIO_RATE_HZ;

  for (;;) {
    size_t bytesRead = 0;
    esp_err_t res = i2s_read(I2S_PORT, raw, sizeof(raw), &bytesRead, portMAX_DELAY);
    int64_t tDone = esp_timer_get_time();
    if (res != ESP_OK || bytesRead != sizeof(raw)) continue;
    int64_t tFirst = tDone - (int64_t)(AUDIO_BLOCK * inPeriodUs);

    // The INMP441 drives only the slot selected by its L/R pin; the other slot reads a
    // constant. Pick the slot with the larger AC energy (decided over the first ~0.5 s,
    // re-checked continuously in case the mic is re-wired).
    for (int c = 0; c < 2; c++) {
      double m = 0.0, m2 = 0.0;
      for (int i = 0; i < AUDIO_BLOCK; i++) { double x = raw[2 * i + c] >> AUDIO_SHIFT; m += x; m2 += x * x; }
      m /= AUDIO_BLOCK;
      double var = m2 / AUDIO_BLOCK - m * m;
      varEma[c] = blocksSeen == 0 ? var : 0.95 * varEma[c] + 0.05 * var;
    }
    if (++blocksSeen >= 30) micChannel = varEma[1] > varEma[0] ? 1 : 0;
    const int ch = micChannel < 0 ? 0 : micChannel;

    double sumSq = 0.0;
    for (int i = 0; i < AUDIO_BLOCK; i++) {
      int32_t v = raw[2 * i + ch] >> AUDIO_SHIFT;
      if (v > 32767) v = 32767;
      if (v < -32768) v = -32768;
      sumSq += (double)v * v;
      hist[histPos] = (float)v;
      histPos = (histPos + 1) % FIR_TAPS;

      if (++phase < AUDIO_DECIM) continue;
      phase = 0;
      float acc = 0.0f;
      if (AUDIO_DECIM == 1) {
        acc = (float)v;
      } else {
        int idx = histPos;                      // oldest sample
        for (int n = 0; n < FIR_TAPS; n++) {
          acc += firCoeffs[n] * hist[idx];
          idx = (idx + 1) % FIR_TAPS;
        }
      }
      if (acc > 32767.0f) acc = 32767.0f;
      if (acc < -32768.0f) acc = -32768.0f;
      if (outCount == 0) blockStartUs = tFirst + (int64_t)(i * inPeriodUs);
      block.pcm[outCount++] = (int16_t)lrintf(acc);

      if (outCount == AUDIO_OUT_BLOCK) {
        block.seq = seq++;
        block.t_us = blockStartUs;
        audioBlocksCaptured++;
        if (xQueueSend(audioQueue, &block, 0) != pdTRUE) audioDrops++;
        outCount = 0;
      }
    }
    audioRms = (float)sqrt(sumSq / AUDIO_BLOCK);
  }
}

// ---------------------------------------------------------------- Host link
void sendHello() {
#if defined(SV_TRANSPORT_UART)
  const char *transport = "UART";
#elif defined(SV_TRANSPORT_WIFI)
  const char *transport = "WIFI";
#else
  const char *transport = "USB";
#endif
  host().printf("<<HELLO:SonicVitals,2,%s,%d,i2c=%s,fs=%d,psram=%u,camerr=%d,slots=%d,campid=%x,hwjpeg=%d>>\n",
                transport, SV_ENABLE_MIC, i2cScanResult.c_str(), AUDIO_OUT_RATE_HZ, (unsigned)ESP.getPsramSize(),
                camInitErr, frameSlots, camPid, camHwJpeg ? 1 : 0);
}

// Base64-encodes straight into the link in small pieces, so no frame-sized String is
// allocated on the internal heap for every frame (heap fragmentation).
void writeBase64(const uint8_t *data, size_t len) {
  static const char tbl[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  static char out[1024];
  size_t o = 0;
  for (size_t i = 0; i < len; i += 3) {
    uint32_t v = (uint32_t)data[i] << 16;
    if (i + 1 < len) v |= (uint32_t)data[i + 1] << 8;
    if (i + 2 < len) v |= data[i + 2];
    out[o++] = tbl[(v >> 18) & 63];
    out[o++] = tbl[(v >> 12) & 63];
    out[o++] = i + 1 < len ? tbl[(v >> 6) & 63] : '=';
    out[o++] = i + 2 < len ? tbl[v & 63] : '=';
    if (o >= sizeof(out) - 4) { host().write((const uint8_t *)out, o); o = 0; }
  }
  if (o) host().write((const uint8_t *)out, o);
}

void sendAudioBlocks() {
  if (!audioQueue) return;
  AudioBlock block;
  while (xQueueReceive(audioQueue, &block, 0) == pdTRUE) {
    host().printf("<<AUDIO:%lu,%lld,%d,", (unsigned long)block.seq, (long long)block.t_us, AUDIO_OUT_BLOCK);
    writeBase64((const uint8_t *)block.pcm, sizeof(block.pcm));
    host().print(">>\n");
  }
}

// ---------------------------------------------------------------- Camera task
// Captures at a fixed SV_TARGET_FPS on core 1, timestamps each frame at capture, and
// copies the JPEG into a PSRAM ring. The streamer sends from the ring, so link stalls
// delay frames instead of leaving gaps in the sampling. Frames are dropped (and counted)
// only if the ring is full.
struct FrameMsg {
  uint16_t slot;
  uint16_t len;
  uint32_t seq;
  int64_t  t_us;
};
QueueHandle_t frameQueue = nullptr;
uint8_t *frameRing = nullptr;
volatile uint32_t frameDrops = 0;

// Sums raw RGB565 pixels inside the host's skin boxes (before any compression).
// esp32-camera stores RGB565 high byte first: RRRRRGGG GGGBBBBB.
void sumRoi(camera_fb_t *fb, uint32_t seq, int64_t tCapture) {
  RoiBox boxes[4];
  int n;
  uint32_t stamp;
  portENTER_CRITICAL(&roiMux);
  n = roiCount;
  stamp = roiStampMs;
  for (int i = 0; i < n; i++) boxes[i] = roiBoxes[i];
  portEXIT_CRITICAL(&roiMux);
  if (n == 0 || millis() - stamp > ROI_TTL_MS || !rgbQueue) return;
  const int W = fb->width, H = fb->height;
  uint32_t sr = 0, sg = 0, sb = 0, cnt = 0, nclip = 0, ndark = 0;
  for (int i = 0; i < n; i++) {
    int x0 = max(0, (int)boxes[i].x), y0 = max(0, (int)boxes[i].y);
    int x1 = min(W, boxes[i].x + boxes[i].w), y1 = min(H, boxes[i].y + boxes[i].h);
    for (int y = y0; y < y1; y++) {
      const uint8_t *px = fb->buf + ((size_t)y * W + x0) * 2;
      for (int x = x0; x < x1; x++, px += 2) {
        uint8_t hb = px[0], lb = px[1];
        uint8_t r = hb & 0xF8, g = ((hb & 0x07) << 5) | ((lb & 0xE0) >> 3), b = (lb & 0x1F) << 3;
        // A saturated channel cannot show the pulse; near-black pixels are hair, shadow or noise.
        if (r >= 240 || g >= 244 || b >= 240) { nclip++; continue; }
        if (g < 12) { ndark++; continue; }
        sr += r;
        sg += g;
        sb += b;
        cnt++;
      }
    }
  }
  if (cnt + nclip + ndark == 0) return;
  RgbMsg m = {seq, tCapture, cnt, sr, sg, sb, nclip, ndark};
  if (xQueueSend(rgbQueue, &m, 0) != pdTRUE) rgbDrops++;
}

void sendRgb() {
  if (!rgbQueue) return;
  RgbMsg m;
  while (xQueueReceive(rgbQueue, &m, 0) == pdTRUE) {
    if (!hostAttached()) continue;
    host().printf("<<RGB:%lu,%lld,%lu,%lu,%lu,%lu,%lu,%lu>>\n", (unsigned long)m.seq, (long long)m.t_us,
                  (unsigned long)m.n, (unsigned long)m.sr, (unsigned long)m.sg, (unsigned long)m.sb,
                  (unsigned long)m.nclip, (unsigned long)m.ndark);
  }
}

void cameraTask(void *arg) {
  const int64_t periodUs = 1000000LL / SV_CAPTURE_FPS;
  int64_t next = esp_timer_get_time();
  uint16_t slot = 0;
  uint32_t seq = 0;
  for (;;) {
    int64_t now = esp_timer_get_time();
    if (now < next) {
      vTaskDelay(pdMS_TO_TICKS((next - now) / 1000 + 1));
      continue;
    }
    next += periodUs;
    if (now - next > periodUs) next = now + periodUs;          // fell behind: resynchronize

    if (!camAutoLocked && millis() > AUTO_LOCK_AFTER_MS) lockCameraAutoControls();
    if (camAutoLocked && pendingExposure >= 0 && camPid == 0x2145) {
      int32_t e = pendingExposure;
      pendingExposure = -1;
      sensor_t *s = esp_camera_sensor_get();
      if (s) gc2145SetExposure(s, e);
    }

    camera_fb_t *fb = esp_camera_fb_get();
    int64_t tCapture = esp_timer_get_time();
    if (!fb) continue;
    uint32_t thisSeq = seq++;
    if (fb->format == PIXFORMAT_RGB565) sumRoi(fb, thisSeq, tCapture);
    if (thisSeq % JPEG_EVERY != 0) {                          // ROI sums only for this capture
      esp_camera_fb_return(fb);
      continue;
    }
    const uint8_t *jpg = fb->buf;
    size_t jpgLen = fb->len;
    uint8_t *encoded = nullptr;
    if (fb->format != PIXFORMAT_JPEG) {
      if (!frame2jpg(fb, SW_JPEG_QUALITY, &encoded, &jpgLen)) jpgLen = 0;
      jpg = encoded;
    }
    if (jpg && jpgLen > 0 && jpgLen <= FRAME_SLOT_BYTES) {
      memcpy(frameRing + (size_t)slot * FRAME_SLOT_BYTES, jpg, jpgLen);
      FrameMsg m = {slot, (uint16_t)jpgLen, thisSeq, tCapture};
      if (xQueueSend(frameQueue, &m, 0) == pdTRUE) slot = (slot + 1) % frameSlots;
      else frameDrops++;                                       // ring full: host link too slow
    } else {
      frameDrops++;
    }
    if (encoded) free(encoded);
    esp_camera_fb_return(fb);
  }
}

// Sends one queued frame (waits up to 20 ms for one). Without a host, frames are discarded.
void sendFrame() {
  FrameMsg m;
  if (!frameQueue || xQueueReceive(frameQueue, &m, pdMS_TO_TICKS(20)) != pdTRUE) return;
  // Live view: if the link fell behind, skip to the newest frame instead of sending a backlog
  // (a backlog made the dashboard video seconds late). Skin-colour sums are not affected:
  // they are sent for every capture through their own queue.
  FrameMsg newer;
  while (xQueueReceive(frameQueue, &newer, 0) == pdTRUE) { m = newer; staleFrameDrops++; }
  if (!hostAttached()) return;
  const uint8_t *jpg = frameRing + (size_t)m.slot * FRAME_SLOT_BYTES;
  host().printf("<<FRAME_START:%lu,%lld,%u>>\n", (unsigned long)m.seq, (long long)m.t_us, (unsigned)m.len);
  writeBase64(jpg, m.len);
  host().print("\n<<FRAME_END>>\n");

  framesSent++;
  jpegBytesAccum += m.len;
  jpegFramesAccum++;
}

// 1 if the SSD1306 acknowledges on the I2C bus, 0 otherwise (reported in STAT for diagnosis).
int oledAck() {
  Wire.beginTransmission(0x3C);
  return Wire.endTransmission() == 0 ? 1 : 0;
}

void sendStats() {
  host().printf("<<INFO:%s,mic_ch=%s,rgb_drops=%lu,capture_fps=%d,jpeg_every=%d,reset=%d,uptime_s=%lu,"
                "heap_free=%u,heap_min=%u,heap_block=%u,psram_free=%u,stack_cam=%u,stack_audio=%u,stack_loop=%u,"
                "stale_drops=%lu,exp=%ld>>\n", camLockInfo.c_str(),
                micChannel < 0 ? "?" : (micChannel ? "R" : "L"), (unsigned long)rgbDrops, SV_CAPTURE_FPS, JPEG_EVERY,
                (int)esp_reset_reason(), (unsigned long)(millis() / 1000),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
                cameraTaskHandle ? (unsigned)uxTaskGetStackHighWaterMark(cameraTaskHandle) : 0,
                audioTaskHandle ? (unsigned)uxTaskGetStackHighWaterMark(audioTaskHandle) : 0,
                (unsigned)uxTaskGetStackHighWaterMark(NULL), (unsigned long)staleFrameDrops, (long)camExposure);
  uint32_t avgJpeg = jpegFramesAccum ? jpegBytesAccum / jpegFramesAccum : 0;
  host().printf("<<STAT:%d,%lu,%lu,%lu,%d,%d,%lu,%d,%d,%d,%lu>>\n",
                (int)lroundf(currentFps * 10.0f),
                (unsigned long)framesSent,
                (unsigned long)audioBlocksCaptured,
                (unsigned long)audioDrops,
                micReady ? 1 : 0,
                camReady ? 1 : 0,
                (unsigned long)avgJpeg,
                oledReady ? 1 : 0, oledAck(), camAutoLocked ? 1 : 0, (unsigned long)frameDrops);
  jpegBytesAccum = 0;
  jpegFramesAccum = 0;
}

// Parses <<VITALS:HR,RR,SpO2,CONF,STATUS>> (5 fields) or the legacy
// <<VITALS:HR,RR,SpO2,STATUS>> (4 fields).
void handleVitalsLine(const String &line) {
  if (!line.startsWith("<<VITALS:") || !line.endsWith(">>")) return;
  String p = line.substring(9, line.length() - 2);

  int idx[4];
  int count = 0;
  for (int i = 0; i < (int)p.length() && count < 4; i++) {
    if (p[i] == ',') idx[count++] = i;
  }
  if (count < 3) return;

  currentHR = p.substring(0, idx[0]).toInt();
  currentRR = p.substring(idx[0] + 1, idx[1]).toInt();
  currentSpO2 = p.substring(idx[1] + 1, idx[2]).toInt();
  String st;
  if (count == 4) {
    currentConf = p.substring(idx[2] + 1, idx[3]).toInt();
    st = p.substring(idx[3] + 1);
  } else {
    currentConf = 0;
    st = p.substring(idx[2] + 1);
  }

  if (st == "STABLE") currentStatusStr = "PATIENT: STABLE";
  else if (st == "CALIBRATING" || st == "CALIB") currentStatusStr = "OBSERVING / CALIB";
  else currentStatusStr = "PATIENT: SEARCH";
}

// Parses <<ROI:x,y,w,h;x,y,w,h;...>> (up to 4 boxes) or <<ROI:none>>.
void handleRoiLine(const String &line) {
  if (!line.startsWith("<<ROI:") || !line.endsWith(">>")) return;
  String p = line.substring(6, line.length() - 2);
  RoiBox boxes[4];
  int n = 0;
  int start = 0;
  while (n < 4 && start < (int)p.length() && p != "none") {
    int end = p.indexOf(';', start);
    if (end < 0) end = p.length();
    String b = p.substring(start, end);
    int v[4], k = 0, s0 = 0;
    for (int i = 0; i <= (int)b.length() && k < 4; i++) {
      if (i == (int)b.length() || b[i] == ',') { v[k++] = b.substring(s0, i).toInt(); s0 = i + 1; }
    }
    if (k == 4 && v[2] > 0 && v[3] > 0) boxes[n++] = {(int16_t)v[0], (int16_t)v[1], (int16_t)v[2], (int16_t)v[3]};
    start = end + 1;
  }
  portENTER_CRITICAL(&roiMux);
  for (int i = 0; i < n; i++) roiBoxes[i] = boxes[i];
  roiCount = n;
  roiStampMs = millis();
  portEXIT_CRITICAL(&roiMux);
}

void pollHostCommands() {
  while (host().available() > 0) {
    char c = (char)host().read();
    if (c == '\n' || c == '\r') {
      if (serialRxBuf.startsWith("<<ROI:")) handleRoiLine(serialRxBuf);
      else if (serialRxBuf.startsWith("<<CAM:EXP,") && serialRxBuf.endsWith(">>")) {
        long e = serialRxBuf.substring(10, serialRxBuf.length() - 2).toInt();
        if (e > 0) pendingExposure = e;
      }
      else if (serialRxBuf.length() > 0) handleVitalsLine(serialRxBuf);
      serialRxBuf = "";
    } else if (serialRxBuf.length() < 120) {
      serialRxBuf += c;
    }
  }
}

// ---------------------------------------------------------------- OLED HUD
void renderOled() {
  display.clearDisplay();
  display.setTextWrap(false);
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  display.setCursor(4, 1);
  display.println("SONICVITALS NODE");
  display.drawFastHLine(0, 11, 128, SSD1306_WHITE);

  display.setCursor(2, 15);
  if (currentHR > 0) display.printf("HR: %3d BPM  RR: %2d", currentHR, currentRR);
  else               display.print("HR: --- BPM  RR: --");

  display.setCursor(2, 26);
  char spo2Buf[6];
  char confBuf[6];
  if (currentSpO2 > 0) snprintf(spo2Buf, sizeof(spo2Buf), "%d%%", currentSpO2);
  else                 snprintf(spo2Buf, sizeof(spo2Buf), "--");
  if (currentConf > 0) snprintf(confBuf, sizeof(confBuf), "%d%%", currentConf);
  else                 snprintf(confBuf, sizeof(confBuf), "--");
  display.printf("SpO2:%-4s  Q:%s", spo2Buf, confBuf);

  display.setCursor(2, 37);
  const char *micStr = !SV_ENABLE_MIC ? "OFF" : (!micReady ? "ERR" : (audioRms > 400 ? "ACT" : "OK"));
  display.printf("Cam:%4.1ffps Mic:%s", currentFps, micStr);

  display.drawFastHLine(0, 47, 128, SSD1306_WHITE);
  display.setCursor(2, 52);
#ifdef SV_TRANSPORT_WIFI
  if (!hostAttached()) display.print(wifiLabel);     // shows where the host should connect
  else display.print(currentStatusStr);
#else
  display.print(currentStatusStr);
#endif
  display.display();
}

// ---------------------------------------------------------------- Wi-Fi
#ifdef SV_TRANSPORT_WIFI
void showBootLine(const String &line) {
  if (!oledReady) return;
  display.fillRect(0, 52, 128, 12, SSD1306_BLACK);
  display.setCursor(2, 52);
  display.print(line);
  display.display();
}

// Human-readable reason for the OLED when the station link is down.
String wifiStatusText(wl_status_t st) {
  switch (st) {
    case WL_NO_SSID_AVAIL: return "SSID not found/5GHz";
    case WL_CONNECT_FAILED: return "WiFi: wrong password";
    case WL_DISCONNECTED: return "WiFi: joining...";
    default: return "WiFi: status " + String((int)st);
  }
}

void updateWifiLabel();

void initWiFi() {
  WiFi.persistent(false);
  if (strlen(SV_WIFI_SSID) > 0) {
    // AP + station: the node is always reachable on its own hotspot, and joins the
    // configured network whenever it becomes available (the driver keeps retrying).
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(SV_AP_SSID, SV_AP_PASSWORD);
    WiFi.setAutoReconnect(true);
    WiFi.begin(SV_WIFI_SSID, SV_WIFI_PASSWORD);
    showBootLine("WiFi: joining...");
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) delay(250);
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(SV_AP_SSID, SV_AP_PASSWORD);
  }
  WiFi.setSleep(false);                       // modem sleep adds latency and jitter
  if (MDNS.begin("sonicvitals")) MDNS.addService("sonicvitals", "tcp", SV_TCP_PORT);
  tcpServer.begin();
  tcpServer.setNoDelay(true);
  updateWifiLabel();
  showBootLine(wifiLabel);
}

// OLED label: station IP when joined, otherwise the failure reason (or the AP address).
void updateWifiLabel() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiLabel = "IP " + WiFi.localIP().toString();
  } else if (strlen(SV_WIFI_SSID) > 0) {
    static unsigned long lastRetry = 0;
    wifiLabel = wifiStatusText(WiFi.status());
    if (WiFi.status() != WL_DISCONNECTED && millis() - lastRetry > 10000) {
      lastRetry = millis();
      WiFi.begin(SV_WIFI_SSID, SV_WIFI_PASSWORD);   // retry after a hard failure
    }
  } else {
    wifiLabel = "AP " + WiFi.softAPIP().toString();
  }
}

// Accept a host connection (one at a time; a new host replaces the old one).
void serviceWiFi() {
  static unsigned long lastLabel = 0;
  if (millis() - lastLabel > 1000) {
    lastLabel = millis();
    updateWifiLabel();
  }
  WiFiClient incoming = tcpServer.available();
  if (incoming) {
    if (tcpClient) tcpClient.stop();
    tcpClient = incoming;
    tcpClient.setNoDelay(true);
    sendHello();
  }
}
#endif

// ---------------------------------------------------------------- setup/loop
void setup() {
#if defined(SV_TRANSPORT_UART)
  Serial.setTxBufferSize(16384);
  Serial.begin(SV_UART_BAUD);
#elif defined(SV_TRANSPORT_WIFI)
  // UART0 is not started: GPIO43/44 belong to the microphone in this build.
#else
  Serial.setTxBufferSize(16384);
  Serial.setTxTimeoutMs(50);     // do not stall for long when no host is reading
  Serial.begin();
#endif
  delay(400);

  initOLED();
  initCamera();
  if (camReady) {
    frameSlots = FRAME_SLOTS;
    frameRing = psramFound() ? (uint8_t *)ps_malloc((size_t)frameSlots * FRAME_SLOT_BYTES) : nullptr;
    if (!frameRing) {                                    // no PSRAM: smaller ring in internal RAM
      frameSlots = 6;
      frameRing = (uint8_t *)malloc((size_t)frameSlots * FRAME_SLOT_BYTES);
    }
    frameQueue = xQueueCreate(frameSlots - 2, sizeof(FrameMsg));
    rgbQueue = xQueueCreate(RGB_QUEUE_DEPTH, sizeof(RgbMsg));
    if (frameRing && frameQueue) xTaskCreatePinnedToCore(cameraTask, "camera", CAMERA_TASK_STACK, NULL, 4, &cameraTaskHandle, 1);
    else camReady = false;
  }

#if SV_ENABLE_MIC
  designDecimationFilter();
  audioQueue = xQueueCreate(AUDIO_QUEUE_DEPTH, sizeof(AudioBlock));
  initI2S();
  if (micReady && audioQueue) {
    xTaskCreatePinnedToCore(audioTask, "audio", 6144, NULL, 5, &audioTaskHandle, 0);
  }
#endif

#ifdef SV_TRANSPORT_WIFI
  initWiFi();
#endif
  sendHello();
}

unsigned long lastOledMs = 0;
unsigned long lastStatMs = 0;
unsigned long lastHelloMs = 0;
uint32_t framesAtLastStat = 0;

void loop() {
#ifdef SV_TRANSPORT_WIFI
  serviceWiFi();
#endif
  pollHostCommands();

  sendRgb();                       // tiny lines; sent first so link stalls never delay them behind video
  if (camReady) sendFrame();
  else delay(5);
  sendRgb();

  // Flush every audio block captured while the frame was encoded and sent.
  sendAudioBlocks();

  if (exposureApplied != exposureReported && hostAttached()) {
    exposureReported = exposureApplied;
    host().printf("<<CAMEXP:%ld,%lu>>\n", (long)camExposure, (unsigned long)exposureApplied);
  }

  unsigned long now = millis();
  if (now - lastStatMs >= 1000) {
    float dt = (now - lastStatMs) / 1000.0f;
    currentFps = (framesSent - framesAtLastStat) / dt;
    framesAtLastStat = framesSent;
    lastStatMs = now;
    sendStats();
  }

  if (now - lastHelloMs >= 5000) {
    lastHelloMs = now;
    sendHello();
  }

  // Re-detect the display every 2 s so a loose or re-seated OLED recovers without a reboot.
  static unsigned long lastOledCheckMs = 0;
  if (now - lastOledCheckMs >= 2000) {
    lastOledCheckMs = now;
    bool present = oledAck() == 1;
    if (present && !oledPresent) {
      display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
      oledReady = true;
    }
    oledPresent = present;
  }

  if (oledReady && oledPresent && now - lastOledMs >= 200) {
    lastOledMs = now;
    renderOled();
  }

}
