#!/usr/bin/env bash
# Builds benchmark/SonicVitals_benchmark.zip for the Colab notebook: the SonicVitals DSP and
# camera engine (backend/) plus the benchmark package. rPPG-Toolbox is cloned inside Colab.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -f benchmark/SonicVitals_benchmark.zip
zip -q -r benchmark/SonicVitals_benchmark.zip \
    backend/vitals_dsp.py backend/rppg_engine.py \
    benchmark/sv_bench benchmark/run_benchmark.py benchmark/make_synthetic.py benchmark/plots.py \
    benchmark/README.md Report/images/anatomical_dashboard.png \
    -x '*/__pycache__/*'
unzip -l benchmark/SonicVitals_benchmark.zip | tail -1
