#!/usr/bin/env bash
# Demo-values mode: live ESP32 camera and face detection, simulated vital signs.
# After 30 s of a detected face all values appear; 5 s without a face resets.
# The dashboard shows a "DEMO VALUES" banner the whole time. Ctrl+C to stop.
# For real measurements use the normal start (./start.sh) instead.
cd "$(dirname "$0")/.." || exit 1
pkill -f "python3 backend/usb_streamer[.]py" 2>/dev/null
sleep 1
SONICVITALS_DEMO_VITALS=1 SONICVITALS_LINK=wifi SONICVITALS_WEBCAM=0 python3 backend/usb_streamer.py
