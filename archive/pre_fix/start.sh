#!/usr/bin/env bash

# ==============================================================================
# SonicVitals - Clinical Biomedical Diagnostic Studio
# All-in-One Startup Script (Backend + Frontend + Browser Auto-Launch)
# ==============================================================================

# Move to the repository root directory
cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo " 🩺  Starting SonicVitals Diagnostic Platform"
echo "============================================================"

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not found in PATH."
    exit 1
fi

# 2. Check Python dependencies
python3 -c "import flask, flask_cors, cv2, serial, numpy, scipy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Missing Python dependencies detected. Installing required packages..."
    pip3 install flask flask-cors opencv-python pyserial numpy scipy
fi

# 3. Clean up any stale processes on port 5001 (backend) and port 3000 (frontend)
echo "🧹 Checking for stale processes on ports 5001 & 3000..."
STALE_BACKEND=$(lsof -ti:5001 2>/dev/null)
if [ -n "$STALE_BACKEND" ]; then
    echo "   Stopping existing process on port 5001 (PID: $STALE_BACKEND)..."
    kill -9 $STALE_BACKEND 2>/dev/null
fi

STALE_FRONTEND=$(lsof -ti:3000 2>/dev/null)
if [ -n "$STALE_FRONTEND" ]; then
    echo "   Stopping existing process on port 3000 (PID: $STALE_FRONTEND)..."
    kill -9 $STALE_FRONTEND 2>/dev/null
fi

# 4. Check for ESP32 USB serial connection
PORTS=$(ls /dev/cu.usbserial* /dev/cu.usbmodem* /dev/cu.wch* /dev/cu.SLAB* 2>/dev/null)
if [ -z "$PORTS" ]; then
    echo "ℹ️  Note: No ESP32-S3 USB serial device currently plugged in."
    echo "   The server will start and auto-connect as soon as you plug it in."
else
    echo "🔌 Detected hardware device on: $PORTS"
fi

# 5. Process cleanup handler on exit / Ctrl+C
cleanup() {
    echo ""
    echo "🛑 Shutting down SonicVitals services..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    # Ensure ports are completely released
    lsof -ti:5001 2>/dev/null | xargs kill -9 2>/dev/null
    lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null
    echo "✅ SonicVitals stopped cleanly."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 6. Start Backend (Flask + Clinical rPPG Engine + Resilient Serial Reader)
echo "🚀 Launching Python Backend on http://localhost:5001..."
python3 backend/usb_streamer.py &
BACKEND_PID=$!

# Wait for backend initialization
sleep 1.5

# 7. Start Frontend (HTTP Static Server)
echo "🌐 Launching Frontend Workstation on http://localhost:3000..."
if command -v npx &> /dev/null; then
    npx -y http-server ./Frontend -p 3000 -c-1 --silent &
    FRONTEND_PID=$!
else
    python3 -m http.server 3000 -d ./Frontend &
    FRONTEND_PID=$!
fi

sleep 1.0

# 8. Automatically open workstation in browser
echo "💻 Opening Clinical Workstation in browser..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:3000"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:3000" 2>/dev/null || sensible-browser "http://localhost:3000" 2>/dev/null
fi

echo ""
echo "============================================================"
echo " 🌟 SonicVitals is Live and Ready!"
echo "------------------------------------------------------------"
echo " 🖥️  Dashboard Workstation : http://localhost:3000"
echo " 📹 Video Stream (1x)     : http://localhost:5001/video_feed"
echo " 📊 Clinical Vitals API   : http://localhost:5001/api/vitals"
echo " 🎯 Best Moment API       : http://localhost:5001/api/best_moment_status"
echo "------------------------------------------------------------"
echo " Press [Ctrl+C] to stop all services cleanly."
echo "============================================================"
echo ""

# Wait for processes
wait
