#!/usr/bin/env python3
"""
Ask Qwen2-VL-2B on the AI HAT+ 2 a question about an image, through the
HailoRT 5.2.0 Python GenAI API (hailo_platform.genai.VLM). hailo-ollama cannot
serve VLMs, so this is the only path to the vision model on the HAT.

Needs: ~/voice/.venv with the hailort-5.2.0 cp313 wheel and opencv-python-headless,
and the HEF from https://dev-public.hailo.ai/v5.2.0/blob/Qwen2-VL-2B-Instruct.hef.
The HAT is exclusive: if hailo-ollama holds it you get HAILO_OUT_OF_PHYSICAL_DEVICES
(stop it with `sudo systemctl stop hailo-ollama` first).

Usage:
  ~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --image photo.jpg [--prompt "..."]
  ~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --camera          # grabs a frame with rpicam-still
"""
import argparse
import subprocess
import sys
import time

import cv2
import numpy as np
from hailo_platform import VDevice
from hailo_platform.genai import VLM

HEF = "/home/admin/hailo520/Qwen2-VL-2B-Instruct.hef"
SIZE = 336  # Qwen2-VL-2B HEF expects 336x336 RGB


def load_image(path):
    img = cv2.imread(path)
    if img is None:
        sys.exit(f"cannot read image: {path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hef", default=HEF)
    ap.add_argument("--image", help="image file")
    ap.add_argument("--camera", action="store_true", help="grab a frame with rpicam-still")
    ap.add_argument("--prompt", default="Describe this image in two sentences.")
    ap.add_argument("--max-tokens", type=int, default=150)
    a = ap.parse_args()

    if a.camera:
        a.image = "/tmp/vlm_frame.jpg"
        subprocess.run(["rpicam-still", "-n", "-t", "1000", "--width", "1024", "--height", "768",
                        "-o", a.image], check=True)
    if not a.image:
        sys.exit("give --image FILE or --camera")
    frame = load_image(a.image)

    t0 = time.time()
    params = VDevice.create_params()
    params.group_id = "SHARED"
    vdevice = VDevice(params)
    vlm = VLM(vdevice, a.hef)
    print(f"model loaded in {time.time() - t0:.1f} s", flush=True)

    prompt = [
        {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant that describes images accurately."}]},
        {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": a.prompt}]},
    ]
    try:
        t1 = time.time()
        out = vlm.generate_all(prompt=prompt, frames=[frame], temperature=0.1, seed=42,
                               max_generated_tokens=a.max_tokens)
        dt = time.time() - t1
        text = out.split("<|im_end|>")[0].strip()
        words = len(text.split())
        print("-" * 60)
        print(text)
        print("-" * 60)
        print(f"{dt:.1f} s for ~{words} words (~{words * 4 / 3 / dt:.1f} tok/s incl. image prefill)")
    finally:
        try:
            vlm.clear_context()
            vlm.release()
        except Exception:
            pass
        vdevice.release()


if __name__ == "__main__":
    main()
