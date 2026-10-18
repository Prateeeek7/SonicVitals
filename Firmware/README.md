# SonicVitals ESP32-S3 Firmware compilation & Flashing Guide

This directory contains the production-grade, multitasking firmware for the **SonicVitals** edge node. Follow the instructions below to compile and flash the firmware using the Arduino IDE.

## 1. Hardware Pin Mappings
The firmware is configured for the **ESP32-S3 WROOM 1U CAM** 16-pin development board and is wired as follows:

* **OV2640 Camera**: Internal board-to-board connector.
* **External INMP441 Digital Microphone**:
  * **SCK / BCLK** -> `TX (GPIO 43)`
  * **WS / LRC** -> `RX (GPIO 44)`
  * **SD / DOUT** -> `BOOT (GPIO 0)`
  * **L/R Pin** -> `GND` (Selects Left Channel)
  * **VDD** -> `3.3V`
  * **GND** -> `GND`
* **SSD1306 OLED Display (I2C)**:
  * **SDA** -> `SDA Port`
  * **SCK** -> `SCL Port`
  * **VDD** -> `3.3V`
  * **GND** -> `GND`

> [!WARNING]
> Because you are using the TX and RX pins for the microphone, you **cannot** use a hardware serial FTDI programmer on those pins. You must program the board using the native USB CDC interface over its USB port. Additionally, if the microphone pulls the BOOT pin low during power-up, the ESP32 will fail to start. If this happens, simply unplug the microphone's SD wire when powering on or flashing the board.

---

## 2. Software & IDE Configurations
To compile the firmware without compilation errors, follow these steps:

### A. Arduino IDE Setup
1. Download and install **Arduino IDE** (version 2.x recommended).
2. Go to **Settings/Preferences** and add the official ESP32 Board Manager URL:
   ```text
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. Go to **Tools > Board > Boards Manager**, search for `esp32` by **Espressif Systems**, and install version **`2.0.17`**.
   > [!IMPORTANT]
   > Do **NOT** install version `3.0.x` or higher, as the I2S drivers undergo breaking API changes in version 3.x. Version `2.0.17` is recommended for compiling the legacy I2S configuration used in this firmware.

### B. Required Libraries
Install the following libraries using the **Library Manager** (`Ctrl+Shift+I` / `Cmd+Shift+I`):
1. **Adafruit SSD1306** (by Adafruit) - OLED Display Driver.
2. **Adafruit GFX Library** (by Adafruit) - Core graphics rendering suite.
3. **Adafruit BusIO** (by Adafruit) - Core dependency.

### C. Board Upload Configurations
Select **Tools** in the top menu and configure the parameters exactly as follows:
* **Board**: `"ESP32S3 Dev Module"` (Since it's a generic WROOM board)
* **USB CDC On Boot**: `"Enabled"` (Allows serial printing over the native Type-C port)
* **CPU Frequency**: `"240MHz (WiFi/BT)"`
* **Core Debug Level**: `"None"` (or `"Info"` for debugging)
* **Flash Mode**: `"QIO 80MHz"`
* **PSRAM**: `"OPI PSRAM"` (Required for double-buffered DVP frame capture buffers)
* **Upload Speed**: `"921600"`

---

## 3. Configuration Customization
Before flashing, modify the SSID, password, and host IP configurations in `Firmware.ino` (lines 15–18) to match your local research environment:

```cpp
const char* ssid = "YOUR_WIFI_SSID";          // Local Wi-Fi Router SSID
const char* password = "YOUR_WIFI_PASSWORD";  // Local Wi-Fi Password
const char* host_ip = "192.168.1.100";        // Your host PC running the python backend
const int udp_port = 50005;                   // Server UDP Socket Port
```

---

## 4. Compile and Upload
1. Connect your ESP32-S3 board to your PC via a USB cable. Ensure it is connected to the native USB port if your carrier board has two ports.
2. Under **Tools > Port**, select the COM/serial port matching your module.
3. Click the **Verify** button (check icon) to compile.
4. Click the **Upload** button (arrow icon) to write the compiled bin file to the chip.
5. Open the **Serial Monitor** at **`115200` baud** to verify that the initialization prints complete and a Wi-Fi connection indicator status appears on the SSD1306 OLED display.
