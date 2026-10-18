# SonicVitals rPPG benchmark

This folder evaluates the SonicVitals camera pipeline on public datasets that come with a
contact-PPG reference. It compares SonicVitals with:

- signal-processing baselines: GREEN, CHROM and POS;
- pretrained deep models: TS-CAN, PhysNet and EfficientPhys.

## What is compared

| Method | Type | Input | Notes |
|---|---|---|---|
| GREEN (Verkruysse 2008) | signal processing | mean RGB of the face crop | ported from rPPG-Toolbox, verified identical |
| CHROM (de Haan 2013) | signal processing | mean RGB of the face crop | ported from rPPG-Toolbox, verified identical |
| POS (Wang 2017) | signal processing | mean RGB of the face crop | ported from rPPG-Toolbox, max difference 6e-15 |
| **SonicVitals** | signal processing + quality control | the live `RPPGEngine` front end | see below |
| TS-CAN, PhysNet, EfficientPhys | deep learning | 72x72 face crops | rPPG-Toolbox pretrained weights |

The SonicVitals front end is the same code the live system runs. Each dataset video goes
through `RPPGEngine.process_frame`: Haar face detection, box smoothing, the ROI lock and the
five-test face gate, and then the forehead, cheek and nose skin boxes.

The analysis is `vitals_dsp.estimate_optical`:

1. motion-free stretch selection;
2. artefact suppression;
3. CHROM pulse with Welch peak tracking;
4. consensus with POS and green;
5. the SNR gate.

SonicVitals is reported in three forms:

- **raw**: always gives a value;
- **gated**: gives a value only when the quality gate passes, with coverage reported;
- **display**: a replay of the live dashboard, including 3-in-a-row confirmation, hold and EMA.

## Protocol

**Ground truth.** The contact PPG is interpolated onto the frame times. It goes through the same
post-processing as every prediction:

- smoothness-priors detrending (lambda 100);
- first-order Butterworth band-pass, 0.75-2.5 Hz;
- periodogram peak, zero-padded to at least 4096 points.

**Windows.** 30 s windows with a 10 s step (window level), plus one whole-video window (the
rPPG-Toolbox default protocol).

**Metrics:**

- MAE, RMSE, MAPE and Pearson r;
- share of windows within 5 BPM;
- coverage: the share of windows where a method outputs an HR. Errors are computed only over
  covered windows, so always read MAE together with coverage.

**Latency.** Median compute time per 30 s window. For the deep models this is the forward pass
per 30 s of video on the stated device.

**Cross-dataset generalization.** The deep models are only tested on datasets they were not
trained on (`--dl-train`):

- UBFC-rPPG is tested with PURE- and SCAMPS-trained weights;
- PURE is tested with UBFC-rPPG- and SCAMPS-trained weights.

The signal-processing methods have no training step. SonicVitals' thresholds were set on
synthetic signals and our own recordings, never on these datasets.

**Deep-model preprocessing.** This reproduces the rPPG-Toolbox inference configs:

- Haar face box on the first frame, enlarged 1.5x;
- 72x72 crops resized with INTER_AREA;
- DiffNormalized / Standardized inputs;
- chunks of 180 frames (128 for PhysNet);
- the predicted first difference is integrated (cumulative sum) before HR estimation.

## Datasets

| Dataset | Content | Access |
|---|---|---|
| UBFC-rPPG | 42 subjects, 640x480 @ 30 fps, uncompressed (~1.6 GB per video), CMS50E finger oximeter | Public Google Drive folder, linked from the authors' page (sites.google.com/view/ybenezeth/ubfcrppg). Cite Bobbia et al., *Pattern Recognition Letters* 2017. |
| PURE | 10 subjects x 6 head-motion tasks, 640x480 PNG @ 30 fps, 60 Hz pulse oximeter | On request from TU Ilmenau (Neuroinformatics and Cognitive Robotics Lab). Cite Stricker et al., RO-MAN 2014. |
| VIPL-HR | 107 subjects, 3 RGB devices, motion and lighting changes | Licence agreement signed by a faculty member, e-mailed to the VIPL lab (ICT, CAS). Cite Niu et al., *IEEE TIP* 2019. |

## Running

**In Colab (recommended, no local download):**

1. Run `./benchmark/pack_for_colab.sh`.
2. Upload `benchmark/SonicVitals_benchmark.zip` to *My Drive/SonicVitals/*.
3. Open `benchmark/SonicVitals_rPPG_Benchmark.ipynb` in Colab and follow its cells.

**Locally:**

```bash
python benchmark/make_synthetic.py --out /tmp/sv_synth --subjects 3   # code self-test
python benchmark/run_benchmark.py --dataset ubfc --root /tmp/sv_synth --dl-train PURE
python benchmark/run_benchmark.py --dataset ubfc --root /path/UBFC-rPPG/DATASET_2 --dl-train PURE,SCAMPS
python benchmark/plots.py benchmark/results/UBFC-rPPG
```

`run_benchmark.py` writes these files to `<out>/<dataset>/`:

- `per_window.csv`
- `summary.csv`, `summary.md`, `summary.tex`
- `latency.csv`

`plots.py` adds `bland_altman.png` and `scatter.png`.

The synthetic data only checks that the code runs end to end. It is not evidence of accuracy.
