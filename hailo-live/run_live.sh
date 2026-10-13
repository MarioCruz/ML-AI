#!/bin/bash
# Live YOLO11m detection on the Hailo-10H, using the Pi camera.
#
# Camera frames are letterboxed to 640x640 by capture_letterbox.py, then fed
# into hailonet. The generic TAPPAS filter (no function-name) decodes the
# YOLO11 NMS output. Each annotated frame overwrites live/latest.jpg, which
# viewer.html reloads.
#
# Usage (on the Pi, from ~/hailo_test):
#   ./run_live.sh            # Ctrl-C to stop
#   view: http://<pi-ip>:8001/viewer.html   (8000 belongs to hailo-ollama)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HEF=/usr/share/hailo-models/yolov11m_h10.hef
POST=/usr/lib/aarch64-linux-gnu/hailo/tappas/post_processes/libyolo_hailortpp_post.so
LIVE="$HERE/live"
mkdir -p "$LIVE"
cp "$HERE/viewer.html" "$LIVE/viewer.html"

# Serve the viewer and latest frame in the background
python3 -m http.server 8001 --directory "$LIVE" --bind 0.0.0.0 >/dev/null 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID 2>/dev/null || true' EXIT

python3 "$HERE/capture_letterbox.py" | gst-launch-1.0 -q \
  fdsrc fd=0 ! rawvideoparse width=640 height=640 format=rgb framerate=15/1 \
  ! hailonet hef-path="$HEF" \
  ! hailofilter so-path="$POST" qos=false \
  ! hailooverlay ! videoconvert ! jpegenc quality=85 \
  ! multifilesink location="$LIVE/latest.jpg"
