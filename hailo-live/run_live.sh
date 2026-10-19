#!/bin/bash
# Live YOLO11m detection on the Hailo-10H with the Pi camera, sharing the HAT
# with hailo-ollama (HailoRT 5.3.0+, Python API; see live_yolo.py).
#
# Annotated frames overwrite live/latest.jpg; viewer.html (port 8001) and the
# web page's camera panel reload it. hailo-live.service runs this at boot.
#
# Usage (on the Pi):  ./run_live.sh      # Ctrl-C to stop; or ./stop_live.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LIVE="$HERE/live"
mkdir -p "$LIVE"
cp "$HERE/viewer.html" "$LIVE/viewer.html"

# Serve the viewer and latest frame in the background
python3 -m http.server 8001 --directory "$LIVE" --bind 0.0.0.0 >/dev/null 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID 2>/dev/null || true' EXIT

exec /home/admin/voice/.venv/bin/python "$HERE/live_yolo.py"
