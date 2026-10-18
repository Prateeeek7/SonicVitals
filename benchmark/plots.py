"""Bland-Altman and scatter plots from a benchmark result folder.

    python benchmark/plots.py benchmark/results/UBFC-rPPG
writes bland_altman.png and scatter.png (window level, every method with outputs).
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import pandas as pd               # noqa: E402


def main(folder):
    path = os.path.join(folder, 'per_window.csv')
    if not os.path.isfile(path):
        sys.exit(f'no results in {folder}: the benchmark run did not finish (see its log above)')
    df = pd.read_csv(path)
    df = df[(df.level == 'window')].dropna(subset=['hr_pred', 'hr_gt'])
    methods = list(dict.fromkeys(df.method))
    n = len(methods)
    cols = min(4, n)
    rows = int(np.ceil(n / cols))
    for kind in ('bland_altman', 'scatter'):
        fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.4 * rows), squeeze=False)
        for ax, m in zip(axes.flat, methods):
            g = df[df.method == m]
            if kind == 'scatter':
                ax.scatter(g.hr_gt, g.hr_pred, s=8, alpha=0.6)
                lo, hi = 40, 150
                ax.plot([lo, hi], [lo, hi], 'k--', lw=0.8)
                ax.set_xlim(lo, hi), ax.set_ylim(lo, hi)
                ax.set_xlabel('reference HR (BPM)'), ax.set_ylabel('estimated HR (BPM)')
            else:
                mean, diff = (g.hr_gt + g.hr_pred) / 2, g.hr_pred - g.hr_gt
                bias, sd = diff.mean(), diff.std()
                ax.scatter(mean, diff, s=8, alpha=0.6)
                for y, ls in ((bias, '-'), (bias + 1.96 * sd, '--'), (bias - 1.96 * sd, '--')):
                    ax.axhline(y, color='k', ls=ls, lw=0.8)
                ax.set_xlabel('mean HR (BPM)'), ax.set_ylabel('estimate - reference (BPM)')
                ax.text(0.02, 0.95, f'bias {bias:+.1f}, LoA ±{1.96 * sd:.1f}', transform=ax.transAxes,
                        va='top', fontsize=8)
            mae = (g.hr_pred - g.hr_gt).abs().mean()
            ax.set_title(f'{m}\nMAE {mae:.2f} BPM, n={len(g)}', fontsize=9)
        for ax in axes.flat[n:]:
            ax.axis('off')
        fig.tight_layout()
        fig.savefig(os.path.join(folder, kind + '.png'), dpi=130)
        plt.close(fig)
    print('wrote', os.path.join(folder, 'bland_altman.png'), 'and scatter.png')


if __name__ == '__main__':
    main(sys.argv[1])
