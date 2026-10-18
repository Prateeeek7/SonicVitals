"""Draw numbered markers on the dashboard screenshots for the viva guide."""
from PIL import Image, ImageDraw, ImageFont

FONT = '/System/Library/Fonts/Helvetica.ttc'

def mark(src, dst, points, r):
    im = Image.open(src).convert('RGB')
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, int(r * 1.15))
    for n, (x, y) in enumerate(points, 1):
        d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill='white')
        d.ellipse([x - r, y - r, x + r, y + r], fill=(200, 30, 40))
        d.text((x, y), str(n), fill='white', font=f, anchor='mm')
    im.save(dst)

mark('images/dashboard_main.png', 'viva/fig/dash.png', [
    (1092, 25),    # 1 header / connection
    (13, 92),      # 2 vision stream panel
    (380, 252),    # 3 face box + ROI
    (40, 517),     # 4 systolic peak / sigma^2
    (585, 517),    # 5 capture button
    (880, 128),    # 6 HR
    (1155, 128),   # 7 RR
    (1430, 128),   # 8 HRV
    (880, 208),    # 9 signal quality
    (1155, 208),   # 10 stress
    (1430, 208),   # 11 fusion confidence
    (609, 300),    # 12 acoustic input
    (22, 597),     # 13 BVP
    (747, 597),    # 14 respiration
], 13)

mark('images/anatomical_dashboard.png', 'viva/fig/diag.png', [
    (552, 93),     # 1 controls
    (11, 142),     # 2 pipeline steps
    (11, 192),     # 3 view tabs
    (11, 238),     # 4 frame info strip
    (398, 404),    # 5 annotated ROIs
    (596, 190),    # 6 triage cards
    (596, 357),    # 7 interpretation text
    (596, 503),    # 8 EI
    (596, 546),    # 9 pallor
    (596, 596),    # 10 jaundice
    (596, 640),    # 11 cyanosis
    (596, 684),    # 12 hemifacial
    (596, 727),    # 13 frame clarity
    (11, 734),     # 14 ROI list
], 13)

s = 1.47
mark('images/Signal analysis dashboard.png', 'viva/fig/sig.png', [
    (int(40 * s), int(90 * s)),     # 1 F0
    (int(360 * s), int(90 * s)),    # 2 SNR
    (int(680 * s), int(90 * s)),    # 3 SQI
    (int(1000 * s), int(90 * s)),   # 4 Fr
    (int(1320 * s), int(90 * s)),   # 5 wavelet ratio
    (int(1640 * s), int(90 * s)),   # 6 video source
    (int(28 * s), int(218 * s)),    # 7 PSD
    (int(1043 * s), int(218 * s)),  # 8 spectrogram
    (int(28 * s), int(681 * s)),    # 9 normalized trace
    (int(1043 * s), int(681 * s)),  # 10 decomposition
], 30)
