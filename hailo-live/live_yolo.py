#!/usr/bin/env python3
"""
Live YOLO11m on the AI HAT+ 2 through the HailoRT Python API (5.3.0+), sharing
the HAT with hailo-ollama (same VDevice group id as hailo-ollama.service).

Replaces the GStreamer pipeline of the earlier run_live.sh: the HailoRT
`hailonet` element cannot join a shared VDevice group (error 74 while the LLM
is loaded), the Python API can. Camera frames (Camera Module 3, 640x480) are
letterboxed to 640x640, run through the on-chip NMS model, drawn with boxes and
labels, and written to live/latest.jpg about 15 times a second. viewer.html and
the web page's camera panel read that file.

Usage:
  live_yolo.py                      # camera, forever (run_live.sh starts this)
  live_yolo.py --image in.jpg --out out.jpg   # one image, prints the detections
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
from hailo_platform import VDevice

HEF = "/usr/share/hailo-models/yolov11m_h10.hef"
GROUP = "HAILO_OLLAMA_SHARED"   # must match HAILO_OLLAMA_VDEVICE_GROUP_ID in hailo-ollama.service
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "live", "latest.jpg")
SIZE = 640
CAM_W, CAM_H = 640, 480
PAD_TOP = (SIZE - CAM_H) // 2
FPS = 15
SCORE = 0.4
COCO = ("person bicycle car motorcycle airplane bus train truck boat traffic-light fire-hydrant stop-sign "
        "parking-meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella "
        "handbag tie suitcase frisbee skis snowboard sports-ball kite baseball-bat baseball-glove skateboard "
        "surfboard tennis-racket bottle wine-glass cup fork knife spoon bowl banana apple sandwich orange "
        "broccoli carrot hot-dog pizza donut cake chair couch potted-plant bed dining-table toilet tv laptop "
        "mouse remote keyboard cell-phone microwave oven toaster sink refrigerator book clock vase scissors "
        "teddy-bear hair-drier toothbrush").split()


def detections(nms_output, score=SCORE):
    """HailoRT NMS output: one entry per class, each a (n, 5) array of
    y_min, x_min, y_max, x_max, score in 0..1. Returns [(label, score, x1, y1, x2, y2)] in pixels."""
    found = []
    for cls, rows in enumerate(nms_output):
        rows = np.asarray(rows, dtype=np.float32).reshape(-1, 5)
        for y1, x1, y2, x2, s in rows:
            if s >= score:
                found.append((COCO[cls] if cls < len(COCO) else str(cls), float(s),
                              int(x1 * SIZE), int(y1 * SIZE), int(x2 * SIZE), int(y2 * SIZE)))
    return found


def draw(img_rgb, found):
    out = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    for label, s, x1, y1, x2, y2 in found:
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.putText(out, f"{label} {s:.0%}", (x1, max(14, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1, cv2.LINE_AA)
    return out


def write_atomic(path, bgr):
    ok, data = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data.tobytes())
    os.replace(tmp, path)  # readers never see a half-written frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--out")
    ap.add_argument("--hef", default=HEF)
    a = ap.parse_args()

    cam = None
    if not a.image:
        # picamera2 is a system package (python3-picamera2); the venv does not see it by default.
        sys.path.append("/usr/lib/python3/dist-packages")
        from picamera2 import Picamera2
        cam = Picamera2()
        cam.configure(cam.create_preview_configuration(main={"size": (CAM_W, CAM_H), "format": "RGB888"}))
        cam.start()  # camera first: if it fails, the HAT is never touched

    params = VDevice.create_params()
    params.group_id = GROUP
    vdevice = VDevice(params)
    model = vdevice.create_infer_model(a.hef)
    model.set_batch_size(1)
    print(f"model {os.path.basename(a.hef)} on the HAT (group {GROUP})", flush=True)
    with model.configure() as cm:
        bindings = cm.create_bindings()
        out_buf = np.empty(model.output().shape, dtype=np.float32)  # NMS output, 80 classes

        def infer(rgb):
            bindings.input().set_buffer(np.ascontiguousarray(rgb))
            bindings.output().set_buffer(out_buf)
            cm.run([bindings], 2000)
            return detections(bindings.output().get_buffer())

        if a.image:
            img = cv2.imread(a.image)
            if img is None:
                sys.exit(f"cannot read {a.image}")
            img = cv2.cvtColor(cv2.resize(img, (SIZE, SIZE)), cv2.COLOR_BGR2RGB)
            t0 = time.time()
            found = infer(img)
            print(f"{(time.time() - t0) * 1000:.0f} ms:", ", ".join(f"{l} {s:.0%}" for l, s, *_ in found) or "nothing")
            if a.out:
                cv2.imwrite(a.out, draw(img, found))
            return  # the configured model closes first (with-block), then the VDevice below

        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        canvas = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
        n, t_report = 0, time.time()
        print("live: writing", OUT, flush=True)
        try:
            while True:
                t_frame = time.time()
                frame = cam.capture_array("main")
                canvas[PAD_TOP:PAD_TOP + CAM_H] = frame[:, :, ::-1]  # picamera2 RGB888 is BGR order
                found = infer(canvas)
                write_atomic(OUT, draw(canvas, found))
                n += 1
                if time.time() - t_report >= 10:
                    print(f"{n / (time.time() - t_report):.1f} fps, last: "
                          + (", ".join(f"{l} {s:.0%}" for l, s, *_ in found) or "nothing"), flush=True)
                    n, t_report = 0, time.time()
                time.sleep(max(0.0, 1.0 / FPS - (time.time() - t_frame)))
        except KeyboardInterrupt:
            pass
        finally:
            cam.stop()
    # Release only after the configured model is gone: releasing the VDevice while the
    # model is still configured breaks the shared device for every other process.
    vdevice.release()


if __name__ == "__main__":
    main()
