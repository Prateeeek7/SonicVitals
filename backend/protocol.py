"""Line-oriented parser for the SonicVitals serial protocol (firmware v2, with
backward compatibility for the v1 `<<FRAME_START>>` framing)."""
import base64

import numpy as np


class StreamParser:
    """Feed decoded text lines; get back event tuples.

    Events:
      ('frame', seq | None, t_us | None, jpeg_bytes)
      ('audio', seq, t_us, np.int16 array)
      ('stat', dict)
      ('hello', dict)
      ('error', str)
    """

    def __init__(self):
        self._in_frame = False
        self._frame_hdr = (None, None, None)
        self._chunks = []
        self.frames_ok = 0
        self.frames_bad = 0

    def feed_line(self, text):
        text = text.strip()
        if not text:
            return []
        if text.startswith('<<FRAME_START'):
            if self._in_frame:
                self.frames_bad += 1                    # previous frame never ended
            self._in_frame = True
            self._chunks = []
            self._frame_hdr = self._parse_frame_header(text)
            return []
        if text == '<<FRAME_END>>':
            if not self._in_frame:
                return []
            self._in_frame = False
            return [self._finish_frame()]
        if text.startswith('<<AUDIO:') and text.endswith('>>'):
            return [self._parse_audio(text)]
        if text.startswith('<<STAT:') and text.endswith('>>'):
            return [self._parse_stat(text)]
        if text.startswith('<<RGB:') and text.endswith('>>'):
            # <<RGB:seq,t_us,n,sumR,sumG,sumB[,n_clipped,n_dark]>>: raw-pixel skin sums computed on the
            # node before JPEG; saturated / near-black pixels are excluded from the sums and counted.
            try:
                v = [int(x) for x in text[6:-2].split(',')]
                if len(v) not in (6, 8):
                    raise ValueError
            except ValueError:
                return [('error', 'bad RGB line')]
            seq, t_us, n, sr, sg, sb = v[:6]
            nclip, ndark = (v[6], v[7]) if len(v) == 8 else (0, 0)
            if n + nclip + ndark <= 0:
                return []
            rgb = (sr / n, sg / n, sb / n) if n > 0 else None
            return [('rgb', seq, t_us, n, rgb, nclip, ndark)]
        if text.startswith('<<CAMEXP:') and text.endswith('>>'):
            try:
                exp, count = (int(x) for x in text[9:-2].split(','))
            except ValueError:
                return [('error', 'bad CAMEXP line')]
            return [('camexp', exp, count)]
        if text.startswith('<<INFO:') and text.endswith('>>'):
            return [('info', text[7:-2])]
        if text.startswith('<<HELLO:') and text.endswith('>>'):
            parts = text[8:-2].split(',')
            info = {'name': parts[0], 'version': parts[1] if len(parts) > 1 else '1',
                    'transport': parts[2] if len(parts) > 2 else '?',
                    'mic_enabled': parts[3] == '1' if len(parts) > 3 else None}
            for extra in parts[4:]:                      # key=value fields, e.g. i2c=3c, fs=4000
                if '=' in extra:
                    k, v = extra.split('=', 1)
                    info[k] = int(v) if v.isdigit() else v
            return [('hello', info)]
        if self._in_frame:
            self._chunks.append(text)
        return []

    @staticmethod
    def _parse_frame_header(text):
        # v2: <<FRAME_START:seq,t_us,len>>   v1: <<FRAME_START>>
        if text.startswith('<<FRAME_START:') and text.endswith('>>'):
            try:
                seq, t_us, n = text[14:-2].split(',')
                return int(seq), int(t_us), int(n)
            except ValueError:
                pass
        return None, None, None

    def _finish_frame(self):
        seq, t_us, n = self._frame_hdr
        b64 = ''.join(self._chunks)
        self._chunks = []
        rem = len(b64) % 4
        if rem == 1:
            b64 = b64[:-1]
        elif rem > 1:
            b64 += '=' * (4 - rem)
        try:
            jpeg = base64.b64decode(b64)
        except Exception:
            self.frames_bad += 1
            return ('error', 'frame base64 decode failed')
        if len(jpeg) < 200 or not jpeg.startswith(b'\xff\xd8') or (n is not None and len(jpeg) != n):
            self.frames_bad += 1
            return ('error', 'frame truncated or corrupt')
        self.frames_ok += 1
        return ('frame', seq, t_us, jpeg)

    @staticmethod
    def _parse_audio(text):
        try:
            seq, t_us, n, b64 = text[8:-2].split(',', 3)
            pcm = np.frombuffer(base64.b64decode(b64), dtype='<i2')
            if len(pcm) != int(n):
                return ('error', 'audio block length mismatch')
            return ('audio', int(seq), int(t_us), pcm)
        except Exception:
            return ('error', 'audio block parse failed')

    @staticmethod
    def _parse_stat(text):
        try:
            f = [int(v) for v in text[7:-2].split(',')]
            keys = ['fps_x10', 'frames', 'audio_blocks', 'audio_drops', 'mic_ready', 'cam_ready', 'jpeg_avg_bytes',
                    'oled_ready', 'oled_ack', 'cam_auto_locked', 'frame_drops']
            d = dict(zip(keys, f))
            d['fps'] = d.pop('fps_x10', 0) / 10.0
            return ('stat', d)
        except Exception:
            return ('error', 'stat parse failed')
