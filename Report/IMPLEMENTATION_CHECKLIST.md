# SonicVitals: status before submission

Red **[TODO]** / **TBD** markers in the PDF show what is still open. Set `\showtodosfalse`
only when every item below is ticked and every TBD is a measured value.

## A. Code (done, October 2026)

- [x] Firmware v2 (`Firmware/Firmware.ino`): native USB-CDC host link (frees GPIO43/44 for the mic),
      FreeRTOS audio task on core 0 with an 8×256 DMA buffer and a 1 s queue, 16-bit PCM streaming,
      µs timestamps and sequence numbers on every packet, STAT/HELLO records, AEC/AGC/AWB locked
      after 3 s, real confidence on the OLED. Fallback build `esp32s3_uart` (mic off). Both build cleanly.
- [x] Host uses frame timestamps (resampled to 15 Hz); only gated frames enter the buffer.
- [x] Welch: 256-sample segments, nfft 4096, parabolic peak; de Haan SNR; spectral-concentration quality.
- [x] RR quality gate (no RR is reported from noise).
- [x] Placeholders removed: the SQI-derived "HRV", the "stress index", fallback constants (72/15.5/85), the SpO₂ clamp.
- [x] Acoustic PCG branch: 25–400 Hz → 1 kHz → Shannon-envelope autocorrelation HR; S1 on the Hilbert envelope → RMSSD.
- [x] Fusion with Δ = 8 BPM agreement gate.
- [x] SpO₂: band-passed AC, no clamp, value shown only if `backend/spo2_calibration.json` exists.
- [x] Session recorder (raw frames/audio/estimates) and `analysis/evaluate.py` (dev/test split, repeated-measures
      Bland–Altman, AAMI EC13, ablation, bench stats, LaTeX rows).
- [x] Frontend: INMP441 audio replaces the browser mic; real time axes and units; measured fps; real device
      table; no fake reports, Wi-Fi/battery/UDP values, or clinical claims; Bland–Altman is optical vs acoustic.
- [x] 22 automated tests + node simulator; whole chain verified with the simulator.

## B. Hardware

- [x] Flashed over the CH340 port (`/dev/cu.usbserial-110`). Verified: the ORIGINAL firmware sends no frames once
      the mic is enabled (GPIO43 carries the I2S clock). Dashboards captured with the mic on therefore came from
      the webcam fallback; the old code did not log the source, so individual screenshots can't be attributed.
- [x] `esp32s3_uart` build (mic off) verified on the board: 7.5 fps node / 7.4 fps host, jitter 15.5 ms,
      ~1 % frames rejected at **1 Mbaud** (921600 garbled, 2 Mbaud ~30 % corrupt on this CH340). Table VIII filled.
- [x] Single-port board → `esp32s3_wifi` build (default): camera + mic + OLED together over Wi-Fi via the
      phone hotspot, audio decimated to 4 kHz on the node. Measured: 6.0 fps at the host, 0 corrupt frames,
      0 of 312 audio blocks lost in 20 s. Table VIII updated. Laptop and node must be on the same 2.4 GHz network.
- [ ] If audio is silent: check L/R on GND; try `I2S_CHANNEL_FMT_ONLY_RIGHT`.
- [ ] Longer bench runs (mean ± SD) and Table III (USB power meter).

## C. Study and paperwork

- [ ] Ethics approval number, consent (including consent to publish face images).
- [ ] Reference devices: chest-strap ECG with R–R export, finger oximeter, metronome. Name the models.
- [ ] Record C1–C5 with `SONICVITALS_WEBCAM=0`; pick 2 development participants.
- [ ] Run `analysis/evaluate.py`; paste `tables.tex` rows into Tables VI and VII; add `bland_altman.pdf`.
- [ ] Re-tune the RR gate, Δ and the mic noise floor on the development participants only.
- [ ] Fig. 6 (PCG + ECG), re-capture Figs. 4, 5 and 7 with the new UI from the ESP32 source.
- [ ] Colorimetry repeatability table (CV over repeated snapshots).
- [ ] Abstract and conclusion numbers; target journal, dates, funding, acknowledgment, repository URL.

## D. Removed from the original draft (do not reintroduce)

N = 120 study and every number in its tables; ablation, Keysight power, FLIR thermal, IEC 60601-1 claims;
Symlet-4 DWT; the wrong pin map; 3D organ models; clinical diagnosis claims; about 14 unverifiable or
mis-attributed references. The original is in `archive/SonicVitals_Journal_Paper_ORIGINAL.*`.
