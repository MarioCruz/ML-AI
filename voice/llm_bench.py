#!/usr/bin/env python3
"""
Head-to-head LLM benchmark: the same prompts against two Ollama-compatible
backends, e.g. stock Ollama on the Pi's CPU (:11434) and hailo-ollama on the
AI HAT+ 2 (:8000). Method follows the-diy-life.com's March 2026 test:
temperature 0, fixed seed, a "hello" warm-up, 3 prompts x 3 runs, tokens/s
from the API's own timing when available (Ollama reports eval_duration;
hailo-ollama does not, so wall time is used there and marked).

Also samples CPU load during each run, because the voice assistant needs the
CPU for Vosk and Piper while the LLM generates.

Usage:
  ~/voice/.venv/bin/python ~/voice/llm_bench.py \
      cpu=http://127.0.0.1:11434,qwen2.5:1.5b  hailo=http://127.0.0.1:8000,qwen2.5:1.5b
Writes llm_bench_results.json and llm_bench_answers.md next to this script.
"""
import json
import os
import statistics
import sys
import threading
import time

import requests

PROMPTS = {
    "dns": ("Explain how DNS works in exactly 200 words. Include the recursive resolver, "
            "the authoritative server, caching, and TTL."),
    "physics": ("A ball is thrown straight up at 14 m/s. Take g = 9.8 m/s^2. Find the time to reach "
                "the top, the maximum height, and the total time until it returns to the hand. "
                "Show the equations you use."),
    "intro": ("Write a 120-word blog intro comparing running a small language model on a "
              "Raspberry Pi 5 CPU, on a Raspberry Pi with an AI accelerator, and in the cloud. "
              "Cover privacy, speed and cost."),
}
RUNS = 3
HERE = os.path.dirname(os.path.abspath(__file__))


class CpuSampler:
    """Average CPU busy % across all cores while running."""

    def __init__(self):
        self.samples = []
        self.stop = threading.Event()

    @staticmethod
    def _read():
        with open("/proc/stat") as f:
            parts = f.readline().split()[1:]
        vals = list(map(int, parts))
        idle = vals[3] + vals[4]
        return idle, sum(vals)

    def _run(self):
        idle0, tot0 = self._read()
        while not self.stop.wait(0.5):
            idle1, tot1 = self._read()
            if tot1 > tot0:
                self.samples.append(100.0 * (1 - (idle1 - idle0) / (tot1 - tot0)))
            idle0, tot0 = idle1, tot1

    def __enter__(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.stop.set()

    @property
    def avg(self):
        return statistics.mean(self.samples) if self.samples else float("nan")


def chat(base, model, prompt):
    body = {"model": model, "stream": False, "options": {"temperature": 0, "seed": 42},
            "messages": [{"role": "user", "content": prompt}]}
    t0 = time.time()
    r = requests.post(base + "/api/chat", json=body, timeout=900)
    wall = time.time() - t0
    r.raise_for_status()
    d = r.json()
    text = (d.get("message") or {}).get("content", "")
    n = d.get("eval_count") or len(text.split()) * 4 // 3  # rough fallback: ~1.33 tokens/word
    gen_s = d.get("eval_duration", 0) / 1e9
    api_timing = bool(d.get("eval_duration"))
    tps = n / gen_s if gen_s else n / wall
    return {"text": text, "tokens": n, "tok_per_s": tps, "wall_s": wall,
            "total_s": (d.get("total_duration") or 0) / 1e9 or wall,
            "api_timing": api_timing, "load_s": (d.get("load_duration") or 0) / 1e9}


def main():
    backends = []
    for arg in sys.argv[1:]:
        name, rest = arg.split("=", 1)
        base, model = rest.split(",", 1)
        backends.append((name, base.rstrip("/"), model))
    if not backends:
        sys.exit(__doc__)

    results, answers = {}, []
    for name, base, model in backends:
        print(f"=== {name}: {model} @ {base}", flush=True)
        try:
            chat(base, model, "hello")  # warm-up / model load
        except Exception as e:
            print(f"   backend not reachable: {e}", flush=True)
            continue
        results[name] = {"model": model, "base": base, "prompts": {}}
        for key, prompt in PROMPTS.items():
            runs = []
            for i in range(RUNS):
                with CpuSampler() as cpu:
                    r = chat(base, model, prompt)
                r["cpu_pct"] = cpu.avg
                runs.append(r)
                print(f"   {key} run {i + 1}: {r['tokens']} tok, {r['tok_per_s']:.1f} tok/s"
                      f"{'' if r['api_timing'] else ' (wall)'}, {r['wall_s']:.1f} s wall, cpu {r['cpu_pct']:.0f}%",
                      flush=True)
            results[name]["prompts"][key] = {
                "tok_per_s": statistics.mean(x["tok_per_s"] for x in runs),
                "wall_s": statistics.mean(x["wall_s"] for x in runs),
                "cpu_pct": statistics.mean(x["cpu_pct"] for x in runs),
                "tokens": statistics.mean(x["tokens"] for x in runs),
                "api_timing": runs[0]["api_timing"],
                "runs": runs,
            }
            answers.append(f"## {name} ({model}) — {key}\n\n> {prompt}\n\n{runs[0]['text'].strip()}\n")
        print()

    print("=== summary (mean of 3 runs)")
    print(f"{'backend':8} {'prompt':8} {'tok/s':>7} {'wall s':>7} {'cpu %':>6}  timing")
    for name, res in results.items():
        for key, p in res["prompts"].items():
            print(f"{name:8} {key:8} {p['tok_per_s']:7.1f} {p['wall_s']:7.1f} {p['cpu_pct']:6.0f}  "
                  f"{'api' if p['api_timing'] else 'wall-clock'}")
    with open(os.path.join(HERE, "llm_bench_results.json"), "w") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(HERE, "llm_bench_answers.md"), "w") as f:
        f.write("\n".join(answers))
    print("\nwrote llm_bench_results.json and llm_bench_answers.md")


if __name__ == "__main__":
    main()
