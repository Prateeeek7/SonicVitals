"""SonicVitals rPPG benchmark.

Evaluates the SonicVitals optical pipeline against signal-processing baselines (GREEN, CHROM,
POS) and pretrained deep models from rPPG-Toolbox (PhysNet, TS-CAN, EfficientPhys) on public
datasets with contact-PPG ground truth (UBFC-rPPG, PURE, VIPL-HR). See benchmark/README.md.
"""
import os
import sys

BENCH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BENCH_DIR)
BACKEND_DIR = os.path.join(REPO_DIR, 'backend')
TOOLBOX_DIR = os.environ.get('RPPG_TOOLBOX', os.path.join(BENCH_DIR, 'third_party', 'rPPG-Toolbox'))

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
