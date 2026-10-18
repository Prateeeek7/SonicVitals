<!-- Benchmark run in Google Colab (T4 GPU), 2026-10-15. UBFC-rPPG DATASET_2, first 10 subjects (subject1, 3, 4, 5, 8, 9, 10, 11, 12, 13). Deep models: rPPG-Toolbox pretrained weights, cross-dataset. Videos decoded with the ffmpeg CLI (OpenCV 4.14's reader crashed on the uncompressed AVIs). -->

# UBFC-rPPG (10 recordings), 2026-10-15

## 30 s windows, step 10 s

| method | coverage | MAE | RMSE | MAPE | r | within5 | ms_per_30s_window |
|---|---|---|---|---|---|---|---|
| GREEN | 100% | 22.04 | 34.21 | 19.5 | 0.07 | 47% | 2.4 |
| CHROM | 100% | 2.40 | 6.48 | 2.1 | 0.93 | 86% | 19.6 |
| POS | 100% | 2.08 | 5.41 | 1.9 | 0.95 | 86% | 78.6 |
| GREEN (SV skin boxes) | 100% | 19.32 | 31.92 | 16.8 | 0.10 | 58% | 2.3 |
| CHROM (SV skin boxes) | 100% | 2.50 | 6.30 | 2.3 | 0.93 | 86% | 19.4 |
| POS (SV skin boxes) | 100% | 1.66 | 4.56 | 1.5 | 0.96 | 89% | 76.1 |
| SonicVitals (raw) | 100% | 2.30 | 4.92 | 2.2 | 0.96 | 89% | 71.8 |
| SonicVitals (gated) | 81% | 1.56 | 2.73 | 1.5 | 0.99 | 93% | 71.8 |
| SonicVitals (display) | 86% | 2.45 | 3.30 | 2.3 | 0.98 | 87% | 71.8 |
| TS-CAN [PURE->UBFC-rPPG] | 100% | 1.68 | 4.95 | 1.5 | 0.96 | 89% | 278.5 |
| PhysNet [PURE->UBFC-rPPG] | 100% | 1.90 | 5.00 | 1.9 | 0.95 | 86% | 159.9 |
| EfficientPhys [PURE->UBFC-rPPG] | 100% | 3.88 | 9.09 | 3.6 | 0.88 | 81% | 141.9 |
| TS-CAN [SCAMPS->UBFC-rPPG] | 100% | 2.61 | 5.01 | 2.5 | 0.96 | 78% | 255.6 |
| PhysNet [SCAMPS->UBFC-rPPG] | 100% | 5.30 | 11.27 | 5.1 | 0.83 | 75% | 155.5 |
| EfficientPhys [SCAMPS->UBFC-rPPG] | 100% | 24.34 | 34.91 | 21.5 | -0.01 | 36% | 141.6 |

## whole video

| method | coverage | MAE | RMSE | MAPE | r | within5 | ms_per_30s_window |
|---|---|---|---|---|---|---|---|
| GREEN | 100% | 27.22 | 40.93 | 24.7 | 0.06 | 50% | 2.4 |
| CHROM | 100% | 3.08 | 4.77 | 2.8 | 0.97 | 70% | 19.6 |
| POS | 100% | 1.78 | 4.32 | 1.6 | 0.97 | 90% | 78.6 |
| GREEN (SV skin boxes) | 100% | 28.06 | 37.53 | 24.8 | -0.02 | 40% | 2.3 |
| CHROM (SV skin boxes) | 100% | 1.30 | 3.08 | 1.1 | 0.98 | 90% | 19.4 |
| POS (SV skin boxes) | 100% | 1.22 | 3.06 | 1.1 | 0.98 | 90% | 76.1 |
| SonicVitals (raw) | 100% | 0.86 | 1.06 | 0.9 | 1.00 | 100% | 71.8 |
| SonicVitals (gated) | 70% | 0.84 | 1.04 | 0.9 | 1.00 | 100% | 71.8 |
| TS-CAN [PURE->UBFC-rPPG] | 100% | 0.56 | 1.07 | 0.6 | 1.00 | 100% | 278.5 |
| PhysNet [PURE->UBFC-rPPG] | 100% | 0.60 | 1.12 | 0.7 | 1.00 | 100% | 159.9 |
| EfficientPhys [PURE->UBFC-rPPG] | 100% | 4.15 | 8.55 | 3.8 | 0.88 | 80% | 141.9 |
| TS-CAN [SCAMPS->UBFC-rPPG] | 100% | 5.27 | 7.71 | 4.6 | 0.93 | 60% | 255.6 |
| PhysNet [SCAMPS->UBFC-rPPG] | 100% | 5.52 | 10.22 | 5.2 | 0.83 | 70% | 155.5 |
| EfficientPhys [SCAMPS->UBFC-rPPG] | 100% | 22.94 | 33.23 | 20.0 | 0.00 | 40% | 141.6 |

Coverage = share of windows with an HR output (SonicVitals gated/display withhold low-quality windows; errors are over covered windows only). Latency: median processing time per 30 s window (deep models: forward pass only, per 30 s of video).
