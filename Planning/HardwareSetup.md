# SonicVitals: Hardware Architecture and Setup Guide

This document defines the complete hardware architecture, Bill of Materials (BOM), pin-to-pin wiring diagram, and signal integrity guidelines for the **SonicVitals embedded sensing node**, based on the generic **ESP32-S3 WROOM 1U CAM** module.

To satisfy the requirements of a research-grade platform, this setup is designed for **simultaneous, synchronized data acquisition** from a contactless visual sensor (remote photoplethysmography via the OV2640 camera) and an acoustic sensor (respiratory sound tracking via the INMP441 I2S microphone), while outputting status metrics to an SSD1306 OLED display.

---

## 1. Bill of Materials (BOM)

For high-speed image processing, the ESP32-S3 module **must** have external PSRAM. The reference board selected is the **ESP32-S3 WROOM 1U CAM**. This board features the ESP32-S3 dual-core processor, an OV2640 camera, and 8MB of PSRAM.

| Component | Description | Qty | Indian Source & Availability | Approx. Cost (INR) |
| :--- | :--- | :--- | :--- | :--- |
| **Microcontroller Board** | ESP32-S3 WROOM CAM Module | 1 | Robu.in, QuartzComponents, Amazon | ₹800 – ₹1,200 |
| **Acoustic Sensor** | INMP441 MEMS Digital Microphone Breakout Board (I2S) | 1 | Robu.in, QuartzComponents | ₹140 – ₹180 |
| **Status Display** | SSD1306 0.96" I2C OLED Display (128x64 pixels, 4-pin I2C module) | 1 | Robu.in, QuartzComponents, MakerBazar | ₹120 – ₹150 |
| **Power Source** | 5V USB Power Bank (Portable Charger) | 1 | Any local electronics store | ₹500 - ₹800 |
| **Prototyping Wires** | Jumper Wires and small Breadboard/Perfboard | 1 set | MakerBazar, QuartzComponents, local shops | ₹50 – ₹80 |
| **Total Estimated Cost** | **Fully portable, synchronized physiological sensing node** | **1** | **All components locally stocked in India (2-4 days shipping)** | **~₹1,610 – ₹2,410** |

---

## 2. Pinout Allocation Strategy

> [!WARNING]
> **Severe GPIO Limitation on this Specific Carrier Board:**
> The carrier board you purchased breaks out only 16 pins (many of which are **Not Connected / NC**). The only usable GPIOs available are **SDA, SCL, RX, TX, and BOOT**. Because our project requires 5 free pins, we must use all of them.

- **I2C OLED Display**: Connects to the dedicated **SDA and SCL** ports.
- **I2S Microphone (INMP441)**: Connects to **RX, TX, and BOOT**.

### Important Caveats
1. **Loss of Hardware Serial**: Because we are using RX and TX for the microphone, you cannot use a hardware UART FTDI programmer. You **must** flash the board via its native USB port (USB CDC).
2. **Boot Pin (GPIO 0)**: The microphone's `SD` pin is connected to `BOOT`. If the microphone pulls this pin low when the ESP32 powers on, the ESP32 will get stuck in "Download Mode" and fail to boot. If this happens, **disconnect the microphone's SD wire when powering on or flashing**, then plug it back in.

### Complete System GPIO Assignment Map

```
                     +---------------------------------------+
                     |      ESP32-S3 WROOM 1U CAM            |
                     +---------------------------------------+
                                 |
        +------------------------+-----------------------+
        |                        |                       |
 [I2S Audio Input]       [I2C OLED Display]          [Power]
  - SCK -> TX (GPIO 43)   - SDA -> SDA Port (GPIO 47) - 5V In via USB
  - WS  -> RX (GPIO 44)   - SCL -> SCL Port (GPIO 48)
  - SD  -> BOOT (GPIO 0)
```

---

## 3. Pin-to-Pin Wiring Diagrams

### A. External Microphone (INMP441)
For acoustic fidelity and proper distance placement, an external INMP441 I2S microphone is connected to the header pins via extension wires (allowing it to be clipped to the collar).

| INMP441 Breakout Pin | ESP32-S3 Board Pin | Signal Name | Description |
| :--- | :--- | :--- | :--- |
| **VDD** | **3.3V** | Power | 3.3V power rail |
| **GND** | **GND** | Ground | Common system ground |
| **SCK** | **TX (GPIO 43)** | I2S_BCLK | Bit Clock |
| **WS** | **RX (GPIO 44)** | I2S_LRCK | Word Select |
| **SD** | **BOOT (GPIO 0)** | I2S_DIN | Serial Data Out |
| **L/R** | **GND** | Channel Sel | Left audio channel |

### B. Display Connection (SSD1306 OLED - I2C Protocol)
Connect the OLED display to the dedicated SDA and SCL header ports.

| SSD1306 OLED Pin | ESP32-S3 Board Pin | Signal Name | Description |
| :--- | :--- | :--- | :--- |
| **VDD** | **3.3V or 5V** | Power | 3.3V or 5V power rail |
| **GND** | **GND** | Ground | Common system ground |
| **SDA** | **SDA** | SDA (I2C) | Serial Data Line |
| **SCK** | **SCL** | SCL (I2C) | Serial Clock Line |

---

### C. Power Path (Battery)
- **Power method:** Plug a standard 5V USB Power Bank into the board's USB port (or connect 5V/GND from a regulated source) to make the system portable.

---

## 4. Complete Schematic & Interconnection Diagram

Below is the simplified visual wiring schematic representing all external connections.

```
                  +-------------------------------------------------+
                  |          ESP32-S3 WROOM 1U CAM Board            |
                  |                                                 |
                  |  [3.3V] [GND]   [TX]  [RX] [BOOT]   [SDA] [SCL] |
                  +----+----+--------+-----+------+-------+-----+---+
                       |    |        |     |      |       |     |
                       |    |        |     |      |       |     |
                       |    |        |     |      |       |     |
                       |    |        +-----+------+       |     |
                       |    |        |     |      |       |     |
                       |    +---+----+-----+------+----+  |     |
                       +--+ |   |    |     |      |    |  |     |
                          | |   |    |     |      |    |  |     |
                          | |   |    v     v      v    |  |     |
                          | |   |  (SCK) (WS)   (SD)   |  |     |
                          | |   +--(GND)               |  |     |
                          | |   +--(L/R)               |  |     |
                          | +------(VDD)               |  |     |
                          |       +---------------+    |  |     |
                          |       | INMP441 Mic   |    |  |     |
                          |       +---------------+    |  |     |
                          |                            |  |     |
                          |                            |  v     v
                          |                            | (SDA) (SCL)
                          +----------------------------+-(VDD)
                          +----------------------------+-(GND)
                                                       |
                                                   +---------+
                                                   | SSD1306 |
                                                   +---------+
```

## 5. Signal Integrity Guidelines
1. **Clock Lines (I2S and I2C)**: Keep the SCK, WS, SDA, and SCL wires as short as possible (under 15cm if untwisted). Longer lines increase capacitance and degrade the high-frequency clock edges.
2. **Microphone Placement**: The INMP441 must be placed mechanically away from the ESP32-S3 antenna to prevent WiFi packet bursts from inducing noise on the sensitive audio lines.
3. **Power Stability**: The ESP32-S3 draws heavy current pulses when transmitting WiFi frames and initializing the camera. Ensure the USB power bank can supply at least 2.0A.

---

## 6. Camera Module Optical & Acquisition Setup for Medical Image Processing

For clinical-grade contactless physiological sensing and downstream **MATLAB medical image processing**, the OV2640 camera acquisition pipeline must adhere to specific biomedical optical constraints:

### A. Optical Geometry & Patient Positioning
*   **Target Distance**: $50\text{ cm} - 100\text{ cm}$ directly facing the subject's face at eye level ($\pm 15^\circ$ angle of incidence).
*   **Field of View (FOV)**: The OV2640 sensor features a $66^\circ - 75^\circ$ diagonal FOV. At $60\text{ cm}$, the patient's head occupies approximately $40 - 60\%$ of the frame height, providing optimal pixel density across the forehead and cheek capillary beds.
*   **Focal Adjustment**: The OV2640 M12 lens barrel should be manually focused to provide crisp facial boundary edges without blurring microvascular skin regions.

### B. Ambient Illumination & Color Temperature
*   **Minimum Illuminance**: $250 - 500\text{ lux}$ (standard clinical examination room lighting). Low light conditions increase sensor gain and high-ISO noise, which destroys the subtle micro-pulsatile green reflectance signal ($\approx 0.5 - 2\%$ amplitude modulation).
*   **Light Source**: Diffuse white LED or indirect daylight ($4000\text{K} - 5500\text{K}$ color temperature). Avoid $50\text{Hz} / 60\text{Hz}$ flickering AC fluorescent tubes directly above the subject, as ballast ripple introduces periodic artifact spikes that mimic cardiac frequencies.
*   **Specular Reflection Prevention**: Position illumination at $45^\circ$ angles relative to the camera axis to prevent glare on the oily T-zone of the forehead.

### C. Resolution vs. Frame Rate vs. Compression Optimization
During empirical hardware characterization over USB serial and Wi-Fi streaming:
*   **Selected Resolution**: **HQVGA ($240 \times 160$)** or **QVGA ($320 \times 240$)**.
*   **Frame Rate**: Fixed at **$15\text{ FPS}$** (providing a Nyquist limit of $7.5\text{ Hz}$, well above the $3.0\text{ Hz} / 180\text{ BPM}$ upper physiological cardiac cutoff).
*   **JPEG Quality Factor**: Maintained at **$Q = 60$** or higher. Excessively aggressive compression ($Q < 30$) introduces blocking artifacts that attenuate spatial color variance across skin patches.
*   **MATLAB Processing Ingestion**: Processed offline via uncompressed frame exports or streamed directly into MATLAB via `ipcam` / `VideoReader` using [`matlab/medical_image_processing.m`](file:///Users/pratikkumar/Desktop/SEM5%20Projects/SonicVitals/matlab/medical_image_processing.m).

