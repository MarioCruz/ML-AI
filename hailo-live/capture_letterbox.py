#!/usr/bin/env python3
"""
Camera -> letterboxed 640x640 RGB frames on stdout (raw bytes).

The Camera Module 3 gives 4:3 frames. Stretching them to a square distorts
objects, so we pad top and bottom with black instead (letterbox). The Hailo
YOLO model takes 640x640, so every frame written here is exactly that size.

Usage: python3 capture_letterbox.py | <gstreamer pipeline reading fd 0>
"""

import sys

import numpy as np
from picamera2 import Picamera2

SIZE = 640
CAM_W, CAM_H = 640, 480
PAD_TOP = (SIZE - CAM_H) // 2

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (CAM_W, CAM_H), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()

canvas = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
out = sys.stdout.buffer

try:
    while True:
        frame = picam2.capture_array("main")
        # picamera2 RGB888 is stored in BGR byte order; flip to RGB for the model
        canvas[PAD_TOP:PAD_TOP + CAM_H, :, :] = frame[:, :, ::-1]
        out.write(canvas.tobytes())
        out.flush()
except (BrokenPipeError, KeyboardInterrupt):
    pass
finally:
    picam2.stop()
