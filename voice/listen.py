#!/usr/bin/env python3
"""Offline voice commands for the Pi. Listens on the USB mic and prints recognized commands."""
import json
import subprocess
import sys

from vosk import KaldiRecognizer, Model, SetLogLevel

RATE = 16000
MODEL_DIR = "/home/admin/voice/model"
DEVICE = "usbmic"

# Phrases the recognizer is allowed to output. Anything else maps to [unk].
COMMANDS = {
    "lights on": "lights_on",
    "lights off": "lights_off",
    "what time is it": "time",
    "status": "status",
    "stop listening": "stop",
}

# Map each command to an action. Placeholders for now; replace with real actions.
ACTIONS = {
    "lights_on": lambda: print("ACTION: lights on", flush=True),
    "lights_off": lambda: print("ACTION: lights off", flush=True),
    "time": lambda: print("ACTION: time", flush=True),
    "status": lambda: print("ACTION: status", flush=True),
}


def main():
    SetLogLevel(-1)
    model = Model(MODEL_DIR)
    grammar = json.dumps(list(COMMANDS.keys()) + ["[unk]"])
    rec = KaldiRecognizer(model, RATE, grammar)

    proc = subprocess.Popen(
        ["arecord", "-q", "-D", DEVICE, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE,
    )
    print("Listening. Say a command. Ctrl+C to quit.", flush=True)
    try:
        while True:
            data = proc.stdout.read(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").strip()
                if not text or text == "[unk]":
                    continue
                if text not in COMMANDS:
                    continue
                name = COMMANDS[text]
                print(f"HEARD: {text} -> {name}", flush=True)
                if name == "stop":
                    break
                action = ACTIONS.get(name)
                if action:
                    action()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
