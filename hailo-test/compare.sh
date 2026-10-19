#!/bin/bash
# Run every scene through YOLOv8m and YOLO11m on the Hailo-10H with the same
# settings. Each scene is letterboxed to 640x640 first (same as the live
# pipeline). Output: out/<model>/<scene>.jpg with boxes and labels drawn.
set -euo pipefail
cd "$(dirname "$0")"
POST=/usr/lib/aarch64-linux-gnu/hailo/tappas/post_processes/libyolo_hailortpp_post.so
mkdir -p letterboxed out/yolov8m out/yolov11m

for img in scenes/*.jpg; do
  name=$(basename "$img" .jpg)
  python3 -c "
from PIL import Image
im = Image.open(\"$img\").convert(\"RGB\")
im.thumbnail((640, 640))
canvas = Image.new(\"RGB\", (640, 640), (0, 0, 0))
canvas.paste(im, ((640 - im.width) // 2, (640 - im.height) // 2))
canvas.save(\"letterboxed/$name.jpg\", quality=95)
"
  for model in yolov8m yolov11m; do
    rm -rf "tmp_$model"; mkdir "tmp_$model"
    gst-launch-1.0 -q multifilesrc location="letterboxed/$name.jpg" loop=true num-buffers=10 \
      ! jpegdec ! videoconvert ! video/x-raw,format=RGB,width=640,height=640 \
      ! hailonet hef-path=/usr/share/hailo-models/$( [ $model = yolov8m ] && echo yolov8m_h10 || echo yolov11m_h10 ).hef vdevice-group-id=HAILO_OLLAMA_SHARED \
      ! hailofilter so-path="$POST" qos=false \
      ! hailooverlay ! videoconvert ! jpegenc ! multifilesink location="tmp_$model/f_%02d.jpg"
    cp "$(ls tmp_$model/f_*.jpg | sort | tail -1)" "out/$model/$name.jpg"
    echo "done $model $name"
  done
done
