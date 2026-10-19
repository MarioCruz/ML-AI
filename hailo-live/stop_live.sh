#!/bin/bash
# Stop the live YOLO viewer started by run_live.sh (the capture script, the
# GStreamer pipeline and the http server on 8001). Run this as its own command;
# a `pkill -f` typed inside a longer ssh command line matches that shell too.
pkill -f "hailo-live/capture_letterbox.py"
pkill -f "gst-launch-1.0 -q fdsrc fd=0"
pkill -f "http.server 8001"
pkill -f "hailo-live/run_live.sh"
sleep 1
if pgrep -af "capture_letterbox|gst-launch-1.0 -q fdsrc|http.server 8001" >/dev/null; then
  echo "still running:"; pgrep -af "capture_letterbox|gst-launch-1.0 -q fdsrc|http.server 8001"; exit 1
fi
echo "live viewer stopped"
