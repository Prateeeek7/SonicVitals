"""Chart images for the presentation (Keynote does not import pptxgenjs native charts).
Each image is drawn at the size of its panel on the slide (inches) at 300 dpi. Output: deck_img/chart_*.png"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'deck_img')
GREEN, AMBER, BLUE, RED, GREY, PURPLE, INK = '#0F6A4A', '#D98C00', '#2E86C1', '#B85430', '#6E6E66', '#7B5EA7', '#1F2A24'
plt.rcParams.update({'font.family': 'Helvetica Neue', 'font.size': 11, 'axes.edgecolor': '#C9CCC2',
                     'axes.labelcolor': GREY, 'xtick.color': GREY, 'ytick.color': GREY, 'axes.titlesize': 13,
                     'axes.titleweight': 'bold', 'axes.titlecolor': INK, 'axes.titlelocation': 'left',
                     'axes.titlepad': 12})


def frame(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=300)
    fig.patch.set_facecolor('white')
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    return fig, ax


def save(fig, name):
    fig.tight_layout(pad=0.8)
    fig.savefig(os.path.join(OUT, name), facecolor='white')
    plt.close(fig)


def hbar(name, w, h, title, labels, values, colors, fmt, xmax, note=None):
    fig, ax = frame(w, h)
    y = range(len(labels))
    ax.barh(y, values, color=colors, height=0.62)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, xmax)
    ax.grid(axis='x', color='#E3E5DE', linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis='y', length=0, labelsize=11, labelcolor=INK)
    for i, v in enumerate(values):
        ax.text(v + xmax * 0.015, i, fmt(v), va='center', fontsize=11, color=INK, fontweight='bold')
    ax.set_title(title)
    if note:
        ax.set_xlabel(note, fontsize=10)
    save(fig, name)


def before_after(name, w, h, title, values, color, unit, ymax):
    fig, ax = frame(w, h)
    bars = ax.bar(['Before', 'After'], values, color=[GREY, color], width=0.55)
    ax.set_ylim(0, ymax)
    ax.grid(axis='y', color='#E3E5DE', linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis='x', length=0, labelsize=12, labelcolor=INK)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + ymax * 0.02, f'{v:g} {unit}', ha='center', fontsize=13,
                fontweight='bold', color=INK)
    ax.set_title(title)
    save(fig, name)


def main():
    os.makedirs(OUT, exist_ok=True)
    cost = [('ESP32-S3 camera board', 1200), ('INMP441 microphone', 250), ('SSD1306 OLED', 250), ('USB cable', 150),
            ('Breadboard', 100), ('Jumper wires, harness', 100), ('Antenna, misc.', 100)]
    hbar('chart_cost.png', 5.43, 3.85, 'Where the ₹2,150 goes', [c[0] for c in cost], [c[1] for c in cost],
         [GREEN, AMBER, AMBER, BLUE, GREY, GREY, GREY], lambda v: f'₹{v:,}', 1450)

    bench = [('SonicVitals (gated)', 1.56, GREEN), ('TS-CAN', 1.68, BLUE), ('PhysNet', 1.90, BLUE), ('POS', 2.08, AMBER),
             ('SonicVitals (raw)', 2.30, '#7FB59E'), ('CHROM', 2.40, AMBER), ('EfficientPhys', 3.88, BLUE)]
    hbar('chart_benchmark.png', 6.13, 5.4, 'Mean absolute error on UBFC-rPPG (BPM)', [b[0] for b in bench],
         [b[1] for b in bench], [b[2] for b in bench], lambda v: f'{v:.2f}', 4.6,
         note='lower is better  ·  blue = deep, amber = classic  ·  GREEN 22.04 off scale')

    fig, ax = frame(5.88, 3.55)
    rates = ['8', '12', '15', '18', '24']
    single = [5.97, 0.88, 2.05, 2.71, 7.82]
    fused = [0.14, 0.11, 0.09, 0.08, 0.08]
    x = range(len(rates))
    ax.bar([i - 0.19 for i in x], single, width=0.36, color=GREY, label='Single green peak')
    ax.bar([i + 0.19 for i in x], fused, width=0.36, color=GREEN, label='Four-source fusion')
    for i in x:
        ax.text(i - 0.19, single[i] + 0.15, f'{single[i]:.1f}', ha='center', fontsize=9.5, color=INK)
        ax.text(i + 0.19, fused[i] + 0.15, f'{fused[i]:.2f}', ha='center', fontsize=9.5, color=GREEN, fontweight='bold')
    ax.set_xticks(list(x), [f'{r}/min' for r in rates])
    ax.tick_params(axis='x', length=0, labelcolor=INK)
    ax.set_ylim(0, 10.5)
    ax.set_ylabel('MAE (breaths/min)')
    ax.grid(axis='y', color='#E3E5DE', linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc='upper center', ncol=2, fontsize=10)
    ax.set_title('Breathing-rate error on test faces with drift')
    save(fig, 'chart_rr.png')

    before_after('chart_fps.png', 5.95, 3.7, 'Processed frames per second', [16.4, 27.0], GREEN, 'fps', 32)
    before_after('chart_ms.png', 5.95, 3.7, 'Processing time per frame', [21.4, 10.6], BLUE, 'ms', 25)
    print('charts written to', OUT)


if __name__ == '__main__':
    main()
