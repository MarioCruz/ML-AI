#!/bin/bash
# Classify an image on the Hailo-10H with ResNet-50 via TAPPAS/GStreamer.
# Usage: ./classify.sh <image.jpg> [out.jpg]
# Writes the annotated frame (top label + score) to out.jpg (default: result.jpg).
set -euo pipefail
IMG="$1"
OUT="${2:-result.jpg}"
HEF=/usr/share/hailo-models/resnet_v1_50_h10.hef
POST=/usr/lib/aarch64-linux-gnu/hailo/tappas/post_processes/libclassification.so
TMP=$(mktemp -d)
# Feed 10 copies: the pipeline holds back the last frame until another arrives.
gst-launch-1.0 -q multifilesrc location="$IMG" loop=true num-buffers=10 \
  ! jpegdec ! videoconvert ! videoscale ! video/x-raw,format=RGB,width=224,height=224 \
  ! hailonet hef-path="$HEF" ! hailofilter so-path="$POST" qos=false \
  ! hailooverlay ! videoconvert ! jpegenc ! multifilesink location="$TMP/frame_%02d.jpg"
LAST=$(ls "$TMP"/frame_*.jpg | sort | tail -1)
cp "$LAST" "$OUT"
rm -rf "$TMP"
echo "wrote $OUT"
