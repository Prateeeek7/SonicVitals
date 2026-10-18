#!/usr/bin/env bash
# Starts the node simulator and the server for a clearly labelled demo without hardware.
# The dashboard shows a "SIMULATED DATA" banner while this runs. Ctrl+C stops both.
cd "$(dirname "$0")/.." || exit 1
pkill -f "python3 backend/usb_streamer[.]py" 2>/dev/null
python3 tools/node_simulator.py "$@" > /tmp/sonicvitals_sim.log 2>&1 &
SIM=$!
for _ in $(seq 1 20); do
  PORT=$(grep -o '/dev/ttys[0-9]*' /tmp/sonicvitals_sim.log | head -1)
  [ -n "$PORT" ] && break
  sleep 0.2
done
echo "Simulator on $PORT (synthetic data). Open http://localhost:3000"
trap 'kill $SIM 2>/dev/null' EXIT
SONICVITALS_LINK=serial SONICVITALS_PORT="$PORT" SONICVITALS_BAUD=115200 SONICVITALS_WEBCAM=0 \
  python3 backend/usb_streamer.py
