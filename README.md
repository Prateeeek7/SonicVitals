# SonicVitals

ESP32-S3 node (OV2640 camera + INMP441 chest microphone + SSD1306 OLED) streaming to a
Python host that estimates heart rate (camera rPPG + acoustic PCG, fused), respiration
rate and RMSSD, with a browser workstation. Research prototype — not a medical device.

## 1. Flash the node
Pick the build that matches the board:

| Board | Build | Data link | Mic |
|---|---|---|---|
| Single USB-C (CH340 bridge), e.g. this prototype | `esp32s3_wifi` (default) | Wi-Fi, TCP port 3333 | yes |
| Has a native USB connector | `esp32s3` | native USB-CDC | yes |
| Single USB-C, no Wi-Fi wanted | `esp32s3_uart` | UART 1 Mbaud | no (pin conflict) |

```
cd Firmware
pio run -t upload                      # esp32s3_wifi over /dev/cu.usbserial-110
```
Stop the host server (or run it with `SONICVITALS_LINK=wifi`) while flashing: a server probing the
serial port can reset the chip in the middle of an upload ("The chip stopped responding").
Wi-Fi: copy `wifi_secrets.example.h` to `wifi_secrets.h` and fill in your 2.4 GHz network to join it
(the host finds the node as `sonicvitals.local`). Without that file the node starts its own WPA2 hotspot
(name and password in `wifi_secrets.example.h`); join it from the laptop and the host finds the node at
192.168.4.1. The OLED bottom line shows `IP ...` or `AP ...` until the host connects.

## 2. Run host + UI
```
./start.sh                                  # http://localhost:3000, node over Wi-Fi, hardware input only
SONICVITALS_WEBCAM=1 ./start.sh             # development only: fall back to the laptop webcam
./start.sh                                  # esp32s3_uart build uses 1 Mbaud (the default)
```
Check the **Device Management** tab: measured frame rate must be >= 5 fps (ideally 10-15),
frames rejected < 1 %, audio blocks lost < 1 %, video source = ESP32-S3.

## 3. Record a session
Experiments tab -> participant ID, condition (C1-C5), notes -> Start. Raw data goes to
`data/sessions/<timestamp>_<participant>/` (frames.csv, audio.wav, audio_blocks.csv,
estimates.csv, meta.json). Add the reference data to the same folder:
- `reference.csv`: `host_time` (Unix s, same computer clock) + `hr_ref`, `rr_ref`, `spo2_ref`
- `rpeaks.csv` (optional): `host_time` of each ECG R peak, for reference RMSSD

## 4. Evaluate (fills paper Tables VI-VIII)
```
python3 analysis/evaluate.py data/sessions/* --out analysis/results --dev-participants P01,P02 --write-calibration
```
Development participants are used only for thresholds and the SpO2 calibration and are
excluded from all reported metrics. Output: `tables.tex`, CSVs, `bland_altman.pdf`.

## Tests
```
python3 -m pytest backend/tests -q
```
The unit tests use synthetic signals to check the DSP; the running system only ever shows
data measured by the node.

`Server/` is the older PySide prototype and is not used by `start.sh`. Original pre-fix sources are in `archive/pre_fix/`.

The earlier simulator and demo-values tools were removed from the working tree; they are kept
for reference only in `archive/simulation/`.
