"""3.1.2 Latency benchmark: embed 10 / 30 / 40 / 50 thumbnails at batch sizes 1 / 8 / 16 per device.

Run:  uv run python 02_benchmark.py                      # all devices, 5 timed runs per cell
      uv run python 02_benchmark.py --devices cpu --runs 3

Needs the sample images first:  uv run python 00_fetch_images.py

What is timed (model load excluded, a warm-up pass done first):
    JPEG bytes (long edge ~400 px, held in memory like a downloaded thumbnail)
      -> decode -> open_clip preprocess (resize to 224x224, normalise)
      -> batch -> encode_image(normalize=True) on the device -> copy back to CPU
The network download of the thumbnails is NOT included (that is a separate budget, plan R3).
Each cell reports the median of --runs runs plus min/max, and a split into
preprocess (CPU) vs forward (device) seconds. 50 thumbnails are made by cycling the sample
images; model compute does not depend on pixel content.

Writes results/benchmark.json. Machine state (load average, power source) is recorded because
other processes on the laptop change the numbers.
"""

from __future__ import annotations

import argparse
import io
import resource
import subprocess
import sys
import time

import common

parser = argparse.ArgumentParser()
parser.add_argument("--devices", nargs="*", default=None, help="default: every available device")
parser.add_argument("--runs", type=int, default=5, help="timed runs per cell (median reported)")
parser.add_argument("--sizes", type=int, nargs="*", default=[10, 30, 40, 50])
parser.add_argument("--batches", type=int, nargs="*", default=[1, 8, 16])
parser.add_argument("--out", default="benchmark.json")
args = parser.parse_args()

import torch  # noqa: E402
from PIL import Image  # noqa: E402


def power_source() -> str:
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        return out.strip().splitlines()[0] if out else "unknown"
    except Exception as exc:  # noqa: BLE001 - informational only
        return f"unknown ({exc})"


def run_once(model, preprocess, device: str, jpegs: list[bytes], batch_size: int) -> dict:
    """Embed every JPEG; return seconds for the whole thing and its CPU / device split."""
    preprocess_s = 0.0
    forward_s = 0.0
    embeddings = []
    start = time.perf_counter()
    for i in range(0, len(jpegs), batch_size):
        t0 = time.perf_counter()
        tensors = []
        for data in jpegs[i : i + batch_size]:
            with Image.open(io.BytesIO(data)) as img:
                tensors.append(preprocess(common.to_rgb(img)))
        batch = torch.stack(tensors)
        t1 = time.perf_counter()
        with torch.inference_mode():
            emb = model.encode_image(batch.to(device), normalize=True)
            embeddings.append(emb.cpu())  # .cpu() forces the device to finish
        t2 = time.perf_counter()
        preprocess_s += t1 - t0
        forward_s += t2 - t1
    total = time.perf_counter() - start
    assert sum(e.shape[0] for e in embeddings) == len(jpegs)
    return {"total_s": total, "preprocess_s": preprocess_s, "forward_s": forward_s}


def main() -> int:
    entries = common.load_image_set()
    base = [common.make_thumbnail_bytes(e["path"]) for e in entries]
    sizes_px = []
    for data in base:
        with Image.open(io.BytesIO(data)) as img:
            sizes_px.append(max(img.size))
    max_n = max(args.sizes)
    pool = [base[i % len(base)] for i in range(max_n)]

    devices = args.devices or common.available_devices()
    result: dict = {
        "versions": common.versions(),
        "torch_threads": torch.get_num_threads(),
        "power_source": power_source(),
        "load_average_start": common.load_average(),
        "thumbnail_source_images": len(base),
        "thumbnail_long_edge_px": {"min": min(sizes_px), "max": max(sizes_px)},
        "thumbnail_jpeg_bytes_mean": sum(len(b) for b in base) / len(base),
        "runs_per_cell": args.runs,
        "model_input_px": 224,
        "devices": {},
    }
    print("power:", result["power_source"], "| load avg:", result["load_average_start"],
          "| torch threads:", result["torch_threads"])

    for device in devices:
        model, preprocess, _tok, info = common.load_model(device)
        dev: dict = {"load_build_and_to_device_s": info["build_and_to_device_seconds"], "cells": []}

        # Cold first call right after load (no warm-up): what the first request in a session pays.
        cold = run_once(model, preprocess, device, pool[:8], 8)
        dev["cold_first_call_8_images_s"] = cold["total_s"]
        print(f"[{device}] cold first call (8 images, batch 8): {cold['total_s']:.2f}s")

        for batch_size in args.batches:
            # Warm-up for this batch size: one full 16-image pass (kernels, allocator, shape caches).
            run_once(model, preprocess, device, pool[:16], batch_size)
            for n in args.sizes:
                runs = [run_once(model, preprocess, device, pool[:n], batch_size) for _ in range(args.runs)]
                totals = [r["total_s"] for r in runs]
                cell = {
                    "n": n,
                    "batch": batch_size,
                    "median_s": common.median(totals),
                    "min_s": min(totals),
                    "max_s": max(totals),
                    "median_preprocess_s": common.median([r["preprocess_s"] for r in runs]),
                    "median_forward_s": common.median([r["forward_s"] for r in runs]),
                    "images_per_s": n / common.median(totals),
                    "runs_s": totals,
                }
                dev["cells"].append(cell)
                print(f"[{device}] n={n:>2} batch={batch_size:>2}: median {cell['median_s']:.3f}s "
                      f"(min {cell['min_s']:.3f}, max {cell['max_s']:.3f}) "
                      f"preprocess {cell['median_preprocess_s']:.3f}s forward {cell['median_forward_s']:.3f}s")
        result["devices"][device] = dev
        del model
        if device == "mps":
            torch.mps.empty_cache()

    # ru_maxrss is bytes on macOS (kilobytes on Linux). Peak across the whole process, both devices.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["peak_rss_mb"] = peak / 1e6 if sys.platform == "darwin" else peak / 1e3
    result["load_average_end"] = common.load_average()
    path = common.write_json(args.out, result)
    print("load avg end:", result["load_average_end"], "->", path.relative_to(common.SPIKE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
